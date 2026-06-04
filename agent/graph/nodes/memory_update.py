"""
memory_update.py — 记忆更新节点

功能：在每轮对话结束时，刷新 L2/L4 内存快照（只读，不写 DB）。
计数与批量写入逻辑由 runtime.sync_memory_snapshot() 负责，
避免跨 invoke 的 state 无法累积计数器的问题。

节点职责：
1. 把本次识别到的 intent + topic 写入 L2 的 session_events_buffer
2. 刷新 state["memory_l2"] 和 state["memory_l4"] 为最新值
"""

import logging
from datetime import datetime

from agent.graph.state import AgentState

logger = logging.getLogger(__name__)


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


def run_batch_profile_update(user_id: str, messages: list) -> None:
    """
    从最近对话历史生成 digest，批量写入 L2/L4（fire-and-forget 调用）。

    由 sync_memory_snapshot() 在线程中调用，不阻塞主流程。

    Args:
        user_id:  当前用户 ID，确保画像写入正确用户
        messages: 当前 LangChain 消息历史列表
    """
    import json
    import re
    from memory.hooks import SCRIBE_PROMPT
    from core.llm_client import get_llm_client

    # 从 messages 中提取最近 12 条（约 6 轮）对话文本
    conversation_lines = []
    for msg in messages[-12:]:
        if hasattr(msg, "type"):
            if msg.type == "human":
                conversation_lines.append(f"用户: {msg.content}")
            elif msg.type == "ai":
                conversation_lines.append(f"助手: {msg.content}")

    conversation_text = "\n".join(conversation_lines)
    if not conversation_text.strip():
        logger.debug("run_batch_profile_update: 对话为空，跳过 user_id=%s", user_id)
        return

    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=client.default_model,
            messages=[
                {"role": "system", "content": "你是一个精确的学习记录分析师。只输出 JSON，不要多余文字。"},
                {"role": "user", "content": SCRIBE_PROMPT.replace("{conversation}", conversation_text)},
            ],
        )
        raw = response.choices[0].message.content
    except Exception as exc:
        logger.warning("批量更新 LLM 调用失败 user_id=%s: %s", user_id, exc)
        return

    try:
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        digest = json.loads(text)
    except Exception as exc:
        logger.warning("批量更新 digest 解析失败 user_id=%s: %s", user_id, exc)
        return

    # 更新 L2 任务状态
    try:
        from memory.l2_task import load_task_state, update_task_state
        task = load_task_state(user_id)
        update_task_state(digest, task, user_id)
        logger.info("批量 L2 更新完成 user_id=%s", user_id)
    except Exception as exc:
        logger.warning("批量 L2 更新失败 user_id=%s: %s", user_id, exc)

    # 更新 L4 用户画像
    try:
        from memory.l4_profile import update_profile_from_digest
        update_profile_from_digest(digest, "batch_update", user_id)
        logger.info("批量 L4 更新完成 user_id=%s", user_id)
    except Exception as exc:
        logger.warning("批量 L4 更新失败 user_id=%s: %s", user_id, exc)
