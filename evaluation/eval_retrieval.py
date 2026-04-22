"""
eval_retrieval.py — RAG 检索质量评估脚本

评估指标：
- Hit@K（K=1,3,5）：top-K 结果中是否包含相关文档
  判断依据：relevant_keywords 中任意一个关键词出现在检索结果文本中，即视为命中
- MRR（Mean Reciprocal Rank）：第一个命中结果排名倒数的均值

支持两种模式：
- hybrid      ：使用 retrieve()（向量 + BM25 + RRF 融合管线）
- vector_only ：使用 _query_collection() 纯向量检索（baseline）

用法：
    python evaluation/eval_retrieval.py --mode hybrid
    python evaluation/eval_retrieval.py --mode vector_only
    python evaluation/eval_retrieval.py  # 默认 hybrid

    from evaluation.eval_retrieval import evaluate_single, run_evaluation, print_report
"""

import json
import os
import sys
import logging
from typing import Callable

# 将项目根目录加入 sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# ============================================================
# 单条用例评估
# ============================================================

def evaluate_single(query_item: dict, retrieve_fn: Callable, k: int = 5) -> dict:
    """
    对单条测试用例执行检索并计算评估指标。

    命中判断规则：
        relevant_keywords 中任意一个关键词（不区分大小写）出现在
        检索结果的文本内容中，则该条结果视为"命中"。

    Args:
        query_item  : 测试用例字典，包含 query、relevant_keywords 等字段
        retrieve_fn : 检索函数，签名为 f(query: str) -> list[dict]
                      每个 dict 至少包含 "text" 字段
        k           : 最大检索数量（评估 Hit@1, Hit@3, Hit@k）

    Returns:
        评估结果字典，包含：
            - id           : 测试用例 ID
            - query        : 原始查询
            - subject      : 所属科目
            - difficulty   : 难度
            - hit_at_1     : bool，top-1 是否命中
            - hit_at_3     : bool，top-3 是否有命中
            - hit_at_k     : bool，top-k 是否有命中（k 由参数决定）
            - mrr          : float，本条用例的倒数排名（未命中为 0）
            - first_hit_rank : int，第一个命中结果的排名（未命中为 -1）
            - retrieved_count : int，实际检索到的结果数量
    """
    query = query_item["query"]
    keywords = [kw.lower() for kw in query_item.get("relevant_keywords", [])]
    case_id = query_item.get("id", "unknown")

    # 执行检索
    try:
        raw_results = retrieve_fn(query)
    except Exception as e:
        logger.warning(f"[eval_single] 检索失败 {case_id}：{e}")
        raw_results = []

    # 统一解析结果：支持 list[dict]（含 text 字段）和 str（格式化字符串）
    docs = _parse_retrieve_results(raw_results)[:k]

    # 命中判断
    hit_ranks = []
    for rank, doc_text in enumerate(docs, start=1):
        doc_lower = doc_text.lower()
        if any(kw in doc_lower for kw in keywords):
            hit_ranks.append(rank)

    first_hit = hit_ranks[0] if hit_ranks else -1
    mrr = 1.0 / first_hit if first_hit > 0 else 0.0

    return {
        "id": case_id,
        "query": query,
        "subject": query_item.get("subject", ""),
        "difficulty": query_item.get("difficulty", ""),
        "hit_at_1": first_hit == 1,
        "hit_at_3": any(r <= 3 for r in hit_ranks),
        "hit_at_k": len(hit_ranks) > 0,
        "mrr": mrr,
        "first_hit_rank": first_hit,
        "retrieved_count": len(docs),
    }


def _parse_retrieve_results(raw) -> list[str]:
    """
    将检索函数的原始返回值统一解析为文本列表。

    兼容两种返回格式：
    1. list[dict]（新版 retrieve 内部结构）—— 取 "text" 字段
    2. str（_format_results 格式化字符串）—— 按段落分割
    3. 其他类型 —— 返回空列表
    """
    if isinstance(raw, list):
        texts = []
        for item in raw:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return [t for t in texts if t]
    elif isinstance(raw, str):
        # 格式化字符串按双换行分割，每段为一个文档
        segments = [seg.strip() for seg in raw.split("\n\n") if seg.strip()]
        return segments
    return []


# ============================================================
# 批量评估
# ============================================================

def run_evaluation(test_cases_path: str, mode: str = "hybrid") -> dict:
    """
    读取测试用例 JSON，批量运行检索评估，返回汇总统计。

    Args:
        test_cases_path : test_cases.json 的绝对或相对路径
        mode            : 检索模式
                          "hybrid"      — 使用 retrieve()（混合管线）
                          "vector_only" — 使用 _query_collection() 纯向量检索

    Returns:
        汇总结果字典，包含：
            - mode            : 检索模式
            - total           : 测试用例总数
            - hit_at_1        : float，Hit@1 均值
            - hit_at_3        : float，Hit@3 均值
            - hit_at_5        : float，Hit@5 均值
            - mrr             : float，MRR 均值
            - by_subject      : dict，按科目细分指标
            - by_difficulty   : dict，按难度细分指标
            - details         : list[dict]，每条用例的详细结果
    """
    # 加载测试用例
    with open(test_cases_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    # 构建检索函数
    retrieve_fn = _build_retrieve_fn(mode)

    # 逐条评估
    details = []
    for i, case in enumerate(test_cases):
        logger.info(f"[eval] 评估 {i+1}/{len(test_cases)}: {case['id']} - {case['query'][:30]}")
        result = evaluate_single(case, retrieve_fn, k=5)
        details.append(result)
        # 打印简要进度
        hit_str = "✓" if result["hit_at_5"] else "✗"
        print(f"  [{hit_str}] {case['id']:10s} Hit@1={int(result['hit_at_1'])} "
              f"Hit@3={int(result['hit_at_3'])} Hit@5={int(result['hit_at_k'])} "
              f"MRR={result['mrr']:.3f}  {case['query'][:25]}")

    # 汇总统计
    n = len(details)
    summary = {
        "mode": mode,
        "total": n,
        "hit_at_1": sum(d["hit_at_1"] for d in details) / n if n else 0.0,
        "hit_at_3": sum(d["hit_at_3"] for d in details) / n if n else 0.0,
        "hit_at_5": sum(d["hit_at_k"] for d in details) / n if n else 0.0,
        "mrr": sum(d["mrr"] for d in details) / n if n else 0.0,
        "by_subject": _aggregate_by(details, "subject"),
        "by_difficulty": _aggregate_by(details, "difficulty"),
        "details": details,
    }
    return summary


def _build_retrieve_fn(mode: str) -> Callable:
    """
    根据 mode 构建检索函数，返回 list[dict]（含 text 字段）。
    """
    if mode == "hybrid":
        try:
            from memory.rag.retriever_rag import retrieve as _hybrid_retrieve
            from memory.rag.retriever_rag import _dual_retrieve

            def hybrid_fn(query: str) -> list[dict]:
                """混合检索：向量 + BM25 + RRF，返回 list[dict]。"""
                try:
                    vector_results, bm25_results = _dual_retrieve(query)
                    from memory.rag.hybrid_fusion import rrf_fusion
                    fused = rrf_fusion(vector_results, bm25_results)
                    return fused
                except Exception as e:
                    logger.warning(f"[eval] hybrid 检索失败：{e}")
                    return []

            return hybrid_fn
        except ImportError as e:
            logger.warning(f"[eval] hybrid 模块导入失败，降级为 vector_only：{e}")
            mode = "vector_only"

    # vector_only：使用 _query_collection 纯向量检索
    try:
        from memory.rag.retriever_rag import _query_collection
        from memory.rag.indexer import (
            COLLECTION_TEXTBOOKS, COLLECTION_EXAM, COLLECTION_KEYPOINTS
        )

        def vector_fn(query: str) -> list[dict]:
            """纯向量检索：三个集合各取 5 条，合并去重。"""
            results = []
            seen = set()
            for coll in [COLLECTION_TEXTBOOKS, COLLECTION_EXAM, COLLECTION_KEYPOINTS]:
                for item in _query_collection(coll, query, n_results=5):
                    key = item["text"][:100].strip()
                    if key not in seen:
                        seen.add(key)
                        results.append(item)
            return results

        return vector_fn
    except ImportError as e:
        logger.warning(f"[eval] vector_only 模块导入失败，使用空检索：{e}")
        return lambda q: []


def _aggregate_by(details: list[dict], field: str) -> dict:
    """
    按指定字段（subject / difficulty）分组聚合评估指标。

    Returns:
        {field_value: {"count": int, "hit_at_1": float, "hit_at_3": float,
                       "hit_at_5": float, "mrr": float}}
    """
    groups: dict[str, list[dict]] = {}
    for d in details:
        key = d.get(field, "unknown")
        groups.setdefault(key, []).append(d)

    aggregated = {}
    for key, items in groups.items():
        n = len(items)
        aggregated[key] = {
            "count": n,
            "hit_at_1": sum(i["hit_at_1"] for i in items) / n,
            "hit_at_3": sum(i["hit_at_3"] for i in items) / n,
            "hit_at_5": sum(i["hit_at_k"] for i in items) / n,
            "mrr": sum(i["mrr"] for i in items) / n,
        }
    return aggregated


# ============================================================
# 报告打印
# ============================================================

def print_report(results: dict) -> None:
    """
    将评估结果以可读格式打印到控制台。

    Args:
        results : run_evaluation() 返回的汇总结果字典
    """
    mode = results.get("mode", "unknown")
    total = results.get("total", 0)

    print("\n" + "=" * 60)
    print(f"  408考研 RAG 检索质量评估报告")
    print(f"  检索模式: {mode}  |  测试用例: {total} 条")
    print("=" * 60)

    # 核心指标
    print("\n【核心指标】")
    print(f"  Hit@1 : {results['hit_at_1']:.4f}  ({results['hit_at_1']*100:.1f}%)")
    print(f"  Hit@3 : {results['hit_at_3']:.4f}  ({results['hit_at_3']*100:.1f}%)")
    print(f"  Hit@5 : {results['hit_at_5']:.4f}  ({results['hit_at_5']*100:.1f}%)")
    print(f"  MRR   : {results['mrr']:.4f}  ({results['mrr']*100:.1f}%)")

    # 按科目
    by_subject = results.get("by_subject", {})
    if by_subject:
        print("\n【按科目细分】")
        header = f"  {'科目':<12} {'条数':>4} {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'MRR':>7}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for subj, m in sorted(by_subject.items()):
            print(f"  {subj:<12} {m['count']:>4} "
                  f"{m['hit_at_1']:>7.3f} {m['hit_at_3']:>7.3f} "
                  f"{m['hit_at_5']:>7.3f} {m['mrr']:>7.3f}")

    # 按难度
    by_diff = results.get("by_difficulty", {})
    if by_diff:
        print("\n【按难度细分】")
        order = {"easy": 0, "medium": 1, "hard": 2}
        header2 = f"  {'难度':<8} {'条数':>4} {'Hit@1':>7} {'Hit@3':>7} {'Hit@5':>7} {'MRR':>7}"
        print(header2)
        print("  " + "-" * (len(header2) - 2))
        for diff, m in sorted(by_diff.items(), key=lambda x: order.get(x[0], 9)):
            print(f"  {diff:<8} {m['count']:>4} "
                  f"{m['hit_at_1']:>7.3f} {m['hit_at_3']:>7.3f} "
                  f"{m['hit_at_5']:>7.3f} {m['mrr']:>7.3f}")

    print("\n" + "=" * 60)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="408考研 RAG 检索质量评估")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "vector_only"],
        default="hybrid",
        help="检索模式：hybrid（混合检索）或 vector_only（纯向量）",
    )
    parser.add_argument(
        "--cases",
        default=os.path.join(os.path.dirname(__file__), "test_cases.json"),
        help="测试用例 JSON 文件路径（默认：evaluation/test_cases.json）",
    )
    args = parser.parse_args()

    print(f"🔍 开始评估，模式：{args.mode}，用例文件：{args.cases}")
    results = run_evaluation(args.cases, mode=args.mode)
    print_report(results)
