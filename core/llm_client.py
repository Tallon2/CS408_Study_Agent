"""
core/llm_client.py — 统一 LLM 客户端层

设计目标：
  1. 高内聚：所有 LLM 初始化逻辑集中在本模块
  2. 低耦合：调用方只依赖本模块，不直接依赖 zhipuai / openai SDK
  3. 可替换：通过 .env 中的 LLM_PROVIDER 切换底层 Provider，业务代码零改动

支持的 Provider：
  ┌─────────────────┬──────────────────────────────────────────────────┐
  │ LLM_PROVIDER    │ 说明                                              │
  ├─────────────────┼──────────────────────────────────────────────────┤
  │ zhipu (default) │ 智谱 GLM，使用 zhipuai SDK                        │
  │ openai_compat   │ 任意 OpenAI Chat API 兼容服务：                   │
  │                 │   DeepSeek、通义千问、Moonshot、Ollama 等          │
  └─────────────────┴──────────────────────────────────────────────────┘

快速切换示例（只需修改 .env，业务代码不动）：
  # 切换到 DeepSeek
  LLM_PROVIDER=openai_compat
  OPENAI_COMPAT_API_KEY=sk-xxx
  OPENAI_COMPAT_BASE_URL=https://api.deepseek.com/v1
  MODEL_NAME=deepseek-chat

  # 切换到通义千问
  LLM_PROVIDER=openai_compat
  OPENAI_COMPAT_API_KEY=sk-xxx
  OPENAI_COMPAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  MODEL_NAME=qwen-turbo

  # 切换到本地 Ollama
  LLM_PROVIDER=openai_compat
  OPENAI_COMPAT_API_KEY=ollama
  OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1
  MODEL_NAME=llama3

使用方式（业务代码）：
  from core.llm_client import get_llm_client, chat_completion, chat_completion_stream

  # 方式 1 — 直接调用便捷函数（推荐）
  response = chat_completion(messages=[...])
  text = response.choices[0].message.content

  # 方式 2 — 流式
  for chunk in chat_completion_stream(messages=[...]):
      print(chunk.choices[0].delta.content or "", end="")

  # 方式 3 — 获取原始客户端（仅在需要 SDK 特有功能时使用）
  client = get_llm_client()
  client.chat.completions.create(...)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generator, Iterator

logger = logging.getLogger(__name__)


# ================================================================
# 抽象基类（Provider 契约）
# ================================================================

class BaseLLMProvider(ABC):
    """所有 LLM Provider 必须实现的接口契约。

    子类只需实现 chat_completions_create() 即可接入系统。
    """

    @abstractmethod
    def chat_completions_create(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """发起 chat completion 请求。

        Args:
            messages   : 符合 OpenAI 格式的消息列表 [{"role": ..., "content": ...}]
            model      : 模型名称，None 时使用 Provider 默认模型
            temperature: 采样温度 [0.0, 1.0]
            stream     : 是否启用流式输出
            **kwargs   : Provider 特有的额外参数

        Returns:
            非流式：包含 .choices[0].message.content 的响应对象
            流式  ：可迭代的 chunk 序列，每个 chunk 含 .choices[0].delta.content
        """
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """返回 Provider 的默认模型名称。"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """返回 Provider 标识名，用于日志和错误信息。"""
        ...


# ================================================================
# Provider 实现 — 智谱 ZhipuAI
# ================================================================

class ZhipuProvider(BaseLLMProvider):
    """智谱 GLM Provider（使用 zhipuai SDK）。

    支持 GLM-4-Flash、GLM-4-Air、GLM-4 等系列模型。
    """

    def __init__(self, api_key: str, model_name: str = "glm-4-flash") -> None:
        if not api_key:
            raise ValueError(
                "[ZhipuProvider] ZHIPU_API_KEY 未配置。"
                "请在 .env 文件中设置 ZHIPU_API_KEY=your_key"
            )
        try:
            from zhipuai import ZhipuAI
            self._client = ZhipuAI(api_key=api_key)
        except ImportError as e:
            raise ImportError(
                "[ZhipuProvider] 未安装 zhipuai 包。"
                "请执行：pip install zhipuai"
            ) from e
        self._model_name = model_name
        logger.debug("ZhipuProvider 初始化完成，默认模型：%s", model_name)

    @property
    def default_model(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "zhipu"

    def chat_completions_create(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        return self._client.chat.completions.create(
            model=model or self._model_name,
            messages=messages,
            temperature=temperature,
            stream=stream,
            **kwargs,
        )


# ================================================================
# Provider 实现 — OpenAI 兼容接口（通用）
# ================================================================

class OpenAICompatProvider(BaseLLMProvider):
    """OpenAI Chat API 兼容 Provider（使用 openai SDK）。

    适配所有实现了 OpenAI Chat Completions 接口的服务：
      - DeepSeek          https://api.deepseek.com/v1
      - 通义千问           https://dashscope.aliyuncs.com/compatible-mode/v1
      - Moonshot（Kimi）  https://api.moonshot.cn/v1
      - 硅基流动           https://api.siliconflow.cn/v1
      - 本地 Ollama        http://localhost:11434/v1
      - 任何自部署兼容服务
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "gpt-3.5-turbo",
    ) -> None:
        if not api_key:
            raise ValueError(
                "[OpenAICompatProvider] OPENAI_COMPAT_API_KEY 未配置。"
                "请在 .env 文件中设置 OPENAI_COMPAT_API_KEY=your_key"
            )
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        except ImportError as e:
            raise ImportError(
                "[OpenAICompatProvider] 未安装 openai 包。"
                "请执行：pip install openai"
            ) from e
        self._model_name = model_name
        self._base_url = base_url
        logger.debug(
            "OpenAICompatProvider 初始化完成，base_url=%s，默认模型：%s",
            base_url, model_name,
        )

    @property
    def default_model(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return f"openai_compat({self._base_url})"

    def chat_completions_create(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        return self._client.chat.completions.create(
            model=model or self._model_name,
            messages=messages,
            temperature=temperature,
            stream=stream,
            **kwargs,
        )


# ================================================================
# LLMClient — 统一代理层（供业务代码使用）
# ================================================================

class LLMClient:
    """统一 LLM 客户端代理。

    包装 BaseLLMProvider，对外暴露与 zhipuai SDK 兼容的接口，
    使得原有调用方式（client.chat.completions.create(...)）无需修改。

    同时提供便捷方法 complete() 和 stream() 供新代码使用。
    """

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider
        # 兼容旧的 client.chat.completions.create(...) 调用链
        self.chat = _ChatNamespace(provider)
        # 代理嵌入 API（供 indexer.py 中的 ZhipuEmbeddingFunction 使用）
        # ZhipuProvider：透传原生 SDK 的 embeddings 属性
        # 其他 Provider：使用 OpenAI 兼容 embeddings 接口
        self.embeddings = _EmbeddingsNamespace(provider)

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def default_model(self) -> str:
        return self._provider.default_model

    def complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """便捷方法：非流式调用，直接返回文本内容字符串。

        Args:
            messages   : 消息列表
            model      : 模型名称，None 使用 Provider 默认
            temperature: 采样温度

        Returns:
            str: LLM 生成的文本内容
        """
        resp = self._provider.chat_completions_create(
            messages,
            model=model,
            temperature=temperature,
            stream=False,
            **kwargs,
        )
        return resp.choices[0].message.content

    def stream(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Iterator[str]:
        """便捷方法：流式调用，逐 token yield 字符串。

        Args:
            messages   : 消息列表
            model      : 模型名称
            temperature: 采样温度

        Yields:
            str: 每个 token 片段（可能为空字符串，调用方需过滤）
        """
        chunks = self._provider.chat_completions_create(
            messages,
            model=model,
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        for chunk in chunks:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class _EmbeddingsNamespace:
    """代理 embeddings API，供 ZhipuEmbeddingFunction（indexer.py）使用。

    ZhipuProvider  → 透传到原生 ZhipuAI SDK 的 embeddings.create()
    OpenAICompatProvider → 透传到 openai SDK 的 embeddings.create()
    其他 Provider  → 若未实现则抛出 NotImplementedError，提示接入方式
    """

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    def create(self, model: str, input: Any, **kwargs: Any) -> Any:  # noqa: A002
        """调用嵌入 API，签名与 ZhipuAI / OpenAI SDK 兼容。"""
        if isinstance(self._provider, ZhipuProvider):
            return self._provider._client.embeddings.create(
                model=model, input=input, **kwargs
            )
        if isinstance(self._provider, OpenAICompatProvider):
            return self._provider._client.embeddings.create(
                model=model, input=input, **kwargs
            )
        raise NotImplementedError(
            f"Provider '{self._provider.provider_name}' 尚未实现 embeddings 接口。"
            "请在 core/llm_client.py 的 _EmbeddingsNamespace.create() 中添加支持。"
        )


class _ChatNamespace:
    """模拟 client.chat 命名空间，保持向后兼容。"""

    def __init__(self, provider: BaseLLMProvider) -> None:
        self.completions = _CompletionsNamespace(provider)


class _CompletionsNamespace:
    """模拟 client.chat.completions 命名空间，保持向后兼容。"""

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    def create(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """与 zhipuai/openai SDK 的 client.chat.completions.create() 签名兼容。"""
        return self._provider.chat_completions_create(
            messages,
            model=model,
            temperature=temperature,
            stream=stream,
            **kwargs,
        )


# ================================================================
# 工厂函数（全局单例）
# ================================================================

_llm_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """返回全局单例 LLMClient。

    根据 settings.LLM_PROVIDER 自动选择 Provider：
      - "zhipu"         → ZhipuProvider
      - "openai_compat" → OpenAICompatProvider

    Provider 初始化只发生一次（首次调用时），后续调用直接返回缓存实例。

    Returns:
        LLMClient: 统一 LLM 客户端实例

    Raises:
        ValueError: API Key 未配置时
        ImportError: 所需 SDK 未安装时
        ValueError: LLM_PROVIDER 值无法识别时
    """
    global _llm_client_instance
    if _llm_client_instance is not None:
        return _llm_client_instance

    from core.settings import get_settings
    s = get_settings()

    provider_name = (s.LLM_PROVIDER or "zhipu").strip().lower()

    if provider_name == "zhipu":
        provider: BaseLLMProvider = ZhipuProvider(
            api_key=s.ZHIPU_API_KEY,
            model_name=s.MODEL_NAME,
        )
    elif provider_name == "openai_compat":
        provider = OpenAICompatProvider(
            api_key=s.OPENAI_COMPAT_API_KEY,
            base_url=s.OPENAI_COMPAT_BASE_URL,
            model_name=s.MODEL_NAME,
        )
    else:
        raise ValueError(
            f"未知的 LLM_PROVIDER='{provider_name}'。"
            f"支持的值：'zhipu'、'openai_compat'。"
            f"请检查 .env 文件中的 LLM_PROVIDER 配置。"
        )

    _llm_client_instance = LLMClient(provider)
    logger.info(
        "LLM 客户端初始化完成：provider=%s，model=%s",
        _llm_client_instance.provider_name,
        _llm_client_instance.default_model,
    )
    return _llm_client_instance


def reset_llm_client() -> None:
    """重置全局单例（仅供测试使用）。

    测试中切换 Provider 配置后，调用此函数强制重新初始化。
    """
    global _llm_client_instance
    _llm_client_instance = None


# ================================================================
# 模块级便捷函数（最简调用路径）
# ================================================================

def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> str:
    """模块级便捷函数：非流式 LLM 调用，直接返回文本字符串。

    等价于 get_llm_client().complete(messages, ...)，但更简洁。

    Example:
        from core.llm_client import chat_completion
        answer = chat_completion([{"role": "user", "content": "你好"}])
    """
    return get_llm_client().complete(
        messages, model=model, temperature=temperature, **kwargs
    )


def chat_completion_stream(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> Iterator[str]:
    """模块级便捷函数：流式 LLM 调用，逐 token yield 字符串。

    Example:
        from core.llm_client import chat_completion_stream
        for token in chat_completion_stream([{"role": "user", "content": "讲解进程"}]):
            print(token, end="", flush=True)
    """
    yield from get_llm_client().stream(
        messages, model=model, temperature=temperature, **kwargs
    )
