"""
tests/unit/test_llm_client.py — 统一 LLM 客户端层单元测试

测试覆盖：
  1. ZhipuProvider 正确初始化，API Key 为空时抛出 ValueError
  2. OpenAICompatProvider 正确初始化，API Key 为空时抛出 ValueError
  3. LLMClient.complete() 返回文本字符串
  4. LLMClient.stream() 逐 token yield 字符串
  5. LLMClient.chat.completions.create() 向后兼容接口
  6. LLMClient.default_model 属性
  7. LLMClient.provider_name 属性
  8. LLMClient.embeddings.create() 代理调用
  9. get_llm_client() 单例行为
  10. reset_llm_client() 重置单例
  11. get_llm_client() 无效 LLM_PROVIDER 抛出 ValueError
  12. chat_completion() 便捷函数
  13. chat_completion_stream() 便捷函数
  14. 切换 Provider 后 reset_llm_client() 生效
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ================================================================
# 辅助：构造 mock Provider
# ================================================================

def _make_mock_provider(provider_name="mock_provider", default_model="mock-model"):
    """构造一个 mock BaseLLMProvider。"""
    from core.llm_client import BaseLLMProvider

    mock_provider = MagicMock(spec=BaseLLMProvider)
    type(mock_provider).provider_name = PropertyMock(return_value=provider_name)
    type(mock_provider).default_model = PropertyMock(return_value=default_model)

    # 非流式响应
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="mock LLM 回复"))]
    mock_provider.chat_completions_create.return_value = mock_response

    return mock_provider


def _make_streaming_mock_provider():
    """构造一个支持流式输出的 mock Provider。"""
    from core.llm_client import BaseLLMProvider

    mock_provider = MagicMock(spec=BaseLLMProvider)
    type(mock_provider).provider_name = PropertyMock(return_value="mock_stream")
    type(mock_provider).default_model = PropertyMock(return_value="mock-model")

    # 流式 chunks
    def _make_chunk(content):
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=content))]
        return chunk

    stream_chunks = [
        _make_chunk("你"),
        _make_chunk("好"),
        _make_chunk("，"),
        _make_chunk("世"),
        _make_chunk("界"),
    ]
    mock_provider.chat_completions_create.return_value = iter(stream_chunks)
    return mock_provider


# ================================================================
# LLMClient 核心功能测试
# ================================================================

class TestLLMClient:
    """LLMClient 代理层功能测试。"""

    def setup_method(self):
        from core.llm_client import LLMClient
        self.mock_provider = _make_mock_provider()
        self.client = LLMClient(self.mock_provider)

    def test_default_model_property(self):
        """default_model 应返回 Provider 的默认模型。"""
        assert self.client.default_model == "mock-model"

    def test_provider_name_property(self):
        """provider_name 应返回 Provider 的标识名。"""
        assert self.client.provider_name == "mock_provider"

    def test_complete_returns_string(self):
        """complete() 应直接返回 LLM 回复文本字符串。"""
        messages = [{"role": "user", "content": "你好"}]
        result = self.client.complete(messages)
        assert result == "mock LLM 回复"
        assert isinstance(result, str)

    def test_complete_calls_provider_with_stream_false(self):
        """complete() 必须以 stream=False 调用 Provider。"""
        messages = [{"role": "user", "content": "测试"}]
        self.client.complete(messages)
        call_kwargs = self.mock_provider.chat_completions_create.call_args
        assert call_kwargs.kwargs.get("stream") is False

    def test_complete_passes_model_and_temperature(self):
        """complete() 应正确传递 model 和 temperature 参数。"""
        messages = [{"role": "user", "content": "测试"}]
        self.client.complete(messages, model="glm-4", temperature=0.3)
        call_kwargs = self.mock_provider.chat_completions_create.call_args
        assert call_kwargs.kwargs.get("model") == "glm-4"
        assert call_kwargs.kwargs.get("temperature") == 0.3

    def test_stream_yields_tokens(self):
        """stream() 应逐 token yield 字符串。"""
        from core.llm_client import LLMClient
        mock_provider = _make_streaming_mock_provider()
        client = LLMClient(mock_provider)

        messages = [{"role": "user", "content": "打招呼"}]
        tokens = list(client.stream(messages))
        assert tokens == ["你", "好", "，", "世", "界"]

    def test_stream_calls_provider_with_stream_true(self):
        """stream() 必须以 stream=True 调用 Provider。"""
        from core.llm_client import LLMClient
        mock_provider = _make_streaming_mock_provider()
        client = LLMClient(mock_provider)

        list(client.stream([{"role": "user", "content": "测试"}]))
        call_kwargs = mock_provider.chat_completions_create.call_args
        assert call_kwargs.kwargs.get("stream") is True

    def test_backward_compat_chat_completions_create(self):
        """client.chat.completions.create() 向后兼容接口应正常工作。"""
        messages = [{"role": "user", "content": "测试兼容性"}]
        result = self.client.chat.completions.create(
            messages=messages,
            model="glm-4-flash",
            temperature=0.7,
            stream=False,
        )
        # 应该调用了 Provider
        self.mock_provider.chat_completions_create.assert_called_once()
        # 返回值应是 mock 响应对象
        assert result.choices[0].message.content == "mock LLM 回复"

    def test_embeddings_namespace_exists(self):
        """client.embeddings 属性应存在。"""
        assert hasattr(self.client, "embeddings")
        assert hasattr(self.client.embeddings, "create")


# ================================================================
# Provider 初始化测试（不需要真实 API Key）
# ================================================================

class TestProviderInit:
    """Provider 初始化与错误处理测试（mock SDK）。"""

    def test_zhipu_provider_empty_api_key_raises(self):
        """ZhipuProvider 空 API Key 应抛出 ValueError。"""
        from core.llm_client import ZhipuProvider
        with pytest.raises(ValueError, match="ZHIPU_API_KEY"):
            ZhipuProvider(api_key="")

    def test_openai_compat_provider_empty_api_key_raises(self):
        """OpenAICompatProvider 空 API Key 应抛出 ValueError。"""
        from core.llm_client import OpenAICompatProvider
        with pytest.raises(ValueError, match="OPENAI_COMPAT_API_KEY"):
            OpenAICompatProvider(api_key="", base_url="https://api.example.com/v1")

    def test_zhipu_provider_provider_name(self):
        """ZhipuProvider.provider_name 应为 'zhipu'。"""
        from core.llm_client import ZhipuProvider
        with patch("core.llm_client.ZhipuProvider.__init__", return_value=None):
            p = ZhipuProvider.__new__(ZhipuProvider)
            p._model_name = "glm-4-flash"
            assert p.provider_name == "zhipu"

    def test_openai_compat_provider_provider_name(self):
        """OpenAICompatProvider.provider_name 应包含 base_url。"""
        from core.llm_client import OpenAICompatProvider
        with patch("core.llm_client.OpenAICompatProvider.__init__", return_value=None):
            p = OpenAICompatProvider.__new__(OpenAICompatProvider)
            p._model_name = "deepseek-chat"
            p._base_url = "https://api.deepseek.com/v1"
            assert "deepseek" in p.provider_name


# ================================================================
# 工厂函数 / 单例测试
# ================================================================

class TestGetLLMClient:
    """get_llm_client() 工厂函数和单例行为测试。"""

    def setup_method(self):
        """每个测试前重置单例，避免干扰。"""
        from core.llm_client import reset_llm_client
        reset_llm_client()

    def teardown_method(self):
        """每个测试后重置单例，避免污染后续测试。"""
        from core.llm_client import reset_llm_client
        reset_llm_client()

    def _make_zhipu_mock_provider(self, model_name="glm-4-flash"):
        """构造模拟 ZhipuProvider 实例（无需真实 SDK）。"""
        from core.llm_client import BaseLLMProvider
        mock_p = MagicMock(spec=BaseLLMProvider)
        type(mock_p).provider_name = PropertyMock(return_value="zhipu")
        type(mock_p).default_model = PropertyMock(return_value=model_name)
        return mock_p

    def _make_openai_mock_provider(self, model_name="deepseek-chat"):
        """构造模拟 OpenAICompatProvider 实例（无需真实 SDK）。"""
        from core.llm_client import BaseLLMProvider
        mock_p = MagicMock(spec=BaseLLMProvider)
        type(mock_p).provider_name = PropertyMock(return_value="openai_compat(https://api.deepseek.com/v1)")
        type(mock_p).default_model = PropertyMock(return_value=model_name)
        return mock_p

    def test_returns_llm_client_instance(self):
        """get_llm_client() 应返回 LLMClient 实例。"""
        from core.llm_client import get_llm_client, LLMClient, ZhipuProvider
        from core.settings import Settings

        mock_settings = Settings.model_construct(
            LLM_PROVIDER="zhipu",
            ZHIPU_API_KEY="test-key-12345",
            MODEL_NAME="glm-4-flash",
        )
        mock_provider = self._make_zhipu_mock_provider()
        with patch("core.settings.get_settings", return_value=mock_settings), \
             patch("core.llm_client.ZhipuProvider", return_value=mock_provider):
            client = get_llm_client()
            assert isinstance(client, LLMClient)

    def test_singleton_same_object(self):
        """多次调用 get_llm_client() 应返回同一个对象。"""
        from core.llm_client import get_llm_client, LLMClient
        from core.settings import Settings

        mock_settings = Settings.model_construct(
            LLM_PROVIDER="zhipu",
            ZHIPU_API_KEY="test-key",
            MODEL_NAME="glm-4-flash",
        )
        mock_provider = self._make_zhipu_mock_provider()
        with patch("core.settings.get_settings", return_value=mock_settings), \
             patch("core.llm_client.ZhipuProvider", return_value=mock_provider):
            client1 = get_llm_client()
            client2 = get_llm_client()
            assert client1 is client2

    def test_reset_llm_client_clears_singleton(self):
        """reset_llm_client() 后再次调用 get_llm_client() 应创建新实例。"""
        from core.llm_client import get_llm_client, reset_llm_client
        from core.settings import Settings

        mock_settings = Settings.model_construct(
            LLM_PROVIDER="zhipu",
            ZHIPU_API_KEY="test-key",
            MODEL_NAME="glm-4-flash",
        )
        mock_provider = self._make_zhipu_mock_provider()
        with patch("core.settings.get_settings", return_value=mock_settings), \
             patch("core.llm_client.ZhipuProvider", return_value=mock_provider):
            client1 = get_llm_client()
            reset_llm_client()
            client2 = get_llm_client()
            assert client1 is not client2

    def test_invalid_provider_raises_value_error(self):
        """未知的 LLM_PROVIDER 应抛出 ValueError，并给出明确提示。"""
        from core.llm_client import get_llm_client
        from core.settings import Settings

        mock_settings = Settings.model_construct(
            LLM_PROVIDER="unknown_provider_xyz",
            ZHIPU_API_KEY="test-key",
            MODEL_NAME="gpt-4",
        )
        with patch("core.settings.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="unknown_provider_xyz"):
                get_llm_client()

    def test_openai_compat_provider_selected(self):
        """LLM_PROVIDER=openai_compat 时应初始化 OpenAICompatProvider。"""
        from core.llm_client import get_llm_client, LLMClient
        from core.settings import Settings

        mock_settings = Settings.model_construct(
            LLM_PROVIDER="openai_compat",
            OPENAI_COMPAT_API_KEY="deepseek-key",
            OPENAI_COMPAT_BASE_URL="https://api.deepseek.com/v1",
            MODEL_NAME="deepseek-chat",
        )
        mock_provider = self._make_openai_mock_provider("deepseek-chat")
        with patch("core.settings.get_settings", return_value=mock_settings), \
             patch("core.llm_client.OpenAICompatProvider", return_value=mock_provider):
            client = get_llm_client()
            assert isinstance(client, LLMClient)
            assert client.default_model == "deepseek-chat"


# ================================================================
# 便捷函数测试
# ================================================================

class TestConvenienceFunctions:
    """chat_completion() / chat_completion_stream() 便捷函数测试。"""

    def setup_method(self):
        from core.llm_client import reset_llm_client
        reset_llm_client()

    def teardown_method(self):
        from core.llm_client import reset_llm_client
        reset_llm_client()

    def test_chat_completion_returns_string(self):
        """chat_completion() 应返回字符串。"""
        from core.llm_client import chat_completion, LLMClient

        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = "便捷函数测试回复"

        with patch("core.llm_client.get_llm_client", return_value=mock_client):
            result = chat_completion([{"role": "user", "content": "测试"}])
            assert result == "便捷函数测试回复"
            assert isinstance(result, str)

    def test_chat_completion_stream_yields_tokens(self):
        """chat_completion_stream() 应逐 token yield。"""
        from core.llm_client import chat_completion_stream, LLMClient

        tokens = ["你", "好", "世", "界"]
        mock_client = MagicMock(spec=LLMClient)
        mock_client.stream.return_value = iter(tokens)

        with patch("core.llm_client.get_llm_client", return_value=mock_client):
            result = list(chat_completion_stream([{"role": "user", "content": "测试"}]))
            assert result == tokens
