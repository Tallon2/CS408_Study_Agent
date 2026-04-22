"""
settings.py — 应用配置中心（Pydantic Settings）

所有配置项通过环境变量或 .env 文件注入，
带类型校验和默认值。

使用方式：
    from core.settings import get_settings
    settings = get_settings()
    print(settings.ZHIPU_API_KEY)

LLM Provider 切换示例（.env 文件）：
    # 使用智谱（默认）
    LLM_PROVIDER=zhipu
    ZHIPU_API_KEY=your_key

    # 使用 DeepSeek
    LLM_PROVIDER=openai_compat
    OPENAI_COMPAT_API_KEY=your_deepseek_key
    OPENAI_COMPAT_BASE_URL=https://api.deepseek.com/v1
    MODEL_NAME=deepseek-chat

    # 使用通义千问（DashScope OpenAI 兼容接口）
    LLM_PROVIDER=openai_compat
    OPENAI_COMPAT_API_KEY=your_dashscope_key
    OPENAI_COMPAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    MODEL_NAME=qwen-turbo

    # 使用本地 Ollama
    LLM_PROVIDER=openai_compat
    OPENAI_COMPAT_API_KEY=ollama
    OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1
    MODEL_NAME=llama3
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM Provider 选择 ──────────────────────────────────────
    # 可选值：
    #   "zhipu"         — 智谱 GLM（使用 zhipuai SDK）
    #   "openai_compat" — 任意兼容 OpenAI Chat API 的服务
    #                     （DeepSeek / 通义千问 / Moonshot / Ollama 等）
    LLM_PROVIDER: str = "zhipu"

    # ── 智谱 Provider 配置 ────────────────────────────────────
    ZHIPU_API_KEY: str = ""
    MODEL_NAME: str = "glm-4-flash"
    EMBEDDING_MODEL: str = "embedding-3"

    # ── OpenAI 兼容 Provider 配置 ─────────────────────────────
    # 适用于 DeepSeek、通义千问、Moonshot、Ollama 等任意兼容接口
    OPENAI_COMPAT_API_KEY: str = ""
    OPENAI_COMPAT_BASE_URL: str = "https://api.openai.com/v1"

    # ── Reranker 配置 ──────────────────────────────────────────
    JINA_API_KEY: str = ""
    SILICONFLOW_API_KEY: str = ""
    USE_RERANKER_API: bool = True

    # ── 数据库 ────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./storage/study_agent.db"

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    # ── JWT 认证 ──────────────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 小时

    # ── 服务配置 ──────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # ── 存储路径 ──────────────────────────────────────────────
    STORAGE_DIR: str = "storage"
    CHROMA_DIR: str = "storage/chroma_db"
    BM25_INDEX_DIR: str = "storage/bm25_index"
    KNOWLEDGE_UPLOAD_DIR: str = "storage/knowledge"

    # ── RAG 管线配置 ──────────────────────────────────────────
    RAG_VECTOR_N_TEXTBOOKS: int = 5
    RAG_VECTOR_N_EXAM: int = 5
    RAG_VECTOR_N_KEYPOINTS: int = 3
    RAG_BM25_N_RESULTS: int = 5
    RAG_RRF_K: int = 60
    RAG_GATE_MODE: str = "normal"  # strict / normal / loose
    RAG_TOP_K_FINAL: int = 5

    @property
    def active_api_key(self) -> str:
        """返回当前 Provider 对应的 API Key，供向后兼容层使用。"""
        if self.LLM_PROVIDER == "zhipu":
            return self.ZHIPU_API_KEY
        return self.OPENAI_COMPAT_API_KEY


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一的 Settings 实例（首次调用后缓存）"""
    return Settings()
