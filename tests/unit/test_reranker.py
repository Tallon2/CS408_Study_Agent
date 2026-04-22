"""
tests/unit/test_reranker.py — Reranker 降级链单元测试

测试覆盖（P1 优先级）：
  1. rerank() — API 失败时降级到 LLM Rerank（§9.3 设计文档示例）
  2. rerank() — LLM 也失败时返回原序兜底
  3. rerank() — top_k 限制输出数量
  4. rerank() — 有 API key 时优先使用外部 API
  5. rerank() — 空候选列表直接返回空
  6. _api_rerank() — 无 API key 时返回 None
  7. _llm_rerank() — LLM 异常时返回原候选列表
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from unittest.mock import patch, MagicMock

from memory.rag.reranker import rerank, _api_rerank, _llm_rerank


# ================================================================
# rerank() 降级链测试
# ================================================================

class TestRerank:
    """rerank() 三级降级精排入口测试。"""

    def test_rerank_falls_back_to_llm_when_api_fails(self):
        """当外部 Reranker API 失败时，应降级到 LLM Rerank。"""
        candidates = [
            {"doc_id": "A", "text": "文档 A", "metadata": {}},
            {"doc_id": "B", "text": "文档 B", "metadata": {}},
        ]
        # Mock settings: USE_RERANKER_API=True，但 _api_rerank 返回 None（失败）
        mock_settings = MagicMock()
        mock_settings.USE_RERANKER_API = True
        mock_settings.JINA_API_KEY = "fake-key"
        mock_settings.SILICONFLOW_API_KEY = ""

        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("memory.rag.reranker._api_rerank", return_value=None):
                with patch("memory.rag.reranker._llm_rerank") as mock_llm:
                    mock_llm.return_value = candidates[::-1]
                    result, method = rerank("测试查询", candidates, top_k=2)
                    mock_llm.assert_called_once()
                    assert result[0]["doc_id"] == "B"

    def test_rerank_returns_original_when_llm_fails(self):
        """API 和 LLM 均失败时，应返回原始候选列表（原序兜底）。"""
        candidates = [
            {"doc_id": "A", "text": "文档 A", "metadata": {}},
            {"doc_id": "B", "text": "文档 B", "metadata": {}},
        ]
        mock_settings = MagicMock()
        mock_settings.USE_RERANKER_API = True
        mock_settings.JINA_API_KEY = "fake-key"
        mock_settings.SILICONFLOW_API_KEY = ""

        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("memory.rag.reranker._api_rerank", return_value=None):
                # _llm_rerank 内部异常，返回原列表
                with patch("memory.rag.reranker._llm_rerank", return_value=candidates):
                    result, method = rerank("查询", candidates, top_k=2)
        assert len(result) == 2
        assert result[0]["doc_id"] == "A"  # 原序

    def test_rerank_respects_top_k(self):
        """rerank 返回的结果数应不超过 top_k。"""
        candidates = [
            {"doc_id": str(i), "text": f"文档{i}", "metadata": {}}
            for i in range(10)
        ]
        mock_settings = MagicMock()
        mock_settings.USE_RERANKER_API = False  # 直接走 LLM

        # _llm_rerank 返回按 rerank_score 降序的所有候选
        scored = [{**c, "rerank_score": 10 - int(c["doc_id"])} for c in candidates]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)

        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("memory.rag.reranker._llm_rerank", return_value=scored[:3]):
                result, method = rerank("查询", candidates, top_k=3)
        # rerank() 的截断语义：_llm_rerank 已按 top_k 截断返回，rerank() 原样传递
        assert len(result) == 3
        assert result[0]["doc_id"] == "0"  # rerank_score 最高（10-0=10）

    def test_rerank_uses_api_when_key_available(self):
        """配置了 API key 且 USE_RERANKER_API=True 时，应优先使用外部 API。"""
        candidates = [
            {"doc_id": "X", "text": "文档 X", "metadata": {}},
        ]
        api_result = [{**candidates[0], "rerank_score": 0.9}]

        mock_settings = MagicMock()
        mock_settings.USE_RERANKER_API = True
        mock_settings.JINA_API_KEY = "jina-fake-key"
        mock_settings.SILICONFLOW_API_KEY = ""

        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("memory.rag.reranker._api_rerank", return_value=api_result) as mock_api:
                result, method = rerank("查询", candidates, top_k=1)
                mock_api.assert_called_once()
        assert result[0]["doc_id"] == "X"

    def test_rerank_empty_candidates(self):
        """空候选列表应直接返回 ([], 'none')，不调用任何精排逻辑。"""
        result, method = rerank("查询", [], top_k=5)
        assert result == []
        assert method == "none"

    def test_rerank_skip_api_when_disabled(self):
        """USE_RERANKER_API=False 时，应跳过 _api_rerank 直接走 LLM。"""
        candidates = [{"doc_id": "A", "text": "文档 A", "metadata": {}}]
        mock_settings = MagicMock()
        mock_settings.USE_RERANKER_API = False

        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("memory.rag.reranker._api_rerank") as mock_api:
                with patch("memory.rag.reranker._llm_rerank", return_value=candidates):
                    result, method = rerank("查询", candidates, top_k=1)
                    mock_api.assert_not_called()
        assert method == "llm_rerank"


# ================================================================
# _api_rerank() 测试
# ================================================================

class TestApiRerank:
    """_api_rerank() 外部 API 调用测试。"""

    def test_api_rerank_returns_none_when_no_keys(self):
        """无 Jina 和 SiliconFlow API key 时，应返回 None（不发请求）。"""
        mock_settings = MagicMock()
        mock_settings.JINA_API_KEY = ""
        mock_settings.SILICONFLOW_API_KEY = ""

        candidates = [{"doc_id": "A", "text": "文档 A", "metadata": {}}]
        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            result = _api_rerank("查询", candidates, top_k=1)
        assert result is None

    def test_api_rerank_returns_none_on_http_error(self):
        """HTTP 请求失败时应返回 None，触发降级。"""
        import httpx
        mock_settings = MagicMock()
        mock_settings.JINA_API_KEY = "fake-jina-key"
        mock_settings.SILICONFLOW_API_KEY = ""

        candidates = [{"doc_id": "A", "text": "文档 A", "metadata": {}}]
        with patch("memory.rag.reranker.get_settings", return_value=mock_settings):
            with patch("httpx.post", side_effect=httpx.RequestError("连接失败", request=MagicMock())):
                result = _api_rerank("查询", candidates, top_k=1)
        assert result is None


# ================================================================
# _llm_rerank() 测试
# ================================================================

class TestLlmRerank:
    """_llm_rerank() LLM 语义精排测试。"""

    def test_llm_rerank_returns_original_on_exception(self):
        """LLM 调用异常时应返回原始候选列表（降级兜底）。"""
        candidates = [
            {"doc_id": "A", "text": "文档 A", "metadata": {}},
            {"doc_id": "B", "text": "文档 B", "metadata": {}},
        ]
        with patch("memory.rag.reranker.get_llm_client", side_effect=Exception("API 不可用")):
            result = _llm_rerank("查询", candidates, top_k=2)
        # 异常时返回原始候选（原序兜底）
        assert result is candidates  # 同一对象引用

    def test_llm_rerank_empty_candidates(self):
        """空候选列表时应直接返回空列表。"""
        result = _llm_rerank("查询", [], top_k=5)
        assert result == []

    def test_llm_rerank_reorders_by_score(self):
        """LLM 返回有效评分时，应按分数降序重排候选文档。"""
        candidates = [
            {"doc_id": "A", "text": "文档 A", "metadata": {}},
            {"doc_id": "B", "text": "文档 B", "metadata": {}},
            {"doc_id": "C", "text": "文档 C", "metadata": {}},
        ]
        # LLM 返回 B 最高分
        mock_response_content = '[{"index": 0, "score": 3}, {"index": 1, "score": 9}, {"index": 2, "score": 5}]'
        mock_client = MagicMock()
        mock_client.default_model = "glm-4-flash"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_response_content))]
        )
        with patch("memory.rag.reranker.get_llm_client", return_value=mock_client):
            result = _llm_rerank("查询", candidates, top_k=3)
        assert result[0]["doc_id"] == "B"  # 最高分 9
        assert result[1]["doc_id"] == "C"  # 次高分 5
        assert result[2]["doc_id"] == "A"  # 最低分 3
