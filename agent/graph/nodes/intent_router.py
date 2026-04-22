"""
intent_router.py — 意图路由节点

功能：对用户最新消息进行语义分类，决定走哪条分支。
路由结果写入 state["intent"]：
    - "study"  ：需要知识讲解/出题/判答 → 走 RAG + 工具链
    - "plan"   ：学习计划管理（创建/查看/完成任务）
    - "review" ：复习推荐（基于用户画像分析薄弱点）
    - "unknown"：无法分类，走默认 LLM 直接回复
"""

import json

from core.llm_client import get_llm_client
from agent.graph.state import AgentState
from langchain_core.messages import HumanMessage


# intent → tool_name 默认映射
_INTENT_TOOL_MAP = {
    "study":   "explain_concept",   # 默认知识讲解
    "plan":    "read_study_plan",   # 默认查看计划
    "review":  "recommend_next",    # 复习推荐
    "unknown": "",                  # 无工具
}

# 关键词 → 精确工具覆盖（优先级高于 intent 默认）
_KEYWORD_TOOL_MAP = {
    "出题":   "generate_quiz",
    "练习":   "generate_quiz",
    "做题":   "generate_quiz",
    "判断":   "check_answer",
    "对吗":   "check_answer",
    "答案":   "check_answer",
    "计划":   "save_study_plan",
    "安排":   "save_study_plan",
    "推荐":   "recommend_next",
    "接下来": "recommend_next",
    "进度":   "read_study_plan",
    "完成":   "complete_task",
}


_SYSTEM_PROMPT = """你是一个意图分类器。用户的输入是一条学习助手的对话消息。

请将用户意图分类为以下四类之一：
- "study"  ：用户想了解/学习某个知识点、请求讲解、出题、判答等学习行为
- "plan"   ：用户想创建、查看、更新学习计划，或标记任务完成
- "review" ：用户想复习，或问自己的薄弱点、推荐复习内容
- "unknown"：无法归入以上任何一类

请只返回如下 JSON，不要有任何其他文字：
{"intent": "study", "confidence": 0.95, "topic": "装饰器"}

说明：
- intent 只能是 study / plan / review / unknown 之一
- confidence 是 0.0~1.0 的浮点数，表示分类置信度
- topic 是识别到的知识点名称（如无则填空字符串 ""）
"""


def _is_quiz_answer(user_text: str, quiz_answer: str) -> bool:
    """
    判断用户消息是否是对当前选择题的回答。
    条件：存在未消费的 quiz_answer，且用户消息像是一个选项（A/B/C/D）。
    """
    import re
    if not quiz_answer:
        return False
    # 用户消息去掉空白后，匹配单个选项字母，或 "选A"、"我选B"、"答案是C" 等常见模式
    stripped = user_text.strip().upper()
    if re.match(r'^[A-D]\.?$', stripped):
        return True
    if re.search(r'(?:选|答案|选择)\s*[A-D]', stripped):
        return True
    return False


def _extract_user_choice(user_text: str) -> str:
    """从用户消息中提取选项字母（A/B/C/D）"""
    import re
    stripped = user_text.strip().upper()
    m = re.search(r'[A-D]', stripped)
    return m.group(0) if m else stripped


def intent_router_node(state: AgentState) -> AgentState:
    """意图路由节点：对用户最新消息做语义分类，写入 state['intent']。"""

    # 取最后一条 HumanMessage 的内容
    user_text = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_text = msg.content
            break

    if not user_text:
        return {**state, "intent": "unknown"}

    # ── 快速路径：检测用户是否在回答选择题 ────────────────────
    quiz_answer = state.get("current_quiz_answer", "")
    if _is_quiz_answer(user_text, quiz_answer):
        user_choice = _extract_user_choice(user_text)
        return {
            **state,
            "intent": "study",
            "tool_name": "check_answer",
            "tool_args": {
                "user_answer": user_choice,
                "correct_answer": quiz_answer,
            },
        }

    # 调用 GLM-4-Flash 做分类
    intent = "study"  # 降级默认值
    topic = ""
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=client.default_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.1,
            max_tokens=100,
        )
        raw = resp.choices[0].message.content.strip()
        # 去掉可能的 markdown 代码块
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        intent = result.get("intent", "study")
        if intent not in ("study", "plan", "review", "unknown"):
            intent = "study"
        topic = result.get("topic", "")
    except Exception:
        # LLM 调用失败或解析失败，降级为 study
        intent = "study"

    # 更新 state
    new_tool_args = dict(state.get("tool_args") or {})
    if topic:
        new_tool_args["topic"] = topic

    # ── 推断 tool_name ──────────────────────────────────────────
    # 1. 先取 intent 默认工具
    tool_name = _INTENT_TOOL_MAP.get(intent, "")

    # 2. 扫描用户消息关键词，命中则覆盖（关键词优先级更高）
    for kw, kw_tool in _KEYWORD_TOOL_MAP.items():
        if kw in user_text:
            tool_name = kw_tool
            break  # 取第一个命中的关键词即可

    return {**state, "intent": intent, "tool_args": new_tool_args, "tool_name": tool_name}
