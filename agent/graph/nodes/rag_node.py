"""
rag_node.py — RAG 检索节点

功能：在工具执行前预先检索相关知识，注入到 state["rag_context"]。
在 intent 为 "study" 或 "review" 时执行，其他分支跳过。
"""

from agent.graph.state import AgentState
from langchain_core.messages import HumanMessage


def rag_node(state: AgentState) -> AgentState:
    """RAG 检索节点：检索相关知识，写入 state['rag_context']。"""

    # 非 study/review 意图直接跳过（review 意图同样需要 RAG 上下文）
    RAG_INTENTS = {"study", "review"}
    if state.get("intent") not in RAG_INTENTS:
        return {**state, "rag_context": ""}

    # 优先取 tool_args 中的 topic，否则取最后一条 HumanMessage
    query = state.get("tool_args", {}).get("topic", "")
    if not query:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                query = msg.content
                break

    if not query:
        return {**state, "rag_context": ""}

    # 调用 RAG 检索（带管线追踪），失败时静默处理
    rag_context = ""
    rag_pipeline_trace: list[dict] = []
    try:
        from memory.rag.retriever_rag import retrieve_with_trace
        result = retrieve_with_trace(query)
        rag_context = result.get("context", "") or ""
        rag_pipeline_trace = result.get("trace", [])
    except Exception:
        # retrieve_with_trace 不可用时降级到 retrieve
        try:
            from memory.rag.retriever_rag import retrieve
            rag_context = retrieve(query) or ""
        except Exception:
            rag_context = ""

    return {
        **state,
        "rag_context": rag_context,
        "rag_pipeline_trace": rag_pipeline_trace,
    }
