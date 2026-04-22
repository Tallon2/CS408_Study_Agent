"""
agent/tools/registry.py — 工具注册表

设计目标：
  - 新增工具只需在 agent/tools/ 创建新文件并在此处注册
  - 无需修改 tools.py 主体（解耦扩展点）
  - TOOL_REGISTRY 是工具名 → 处理函数的单一映射源
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime
from typing import Callable

# ── 从子模块导入（已独立实现） ──
from agent.tools.quiz import generate_quiz

# ── RAG 辅助（懒加载，不可用时静默降级） ──
def _get_rag_context(query: str, use_exam: bool = False) -> str:
    try:
        if use_exam:
            from memory.rag.retriever_rag import retrieve_exam_questions
            return retrieve_exam_questions(query)
        else:
            from memory.rag.retriever_rag import retrieve
            return retrieve(query)
    except Exception:
        return ""


# ============================================================
# 简单工具实现（不值得单独文件）
# ============================================================

def _explain_concept(args: dict, state: dict | None = None) -> str:
    topic = args.get("topic", "")
    depth = args.get("depth", "beginner")
    depth_map = {
        "beginner": "入门级（用生活比喻，配简单代码示例）",
        "intermediate": "进阶级（讲原理，配实际使用场景）",
        "advanced": "深入级（讲底层机制和边界情况）",
    }
    depth_desc = depth_map.get(depth, depth_map["beginner"])
    rag_context = _get_rag_context(topic, use_exam=False)
    base_instruction = (
        f"[工具指令] 请用{depth_desc}方式，为用户讲解「{topic}」。\n"
        f"要求：先给一个生活中的类比，再给代码示例，最后总结一句话。"
    )
    if rag_context:
        return (
            f"{base_instruction}\n\n"
            f"【以下是来自408教材的参考资料，请优先基于这些内容回答，确保准确性】\n"
            f"{rag_context}"
        )
    return base_instruction


def _check_answer(args: dict, state: dict | None = None) -> str:
    question = args.get("question", "")
    user_answer = args.get("user_answer", "").strip().upper()
    correct_answer = args.get("correct_answer", "").strip().upper()

    rag_explanation = ""
    if question:
        try:
            from memory.rag.retriever_rag import _query_collection
            hits = _query_collection("exam_questions", question[:80], n_results=1)
            if hits and hits[0]["distance"] < 1.2:
                rag_explanation = hits[0]["text"]
        except Exception:
            pass

    if correct_answer:
        is_correct = (user_answer == correct_answer)
    else:
        is_correct = None

    if is_correct is True:
        verdict = f"✅ 回答正确！用户选择了 {user_answer}，正确答案就是 {correct_answer}。"
        instruction = (
            f"[工具指令] 用户答对了这道题。\n"
            f"{verdict}\n"
            f"要求：先祝贺用户答对，再简要解释为什么 {correct_answer} 是正确答案，巩固知识点。\n"
            f"语气：鼓励、肯定。"
        )
    elif is_correct is False:
        verdict = f"❌ 回答错误。用户选择了 {user_answer}，但正确答案是 {correct_answer}。"
        instruction = (
            f"[工具指令] 用户答错了这道题。\n"
            f"{verdict}\n"
            f"要求：\n"
            f"1. 第一句话必须明确告知用户答错了，正确答案是 {correct_answer}\n"
            f"2. 解释为什么 {correct_answer} 是正确答案\n"
            f"3. 解释为什么用户选择的 {user_answer} 是错误的\n"
            f"4. 给出相关知识点帮助记忆\n"
            f"语气：温和鼓励，不要打击信心。"
        )
    else:
        instruction = (
            f"[工具指令] 请判断用户的回答是否正确并给出详细反馈。\n"
            f"题目：{question}\n"
            f"用户答案：{user_answer}\n"
            f"要求：先给出对/错判断，再解释原因，如果错了给出正确答案和关键知识点。"
        )

    if rag_explanation:
        instruction += f"\n\n【知识库参考解析（请基于此内容回答）】\n{rag_explanation}"
    return instruction


def _recommend_next(args: dict, state: dict | None = None) -> str:
    return (
        "[工具指令] 请根据本次对话中用户的表现，推荐接下来应该学习的内容。"
        "给出 2~3 个具体的学习建议，按优先级排列。"
    )


# ── 学习计划存储路径 ──
PLANS_DIR = "storage/plans"


def _save_study_plan(args: dict, state: dict | None = None) -> str:
    """保存学习计划到 JSON 文件"""
    plan_name = args.get("plan_name", "默认计划")
    tasks = args.get("tasks", [])

    os.makedirs(PLANS_DIR, exist_ok=True)
    safe_name = plan_name.replace(" ", "_").replace("/", "_")
    plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")

    plan_data = {
        "plan_name": plan_name,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "tasks": [],
    }
    for i, t in enumerate(tasks):
        plan_data["tasks"].append({
            "index": i + 1,
            "task": t.get("task", ""),
            "deadline": t.get("deadline", ""),
            "priority": t.get("priority", "medium"),
            "completed": False,
            "completed_at": None,
        })

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)

    total = len(plan_data["tasks"])
    return (
        f"[工具结果] ✅ 学习计划「{plan_name}」已保存，共 {total} 个任务。\n"
        f"请向用户确认计划内容，并鼓励ta按计划执行。"
    )


def _read_study_plan(args: dict, state: dict | None = None) -> str:
    """读取学习计划"""
    os.makedirs(PLANS_DIR, exist_ok=True)
    plan_name = args.get("plan_name", "")

    if plan_name:
        safe_name = plan_name.replace(" ", "_").replace("/", "_")
        plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")
        if not os.path.exists(plan_path):
            return f"[工具结果] ❌ 未找到计划「{plan_name}」，可以创建一个新的。"
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        return _format_plan(plan)
    else:
        files = [fn for fn in os.listdir(PLANS_DIR) if fn.endswith(".json")]
        if not files:
            return "[工具结果] 📋 当前没有任何学习计划，建议为用户创建一个。"
        all_plans = []
        for fname in files:
            with open(os.path.join(PLANS_DIR, fname), "r", encoding="utf-8") as f:
                plan = json.load(f)
            all_plans.append(_format_plan(plan))
        return "\n\n---\n\n".join(all_plans)


def _complete_task(args: dict, state: dict | None = None) -> str:
    """标记任务为已完成"""
    plan_name = args.get("plan_name", "")
    task_index = args.get("task_index", 0)

    safe_name = plan_name.replace(" ", "_").replace("/", "_")
    plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")
    if not os.path.exists(plan_path):
        return f"[工具结果] ❌ 未找到计划「{plan_name}」"

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    for t in plan["tasks"]:
        if t["index"] == task_index:
            t["completed"] = True
            t["completed_at"] = datetime.now().isoformat()
            break
    else:
        return f"[工具结果] ❌ 未找到第 {task_index} 个任务"

    plan["updated_at"] = datetime.now().isoformat()
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    done = sum(1 for t in plan["tasks"] if t["completed"])
    total = len(plan["tasks"])
    return (
        f"[工具结果] ✅ 已完成任务 #{task_index}！\n"
        f"当前进度：{done}/{total}（{done * 100 // total}%）\n"
        f"请鼓励用户继续努力！"
    )


def _format_plan(plan: dict) -> str:
    """格式化计划为可读文本"""
    tasks = plan.get("tasks", [])
    done = sum(1 for t in tasks if t.get("completed"))
    total = len(tasks)
    pct = (done * 100 // total) if total > 0 else 0

    lines = [f"[工具结果] 📋 计划「{plan['plan_name']}」 进度：{done}/{total}（{pct}%）"]
    for t in tasks:
        status = "✅" if t.get("completed") else "⬜"
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.get("priority", ""), "")
        deadline = f" (截止: {t['deadline']})" if t.get("deadline") else ""
        lines.append(f"  {status} {t['index']}. {priority_icon} {t['task']}{deadline}")
    return "\n".join(lines)


# ============================================================
# 注册表：工具名 → 处理函数的单一映射源
# 新增工具只需：1) 在 agent/tools/ 创建新文件  2) 在此处注册
# ============================================================
TOOL_REGISTRY: dict[str, Callable[[dict, dict | None], str]] = {
    "generate_quiz":   lambda args, state: generate_quiz(
                           args.get("topic", ""), args.get("difficulty", "easy"), state
                       ),
    "explain_concept": _explain_concept,
    "check_answer":    _check_answer,
    "recommend_next":  _recommend_next,
    "save_study_plan": _save_study_plan,
    "read_study_plan": _read_study_plan,
    "complete_task":   _complete_task,
}


def execute_tool_from_registry(name: str, args: dict, state: dict | None = None) -> str:
    """
    通过注册表分发工具调用。

    Args:
        name  : 工具名（与 TOOL_REGISTRY 键对应）
        args  : 已解析的参数字典
        state : 当前 AgentState 字典（可为 None）

    Returns:
        工具执行结果字符串
    """
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        return f"[工具指令] 未知工具: {name}"
    return handler(args, state)