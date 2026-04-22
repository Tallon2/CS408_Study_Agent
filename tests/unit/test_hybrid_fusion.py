"""
tests/unit/test_hybrid_fusion.py — RRF 混合融合算法单元测试

测试覆盖：
  1. rrf_fusion() 空输入
  2. rrf_fusion() 重叠文档得分更高
  3. rrf_fusion() k 参数平滑效果
  4. rrf_fusion() 集合权重（collection_weights）
  5. rrf_fusion() 去重逻辑（同一列表重复文档）
  6. rrf_fusion() 输出字段完整性（rrf_score / in_vector / in_bm25）
  7. rrf_fusion() 仅单一列表时仍能工作
  8. rrf_fusion() 无 text 字段的文档被跳过
  9. normalize_scores() 正常归一化
  10. normalize_scores() 空列表
  11. normalize_scores() 所有分数相同
  12. normalize_scores() 不存在目标字段
"""
import sys
import os

# 确保项目根目录在 PYTHONPATH（Phase 6 包化后可移除此 hack）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from memory.rag.hybrid_fusion import rrf_fusion, normalize_scores


# ================================================================
# rrf_fusion() 测试
# ================================================================

class TestRrfFusion:
    """RRF 融合算法功能测试。"""

    # ── 设计文档 §9.3 指定用例（原文搬移，必须保留）──────────────

    def test_rrf_fusion_empty_inputs(self):
        """空输入应返回空列表。"""
        result = rrf_fusion(vector_results=[], bm25_results=[], k=60)
        assert result == []

    def test_rrf_fusion_prefers_items_in_both_lists(self):
        """同时出现在两个列表中的文档应得到更高 RRF 分数。"""
        doc_both = {"doc_id": "A", "text": "在两个列表中都出现", "metadata": {}, "score": 0.9}
        doc_vector_only = {"doc_id": "B", "text": "只在向量列表中", "metadata": {}, "score": 0.8}
        doc_bm25_only = {"doc_id": "C", "text": "只在 BM25 列表中", "metadata": {}, "score": 0.7}
        result = rrf_fusion(
            vector_results=[doc_both, doc_vector_only],
            bm25_results=[doc_both, doc_bm25_only],
            k=60,
        )
        # 使用 in_vector + in_bm25 标志定位文档，避免中文切片编码问题
        score_both = next(d["rrf_score"] for d in result if d["in_vector"] and d["in_bm25"])
        score_vector_only = next(d["rrf_score"] for d in result if d["in_vector"] and not d["in_bm25"])
        score_bm25_only = next(d["rrf_score"] for d in result if not d["in_vector"] and d["in_bm25"])
        assert score_both > score_vector_only
        assert score_both > score_bm25_only

    # ── 覆盖测试 ──────────────────────────────────────────────────

    def test_empty_both_inputs_returns_empty(self):
        """双空输入应返回空列表（别名测试，与 test_rrf_fusion_empty_inputs 等价）。"""
        result = rrf_fusion(vector_results=[], bm25_results=[], k=60)
        assert result == []

    def test_empty_vector_results_only_bm25(self, sample_bm25_results):
        """向量结果为空时，只基于 BM25 结果计算 RRF。"""
        result = rrf_fusion(vector_results=[], bm25_results=sample_bm25_results, k=60)
        assert len(result) == len(sample_bm25_results)
        for doc in result:
            assert doc["in_bm25"] is True
            assert doc["in_vector"] is False

    def test_empty_bm25_results_only_vector(self, sample_vector_results):
        """BM25 结果为空时，只基于向量结果计算 RRF。"""
        result = rrf_fusion(vector_results=sample_vector_results, bm25_results=[], k=60)
        assert len(result) == len(sample_vector_results)
        for doc in result:
            assert doc["in_vector"] is True
            assert doc["in_bm25"] is False

    def test_overlapping_document_scores_higher(
        self, sample_vector_results, sample_bm25_results
    ):
        """同时出现在两个列表中的文档 rrf_score 应高于只出现在单一列表中的文档。"""
        result = rrf_fusion(
            vector_results=sample_vector_results,
            bm25_results=sample_bm25_results,
            k=60,
        )
        overlapping = [d for d in result if d["in_vector"] and d["in_bm25"]]
        only_vector = [d for d in result if d["in_vector"] and not d["in_bm25"]]
        only_bm25 = [d for d in result if not d["in_vector"] and d["in_bm25"]]

        assert len(overlapping) >= 1, "应存在至少一个重叠文档"
        if overlapping and (only_vector or only_bm25):
            max_overlap_score = max(d["rrf_score"] for d in overlapping)
            max_single_score = max(
                d["rrf_score"]
                for d in (only_vector + only_bm25)
            )
            assert max_overlap_score > max_single_score, (
                f"重叠文档最高分 {max_overlap_score:.5f} 应大于单一列表最高分 {max_single_score:.5f}"
            )

    def test_output_sorted_by_rrf_score_descending(
        self, sample_vector_results, sample_bm25_results
    ):
        """输出列表应按 rrf_score 降序排列。"""
        result = rrf_fusion(
            vector_results=sample_vector_results,
            bm25_results=sample_bm25_results,
        )
        scores = [d["rrf_score"] for d in result]
        assert scores == sorted(scores, reverse=True), "应按 rrf_score 降序排列"

    def test_output_fields_complete(self, sample_vector_results, sample_bm25_results):
        """每条结果都必须包含 rrf_score、in_vector、in_bm25 字段。"""
        result = rrf_fusion(
            vector_results=sample_vector_results,
            bm25_results=sample_bm25_results,
        )
        for doc in result:
            assert "rrf_score" in doc, "缺少 rrf_score 字段"
            assert "in_vector" in doc, "缺少 in_vector 字段"
            assert "in_bm25" in doc, "缺少 in_bm25 字段"
            assert isinstance(doc["rrf_score"], float)
            assert isinstance(doc["in_vector"], bool)
            assert isinstance(doc["in_bm25"], bool)

    def test_k_parameter_larger_k_smoother_effect(self):
        """k 值越大，排名差异对分数的影响越平滑（头部优势减小）。"""
        doc_rank1 = {"text": "第一名文档", "metadata": {}, "score": 1.0, "collection": "textbooks"}
        doc_rank2 = {"text": "第二名文档", "metadata": {}, "score": 0.5, "collection": "textbooks"}
        docs = [doc_rank1, doc_rank2]

        result_k1 = rrf_fusion(docs, [], k=1)
        result_k100 = rrf_fusion(docs, [], k=100)

        score_diff_k1 = result_k1[0]["rrf_score"] - result_k1[1]["rrf_score"]
        score_diff_k100 = result_k100[0]["rrf_score"] - result_k100[1]["rrf_score"]

        assert score_diff_k1 > score_diff_k100, (
            "k 小时排名差异应更大（头部优势更强），k 大时差异更小（更平滑）"
        )

    def test_collection_weights_applied(self):
        """collection_weights 参数应正确影响最终 RRF 分数。"""
        # 使两个文档只分别出现在各自列表的同一排名（排名 1），以控制变量
        doc_exam = {"text": "真题文档", "metadata": {}, "score": 0.8, "collection": "exam_questions"}
        doc_text = {"text": "教材文档", "metadata": {}, "score": 0.9, "collection": "textbooks"}

        # 不加权：两个文档各自只出现在一个长度为 1 的列表中，排名相同（均为 1）
        # score = 1/(60+1)，应相等
        result_no_weight = rrf_fusion([doc_exam], [doc_text], k=60)
        scores_no_weight = {d["text"]: d["rrf_score"] for d in result_no_weight}
        assert abs(scores_no_weight["真题文档"] - scores_no_weight["教材文档"]) < 1e-9, \
            "不加权时两文档各排第 1 时 RRF 分数应相等"

        # 加权：真题 collection 权重 1.5，应使真题分数更高
        result_weighted = rrf_fusion(
            [doc_exam], [doc_text],
            k=60,
            collection_weights={"exam_questions": 1.5, "textbooks": 1.0},
        )
        scores_weighted = {d["text"]: d["rrf_score"] for d in result_weighted}
        assert scores_weighted["真题文档"] > scores_weighted["教材文档"], (
            "真题加权 1.5 后，真题分数应高于权重 1.0 的教材文档"
        )

    def test_deduplication_same_document_in_same_list(self):
        """同一列表中重复出现的文档，只保留排名最靠前的那次。"""
        doc = {"text": "重复文档内容", "metadata": {}, "score": 0.9, "collection": "textbooks"}
        doc_same = {"text": "重复文档内容", "metadata": {}, "score": 0.5, "collection": "textbooks"}
        other = {"text": "其他不同文档内容", "metadata": {}, "score": 0.6, "collection": "textbooks"}

        # 向量列表中有两个相同文档
        result = rrf_fusion([doc, doc_same, other], [])
        text_counts = {}
        for d in result:
            key = d["text"][:100]
            text_counts[key] = text_counts.get(key, 0) + 1

        for key, count in text_counts.items():
            assert count == 1, f"文档 '{key[:20]}...' 在结果中出现了 {count} 次，应去重为 1 次"

    def test_document_without_text_field_is_skipped(self):
        """不含 text 字段或 text 为空的文档应被跳过。"""
        doc_no_text = {"metadata": {}, "score": 0.9, "collection": "textbooks"}
        doc_empty_text = {"text": "", "metadata": {}, "score": 0.8, "collection": "textbooks"}
        doc_valid = {"text": "正常文档内容", "metadata": {}, "score": 0.7, "collection": "textbooks"}

        result = rrf_fusion([doc_no_text, doc_empty_text, doc_valid], [])
        assert len(result) == 1, f"应只有 1 条有效结果，实际得到 {len(result)}"
        assert result[0]["text"] == "正常文档内容"

    def test_rrf_score_is_positive_for_all_results(
        self, sample_vector_results, sample_bm25_results
    ):
        """所有结果的 rrf_score 应为正数。"""
        result = rrf_fusion(
            vector_results=sample_vector_results,
            bm25_results=sample_bm25_results,
        )
        for doc in result:
            assert doc["rrf_score"] > 0, f"rrf_score 应为正数，实际为 {doc['rrf_score']}"

    def test_total_result_count_with_overlap(
        self, sample_vector_results, sample_bm25_results
    ):
        """
        融合结果数量 = 两列表并集（去重后）的文档总数。
        sample_vector_results 有 5 条，sample_bm25_results 有 4 条，其中 1 条重叠。
        预期融合后结果数 = 5 + 4 - 1 = 8。
        """
        result = rrf_fusion(
            vector_results=sample_vector_results,
            bm25_results=sample_bm25_results,
        )
        assert len(result) == 8, f"预期 8 条融合结果，实际得到 {len(result)} 条"


# ================================================================
# normalize_scores() 测试
# ================================================================

class TestNormalizeScores:
    """分数归一化函数测试。"""

    def test_empty_list_returns_empty(self):
        """空列表应直接返回空列表。"""
        result = normalize_scores([])
        assert result == []

    def test_normal_normalization(self):
        """正常情况：分数应归一化到 [0, 1]。"""
        data = [
            {"text": "doc1", "score": 0.2},
            {"text": "doc2", "score": 0.8},
            {"text": "doc3", "score": 0.5},
        ]
        result = normalize_scores(data, score_field="score")

        scores = {d["text"]: d["score"] for d in result}
        assert scores["doc2"] == pytest.approx(1.0), "最大值应归一化为 1.0"
        assert scores["doc1"] == pytest.approx(0.0), "最小值应归一化为 0.0"
        assert scores["doc3"] == pytest.approx(0.5), "中间值应归一化为 0.5"

    def test_all_same_scores_normalized_to_one(self):
        """所有分数相同时，归一化结果统一为 1.0。"""
        data = [
            {"text": "doc1", "score": 0.5},
            {"text": "doc2", "score": 0.5},
            {"text": "doc3", "score": 0.5},
        ]
        result = normalize_scores(data, score_field="score")
        for doc in result:
            assert doc["score"] == pytest.approx(1.0), "分数相同时应统一归一化为 1.0"

    def test_single_document_normalized_to_one(self):
        """只有一条文档时，归一化结果应为 1.0（max == min）。"""
        data = [{"text": "only doc", "score": 0.7}]
        result = normalize_scores(data, score_field="score")
        assert result[0]["score"] == pytest.approx(1.0)

    def test_missing_score_field_document_unchanged(self):
        """不含目标字段的文档应保持原样（不报错，不被删除）。"""
        data = [
            {"text": "doc1", "score": 0.8},
            {"text": "doc2"},           # 缺少 score 字段
            {"text": "doc3", "score": 0.4},
        ]
        result = normalize_scores(data, score_field="score")

        assert len(result) == 3, "不应删除任何文档"
        assert "score" not in result[1], "缺少字段的文档不应被添加该字段"

    def test_custom_score_field_name(self):
        """使用自定义字段名（如 rrf_score）进行归一化。"""
        data = [
            {"text": "doc1", "rrf_score": 0.030},
            {"text": "doc2", "rrf_score": 0.015},
            {"text": "doc3", "rrf_score": 0.005},
        ]
        result = normalize_scores(data, score_field="rrf_score")

        assert result[0]["rrf_score"] == pytest.approx(1.0)
        assert result[2]["rrf_score"] == pytest.approx(0.0)
        # 中间值：(0.015 - 0.005) / (0.030 - 0.005) = 0.4
        assert result[1]["rrf_score"] == pytest.approx(0.4)

    def test_returns_same_list_reference(self):
        """normalize_scores 应返回同一列表引用（原地修改）。"""
        data = [{"score": 0.5}, {"score": 0.8}]
        result = normalize_scores(data, score_field="score")
        assert result is data, "应返回同一列表对象（原地修改）"

    def test_normalized_scores_in_range_zero_to_one(self, sample_rrf_results):
        """使用标准测试数据集，验证所有归一化后的分数在 [0, 1] 范围内。"""
        import copy
        data = copy.deepcopy(sample_rrf_results)
        result = normalize_scores(data, score_field="rrf_score")
        for doc in result:
            if "rrf_score" in doc:
                assert 0.0 <= doc["rrf_score"] <= 1.0, (
                    f"归一化后分数 {doc['rrf_score']} 超出 [0,1] 范围"
                )
