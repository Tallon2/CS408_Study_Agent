"""
tests/unit/test_score_gate.py — 检索质量门控单元测试

测试覆盖：
  1. check() 空列表返回 False
  2. check() 分数达标返回 True
  3. check() 分数不达标返回 False
  4. check() 返回值三元组格式正确
  5. check() 不同模式阈值（strict/normal/loose）
  6. apply_gate() 空列表返回空列表
  7. apply_gate() 正常过滤低质量文档
  8. apply_gate() top-3 保底机制
  9. apply_gate() 噪声地板绝对过滤
  10. apply_gate() 返回结果不包含噪声文档
  11. check_by_mode() 模式名称映射正确
  12. apply_gate_by_mode() 模式名称映射正确
  13. get_score_gate() 单例行为
  14. GATE_THRESHOLDS 字典完整性
"""
import sys
import os

# 确保项目根目录在 PYTHONPATH（Phase 6 包化后可移除此 hack）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from memory.rag.score_gate import ScoreGate, GATE_THRESHOLDS, get_score_gate, _NOISE_FLOOR


# ================================================================
# ScoreGate.check() 测试
# ================================================================

class TestScoreGateCheck:
    """ScoreGate.check() 整体质量检查测试。"""

    def setup_method(self):
        """每个测试方法前创建新的 ScoreGate 实例。"""
        self.gate = ScoreGate()

    def test_check_empty_results_returns_false(self):
        """空结果列表应返回 False。"""
        passed, best_score, reason = self.gate.check([])
        assert passed is False
        assert best_score == 0.0
        assert isinstance(reason, str) and len(reason) > 0

    def test_check_high_quality_results_returns_true(self, sample_rrf_results):
        """高质量结果（rrf_score 超过默认阈值）应通过检查。"""
        # sample_rrf_results 最高分 0.0328 > normal 阈值 0.010
        passed, best_score, reason = self.gate.check(
            sample_rrf_results,
            threshold=GATE_THRESHOLDS["normal"]
        )
        assert passed is True
        assert best_score == pytest.approx(0.0328)

    def test_check_low_quality_results_returns_false(self):
        """低质量结果（rrf_score 低于阈值）应不通过检查。"""
        low_quality = [
            {"text": "低质量文档 A", "rrf_score": 0.002},
            {"text": "低质量文档 B", "rrf_score": 0.001},
        ]
        passed, best_score, reason = self.gate.check(
            low_quality,
            threshold=GATE_THRESHOLDS["normal"]
        )
        assert passed is False
        assert best_score == pytest.approx(0.002)

    def test_check_return_tuple_format(self, sample_rrf_results):
        """返回值应为 (bool, float, str) 三元组。"""
        result = self.gate.check(sample_rrf_results)
        assert isinstance(result, tuple)
        assert len(result) == 3
        passed, best_score, reason = result
        assert isinstance(passed, bool)
        assert isinstance(best_score, float)
        assert isinstance(reason, str)

    def test_check_strict_mode_harder_to_pass(self, sample_rrf_results):
        """strict 模式阈值更高，更难通过。"""
        passed_normal, _, _ = self.gate.check(
            sample_rrf_results, threshold=GATE_THRESHOLDS["normal"]
        )
        passed_strict, _, _ = self.gate.check(
            sample_rrf_results, threshold=GATE_THRESHOLDS["strict"]
        )
        # strict 通过时 normal 必然也通过
        if passed_strict:
            assert passed_normal is True

    def test_check_loose_mode_easier_to_pass(self):
        """loose 模式阈值更低，更容易通过。"""
        # 构造仅勉强通过 loose 但无法通过 normal 的数据
        borderline = [
            {"text": "边缘质量文档", "rrf_score": 0.007},  # > loose(0.006), < normal(0.010)
        ]
        passed_loose, _, _ = self.gate.check(
            borderline, threshold=GATE_THRESHOLDS["loose"]
        )
        passed_normal, _, _ = self.gate.check(
            borderline, threshold=GATE_THRESHOLDS["normal"]
        )
        assert passed_loose is True
        assert passed_normal is False

    def test_check_exact_threshold_value_passes(self):
        """分数恰好等于阈值时应通过（>= 判断）。"""
        threshold = GATE_THRESHOLDS["normal"]
        results = [{"text": "恰好达标", "rrf_score": threshold}]
        passed, _, _ = self.gate.check(results, threshold=threshold)
        assert passed is True

    def test_check_just_below_threshold_fails(self):
        """分数略低于阈值时应不通过。"""
        threshold = GATE_THRESHOLDS["normal"]
        results = [{"text": "略低于阈值", "rrf_score": threshold - 0.001}]
        passed, _, _ = self.gate.check(results, threshold=threshold)
        assert passed is False

    def test_check_reason_contains_score_info(self, sample_rrf_results):
        """返回的 reason 字符串应包含分数信息。"""
        _, best_score, reason = self.gate.check(sample_rrf_results)
        # reason 中应包含数字（分数值的一部分）
        assert any(char.isdigit() for char in reason), "reason 中应包含分数信息"


# ================================================================
# ScoreGate.apply_gate() 测试
# ================================================================

class TestScoreGateApplyGate:
    """ScoreGate.apply_gate() 细粒度过滤测试。"""

    def setup_method(self):
        self.gate = ScoreGate()

    def test_apply_gate_empty_returns_empty(self):
        """空列表应直接返回空列表。"""
        result = self.gate.apply_gate([])
        assert result == []

    def test_apply_gate_filters_low_quality_tail(self):
        """应过滤掉低质量尾部文档（低于动态下界）。"""
        results = [
            {"text": "高质量文档", "rrf_score": 0.030},
            {"text": "中等质量文档", "rrf_score": 0.020},
            {"text": "低质量文档", "rrf_score": 0.004},   # 低于 noise floor (0.005)
        ]
        filtered = self.gate.apply_gate(results, threshold=0.02)
        # 0.004 < noise floor (0.005)，应被过滤
        filtered_scores = [d["rrf_score"] for d in filtered]
        assert 0.004 not in filtered_scores, "噪声文档（< noise floor）应被过滤"

    def test_apply_gate_top3_fallback(self):
        """
        过滤后结果不足 3 条时，应触发 top-3 保底机制，
        回退为非噪声文档的前 3 条。
        """
        results = [
            {"text": "高质量文档",   "rrf_score": 0.033},
            {"text": "中等文档A",    "rrf_score": 0.008},
            {"text": "中等文档B",    "rrf_score": 0.007},
            {"text": "低质量文档",   "rrf_score": 0.006},
        ]
        # threshold=0.02，动态下界 = max(0.02*0.5, 0.005) = 0.01
        # rrf_score < 0.01 的文档会被动态过滤（0.008, 0.007, 0.006 均被过滤）
        # 过滤后只剩 1 条，触发 top-3 保底
        filtered = self.gate.apply_gate(results, threshold=0.02)
        assert len(filtered) >= 3, (
            f"top-3 保底机制应确保至少返回 3 条，实际返回 {len(filtered)} 条"
        )

    def test_apply_gate_noise_floor_absolute_filter(self):
        """rrf_score 低于 _NOISE_FLOOR 的文档无论如何不应出现在结果中。"""
        results = [
            {"text": "正常文档",  "rrf_score": 0.030},
            {"text": "噪声文档A", "rrf_score": _NOISE_FLOOR - 0.001},  # 低于噪声地板
            {"text": "噪声文档B", "rrf_score": 0.001},                   # 明显低于噪声地板
        ]
        filtered = self.gate.apply_gate(results, threshold=0.02)
        for doc in filtered:
            assert doc["rrf_score"] >= _NOISE_FLOOR, (
                f"结果中不应包含 rrf_score < {_NOISE_FLOOR} 的噪声文档，"
                f"实际发现 rrf_score={doc['rrf_score']}"
            )

    def test_apply_gate_all_noise_returns_empty(self):
        """所有文档都低于噪声地板时，应返回空列表（不额外补充噪声）。"""
        all_noise = [
            {"text": "噪声文档A", "rrf_score": 0.002},
            {"text": "噪声文档B", "rrf_score": 0.003},
        ]
        filtered = self.gate.apply_gate(all_noise, threshold=0.02)
        # 按规则：所有文档均为噪声，过滤后为空，top-3 回退到非噪声文档（仍为空）
        assert len(filtered) == 0, "全是噪声时应返回空列表"

    def test_apply_gate_returns_at_most_all_non_noise(self, sample_rrf_results):
        """过滤后的结果数不应超过原始非噪声文档数。"""
        non_noise_count = sum(
            1 for d in sample_rrf_results if d["rrf_score"] >= _NOISE_FLOOR
        )
        filtered = self.gate.apply_gate(sample_rrf_results, threshold=0.01)
        assert len(filtered) <= non_noise_count

    def test_apply_gate_sufficient_results_no_top3_fallback(self):
        """若过滤后结果足够多（>= 3），不应触发 top-3 保底（不引入额外文档）。"""
        good_results = [
            {"text": f"高质量文档{i}", "rrf_score": 0.030 - i * 0.001}
            for i in range(5)
        ]
        # 所有文档都高于动态下界，不需要保底
        filtered = self.gate.apply_gate(good_results, threshold=0.01)
        # 动态下界 = max(0.01 * 0.5, 0.005) = 0.005
        # 所有文档 rrf_score >= 0.025 > 0.005，均通过
        assert len(filtered) >= 3

    def test_apply_gate_results_remain_sorted(self, sample_rrf_results):
        """过滤后的结果顺序应仍然是按 rrf_score 降序（与原始排序一致）。"""
        filtered = self.gate.apply_gate(sample_rrf_results, threshold=0.01)
        if len(filtered) > 1:
            scores = [d["rrf_score"] for d in filtered]
            assert scores == sorted(scores, reverse=True), "过滤后应仍按 rrf_score 降序"


# ================================================================
# 模式快捷方法测试
# ================================================================

class TestScoreGateModes:
    """check_by_mode / apply_gate_by_mode 快捷方法测试。"""

    def setup_method(self):
        self.gate = ScoreGate()

    def test_check_by_mode_strict(self, sample_rrf_results):
        """check_by_mode('strict') 应使用 GATE_THRESHOLDS['strict']。"""
        passed_direct, score_direct, _ = self.gate.check(
            sample_rrf_results, threshold=GATE_THRESHOLDS["strict"]
        )
        passed_mode, score_mode, _ = self.gate.check_by_mode(sample_rrf_results, mode="strict")
        assert passed_direct == passed_mode
        assert score_direct == pytest.approx(score_mode)

    def test_check_by_mode_normal(self, sample_rrf_results):
        """check_by_mode('normal') 应使用 GATE_THRESHOLDS['normal']。"""
        passed_direct, _, _ = self.gate.check(
            sample_rrf_results, threshold=GATE_THRESHOLDS["normal"]
        )
        passed_mode, _, _ = self.gate.check_by_mode(sample_rrf_results, mode="normal")
        assert passed_direct == passed_mode

    def test_check_by_mode_loose(self, sample_rrf_results):
        """check_by_mode('loose') 应使用 GATE_THRESHOLDS['loose']。"""
        passed_direct, _, _ = self.gate.check(
            sample_rrf_results, threshold=GATE_THRESHOLDS["loose"]
        )
        passed_mode, _, _ = self.gate.check_by_mode(sample_rrf_results, mode="loose")
        assert passed_direct == passed_mode

    def test_check_by_mode_invalid_raises_key_error(self, sample_rrf_results):
        """无效模式名称应抛出 KeyError。"""
        with pytest.raises(KeyError):
            self.gate.check_by_mode(sample_rrf_results, mode="invalid_mode")

    def test_apply_gate_by_mode_normal(self, sample_rrf_results):
        """apply_gate_by_mode('normal') 结果应与 apply_gate(threshold=normal) 一致。"""
        import copy
        results_direct = self.gate.apply_gate(
            copy.deepcopy(sample_rrf_results),
            threshold=GATE_THRESHOLDS["normal"]
        )
        results_mode = self.gate.apply_gate_by_mode(
            copy.deepcopy(sample_rrf_results),
            mode="normal"
        )
        assert len(results_direct) == len(results_mode)


# ================================================================
# GATE_THRESHOLDS 字典完整性测试
# ================================================================

class TestGateThresholds:
    """GATE_THRESHOLDS 常量完整性与合理性测试。"""

    def test_all_three_modes_present(self):
        """应包含 strict / normal / loose 三种模式。"""
        assert "strict" in GATE_THRESHOLDS
        assert "normal" in GATE_THRESHOLDS
        assert "loose" in GATE_THRESHOLDS

    def test_threshold_ordering(self):
        """strict 阈值应 > normal > loose。"""
        assert GATE_THRESHOLDS["strict"] > GATE_THRESHOLDS["normal"] > GATE_THRESHOLDS["loose"]

    def test_thresholds_below_rrf_max(self):
        """所有阈值应低于 RRF(k=60) 理论最大分 1/61 ≈ 0.0164。"""
        rrf_max = 1 / (60 + 1)
        for mode, threshold in GATE_THRESHOLDS.items():
            assert threshold < rrf_max, (
                f"{mode} 模式阈值 {threshold} 不应超过 RRF 理论最大分 {rrf_max:.5f}"
            )

    def test_all_thresholds_are_positive(self):
        """所有阈值应为正数。"""
        for mode, threshold in GATE_THRESHOLDS.items():
            assert threshold > 0, f"{mode} 模式阈值应为正数"


# ================================================================
# get_score_gate() 单例测试
# ================================================================

class TestGetScoreGate:
    """get_score_gate() 单例工厂函数测试。"""

    def test_returns_score_gate_instance(self):
        """应返回 ScoreGate 实例。"""
        gate = get_score_gate()
        assert isinstance(gate, ScoreGate)

    def test_singleton_same_object(self):
        """多次调用应返回同一个对象（单例）。"""
        gate1 = get_score_gate()
        gate2 = get_score_gate()
        assert gate1 is gate2, "get_score_gate() 应返回全局单例"
