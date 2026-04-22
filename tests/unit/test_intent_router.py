"""
tests/unit/test_intent_router.py — 意图路由节点单元测试

测试覆盖（P1 优先级）：
  1. _is_quiz_answer — 单字母 A/B/C/D 识别为答题
  2. _is_quiz_answer — 正常消息不误判为答题
  3. _is_quiz_answer — 无 quiz_answer 时不触发快速路径
  4. _is_quiz_answer — "选A"、"答案是B" 等表达识别
  5. intent_router_node — 快速路径设置正确的 intent/tool_name/tool_args
  6. intent_router_node — 空消息时返回 unknown
  7. intent_router_node — LLM 失败时降级为 study
  8. intent_router_node — state['intent'] 字段被正确写入
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from unittest.mock import patch, MagicMock

# langchain_core is an optional heavy dependency; skip entire module if unavailable
try:
    from langchain_core.messages import HumanMessage
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False
    HumanMessage = None  # type: ignore

pytestmark_langchain = pytest.mark.skipif(
    not _LANGCHAIN_AVAILABLE,
    reason="langchain_core not installed (run: pip install langchain-core)"
)

try:
    from agent.graph.nodes.intent_router import (
        _is_quiz_answer,
        _extract_user_choice,
        intent_router_node,
    )
    _ROUTER_AVAILABLE = _LANGCHAIN_AVAILABLE
except ImportError:
    _is_quiz_answer = None  # type: ignore
    _extract_user_choice = None  # type: ignore
    intent_router_node = None  # type: ignore
    _ROUTER_AVAILABLE = False


# ================================================================
# _is_quiz_answer() 测试
# ================================================================

@pytest.mark.skipif(not _ROUTER_AVAILABLE, reason="langchain_core not installed")
class TestIsQuizAnswer:
    """_is_quiz_answer() 快速路径判断测试。"""

    def test_single_letter_a_detected(self):
        """单字母 'A' 应被识别为答题。"""
        assert _is_quiz_answer("A", quiz_answer="B") is True

    def test_single_letter_b_detected(self):
        """单字母 'B' 应被识别为答题。"""
        assert _is_quiz_answer("B", quiz_answer="A") is True

    def test_single_letter_c_detected(self):
        """单字母 'C' 应被识别为答题。"""
        assert _is_quiz_answer("C", quiz_answer="D") is True

    def test_single_letter_d_detected(self):
        """单字母 'D' 应被识别为答题。"""
        assert _is_quiz_answer("D", quiz_answer="C") is True

    def test_is_quiz_answer_not_triggered_by_normal_message(self):
        """正常消息不应被误判为答题行为。"""
        assert _is_quiz_answer("请讲解操作系统进程调度算法", quiz_answer="A") is False

    def test_is_quiz_answer_returns_false_without_quiz_answer(self):
        """无 quiz_answer（为空字符串）时，任何消息都不应触发快速路径。"""
        assert _is_quiz_answer("A", quiz_answer="") is False
        assert _is_quiz_answer("B", quiz_answer="") is False

    def test_select_a_pattern_detected(self):
        """'选A' 模式应被识别为答题。"""
        assert _is_quiz_answer("选A", quiz_answer="B") is True

    def test_answer_is_c_pattern_detected(self):
        """'答案是C' 模式应被识别为答题。"""
        assert _is_quiz_answer("答案是C", quiz_answer="A") is True

    def test_lowercase_letter_detected(self):
        """小写字母 'a' 也应被识别（代码做了 .upper() 转换）。"""
        assert _is_quiz_answer("a", quiz_answer="A") is True

    def test_long_message_not_quiz_answer(self):
        """较长的普通消息不应被误判为答题。"""
        long_msg = "我想了解一下操作系统中死锁的四个必要条件是什么，请详细解释一下"
        assert _is_quiz_answer(long_msg, quiz_answer="A") is False


# ================================================================
# _extract_user_choice() 测试
# ================================================================

@pytest.mark.skipif(not _ROUTER_AVAILABLE, reason="langchain_core not installed")
class TestExtractUserChoice:
    """_extract_user_choice() 选项提取测试。"""

    def test_extract_pure_letter(self):
        """纯字母应直接提取。"""
        assert _extract_user_choice("A") == "A"
        assert _extract_user_choice("b") == "B"

    def test_extract_from_select_pattern(self):
        """从 '选A' 等模式中提取字母。"""
        assert _extract_user_choice("选B") == "B"

    def test_extract_from_answer_pattern(self):
        """从 '我的答案是C' 中提取字母。"""
        assert _extract_user_choice("我的答案是C") == "C"


# ================================================================
# intent_router_node() 测试
# ================================================================

@pytest.mark.skipif(not _ROUTER_AVAILABLE, reason="langchain_core not installed")
class TestIntentRouterNode:
    """intent_router_node() 节点函数测试。"""

    def _make_state(self, user_text: str, quiz_answer: str = "", **kwargs) -> dict:
        """辅助方法：构建 AgentState 字典。"""
        return {
            "messages": [HumanMessage(content=user_text)],
            "current_quiz_answer": quiz_answer,
            "intent": "",
            "tool_name": "",
            "tool_args": {},
            **kwargs,
        }

    def test_quiz_answer_fast_path_sets_check_answer_tool(self):
        """快速路径：用户回答选择题时，intent 应为 study，tool_name 应为 check_answer。"""
        state = self._make_state("B", quiz_answer="A")
        result = intent_router_node(state)
        assert result["intent"] == "study"
        assert result["tool_name"] == "check_answer"
        assert result["tool_args"]["user_answer"] == "B"
        assert result["tool_args"]["correct_answer"] == "A"

    def test_empty_messages_returns_unknown(self):
        """无消息时应返回 intent='unknown'。"""
        state = {"messages": [], "current_quiz_answer": "", "intent": "", "tool_name": "", "tool_args": {}}
        result = intent_router_node(state)
        assert result["intent"] == "unknown"

    def test_intent_field_is_set_in_state(self):
        """节点调用后 state 中应包含 'intent' 字段。"""
        state = self._make_state("请讲解一下进程调度算法")
        mock_settings_for_settings_cache = MagicMock()

        mock_client = MagicMock()
        mock_client.default_model = "glm-4-flash"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"intent": "study", "confidence": 0.95, "topic": "进程调度"}'))]
        )
        with patch("agent.graph.nodes.intent_router.get_llm_client", return_value=mock_client):
            result = intent_router_node(state)
        assert "intent" in result
        assert result["intent"] in ("study", "plan", "review", "unknown")

    def test_llm_failure_falls_back_to_study(self):
        """LLM 调用失败时，应降级为 intent='study'。"""
        state = self._make_state("我想学习数据结构")
        with patch("agent.graph.nodes.intent_router.get_llm_client", side_effect=Exception("LLM 不可用")):
            result = intent_router_node(state)
        assert result["intent"] == "study"

    def test_invalid_intent_from_llm_falls_back_to_study(self):
        """LLM 返回无效 intent 值时，应矫正为 'study'。"""
        state = self._make_state("帮我复习一下")
        mock_client = MagicMock()
        mock_client.default_model = "glm-4-flash"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"intent": "invalid_value", "confidence": 0.5, "topic": ""}'))]
        )
        with patch("agent.graph.nodes.intent_router.get_llm_client", return_value=mock_client):
            result = intent_router_node(state)
        assert result["intent"] == "study"  # 无效值应被矫正

    def test_keyword_overrides_intent_tool(self):
        """消息中包含关键词（如 '出题'）时，应覆盖默认工具为 generate_quiz。"""
        state = self._make_state("帮我出一道关于进程调度的题")
        mock_client = MagicMock()
        mock_client.default_model = "glm-4-flash"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"intent": "study", "confidence": 0.9, "topic": "进程调度"}'))]
        )
        with patch("agent.graph.nodes.intent_router.get_llm_client", return_value=mock_client):
            result = intent_router_node(state)
        assert result["tool_name"] == "generate_quiz"
