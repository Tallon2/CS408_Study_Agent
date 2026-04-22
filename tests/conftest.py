"""
tests/conftest.py — pytest 全局 fixtures

提供以下 fixtures：
  - set_test_env      : (autouse) 设置测试环境变量，避免配置报错
  - mock_llm_client   : 模拟 ZhipuAI 客户端，避免真实 API 调用
  - in_memory_db      : 内存 SQLite Session，用于 DAO 层测试
  - chroma_ephemeral  : ChromaDB 内存实例，用于 RAG 管线测试
  - sample_rag_docs   : 标准 RAG 测试文档列表
  - sample_vector_results / sample_bm25_results : 标准测试数据集
"""
import os
import pytest
from unittest.mock import MagicMock


# ================================================================
# 环境变量自动设置（避免配置报错）
# ================================================================

@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    """自动为每个测试设置必要的环境变量，防止配置校验报错。"""
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    monkeypatch.setenv("JINA_API_KEY", "")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "")


# ================================================================
# LLM Mock Fixture
# ================================================================

@pytest.fixture
def mock_llm_client():
    """
    提供 mock ZhipuAI 客户端，避免真实 API 调用。

    使用方式：
        def test_something(mock_llm_client):
            with patch("core.llm_client.get_llm_client", return_value=mock_llm_client):
                result = some_function_that_uses_llm()
    """
    mock_client = MagicMock()
    # 模拟同步 completions.create
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="mock 回复内容"))]
    )
    # 模拟流式 completions.create（返回可迭代 chunks）
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock(delta=MagicMock(content="mock token"))]
    mock_client.chat.completions.create.return_value.__iter__ = MagicMock(
        return_value=iter([mock_chunk])
    )
    return mock_client


# ================================================================
# 数据库 Fixture
# ================================================================

@pytest.fixture
def in_memory_db():
    """
    提供内存 SQLite 数据库 Session，用于 DAO 层测试。
    每个测试函数独立创建/销毁，互不干扰。

    使用方式：
        def test_crud(in_memory_db):
            user = create_user(in_memory_db, username="test_user", ...)
            assert user.id is not None
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from dao.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ================================================================
# ChromaDB Fixture
# ================================================================

@pytest.fixture
def chroma_ephemeral():
    """
    提供 ChromaDB 内存实例，用于 RAG 管线集成测试。
    每次测试结束后自动清理，不污染磁盘上的 storage/chroma_db/。

    使用方式：
        def test_indexer(chroma_ephemeral):
            collection = chroma_ephemeral.create_collection("test_col")
            collection.add(documents=["..."], ids=["1"])
    """
    import chromadb
    client = chromadb.EphemeralClient()
    yield client
    # EphemeralClient 内存实例，退出后自动释放


# ================================================================
# 公共测试数据集 Fixtures
# ================================================================

@pytest.fixture
def sample_vector_results():
    """标准向量检索测试数据集（5 条文档，含 collection 字段）。"""
    return [
        {
            "text": "操作系统是管理计算机硬件与软件资源的系统软件，负责进程管理、内存管理、文件系统等核心功能。",
            "metadata": {"source": "os_textbook.pdf", "page": 1, "subject": "操作系统"},
            "score": 0.95,
            "collection": "textbooks",
        },
        {
            "text": "进程是程序的一次执行过程，是系统进行资源分配和调度的基本单位，具有独立性、并发性、动态性。",
            "metadata": {"source": "os_textbook.pdf", "page": 12, "subject": "操作系统"},
            "score": 0.88,
            "collection": "textbooks",
        },
        {
            "text": "页式存储管理将主存划分为固定大小的页框，将程序划分为同等大小的页，可以减少外部碎片。",
            "metadata": {"source": "os_textbook.pdf", "page": 35, "subject": "操作系统"},
            "score": 0.72,
            "collection": "textbooks",
        },
        {
            "text": "2023年真题：以下关于进程与线程的说法，正确的是（）A.进程是资源分配基本单位 B.线程拥有独立地址空间",
            "metadata": {"source": "2023_exam.pdf", "year": 2023, "subject": "操作系统"},
            "score": 0.65,
            "collection": "exam_questions",
        },
        {
            "text": "死锁的四个必要条件：互斥条件、请求与保持、不可剥夺、循环等待。破坏任一条件可预防死锁。",
            "metadata": {"source": "key_points.md", "topic": "死锁", "subject": "操作系统"},
            "score": 0.58,
            "collection": "key_points",
        },
    ]


@pytest.fixture
def sample_bm25_results():
    """标准 BM25 检索测试数据集（4 条文档，与向量结果部分重叠）。"""
    return [
        {
            # 与 sample_vector_results[1] 相同文档（重叠）
            "text": "进程是程序的一次执行过程，是系统进行资源分配和调度的基本单位，具有独立性、并发性、动态性。",
            "metadata": {"source": "os_textbook.pdf", "page": 12, "subject": "操作系统"},
            "score": 1.0,
            "collection": "textbooks",
        },
        {
            "text": "死锁是指多个进程相互等待对方释放资源而造成的僵局，破坏占有且等待条件可以有效预防死锁。",
            "metadata": {"source": "os_textbook.pdf", "page": 50, "subject": "操作系统"},
            "score": 0.80,
            "collection": "textbooks",
        },
        {
            "text": "文件系统负责管理磁盘上的文件和目录结构，为用户提供统一、便捷的文件访问接口。",
            "metadata": {"source": "os_textbook.pdf", "page": 78, "subject": "操作系统"},
            "score": 0.65,
            "collection": "textbooks",
        },
        {
            "text": "虚拟内存技术允许程序使用比物理内存更大的地址空间，通过页面置换算法管理内存。",
            "metadata": {"source": "os_textbook.pdf", "page": 42, "subject": "操作系统"},
            "score": 0.50,
            "collection": "textbooks",
        },
    ]


@pytest.fixture
def sample_rrf_results():
    """标准 RRF 融合测试数据集（已含 rrf_score 字段，按降序排列）。"""
    return [
        {"text": "进程管理核心概念", "rrf_score": 0.0328, "score": 0.95, "collection": "textbooks"},
        {"text": "操作系统内存管理", "rrf_score": 0.0164, "score": 0.88, "collection": "textbooks"},
        {"text": "页式存储管理",     "rrf_score": 0.0160, "score": 0.85, "collection": "textbooks"},
        {"text": "文件系统目录结构", "rrf_score": 0.0082, "score": 0.72, "collection": "textbooks"},
        {"text": "磁盘调度算法",     "rrf_score": 0.0030, "score": 0.45, "collection": "textbooks"},
    ]


@pytest.fixture
def sample_rag_docs():
    """标准 RAG 测试文档列表（3-5 条，含 rrf_score 字段，用于门控/重排等测试）。"""
    return [
        {
            "doc_id": "A",
            "text": "进程是程序的一次执行过程，是系统进行资源分配和调度的基本单位。",
            "metadata": {"source": "os_textbook.pdf", "subject": "操作系统"},
            "score": 0.90,
            "rrf_score": 0.025,
            "collection": "textbooks",
        },
        {
            "doc_id": "B",
            "text": "死锁的四个必要条件：互斥、请求与保持、不可剥夺、循环等待。",
            "metadata": {"source": "os_textbook.pdf", "subject": "操作系统"},
            "score": 0.80,
            "rrf_score": 0.018,
            "collection": "textbooks",
        },
        {
            "doc_id": "C",
            "text": "页式存储管理将主存划分为固定大小的页框，减少外部碎片。",
            "metadata": {"source": "os_textbook.pdf", "subject": "操作系统"},
            "score": 0.70,
            "rrf_score": 0.012,
            "collection": "textbooks",
        },
        {
            "doc_id": "D",
            "text": "2022年真题：以下关于内存管理的说法正确的是？",
            "metadata": {"source": "2022_exam.pdf", "year": 2022, "subject": "操作系统"},
            "score": 0.65,
            "rrf_score": 0.010,
            "collection": "exam_questions",
        },
    ]
