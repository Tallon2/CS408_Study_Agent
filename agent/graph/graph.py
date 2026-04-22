"""
graph.py — LangGraph 主状态图

图结构：
    START
      ↓
    [intent_router]       ← LLM 语义分类
      ↓
    条件路由（4分支）：
      ├─ study  → [rag_node] → [tool_executor] → [response_generator]
      ├─ plan   → [tool_executor] → [response_generator]  （无 RAG，直接执行计划工具）
      ├─ review → [rag_node] → [response_generator]       （RAG 检索 + 直接生成，不走工具）
      └─ unknown→ [response_generator]                    （直接 LLM 回复）
      ↓（所有分支汇聚）
    [memory_update]       ← 更新 L2/L4 快照
      ↓
    END
"""

from langgraph.graph import StateGraph, START, END
from agent.graph.state import AgentState
from agent.graph.nodes.intent_router import intent_router_node
from agent.graph.nodes.rag_node import rag_node
from agent.graph.nodes.tool_executor import tool_executor_node
from agent.graph.nodes.response_generator import response_generator_node
from agent.graph.nodes.memory_update import memory_update_node


def route_by_intent(state: AgentState) -> str:
    """条件路由函数：根据 intent 决定下一个节点"""
    intent = state.get("intent", "unknown")
    tool_name = state.get("tool_name", "")

    # check_answer 判答不需要 RAG 检索，直接走 tool_executor
    if tool_name == "check_answer":
        return "plan_branch"  # 复用 plan 分支：直接 tool_executor → response_generator

    if intent == "study":
        return "rag_then_tool"
    elif intent == "plan":
        return "plan_branch"
    elif intent == "review":
        return "review_branch"
    else:
        return "direct_response"


def route_after_rag(state: AgentState) -> str:
    """RAG 之后的路由：study 走 tool_executor，review 直接走 response_generator"""
    intent = state.get("intent", "study")
    return "tool_executor" if intent == "study" else "response_generator"


def build_graph():
    """
    构建并编译 LangGraph 状态图（完整版，用于 sync 场景）。
    返回编译后的 CompiledGraph，可直接调用 .invoke() 或 .stream()。
    """
    builder = StateGraph(AgentState)

    # 注册所有节点
    builder.add_node("intent_router",      intent_router_node)
    builder.add_node("rag_node",           rag_node)
    builder.add_node("tool_executor",      tool_executor_node)
    builder.add_node("response_generator", response_generator_node)
    builder.add_node("memory_update",      memory_update_node)

    # 入口边
    builder.add_edge(START, "intent_router")

    # 意图路由后的条件分支
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "rag_then_tool":   "rag_node",           # study 分支：先 RAG
            "plan_branch":     "tool_executor",       # plan 分支：直接工具
            "review_branch":   "rag_node",            # review 分支：先 RAG（复用）
            "direct_response": "response_generator",  # unknown：直接生成
        }
    )

    # rag_node 之后的条件路由：study → tool_executor，review → response_generator
    builder.add_conditional_edges(
        "rag_node",
        route_after_rag,
        {
            "tool_executor":      "tool_executor",
            "response_generator": "response_generator",
        }
    )

    # plan / study 分支：tool_executor → response_generator
    builder.add_edge("tool_executor",      "response_generator")

    # 所有 response_generator 后 → memory_update → END
    builder.add_edge("response_generator", "memory_update")
    builder.add_edge("memory_update",      END)

    return builder.compile()


def _route_to_end(state: AgentState) -> str:
    """准备图的汇聚路由：所有分支直接走 END"""
    return "end"


def build_prep_graph():
    """
    构建"准备图"（不含 response_generator 和 memory_update），用于流式场景。
    
    只运行 intent_router → rag_node → tool_executor，返回中间 state，
    之后由外部调用 response_generator_stream() 逐 token 输出。
    """
    builder = StateGraph(AgentState)

    # 注册前半段节点
    builder.add_node("intent_router", intent_router_node)
    builder.add_node("rag_node",      rag_node)
    builder.add_node("tool_executor", tool_executor_node)

    # 入口
    builder.add_edge(START, "intent_router")

    # 意图路由
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "rag_then_tool":   "rag_node",
            "plan_branch":     "tool_executor",
            "review_branch":   "rag_node",
            "direct_response": END,      # unknown：直接结束准备阶段
        }
    )

    # rag 之后路由
    builder.add_conditional_edges(
        "rag_node",
        route_after_rag,
        {
            "tool_executor":      "tool_executor",
            "response_generator": END,   # review 分支：RAG 结束即可
        }
    )

    # tool_executor → END
    builder.add_edge("tool_executor", END)

    return builder.compile()


# 模块级单例（避免重复编译）
_compiled_graph = None
_compiled_prep_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def get_prep_graph():
    """获取准备图（用于流式场景，不含 response_generator 和 memory_update）"""
    global _compiled_prep_graph
    if _compiled_prep_graph is None:
        _compiled_prep_graph = build_prep_graph()
    return _compiled_prep_graph
