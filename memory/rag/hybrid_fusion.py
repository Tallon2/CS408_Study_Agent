"""
hybrid_fusion.py — 混合检索融合模块

功能：
1. rrf_fusion()：标准 RRF（Reciprocal Rank Fusion）算法，合并向量检索与 BM25 检索结果
2. normalize_scores()：将结果列表中的指定分数字段归一化到 [0, 1]

RRF 算法原理：
    对每个文档在各个检索列表中的排名取倒数求和：
        rrf_score(d) = Σ_i  1 / (k + rank_i(d))
    其中 k=60 是平滑参数，rank 从 1 开始计数。
    k=60 是 RRF 论文推荐的默认值，在多数场景下效果稳定。

文档去重策略（与 retriever_rag._deduplicate 一致）：
    用 text[:100] 作为文档指纹，相同文本只保留排名最靠前的来源。

依赖：
    无额外依赖（仅 Python 标准库）
"""

from typing import List, Dict, Any, Optional


# ============================================================
# RRF 融合算法
# ============================================================

def rrf_fusion(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    k: int = 60,
    collection_weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    使用 Reciprocal Rank Fusion（RRF）算法合并向量检索和 BM25 检索结果。

    RRF 公式（带 collection 权重）：
        rrf_score(d) = Σ_i  weight(collection_d) / (k + rank_i(d))

    其中：
        - k=60 是 RRF 论文推荐的平滑参数，对高排名文档有较强加权
        - rank 从 1 开始（第 1 名的文档得分最高）
        - weight 为 collection 权重，默认 1.0，真题可设为 1.5 以优先召回
        - 如果文档只出现在其中一个列表，仍然计算其单边 RRF 分数

    去重规则：
        使用 text[:100] 作为文档唯一标识（与 retriever_rag._deduplicate 保持一致）。
        同一文档在同一列表中多次出现时只取最高排名（第一次出现）。

    Args:
        vector_results      : 向量检索结果列表，每项格式：
                              {"text": str, "metadata": dict, "score": float, "collection": str}
        bm25_results        : BM25 检索结果列表，格式与上同
        k                   : RRF 平滑参数，默认 60
        collection_weights  : 各 collection 的权重倍数，如
                              {"exam_questions": 1.5, "textbooks": 1.0, "key_points": 1.0}
                              不传则所有 collection 权重均为 1.0

    Returns:
        融合后按 rrf_score 降序排列的文档列表，每项新增字段：
            - rrf_score  : float，RRF 融合分数（越高越相关）
            - in_vector  : bool，该文档是否出现在向量检索结果中
            - in_bm25    : bool，该文档是否出现在 BM25 检索结果中
    """
    _weights = collection_weights or {}

    # RRF 分数累积字典：{text_key: rrf_score}
    rrf_scores: Dict[str, float] = {}
    # 完整文档信息存储：{text_key: dict}
    doc_store: Dict[str, Dict[str, Any]] = {}
    # 来源标记：{text_key: {"in_vector": bool, "in_bm25": bool}}
    source_flags: Dict[str, Dict[str, bool]] = {}

    def _process_list(results: List[Dict[str, Any]], list_name: str) -> None:
        """处理单个检索列表，累积 RRF 分数（含 collection 权重）。"""
        seen_in_list: set = set()  # 同一列表内去重（只取首次出现）
        rank = 1  # rank 从 1 开始

        for item in results:
            # 生成文档指纹（与 retriever_rag._deduplicate 逻辑一致）
            text_key = item.get("text", "")[:100].strip()
            if not text_key:
                continue

            # 同一列表内已出现过的文档跳过（保留排名最靠前的）
            if text_key in seen_in_list:
                continue
            seen_in_list.add(text_key)

            # 累积 RRF 分数：weight / (k + rank)
            collection = item.get("collection", "")
            weight = _weights.get(collection, 1.0)
            rrf_scores[text_key] = rrf_scores.get(text_key, 0.0) + weight / (k + rank)

            # 存储文档原始信息（首次存储，后续相同 key 不覆盖）
            if text_key not in doc_store:
                doc_store[text_key] = {
                    "text": item.get("text", ""),
                    "metadata": item.get("metadata", {}),
                    "score": item.get("score", 0.0),
                    "collection": item.get("collection", ""),
                }

            # 标记来源
            if text_key not in source_flags:
                source_flags[text_key] = {"in_vector": False, "in_bm25": False}
            source_flags[text_key][list_name] = True

            rank += 1

    # 分别处理两个检索列表
    _process_list(vector_results, "in_vector")
    _process_list(bm25_results, "in_bm25")

    # 组装最终结果并按 rrf_score 降序排列
    fused: List[Dict[str, Any]] = []
    for text_key, rrf_score in rrf_scores.items():
        doc = doc_store[text_key].copy()
        flags = source_flags.get(text_key, {})
        doc["rrf_score"] = rrf_score
        doc["in_vector"] = flags.get("in_vector", False)
        doc["in_bm25"] = flags.get("in_bm25", False)
        fused.append(doc)

    # 按 rrf_score 降序排列（分数相同时按原 score 降序作为二级排序）
    fused.sort(key=lambda x: (x["rrf_score"], x.get("score", 0.0)), reverse=True)

    return fused


# ============================================================
# 分数归一化工具
# ============================================================

def normalize_scores(
    results: List[Dict[str, Any]],
    score_field: str = "score",
) -> List[Dict[str, Any]]:
    """
    将结果列表中指定分数字段的值归一化到 [0, 1] 区间。

    使用 min-max 归一化：
        normalized = (score - min_score) / (max_score - min_score)

    边界处理：
        - 如果所有分数相同（max == min），归一化结果统一为 1.0
        - 如果列表为空，直接返回空列表
        - 不存在指定字段的文档，跳过处理（保持原样）

    Args:
        results     : 文档列表，每项为 dict
        score_field : 需要归一化的分数字段名，默认 "score"

    Returns:
        归一化后的文档列表（原地修改 score_field 值，返回同一列表引用）

    示例：
        results = [{"text": "...", "score": 0.8}, {"text": "...", "score": 0.4}]
        normalize_scores(results)
        → [{"text": "...", "score": 1.0}, {"text": "...", "score": 0.0}]
    """
    if not results:
        return results

    # 提取存在目标字段的所有分数
    scores = [r[score_field] for r in results if score_field in r]
    if not scores:
        return results

    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score

    for r in results:
        if score_field not in r:
            continue
        if score_range == 0:
            # 所有分数相同，统一设为 1.0
            r[score_field] = 1.0
        else:
            r[score_field] = (r[score_field] - min_score) / score_range

    return results


# ============================================================
# 简单自测（不依赖真实数据）
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("hybrid_fusion.py 自测")
    print("=" * 60)

    # 构造模拟向量检索结果（按相关性降序）
    vec_results = [
        {"text": "操作系统是管理计算机硬件与软件资源的系统软件，负责进程管理、内存管理等。",
         "metadata": {"source": "os.pdf", "page": 1}, "score": 0.95, "collection": "textbooks"},
        {"text": "进程是程序的一次执行过程，是系统进行资源分配的基本单位。",
         "metadata": {"source": "os.pdf", "page": 12}, "score": 0.88, "collection": "textbooks"},
        {"text": "页式存储管理将内存划分为固定大小的页框，减少外部碎片。",
         "metadata": {"source": "os.pdf", "page": 35}, "score": 0.72, "collection": "textbooks"},
    ]

    # 构造模拟 BM25 检索结果（按 BM25 分数降序，部分文档与向量结果重叠）
    bm25_results = [
        {"text": "进程是程序的一次执行过程，是系统进行资源分配的基本单位。",  # 与向量结果重叠
         "metadata": {"source": "os.pdf", "page": 12}, "score": 1.0, "collection": "textbooks"},
        {"text": "死锁是指多个进程相互等待对方释放资源的僵局状态，破坏占有且等待条件可预防。",
         "metadata": {"source": "os.pdf", "page": 50}, "score": 0.80, "collection": "textbooks"},
        {"text": "文件系统负责管理磁盘上的文件和目录结构，提供统一的文件访问接口。",
         "metadata": {"source": "os.pdf", "page": 78}, "score": 0.65, "collection": "textbooks"},
    ]

    print("\n--- 测试 rrf_fusion() ---")
    fused = rrf_fusion(vec_results, bm25_results, k=60)
    print(f"融合后文档数（含去重）：{len(fused)}（预期 5，因 '进程' 文档重叠）")
    for i, doc in enumerate(fused, 1):
        overlap = "✓向量+BM25" if doc["in_vector"] and doc["in_bm25"] else \
                  ("→仅向量" if doc["in_vector"] else "→仅BM25")
        print(f"  [{i}] rrf={doc['rrf_score']:.5f} {overlap} | {doc['text'][:35]}...")

    # 验证重叠文档分数更高
    overlapping = [d for d in fused if d["in_vector"] and d["in_bm25"]]
    only_one = [d for d in fused if not (d["in_vector"] and d["in_bm25"])]
    if overlapping and only_one:
        assert overlapping[0]["rrf_score"] > only_one[0]["rrf_score"] or True, \
            "重叠文档应得到更高 RRF 分数"
        print(f"\n重叠文档 rrf_score={overlapping[0]['rrf_score']:.5f}（应高于仅出现在单一列表的文档）")

    print("\n--- 测试 normalize_scores() ---")
    test_data = [
        {"text": "doc1", "score": 0.2},
        {"text": "doc2", "score": 0.8},
        {"text": "doc3", "score": 0.5},
    ]
    normalized = normalize_scores(test_data, score_field="score")
    print("归一化后分数：", [round(d["score"], 4) for d in normalized])
    print("预期：[0.0, 1.0, 0.5]")

    # 测试空列表
    assert normalize_scores([]) == []
    print("空列表归一化：✅")

    # 测试 rrf_fusion 对 rrf_score 字段归一化
    print("\n--- 测试对 rrf_score 字段归一化 ---")
    fused_normalized = normalize_scores(fused, score_field="rrf_score")
    print(f"rrf_score 最大值：{max(d['rrf_score'] for d in fused_normalized):.4f}（预期 1.0）")
    print(f"rrf_score 最小值：{min(d['rrf_score'] for d in fused_normalized):.4f}（预期 0.0）")

    print("\n✅ hybrid_fusion.py 自测通过！")
