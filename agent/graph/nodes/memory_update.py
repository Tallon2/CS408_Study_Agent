"""
memory_update.py — 记忆更新节点

功能：在每轮对话结束时，异步更新 L2 任务状态和 L4 用户画像。
设计为"轻量更新"——不触发完整的会话结束 Hook（那个在 on_session_end 时触发）。
只做：
1. 把本次识别到的 intent + topic 写入 L2 的 session_events_buffer
2. 刷新 state["memory_l2"] 和 state["memory_l4"] 为最新值
"""

from datetime import datetime

from agent.graph.state import AgentState


def memory_update_node(state: AgentState) -> AgentState:
    """记忆更新节点：刷新 L2/L4 记忆快照到 state，失败时静默处理。"""

    memory_l2 = state.get("memory_l2") or {}
    memory_l4 = state.get("memory_l4") or {}

    # ── 1. 刷新 L2 任务状态快照 ─────────────────────────────────
    try:
        from memory.l2_task import load_task_state
        fresh_l2 = load_task_state()
        if fresh_l2 is not None:
            memory_l2 = fresh_l2
    except Exception:
        pass  # 静默降级，保留原有快照

    # ── 2. 刷新 L4 用户画像快照 ─────────────────────────────────
    try:
        from memory.l4_profile import load_profile
        fresh_l4 = load_profile()
        if fresh_l4 is not None:
            memory_l4 = fresh_l4
    except Exception:
        pass  # 静默降级，保留原有快照

    # ── 3. 把本轮 intent + topic 写入 L2 的 session_events_buffer ─
    # （仅在记忆对象是可变 dict 时追加，不强制要求 L2 存在该字段）
    try:
        intent = state.get("intent", "unknown")
        topic = (state.get("tool_args") or {}).get("topic", "")
        session_events = state.get("session_events") or []

        if isinstance(memory_l2, dict):
            buffer = memory_l2.get("session_events_buffer")
            if buffer is None:
                memory_l2 = dict(memory_l2)  # 浅拷贝，避免修改外部对象
                memory_l2["session_events_buffer"] = []
                buffer = memory_l2["session_events_buffer"]

            buffer.append({
                "intent": intent,
                "topic": topic,
                "events_count": len(session_events),
                "timestamp": datetime.now().isoformat(),
            })
    except Exception:
        pass  # 静默处理，不影响主流程

    return {
        **state,
        "memory_l2": memory_l2,
        "memory_l4": memory_l4,
    }
