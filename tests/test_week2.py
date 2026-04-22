"""
test_week2.py — 第二周 LangGraph 改造测试套件

测试分三层：
  Level 1 (无需API): 状态图结构、路由逻辑、关键词映射
  Level 2 (无需API): 节点逻辑（Mock LLM，验证数据流）
  Level 3 (需要API): 真实 LLM 端到端对话测试

运行方式：
  # 全量（需要 API Key）
  .venv\\Scripts\\python.exe tests/test_week2.py

  # 只跑 Level 1+2（不消耗 API 额度，快速验证结构）
  .venv\\Scripts\\python.exe tests/test_week2.py --no-api
"""

import sys
import os
import json
import argparse

# 设置项目根路径
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

# ============================================================
# 测试工具函数
# ============================================================
_results = []

def run_test(name: str, fn):
    """运行单个测试，捕获异常，记录结果"""
    try:
        fn()
        _results.append(("PASS", name))
        print(f"  ✅ {name}")
    except AssertionError as e:
        _results.append(("FAIL", f"{name}: {e}"))
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        _results.append(("ERROR", f"{name}: {type(e).__name__}: {e}"))
        print(f"  💥 {name}: {type(e).__name__}: {e}")


def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def summary():
    total  = len(_results)
    passed = sum(1 for s, _ in _results if s == "PASS")
    failed = [(s, n) for s, n in _results if s != "PASS"]
    print(f"\n{'=' * 55}")
    print(f"  测试结果：{passed}/{total} 通过")
    if failed:
        print(f"\n  失败项：")
        for s, n in failed:
            print(f"    [{s}] {n}")
    print(f"{'=' * 55}")
    return passed == total


# ============================================================
# Level 1 — 静态结构验证（无需 API，秒级完成）
# ============================================================

def level1_tests():
    section("Level 1 — 静态结构验证（无需 API Key）")

    # 1.1 所有新模块可正常导入
    def test_imports():
        from agent.graph.state import AgentState
        from agent.graph.graph import build_graph, get_graph
        from agent.graph.nodes.intent_router import intent_router_node
        from agent.graph.nodes.rag_node import rag_node
        from agent.graph.nodes.tool_executor import tool_executor_node
        from agent.graph.nodes.response_generator import response_generator_node
        from agent.graph.nodes.memory_update import memory_update_node
        from agent.lc_tools import TOOLS_LIST, get_tool_by_name
        from agent.main_agent import LangGraphAgent
    run_test("所有新模块可导入", test_imports)

    # 1.2 AgentState 字段完整性
    def test_agent_state_fields():
        from agent.graph.state import AgentState
        from langchain_core.messages import HumanMessage, SystemMessage
        state = AgentState(
            messages=[SystemMessage(content="sys"), HumanMessage(content="hello")],
            intent="unknown",
            rag_context="",
            tool_name="",
            tool_args={},
            tool_result="",
            memory_l2={},
            memory_l4={},
            session_events=[],
            final_response="",
            error="",
        )
        assert state["intent"] == "unknown"
        assert len(state["messages"]) == 2
        assert isinstance(state["tool_args"], dict)
    run_test("AgentState 字段完整性", test_agent_state_fields)

    # 1.3 StateGraph 可编译
    def test_graph_compiles():
        from agent.graph.graph import build_graph
        g = build_graph()
        # 编译后的图是可调用对象
        assert callable(g.invoke), "图对象需要有 invoke 方法"
    run_test("StateGraph 可正常编译", test_graph_compiles)

    # 1.4 LangChain Tools 数量和名称
    def test_lc_tools():
        from agent.lc_tools import TOOLS_LIST, get_tool_by_name
        assert len(TOOLS_LIST) == 7, f"期望7个工具，实际{len(TOOLS_LIST)}个"
        expected = [
            "explain_concept", "generate_quiz", "check_answer",
            "recommend_next", "save_study_plan", "read_study_plan", "complete_task",
        ]
        for name in expected:
            t = get_tool_by_name(name)
            assert t is not None, f"找不到工具: {name}"
    run_test("LangChain Tools（7个，get_tool_by_name）", test_lc_tools)

    # 1.5 关键词映射表正确性
    def test_keyword_map():
        from agent.graph.nodes.intent_router import _KEYWORD_TOOL_MAP, _INTENT_TOOL_MAP
        assert len(_KEYWORD_TOOL_MAP) >= 8, "关键词至少8个"
        # 验证核心映射关系
        assert _KEYWORD_TOOL_MAP.get("出题") == "generate_quiz"
        assert _KEYWORD_TOOL_MAP.get("练习") == "generate_quiz"
        assert _KEYWORD_TOOL_MAP.get("推荐") == "recommend_next"
        # 验证 intent 默认映射
        assert _INTENT_TOOL_MAP["study"]   == "explain_concept"
        assert _INTENT_TOOL_MAP["plan"]    == "read_study_plan"
        assert _INTENT_TOOL_MAP["review"]  == "recommend_next"
        assert _INTENT_TOOL_MAP["unknown"] == ""
    run_test("意图→工具关键词映射表", test_keyword_map)

    # 1.6 图路由函数逻辑
    def test_route_functions():
        from agent.graph.graph import route_by_intent, route_after_rag
        # route_by_intent
        assert route_by_intent({"intent": "study"})   == "rag_then_tool"
        assert route_by_intent({"intent": "plan"})    == "plan_branch"
        assert route_by_intent({"intent": "review"})  == "review_branch"
        assert route_by_intent({"intent": "unknown"}) == "direct_response"
        assert route_by_intent({})                    == "direct_response"
        # route_after_rag
        assert route_after_rag({"intent": "study"})  == "tool_executor"
        assert route_after_rag({"intent": "review"}) == "response_generator"
    run_test("路由函数逻辑（route_by_intent + route_after_rag）", test_route_functions)

    # 1.7 Week1 RAG 模块与 Week2 兼容性
    def test_week1_compat():
        from memory.rag.bm25_retriever import get_bm25_retriever
        from memory.rag.hybrid_fusion import rrf_fusion
        from memory.rag.score_gate import ScoreGate
        gate = ScoreGate()
        # 使用修复后的 check_by_mode API
        passed, score, reason = gate.check_by_mode([], "normal")
        assert passed is False
        assert score == 0.0
    run_test("Week1 RAG 模块与 Week2 兼容性", test_week1_compat)


# ============================================================
# Level 2 — 节点数据流验证（Mock LLM，不消耗 API）
# ============================================================

def level2_tests():
    section("Level 2 — 节点数据流验证（Mock LLM）")

    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    def _make_state(**kwargs) -> dict:
        """构造最小可用 AgentState"""
        base = dict(
            messages=[SystemMessage(content="你是学习助手")],
            intent="unknown",
            rag_context="",
            tool_name="",
            tool_args={},
            tool_result="",
            memory_l2={},
            memory_l4={},
            session_events=[],
            final_response="",
            error="",
        )
        base.update(kwargs)
        return base

    # 2.1 intent_router：关键词路由（不调用LLM，通过关键词触发）
    def test_router_keyword_override():
        """关键词优先级高于 LLM 分类——模拟 LLM 返回 study，但关键词命中 generate_quiz"""
        from agent.graph.nodes.intent_router import _KEYWORD_TOOL_MAP, _INTENT_TOOL_MAP
        user_text = "帮我出一道关于快速排序的练习题"
        # 手动运行关键词匹配逻辑
        tool_name = _INTENT_TOOL_MAP.get("study", "")  # 默认
        for kw, kw_tool in _KEYWORD_TOOL_MAP.items():
            if kw in user_text:
                tool_name = kw_tool
                break
        assert tool_name == "generate_quiz", f"关键词'练习'应命中 generate_quiz，实际: {tool_name}"
    run_test("意图路由：关键词优先级覆盖", test_router_keyword_override)

    # 2.2 rag_node：空知识库时优雅降级
    def test_rag_node_graceful_fail():
        from agent.graph.nodes.rag_node import rag_node
        state = _make_state(
            messages=[HumanMessage(content="讲解快速排序")],
            intent="study",
            tool_args={"topic": "快速排序"},
        )
        result = rag_node(state)
        # rag_context 可以是空字符串（知识库为空时降级），但不能报错
        assert "rag_context" in result
        assert isinstance(result["rag_context"], str)
    run_test("rag_node：空知识库优雅降级", test_rag_node_graceful_fail)

    # 2.3 tool_executor：tool_name 为空时 fallback
    def test_tool_executor_fallback():
        from agent.graph.nodes.tool_executor import tool_executor_node
        state = _make_state(
            messages=[HumanMessage(content="讲解操作系统进程")],
            intent="study",
            tool_name="",           # 故意留空，测试 fallback
            tool_args={"topic": "进程"},
        )
        result = tool_executor_node(state)
        # fallback 应该用 explain_concept，tool_result 应该有内容
        assert "tool_result" in result
        assert isinstance(result["tool_result"], str)
        assert len(result["tool_result"]) > 0, "tool_result 不应为空"
    run_test("tool_executor：空 tool_name 的 fallback 机制", test_tool_executor_fallback)

    # 2.4 tool_executor：session_events 追加
    def test_tool_executor_events():
        from agent.graph.nodes.tool_executor import tool_executor_node
        state = _make_state(
            messages=[HumanMessage(content="推荐复习内容")],
            intent="review",
            tool_name="recommend_next",
            tool_args={},
            session_events=[],
        )
        result = tool_executor_node(state)
        events = result.get("session_events", [])
        assert len(events) >= 1, "tool_executor 应追加至少一条 session_event"
        assert events[-1].get("event_type") == "tool_call"
    run_test("tool_executor：session_events 事件追加", test_tool_executor_events)

    # 2.5 memory_update_node：刷新 L2/L4 快照
    def test_memory_update_node():
        from agent.graph.nodes.memory_update import memory_update_node
        state = _make_state(
            intent="study",
            tool_args={"topic": "快速排序"},
            session_events=[{"event_type": "tool_call", "tool_name": "explain_concept"}],
        )
        result = memory_update_node(state)
        # memory_l2 和 memory_l4 应该被更新为 dict（即使磁盘没有数据也返回默认{}）
        assert isinstance(result.get("memory_l2"), dict)
        assert isinstance(result.get("memory_l4"), dict)
    run_test("memory_update_node：L2/L4 快照刷新", test_memory_update_node)

    # 2.6 完整状态流：模拟 plan 分支（不走RAG）
    def test_plan_branch_no_rag():
        """plan 分支不应修改 rag_context"""
        from agent.graph.nodes.rag_node import rag_node
        state = _make_state(
            messages=[HumanMessage(content="查看我的学习计划")],
            intent="plan",          # plan 分支跳过 rag_node
            tool_args={},
        )
        # plan 分支不经过 rag_node，手动调用 rag_node 验证 plan 时它会跳过
        result = rag_node(state)
        # plan 意图时 rag_node 应直接跳过，rag_context 保持空
        assert result.get("rag_context", "") == "", "plan 分支不应触发 RAG 检索"
    run_test("plan 分支：rag_node 正确跳过", test_plan_branch_no_rag)

    # 2.7 RRF 融合算法（Week1集成验证）
    def test_rrf_integration():
        from memory.rag.hybrid_fusion import rrf_fusion
        vec = [
            {"text": "快速排序分治算法", "metadata": {}, "score": 0.9},
            {"text": "归并排序稳定", "metadata": {}, "score": 0.7},
        ]
        bm25 = [
            {"text": "快速排序分治算法", "metadata": {}, "score": 0.85},  # 重复，应去重
            {"text": "堆排序", "metadata": {}, "score": 0.5},
        ]
        fused = rrf_fusion(vec, bm25)
        assert len(fused) == 3, f"去重后应3条，实际{len(fused)}条"
        assert fused[0].get("in_vector") or fused[0].get("in_bm25"), "应有来源标记"
        # 重复文档分数应最高（双路命中）
        max_doc = max(fused, key=lambda x: x["rrf_score"])
        assert "快速排序" in max_doc["text"], "双路命中的文档应排第一"
    run_test("Week1+2 集成：RRF 融合算法正确性", test_rrf_integration)


# ============================================================
# Level 3 — 真实 API 端到端测试（需要 API Key）
# ============================================================

def level3_tests():
    section("Level 3 — 端到端测试（调用真实 LLM API）")

    from langchain_core.messages import HumanMessage, SystemMessage

    def _make_full_state(user_msg: str, intent_hint: str = "study") -> dict:
        return dict(
            messages=[
                SystemMessage(content="你是408考研学习助手"),
                HumanMessage(content=user_msg),
            ],
            intent=intent_hint,
            rag_context="",
            tool_name="",
            tool_args={},
            tool_result="",
            memory_l2={},
            memory_l4={},
            session_events=[],
            final_response="",
            error="",
        )

    # 3.1 意图路由节点：真实LLM分类
    def test_real_intent_router():
        from agent.graph.nodes.intent_router import intent_router_node
        state = _make_full_state("请帮我讲解快速排序的时间复杂度")
        result = intent_router_node(state)
        intent = result.get("intent")
        assert intent in ("study", "plan", "review", "unknown"), f"intent 值非法: {intent}"
        assert intent == "study", f"期望 study，实际: {intent}"
        print(f"      → intent={intent}, tool_name={result.get('tool_name')}, topic={result.get('tool_args',{}).get('topic')}")
    run_test("intent_router：真实LLM分类（快速排序 → study）", test_real_intent_router)

    # 3.2 意图路由节点：plan 分类
    def test_real_intent_plan():
        from agent.graph.nodes.intent_router import intent_router_node
        state = _make_full_state("帮我创建一个两周的408复习计划")
        result = intent_router_node(state)
        intent = result.get("intent")
        print(f"      → intent={intent}, tool_name={result.get('tool_name')}")
        assert intent in ("study", "plan", "review", "unknown")
    run_test("intent_router：真实LLM分类（创建计划）", test_real_intent_plan)

    # 3.3 response_generator：verify 带 tool_result 的回复
    def test_response_with_tool_result():
        from agent.graph.nodes.response_generator import response_generator_node
        state = _make_full_state("快速排序的时间复杂度是多少？")
        # 注入模拟的 tool_result（代替真实工具调用）
        state["tool_result"] = (
            "[工具指令] 请用beginner方式讲解「快速排序」。\n"
            "要求：先生活类比 → 代码示例 → 一句总结"
        )
        state["intent"] = "study"
        result = response_generator_node(state)
        reply = result.get("final_response", "")
        assert len(reply) > 50, f"回复太短，可能生成失败: {repr(reply)}"
        # 验证 AIMessage 已追加到 messages
        from langchain_core.messages import AIMessage
        ai_msgs = [m for m in result.get("messages", []) if isinstance(m, AIMessage)]
        assert len(ai_msgs) >= 1, "回复应追加到 messages"
        print(f"      → 回复前50字：{reply[:50]}...")
    run_test("response_generator：注入tool_result生成回复", test_response_with_tool_result)

    # 3.4 完整 LangGraph 图端到端（study 分支完整链路）
    def test_full_graph_study():
        from agent.graph.graph import build_graph
        from langchain_core.messages import HumanMessage, SystemMessage
        g = build_graph()
        initial = dict(
            messages=[
                SystemMessage(content="你是408考研学习助手"),
                HumanMessage(content="用一句话解释什么是进程"),
            ],
            intent="unknown",
            rag_context="",
            tool_name="",
            tool_args={},
            tool_result="",
            memory_l2={},
            memory_l4={},
            session_events=[],
            final_response="",
            error="",
        )
        result = g.invoke(initial)
        reply = result.get("final_response", "")
        intent = result.get("intent", "")
        tool = result.get("tool_name", "")
        assert len(reply) > 20, f"回复过短: {repr(reply)}"
        print(f"      → intent={intent}, tool={tool}")
        print(f"      → 回复: {reply[:80]}...")
    run_test("完整图端到端：study分支（进程是什么）", test_full_graph_study)

    # 3.5 LangGraphAgent.chat() 接口测试
    def test_langraph_agent_chat():
        from agent.main_agent import LangGraphAgent
        agent = LangGraphAgent(user_id="test_user_001")
        reply = agent.chat("用一句话解释什么是死锁")
        assert isinstance(reply, str), "chat() 应返回字符串"
        assert len(reply) > 10, f"回复过短: {repr(reply)}"
        print(f"      → 回复: {reply[:80]}...")
    run_test("LangGraphAgent.chat()：完整对话接口", test_langraph_agent_chat)


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Week2 LangGraph 测试套件")
    parser.add_argument("--no-api", action="store_true", help="跳过 Level 3（不调用 LLM API）")
    args = parser.parse_args()

    print("=" * 55)
    print("  Week2 LangGraph 改造测试套件")
    print("=" * 55)

    level1_tests()
    level2_tests()

    if not args.no_api:
        level3_tests()
    else:
        print("\n  ⏭️  Level 3 已跳过（--no-api 模式）")

    all_passed = summary()
    sys.exit(0 if all_passed else 1)
