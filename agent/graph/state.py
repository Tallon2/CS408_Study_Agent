"""
state.py — LangGraph AgentState 定义

AgentState 是整个状态图的共享状态对象，在各节点之间传递和更新。
"""

from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ── 对话消息历史（使用 add_messages reducer，自动追加） ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── 路由决策 ──
    intent: Literal["study", "plan", "review", "unknown"]

    # ── RAG 检索上下文（由 rag_node 填充） ──
    rag_context: str

    # ── RAG 管线追踪事件列表（由 rag_node 填充，供 SSE 前端展示） ──
    rag_pipeline_trace: list  # list[dict]，每个 dict 代表一个管线步骤

    # ── 当前工具名称和参数（由 tool_executor 填充） ──
    tool_name: str
    tool_args: dict
    tool_result: str

    # ── L2 任务状态快照（由 memory_update_node 填充） ──
    memory_l2: dict

    # ── L4 用户画像快照 ──
    memory_l4: dict

    # ── 本次会话事件流（L1，用于会话结束时生成摘要） ──
    session_events: list[dict]

    # ── 最终回复 ──
    final_response: str

    # ── 当前题目的正确答案（出题后存入，供下一轮判答使用） ──
    current_quiz_answer: str

    # ── 已出过的题目记录（前60字符 key，防止重复出同一道题） ──
    shown_questions: list

    # ── 错误信息（节点执行失败时写入） ──
    error: str
