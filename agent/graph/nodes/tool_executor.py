"""
tool_executor.py — 工具执行节点

功能：
1. 从 state["messages"] 中检查是否有工具调用请求
2. 如果 LLM 决定调用工具，执行工具并把结果写入 state["tool_result"]
3. 同时把工具调用记录写入 state["session_events"]（L1事件流）

注意：本节点只做工具执行，不做 LLM 调用。
LLM 调用在 response_generator.py 节点进行。
"""

import json
from datetime import datetime

from agent.graph.state import AgentState


def tool_executor_node(state: AgentState) -> AgentState:
    """工具执行节点：执行 state['tool_name'] 指定的工具，结果写入 state['tool_result']。"""

    tool_name = (state.get("tool_name") or "").strip()
    tool_args = state.get("tool_args") or {}
    intent    = (state.get("intent") or "").strip()

    # ── Fallback：tool_name 为空时按 intent 补默认工具 ──────────
    if not tool_name:
        _FALLBACK = {
            "study":  "explain_concept",
            "plan":   "read_study_plan",
            "review": "recommend_next",
        }
        tool_name = _FALLBACK.get(intent, "")

    # 仍然没有工具时直接返回
    if not tool_name:
        return {**state, "tool_result": ""}

    tool_result = ""
    error = state.get("error", "")
    session_events = list(state.get("session_events") or [])

    try:
        from agent.tools import execute_tool
        # check_answer 时把 state 里存的正确答案注入 tool_args
        if tool_name == "check_answer":
            saved_answer = state.get("current_quiz_answer", "")
            if saved_answer and "correct_answer" not in tool_args:
                tool_args = {**tool_args, "correct_answer": saved_answer}
        # execute_tool 第二个参数要求 JSON 字符串
        arguments_json = json.dumps(tool_args, ensure_ascii=False)
        tool_result = execute_tool(tool_name, arguments_json, state=dict(state))

        # 写入 L1 事件流
        session_events.append({
            "event_type": "tool_call",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result_preview": tool_result[:200] if tool_result else "",
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        error = str(e)
        tool_result = "工具执行失败，请稍后重试"
        session_events.append({
            "event_type": "tool_error",
            "tool_name": tool_name,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

    # ── generate_quiz 成功后，把本次出的题加入已出题记录，避免下次重复 ──
    shown_questions = list(state.get("shown_questions") or [])
    if tool_name == "generate_quiz" and tool_result and "===展示内容开始===" in tool_result:
        import re as _re
        # 从 tool_result 中提取题目正文前60字符作为去重 key
        m = _re.search(r'===展示内容开始===\s*\n(.*)', tool_result, _re.DOTALL)
        if m:
            quiz_key = m.group(1).strip()[:60]
            if quiz_key and quiz_key not in shown_questions:
                shown_questions.append(quiz_key)
        # 仅保留最近 50 条记录，防止无限增长
        shown_questions = shown_questions[-50:]

    return {
        **state,
        "tool_result": tool_result,
        "session_events": session_events,
        "error": error,
        "shown_questions": shown_questions,
    }
