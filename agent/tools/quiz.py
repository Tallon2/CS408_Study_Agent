"""
agent/tools/quiz.py — generate_quiz 工具函数

职责：
  - 封装"出题"工具的完整逻辑（从 agent/tools.py 中提取）
  - 优先从 ChromaDB exam_questions 集合检索历年真题
  - 无匹配真题时退回 LLM 自编模拟题
  - 提供 QUIZ_TOOL_DEFINITION 常量供工具注册使用

迁移来源：agent/tools.py 第 229-363 行（generate_quiz 分支）
"""

from __future__ import annotations

import random
import re as _re
from typing import Any


# ============================================================
# 工具 JSON Schema 定义
# ============================================================

QUIZ_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_quiz",
        "description": "针对某个知识点生成一道练习题，帮助用户检验掌握程度",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "出题的知识点"
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["easy", "medium", "hard"],
                    "description": "题目难度"
                }
            },
            "required": ["topic"]
        }
    }
}


# ============================================================
# RAG 辅助：从 exam_questions 集合批量检索候选真题
# ============================================================

def _query_exam_questions(topic: str, n_results: int = 20) -> list[dict]:
    """
    从 ChromaDB exam_questions 集合检索与 topic 相关的真题列表。

    Args:
        topic:     检索关键词（通常是知识点名称）
        n_results: 最多返回条数（用于后续过滤和随机化）

    Returns:
        命中记录列表，每条含 text、distance、metadata 字段；
        检索失败时返回空列表。
    """
    try:
        from memory.rag.retriever_rag import _query_collection
        return _query_collection("exam_questions", topic, n_results=n_results)
    except Exception:
        return []


# ============================================================
# 内部辅助：解析真题文本
# ============================================================

def _parse_exam_text(raw: str) -> tuple[str, str, str]:
    """
    从 text 字段解析题目正文、答案、解析，去掉头部标签行。

    Args:
        raw: ChromaDB 中存储的原始文本

    Returns:
        (body, answer, explanation) 三元组，缺失字段返回空字符串
    """
    import re as _re2
    lines = raw.strip().splitlines()
    # 去掉第一行的 [xxxx年第xx题-...] 头部标签
    if lines and _re.match(r'^\[.*\]$', lines[0].strip()):
        lines = lines[1:]
    body_lines: list[str] = []
    answer_val = ""
    explanation_val = ""
    for ln in lines:
        if ln.startswith("答案："):
            answer_val = ln[3:].strip()
        elif ln.startswith("解析："):
            explanation_val = ln[3:].strip()
        else:
            body_lines.append(ln)

    # 兜底：若 startswith 未匹配（可能冒号为全角异体字），用 regex 再扫一遍
    if not answer_val:
        m = _re2.search(r'答案[：:]\s*([A-D])', raw)
        if m:
            answer_val = m.group(1).strip()

    return "\n".join(body_lines).strip(), answer_val, explanation_val


def _build_source_tag(meta: dict) -> str:
    """根据元数据构建真题来源标签字符串。"""
    year    = meta.get("year", "")
    number  = meta.get("number", "")
    subject = meta.get("subject", "")
    chapter = meta.get("chapter", "")

    source = f"{year}年 全国408统考真题" if year else "全国408统考真题"
    if number:
        source += f" 第{number}题"
    if subject and chapter:
        source += f"（{subject} · {chapter}）"
    elif subject:
        source += f"（{subject}）"
    return source


# ============================================================
# 主函数：generate_quiz
# ============================================================

def generate_quiz(topic: str, difficulty: str = "easy", state: dict | None = None) -> str:
    """
    针对指定知识点生成一道练习题，优先返回历年真题。

    流程：
      1. 从 exam_questions 集合检索最多 20 道候选题（cosine distance < 1.2）
      2. 过滤掉已出过的题目（通过 state["shown_questions"] 去重）
      3. 随机打散，避免每次返回同一道题
      4. 有匹配真题 → 直接组装展示内容，让 LLM 原样输出
      5. 无匹配真题 → 指令 LLM 自编模拟题

    Args:
        topic:      出题的知识点名称
        difficulty: 难度等级，"easy" / "medium" / "hard"，默认 "easy"
        state:      当前 AgentState 字典（可选），用于读取 shown_questions 避免重复

    Returns:
        工具指令字符串，供 LLM 二次处理后输出给用户
    """
    diff_map = {
        "easy":   "简单（概念理解题）",
        "medium": "中等（代码阅读/填空题）",
        "hard":   "困难（代码编写/综合应用题）",
    }
    diff_desc = diff_map.get(difficulty, diff_map["easy"])

    # ── Step 1: 检索候选真题 ──
    exam_hits = _query_exam_questions(topic, n_results=20)

    # ChromaDB cosine distance 范围 0~2（越小越相关）
    # 实测操作系统相关真题 distance ≈ 0.98~1.08，设阈值 1.2 覆盖同科目真题
    good_hits = [h for h in exam_hits if h.get("distance", 2.0) < 1.2]

    # ── Step 2: 过滤已出过的题目，避免重复 ──
    shown_questions: list[str] = (state or {}).get("shown_questions", [])
    if shown_questions and good_hits:
        filtered = [
            h for h in good_hits
            if h["text"][:60].strip() not in shown_questions
        ]
        # 若过滤后还有题，使用过滤结果；否则重置（已刷完一轮）
        if filtered:
            good_hits = filtered

    # ── Step 3: 随机打散，避免每次返回相同的第一道题 ──
    if good_hits:
        random.shuffle(good_hits)

    if good_hits:
        # ── Step 4: 有匹配真题：直接展示原题，标注来源 ──
        h0 = good_hits[0]
        body0, answer0, _ = _parse_exam_text(h0["text"])
        source0 = _build_source_tag(h0.get("metadata", {}))

        # 兜底：text 解析失败时从 metadata 取 answer 字段
        if not answer0:
            answer0 = str(h0.get("metadata", {}).get("answer", "")).strip().upper()

        # 直接生成给用户看的最终文本，LLM 只需原样输出
        ready_output = (
            f"📅 **{source0}**\n\n"
            f"{body0}\n\n"
            f"💬 请选择你的答案（A/B/C/D）："
        )

        return (
            f"[工具指令] 请将下方「展示内容」**原封不动**地输出给用户，"
            f"不要增删任何文字，不要改变任何格式，不要加任何前缀或后缀：\n\n"
            f"===展示内容开始===\n"
            f"{ready_output}\n"
            f"===展示内容结束===\n\n"
            f"[隐藏-仅供判答]正确答案={answer0}[/隐藏]"
        )
    else:
        # ── Step 5: 无匹配真题：LLM 自编，但标注为模拟题 ──
        return (
            f"[工具指令] 知识库中未找到关于「{topic}」的历年真题，"
            f"请自行编写一道{diff_desc}408风格选择题作为模拟练习。\n"
            f"要求：题目严谨，选项具有迷惑性，符合真实考研出题风格，答案必须唯一正确。\n"
            f"格式：\n"
            f"  第一行：📝 **模拟题（{topic}）**\n"
            f"  题目正文\n"
            f"  A. B. C. D. 四个选项\n"
            f"  用「---」分隔后写答案和解析\n"
        )
