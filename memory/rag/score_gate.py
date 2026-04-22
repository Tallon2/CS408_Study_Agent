"""
score_gate.py — 检索质量门控模块

功能：
1. ScoreGate 类：基于 rrf_score 对混合检索结果进行质量过滤
2. GATE_THRESHOLDS 字典：预置不同场景的门控阈值

设计思路：
    RRF 分数的物理含义：
        - 当 k=60 时，排名第 1 的文档 rrf_score = 1/(60+1) ≈ 0.0164
        - 两个列表均排第 1 的文档   rrf_score = 2×(1/61)  ≈ 0.0328
        - 因此 0.02 ≈ 相当于在至少一个列表中排名前 ~50 名内的文档

    门控逻辑：
        check()      → 判断最佳结果是否达到质量阈值（整体通过/不通过）
        apply_gate() → 细粒度过滤，去除低质量尾部，保证最少 3 条结果

依赖：
    无额外依赖（仅 Python 标准库）
"""

from typing import List, Dict, Any, Tuple


# ============================================================
# 预置阈值字典
# ============================================================

# 注意：RRF(k=60) 的理论最高分 = 1/(60+1) ≈ 0.0164
# 因此阈值需低于 0.0164，建议范围：strict=0.014, normal=0.010, loose=0.006
GATE_THRESHOLDS: Dict[str, float] = {
    "strict": 0.014,  # 严格模式：要求排名第一的文档，适用于 AI 出题场景
    "normal": 0.010,  # 默认模式：top-5 内的文档均可通过，平衡精度与召回
    "loose":  0.006,  # 宽松模式：召回优先，接受边缘相关文档
}

# RRF 分数下界（低于此值视为噪声，apply_gate 中绝对过滤）
_NOISE_FLOOR: float = 0.005


class ScoreGate:
    """
    检索质量门控器。

    对经过 RRF 融合后的结果列表执行两类检查：
    1. check()      : 整体质量检查，判断是否值得使用检索结果
    2. apply_gate() : 细粒度过滤，移除低质量尾部文档，保留最少 3 条

    使用示例：
        gate = ScoreGate()

        # 整体检查
        passed, best_score, reason = gate.check(fused_results, threshold=0.02)
        if not passed:
            print(f"检索质量不足：{reason}")

        # 细粒度过滤
        filtered = gate.apply_gate(fused_results, threshold=0.02)
    """

    # ------------------------------------------------------------------
    # 整体质量检查
    # ------------------------------------------------------------------

    def check(
        self,
        results: List[Dict[str, Any]],
        threshold: float = GATE_THRESHOLDS["normal"],
    ) -> Tuple[bool, float, str]:
        """
        检查检索结果整体质量是否达到阈值。

        判断逻辑：
            取 rrf_score 最高分，与 threshold 比较：
            - 最高分 >= threshold → 通过，返回 (True, best_score, "通过原因")
            - 最高分 <  threshold → 不通过，返回 (False, best_score, "失败原因")
            - 结果为空           → 不通过，返回 (False, 0.0, "无检索结果")

        Args:
            results   : RRF 融合后的文档列表（需含 rrf_score 字段）
            threshold : 质量阈值，默认使用 GATE_THRESHOLDS["normal"] = 0.02

        Returns:
            (passed, best_score, reason) 三元组：
                - passed     : bool，是否通过质量检查
                - best_score : float，最高 rrf_score（列表为空时为 0.0）
                - reason     : str，通过/拒绝的描述原因（中文）
        """
        # 边界：空结果列表
        if not results:
            return False, 0.0, "检索结果为空，知识库可能未建立或查询无匹配"

        # 取最高 rrf_score（结果已按 rrf_score 降序排列）
        best_score = max(
            (r.get("rrf_score", 0.0) for r in results),
            default=0.0
        )

        if best_score >= threshold:
            # 通过：说明至少有一个高质量相关文档
            reason = (
                f"最高 rrf_score={best_score:.5f} >= 阈值 {threshold:.3f}，"
                f"共 {len(results)} 条候选结果，质量合格"
            )
            return True, best_score, reason
        else:
            # 不通过：最相关的文档分数仍低于阈值
            reason = (
                f"最高 rrf_score={best_score:.5f} < 阈值 {threshold:.3f}，"
                f"检索结果相关性不足，建议降低阈值或补充知识库"
            )
            return False, best_score, reason

    # ------------------------------------------------------------------
    # 细粒度过滤
    # ------------------------------------------------------------------

    def apply_gate(
        self,
        results: List[Dict[str, Any]],
        threshold: float = GATE_THRESHOLDS["normal"],
    ) -> List[Dict[str, Any]]:
        """
        对 RRF 融合结果执行细粒度过滤，移除低质量尾部文档。

        过滤规则：
            1. 计算最高 rrf_score（best_score）
            2. 过滤掉 rrf_score < threshold * 0.5 的文档
               （即只保留最高分 50% 以上的文档，避免噪声文档混入）
            3. 如果过滤后结果数 < 3，回退到原始结果的 top-3
               （保证调用方始终能获得一定数量的候选，避免返回空列表）
            4. 绝对过滤：rrf_score < _NOISE_FLOOR（0.005）的文档无论如何都不返回
               （这类文��几乎肯定是噪声）

        Args:
            results   : RRF 融合后的文档列表（需含 rrf_score 字段，降序排列）
            threshold : 门控阈值，默认 GATE_THRESHOLDS["normal"] = 0.02

        Returns:
            过滤后的文档列表，保证：
                - 长度 >= min(3, len(results))（至少返回 3 条，除非总数不足 3）
                - 所有返回文档的 rrf_score >= _NOISE_FLOOR

        示例：
            results = [
                {"rrf_score": 0.030}, {"rrf_score": 0.025},
                {"rrf_score": 0.012}, {"rrf_score": 0.003}
            ]
            apply_gate(results, threshold=0.02)
            → 动态门：0.02 * 0.5 = 0.010，过滤掉 0.003 的文档
            → 保留前 3 条（0.030, 0.025, 0.012）
        """
        if not results:
            return results

        # 最少保证返回的数量
        MIN_RESULTS = 3

        # 1. 计算最高分
        best_score = max(
            (r.get("rrf_score", 0.0) for r in results),
            default=0.0
        )

        # 2. 计算动态下界：最高分的 50%，且不低于 _NOISE_FLOOR
        dynamic_floor = max(threshold * 0.5, _NOISE_FLOOR)

        # 3. 先过滤掉绝对噪声（rrf_score < _NOISE_FLOOR）
        non_noise = [r for r in results if r.get("rrf_score", 0.0) >= _NOISE_FLOOR]

        # 4. 在非噪声文档中，按动态下界过滤
        filtered = [r for r in non_noise if r.get("rrf_score", 0.0) >= dynamic_floor]

        # 5. 如果过滤后结果不足 MIN_RESULTS，回退到非噪声文档的 top-MIN_RESULTS
        if len(filtered) < MIN_RESULTS:
            # 回退：取非噪声文档的前 MIN_RESULTS 条（已按 rrf_score 降序排列）
            filtered = non_noise[:MIN_RESULTS]

        # 6. 如果非噪声文档本身不足 MIN_RESULTS，则全部返回（不额外补充噪声文档）
        return filtered

    # ------------------------------------------------------------------
    # 便捷方法：按预置场景名称操作
    # ------------------------------------------------------------------

    def check_by_mode(
        self,
        results: List[Dict[str, Any]],
        mode: str = "normal",
    ) -> Tuple[bool, float, str]:
        """
        按预置模式名称执行整体质量检查。

        Args:
            results : RRF 融合后的文档列表
            mode    : 模式名称，可选 "strict" / "normal" / "loose"

        Returns:
            同 check() 的返回值

        Raises:
            KeyError: 如果 mode 不在 GATE_THRESHOLDS 中
        """
        threshold = GATE_THRESHOLDS[mode]
        return self.check(results, threshold=threshold)

    def apply_gate_by_mode(
        self,
        results: List[Dict[str, Any]],
        mode: str = "normal",
    ) -> List[Dict[str, Any]]:
        """
        按预置模式名称执行细粒度过滤。

        Args:
            results : RRF 融合后的文档列表
            mode    : 模式名称，可选 "strict" / "normal" / "loose"

        Returns:
            同 apply_gate() 的返回值
        """
        threshold = GATE_THRESHOLDS[mode]
        return self.apply_gate(results, threshold=threshold)


# ============================================================
# 模块级便捷实例
# ============================================================
_default_gate: ScoreGate | None = None


def get_score_gate() -> ScoreGate:
    """获取全局 ScoreGate 单例。"""
    global _default_gate
    if _default_gate is None:
        _default_gate = ScoreGate()
    return _default_gate


# ============================================================
# 简单自测（不依赖真实数据）
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("score_gate.py 自测")
    print("=" * 60)

    gate = ScoreGate()

    # 构造模拟 RRF 融合结果（rrf_score 已按降序排列）
    mock_results = [
        {"text": "操作系统进程管理相关内容", "rrf_score": 0.0328, "score": 0.95, "collection": "textbooks"},
        {"text": "进程调度算法：先来先服务FCFS", "rrf_score": 0.0164, "score": 0.88, "collection": "textbooks"},
        {"text": "内存分页管理页表结构",         "rrf_score": 0.0160, "score": 0.85, "collection": "textbooks"},
        {"text": "文件系统目录结构",             "rrf_score": 0.0082, "score": 0.72, "collection": "textbooks"},
        {"text": "磁盘调度算法SSTF",             "rrf_score": 0.0030, "score": 0.45, "collection": "textbooks"},
    ]

    print("\n--- 测试 check() ---")
    for mode, threshold in GATE_THRESHOLDS.items():
        passed, best, reason = gate.check(mock_results, threshold=threshold)
        status = "✅ 通过" if passed else "❌ 未通过"
        print(f"  [{mode:6s}] threshold={threshold:.3f} → {status} | best={best:.5f}")

    print("\n--- 测试 apply_gate() ---")
    for mode, threshold in GATE_THRESHOLDS.items():
        filtered = gate.apply_gate(mock_results, threshold=threshold)
        scores = [round(r["rrf_score"], 5) for r in filtered]
        print(f"  [{mode:6s}] threshold={threshold:.3f} → 保留 {len(filtered)} 条 | scores={scores}")

    print("\n--- 测试空结果列表 ---")
    passed, best, reason = gate.check([])
    print(f"  空列表 check() → passed={passed}, best={best}, reason='{reason}'")
    filtered_empty = gate.apply_gate([])
    print(f"  空列表 apply_gate() → 返回 {len(filtered_empty)} 条（预期 0）")

    print("\n--- 测试 top-3 保底机制 ---")
    # 只有高质量文档 1 条，其余全被过滤
    sparse_results = [
        {"text": "高相关文档", "rrf_score": 0.033, "score": 0.99, "collection": "textbooks"},
        {"text": "中等文档A",  "rrf_score": 0.008, "score": 0.60, "collection": "textbooks"},
        {"text": "中等文档B",  "rrf_score": 0.007, "score": 0.55, "collection": "textbooks"},
        {"text": "低质量文档", "rrf_score": 0.006, "score": 0.30, "collection": "textbooks"},
    ]
    filtered_sparse = gate.apply_gate(sparse_results, threshold=0.02)
    print(f"  稀疏结果 apply_gate(threshold=0.02) → 保留 {len(filtered_sparse)} 条")
    print(f"  （动态下界=0.01，过滤后 < 3 条，应触发 top-3 保底 → 预期 3 条）")
    for r in filtered_sparse:
        print(f"    rrf_score={r['rrf_score']:.4f} | {r['text']}")

    print("\n--- 测试 check_by_mode() / apply_gate_by_mode() ---")
    passed, best, reason = gate.check_by_mode(mock_results, mode="strict")
    print(f"  check_by_mode('strict') → passed={passed}, best_score={best:.5f}")
    result_loose = gate.apply_gate_by_mode(mock_results, mode="loose")
    print(f"  apply_gate_by_mode('loose') → 保留 {len(result_loose)} 条")

    print("\n--- GATE_THRESHOLDS 字典验证 ---")
    for k, v in GATE_THRESHOLDS.items():
        print(f"  {k}: {v}")

    print("\n✅ score_gate.py 自测通过！")
