"""
tests/integration/test_rag_pipeline.py — RAG 管线集成测试

测试覆盖（P2 优先级，mock ChromaDB）：
  1. retrieve() — 返回字符串
  2. retrieve_with_trace() — 返回含 context/trace 的 dict
  3. retrieve() — 知识库为空时返回空字符串而非崩溃
  4. _format_results() — 格式化输出包含参考资料标签
  5. _deduplicate() — 去重逻辑正确

所有测试均 mock ChromaDB 和 BM25，无需真实数据库。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.integration


# ================================================================
# 工具函数测试（无需 mock 数据库）
# ================================================================

class TestFormatResults:
    """_format_results() 格式化函数测试。"""

    def test_format_results_empty_list(self):
        """空列表应返回空字符串。"""
        from memory.rag.retriever_rag import _format_results
        result = _format_results([])
        assert result == ""

    def test_format_results_contains_reference_label(self):
        """格式化结果应包含【参考资料X】标签。"""
        from memory.rag.retriever_rag import _format_results
        docs = [
            {"text": "进程是程序的一次执行过程。", "metadata": {"source": "os.pdf", "subject": "操作系统"}},
        ]
        result = _format_results(docs)
        assert "【参考资料1】" in result
        assert "进程是程序的一次执行过程" in result

    def test_format_results_multiple_docs_numbered(self):
        """多条文档应按序编号。"""
        from memory.rag.retriever_rag import _format_results
        docs = [
            {"text": "第一篇文档。", "metadata": {}},
            {"text": "第二篇文档。", "metadata": {}},
            {"text": "第三篇文档。", "metadata": {}},
        ]
        result = _format_results(docs)
        assert "【参考资料1】" in result
        assert "【参考资料2】" in result
        assert "【参考资料3】" in result


class TestDeduplicate:
    """_deduplicate() 去重函数测试。"""

    def test_deduplicate_removes_duplicates(self):
        """应去除文本前100字符相同的重复文档。"""
        from memory.rag.retriever_rag import _deduplicate
        text = "这是一段重复文档的内容，前100字符相同。" * 2
        docs = [
            {"text": text, "metadata": {"source": "a.pdf"}},
            {"text": text, "metadata": {"source": "b.pdf"}},  # 重复
            {"text": "完全不同的文档内容。", "metadata": {}},
        ]
        result = _deduplicate(docs)
        assert len(result) == 2  # 去重后只有 2 条

    def test_deduplicate_preserves_order(self):
        """去重后应保留首次出现顺序。"""
        from memory.rag.retriever_rag import _deduplicate
        docs = [
            {"text": "文档A", "metadata": {"source": "a.pdf"}},
            {"text": "文档B", "metadata": {"source": "b.pdf"}},
            {"text": "文档A", "metadata": {"source": "c.pdf"}},  # 重复
        ]
        result = _deduplicate(docs)
        assert result[0]["metadata"]["source"] == "a.pdf"  # 保留首次出现
        assert len(result) == 2


# ================================================================
# retrieve() / retrieve_with_trace() 管线集成测试
# ================================================================

class TestRetrievePipeline:
    """RAG 管线集成测试（mock ChromaDB + BM25 + LLM）。"""

    def _make_mock_collection(self, docs: list[dict]):
        """构建模拟 ChromaDB 集合查询结果。"""
        mock_col = MagicMock()
        mock_col.query.return_value = {
            "documents": [[d["text"] for d in docs]],
            "metadatas": [[d.get("metadata", {}) for d in docs]],
            "distances": [[d.get("distance", 0.5) for d in docs]],
        }
        return mock_col

    def test_retrieve_returns_string(self):
        """retrieve() 应始终返回字符串。"""
        from memory.rag.retriever_rag import retrieve

        mock_chroma = MagicMock()
        mock_col = self._make_mock_collection([
            {"text": "进程管理内容", "metadata": {"source": "os.pdf"}, "distance": 0.3},
        ])
        mock_chroma.get_collection.return_value = mock_col

        mock_settings = MagicMock()
        mock_settings.RAG_VECTOR_N_TEXTBOOKS = 3
        mock_settings.RAG_VECTOR_N_EXAM = 3
        mock_settings.RAG_VECTOR_N_KEYPOINTS = 2
        mock_settings.RAG_BM25_N_RESULTS = 3
        mock_settings.RAG_RRF_K = 60
        mock_settings.RAG_GATE_MODE = "normal"
        mock_settings.RAG_TOP_K_FINAL = 3
        mock_settings.USE_RERANKER_API = False

        with patch("memory.rag.retriever_rag.get_chroma_client", return_value=mock_chroma), \
             patch("memory.rag.retriever_rag.get_settings", return_value=mock_settings), \
             patch("memory.rag.retriever_rag.get_bm25_retriever", side_effect=Exception("BM25 未初始化")), \
             patch("memory.rag.retriever_rag._rerank", return_value=([], "none")), \
             patch("memory.rag.retriever_rag.auto_merge_context", side_effect=lambda x: x):
            result = retrieve("进程调度算法")
        assert isinstance(result, str)

    def test_retrieve_handles_empty_db(self):
        """知识库为空时应返回空字符串而非崩溃。"""
        from memory.rag.retriever_rag import retrieve

        mock_chroma = MagicMock()
        # 所有集合查询均返回空
        mock_col = self._make_mock_collection([])
        mock_chroma.get_collection.return_value = mock_col

        mock_settings = MagicMock()
        mock_settings.RAG_VECTOR_N_TEXTBOOKS = 3
        mock_settings.RAG_VECTOR_N_EXAM = 3
        mock_settings.RAG_VECTOR_N_KEYPOINTS = 2
        mock_settings.RAG_BM25_N_RESULTS = 3
        mock_settings.RAG_RRF_K = 60
        mock_settings.RAG_GATE_MODE = "normal"
        mock_settings.RAG_TOP_K_FINAL = 3
        mock_settings.USE_RERANKER_API = False

        with patch("memory.rag.retriever_rag.get_chroma_client", return_value=mock_chroma), \
             patch("memory.rag.retriever_rag.get_settings", return_value=mock_settings), \
             patch("memory.rag.retriever_rag.get_bm25_retriever", side_effect=Exception("BM25 未初始化")), \
             patch("memory.rag.retriever_rag.auto_merge_context", side_effect=lambda x: x):
            result = retrieve("不存在的知识点")
        assert isinstance(result, str)
        assert result == ""  # 空知识库返回空字符串

    def test_retrieve_with_trace_returns_dict(self):
        """retrieve_with_trace() 应返回含 context 和 trace 键的字典。"""
        from memory.rag.retriever_rag import retrieve_with_trace

        mock_chroma = MagicMock()
        mock_col = self._make_mock_collection([])
        mock_chroma.get_collection.return_value = mock_col

        mock_settings = MagicMock()
        mock_settings.RAG_VECTOR_N_TEXTBOOKS = 3
        mock_settings.RAG_VECTOR_N_EXAM = 3
        mock_settings.RAG_VECTOR_N_KEYPOINTS = 2
        mock_settings.RAG_BM25_N_RESULTS = 3
        mock_settings.RAG_RRF_K = 60
        mock_settings.RAG_GATE_MODE = "normal"
        mock_settings.RAG_TOP_K_FINAL = 3
        mock_settings.USE_RERANKER_API = False

        with patch("memory.rag.retriever_rag.get_chroma_client", return_value=mock_chroma), \
             patch("memory.rag.retriever_rag.get_settings", return_value=mock_settings), \
             patch("memory.rag.retriever_rag.get_bm25_retriever", side_effect=Exception("BM25 未初始化")), \
             patch("memory.rag.retriever_rag.auto_merge_context", side_effect=lambda x: x):
            result = retrieve_with_trace("进程调度")
        assert isinstance(result, dict)
        assert "context" in result
        assert "trace" in result
        assert isinstance(result["context"], str)
        assert isinstance(result["trace"], list)
