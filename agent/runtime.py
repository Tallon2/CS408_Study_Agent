"""
agent/runtime.py — Agent 运行时会话管理

职责：
  - 维护 user_id → AgentSession 的映射（内存缓存）
  - 管理 LangGraphAgent 实例的生命周期（创建 / 获取 / 销毁）
  - 触发会话结束 Hook（on_session_end）
  - 提供 AgentState 初始化构建与记忆快照同步工具函数
  - 将会话态从 main_agent.py 中剥离，使 main_agent.py 保持职责单一

使用方式：
    from agent.runtime import get_or_create_session, end_session
    session = get_or_create_session(user_id)
    reply = session.agent.chat(user_message)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # 仅用于类型提示，避免循环导入
    from agent.main_agent import LangGraphAgent

logger = logging.getLogger(__name__)

# 每隔 N 轮对话触发一次批量画像写入（fire-and-forget 后台线程）
BATCH_UPDATE_INTERVAL = 5

# ============================================================
# System Prompt — 角色定义与行为规范（单一真实来源）
# 从 main_agent.py 迁移至此，使 main_agent.py 保持精简
# ============================================================
SYSTEM_PROMPT = """你是一个专业的计算机考研（408）学习助手，帮助用户备考数据结构、操作系统、计算机组成原理、计算机网络四门科目。

你的行为规范：
1. 当用户想了解某个知识点、请求解释或梳理考点时 → 必须调用 explain_concept 工具
2. 当用户想做题、测试自己、出题时 → 必须调用 generate_quiz 工具
3. 当用户回答了题目 → 必须调用 check_answer 工具判断对错
4. 当用户问"接下来复习什么"或需要学习建议时 → 必须调用 recommend_next 工具

严格禁止：
- 禁止在回复文本中写出任何工具名称（如 generate_quiz、explain_concept 等）
- 禁止在回复文本中输出 JSON 格式内容
- 禁止模拟工具调用，必须通过 Function Calling 机制真正调用工具
- 禁止在 explain_concept 回答末尾自行附加"相关真题"、"练习题"等内容，出题必须由用户主动触发 generate_quiz
- 在工具返回结果之前，不要提前输出题目或解释内容

其他注意事项：
- 回答基于工具返回的【参考资料】，内容要严谨准确，符合408考试风格
- 如果参考资料中有历年真题，优先展示真实真题而非自编题目
- 语气友好，鼓励为主，适当提醒易错点
- 可以用类比帮助理解，但结论必须以参考资料为准
"""


def load_initial_memory() -> tuple[dict, dict]:
    """
    加载用户初始记忆快照（L2 任务状态 + L4 用户画像）。

    封装原 main_agent.py.__init__ 中的直接 import，
    使依赖关系显式化，便于测试时 mock。

    Returns:
        (memory_l2, memory_l4) 元组
    """
    from memory.l2_task import load_task_state
    from memory.l4_profile import load_profile
    return load_task_state(), load_profile()


# ============================================================
# AgentSession 数据类：描述单个用户会话的完整状态
# ============================================================

@dataclass
class AgentSession:
    """
    单个用户的 Agent 会话快照。

    Attributes:
        user_id:        用户唯一标识
        agent:          该用户对应的 LangGraphAgent 实例
        created_at:     会话创建时间（UTC）
        last_active_at: 最近一次活跃时间（UTC），用于空闲超时检测
    """
    user_id: str
    agent: "LangGraphAgent"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active_at: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """刷新最近活跃时间，每次 chat 后调用。"""
        self.last_active_at = datetime.utcnow()

    def idle_minutes(self) -> float:
        """返回当前距上次活跃已经过了多少分钟。"""
        delta: timedelta = datetime.utcnow() - self.last_active_at
        return delta.total_seconds() / 60.0


# ============================================================
# 全局会话缓存（内存）
# ============================================================

_sessions: dict[str, AgentSession] = {}


# ============================================================
# AgentState 工厂函数（从 main_agent.py 提取）
# ============================================================

def build_initial_state(
    messages: list,
    memory_l2: dict[str, Any],
    memory_l4: dict[str, Any],
    current_quiz_answer: str = "",
) -> dict[str, Any]:
    """
    构建 LangGraph 图所需的初始 AgentState 字典。

    将 AgentState 的初始化从 LangGraphAgent 内部散落的多处 dict 字面量
    统一收敛到此处，确保字段不遗漏、语义一致。

    Args:
        messages:             当前对话历史（LangChain 消息格式列表）
        memory_l2:            L2 任务状态快照
        memory_l4:            L4 用户画像快照
        current_quiz_answer:  跨轮次保存的当前题目正确答案

    Returns:
        符合 AgentState TypedDict 结构的初始状态字典
    """
    return {
        "messages":            list(messages),
        "intent":              "unknown",
        "rag_context":         "",
        "tool_name":           "",
        "tool_args":           {},
        "tool_result":         "",
        "memory_l2":           memory_l2,
        "memory_l4":           memory_l4,
        "session_events":      [],
        "final_response":      "",
        "error":               "",
        "rag_pipeline_trace":  [],
        "current_quiz_answer": current_quiz_answer,
    }


def sync_memory_snapshot(
    agent: "LangGraphAgent",
    result_state: dict[str, Any],
) -> None:
    """
    将图执行结果中的记忆字段同步回 agent 实例的内存快照，
    并在每 BATCH_UPDATE_INTERVAL 轮触发一次后台批量画像写入。

    每次 chat / chat_stream 执行完成后调用，确保下一轮对话
    能使用最新的 L2/L4 状态。

    Args:
        agent:        LangGraphAgent 实例
        result_state: LangGraph 图执行返回的最终 state 字典
    """
    agent._memory_l2 = result_state.get("memory_l2", agent._memory_l2)
    agent._memory_l4 = result_state.get("memory_l4", agent._memory_l4)
    agent._current_quiz_answer = result_state.get(
        "current_quiz_answer", agent._current_quiz_answer
    )

    # ── 对话轮数计数（存在 agent 实例上，跨 invoke 累积） ──
    agent._chat_round_count = getattr(agent, "_chat_round_count", 0) + 1

    if agent._chat_round_count % BATCH_UPDATE_INTERVAL == 0:
        import threading
        from agent.graph.nodes.memory_update import run_batch_profile_update
        # 取消并发写入保护：同一时刻只允许一个批量更新线程在跑
        if not getattr(agent, "_batch_updating", False):
            agent._batch_updating = True

            def _run():
                try:
                    run_batch_profile_update(agent.user_id, list(agent._messages))
                finally:
                    agent._batch_updating = False

            threading.Thread(target=_run, daemon=True).start()
            logger.info(
                "已触发批量画像更新（第 %d 轮）user_id=%s",
                agent._chat_round_count,
                agent.user_id,
            )


def handle_session_end(agent: "LangGraphAgent") -> None:
    """
    触发会话结束生命周期：执行 L1-L4 全量持久化钩子。

    与 end_session() 配合使用：end_session() 负责从缓存中移除会话，
    本函数负责执行业务层的清理逻辑。

    Args:
        agent: 即将被销毁的 LangGraphAgent 实例
    """
    from memory.hooks import on_session_stop
    try:
        digest = on_session_stop(agent.session)
        if digest:
            logger.info("会话摘要已保存 user_id=%s", agent.user_id)
    except Exception as exc:
        logger.warning("on_session_stop 执行出错 user_id=%s: %s", agent.user_id, exc)


# ============================================================
# 公共 API — 会话生命周期管理
# ============================================================

def get_or_create_session(user_id: str) -> AgentSession:
    """
    获取现有会话，若不存在则新建一个。

    每次调用会自动刷新 last_active_at，避免被空闲清理误删。

    Args:
        user_id: 用户唯一标识（如登录名、UUID 等）

    Returns:
        对应的 AgentSession 实例（已保证 agent 已初始化）
    """
    if user_id in _sessions:
        session = _sessions[user_id]
        session.touch()
        logger.debug("复用已有会话 user_id=%s", user_id)
        return session

    # 延迟导入，避免循环依赖（main_agent → runtime → main_agent）
    from agent.main_agent import LangGraphAgent

    logger.info("为 user_id=%s 创建新会话", user_id)
    agent = LangGraphAgent(user_id)
    session = AgentSession(user_id=user_id, agent=agent)
    _sessions[user_id] = session
    return session


def get_session(user_id: str) -> AgentSession | None:
    """
    获取现有会话（不自动创建）。

    Args:
        user_id: 用户唯一标识

    Returns:
        AgentSession 实例，若不存在则返回 None
    """
    session = _sessions.get(user_id)
    if session:
        session.touch()
    return session


def end_session(user_id: str) -> None:
    """
    结束并销毁指定用户的会话。

    流程：
      1. 查找会话（不存在则静默返回）
      2. 调用 handle_session_end() 触发清理 Hook（如自动摘要写入）
      3. 从全局缓存中删除该会话

    Args:
        user_id: 要结束的会话对应的用户 ID
    """
    session = _sessions.get(user_id)
    if session is None:
        logger.debug("end_session: user_id=%s 不存在，跳过", user_id)
        return

    # 触发 Hook（写摘要、持久化等），失败不阻止会话被清除
    handle_session_end(session.agent)

    del _sessions[user_id]
    logger.info("会话已结束并清除 user_id=%s", user_id)


def list_active_sessions() -> list[str]:
    """
    列出所有当前活跃会话的 user_id。

    Returns:
        user_id 字符串列表（顺序不保证）
    """
    return list(_sessions.keys())


def cleanup_idle_sessions(idle_minutes: int = 60) -> int:
    """
    清理超过指定空闲时长的会话，释放内存。

    对每个超时会话都会调用 end_session()，确保 Hook 正常触发。

    Args:
        idle_minutes: 空闲超时阈值（分钟），默认 60 分钟

    Returns:
        本次清理的会话数量
    """
    expired: list[str] = [
        uid
        for uid, session in list(_sessions.items())
        if session.idle_minutes() >= idle_minutes
    ]

    for uid in expired:
        logger.info(
            "清理空闲会话 user_id=%s（已空闲 %.1f 分钟）",
            uid,
            _sessions[uid].idle_minutes() if uid in _sessions else idle_minutes,
        )
        end_session(uid)

    if expired:
        logger.info("共清理 %d 个空闲会话（阈值 %d 分钟）", len(expired), idle_minutes)

    return len(expired)