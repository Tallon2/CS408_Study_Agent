"""
retriever_rag.py — RAG 混合检索管线（向量 + BM25 + RRF 融合）

管线步骤（v2.0）：
    双路检索(向量+BM25) → RRF融合 → 评分门控
    → [不通过则 Query 重写二次检索] → Reranker精排 → 格式化输出

降级策略：
- BM25 索引不存在 → 仅向量检索
- Reranker API 不可用 → LLM Rerank
- LLM Rerank 失败 → 保持 RRF 原排序
- ChromaDB 不可用 → 返回空字符串
"""

import logging

from core.settings import get_settings
from memory.rag.indexer import (
    get_chroma_client,
    _get_embedding_fn,
    COLLECTION_TEXTBOOKS,
    COLLECTION_EXAM,
    COLLECTION_KEYPOINTS,
)
from memory.rag.bm25_retriever import get_bm25_retriever
from memory.rag.hybrid_fusion import rrf_fusion
from memory.rag.reranker import rerank as _rerank
from memory.rag.score_gate import ScoreGate, GATE_THRESHOLDS
from memory.rag.query_rewriter import get_query_rewriter
from memory.rag.indexer import auto_merge_context

logger = logging.getLogger(__name__)

# RRF 融合时各 collection 的权重倍数（真题 1.5x 加权）
_COLLECTION_WEIGHTS = {
    "exam_questions": 1.5,
    "textbooks": 1.0,
    "key_points": 1.0,
}


def _get_pipeline_config() -> dict:
    """从 settings 读取 RAG 管线配置，消除硬编码。"""
    s = get_settings()
    return {
        "vector_n_textbooks": s.RAG_VECTOR_N_TEXTBOOKS,
        "vector_n_exam":      s.RAG_VECTOR_N_EXAM,
        "vector_n_keypoints": s.RAG_VECTOR_N_KEYPOINTS,
        "bm25_n_results":     s.RAG_BM25_N_RESULTS,
        "rrf_k":              s.RAG_RRF_K,
        "collection_weights": _COLLECTION_WEIGHTS,
        "gate_mode":          s.RAG_GATE_MODE,
        "top_k":              s.RAG_TOP_K_FINAL,
        "use_reranker_api":   s.USE_RERANKER_API,
    }


# ── 内部工具 ─────────────────────────────────────────────────
def _query_collection(collection_name: str, query: str, n_results: int) -> list[dict]:
    """从指定 ChromaDB 集合中检索最相关的文档。"""
    try:
        client = get_chroma_client()
        collection = client.get_collection(
            collection_name,
            embedding_function=_get_embedding_fn()
        )
    except Exception:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        print(f"  [检索警告] 集合 {collection_name} 查询失败：{e}")
        return []

    docs      = results.get("documents", [[]])[0]
    metas     = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(docs, metas, distances)
    ]


def _deduplicate(items: list[dict]) -> list[dict]:
    """按文本前100字符去重，保留首次出现的结果。"""
    seen, unique = set(), []
    for item in items:
        key = item["text"][:100].strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _format_results(items: list[dict]) -> str:
    """将检索结果格式化为 LLM 可直接阅读的参考资料字符串。"""
    if not items:
        return ""

    parts = []
    for i, item in enumerate(items, start=1):
        meta    = item.get("metadata", {})
        source  = meta.get("source", "")
        subject = meta.get("subject", "")
        section = meta.get("section", "")
        page    = meta.get("page", "")

        source_parts = []
        if subject: source_parts.append(subject)
        if source:  source_parts.append(source)
        if section: source_parts.append(f"§{section}")
        if page:    source_parts.append(f"第{page}页")
        source_label = "、".join(source_parts) if source_parts else "知识库"

        parts.append(f"【参考资料{i}】（来源：{source_label}）\n{item['text']}")

    return "\n\n".join(parts)


def _dual_retrieve(query: str, cfg: dict) -> tuple[list[dict], list[dict]]:
    """同时执行向量检索（ChromaDB）和 BM25 稀疏检索，返回 (vector_results, bm25_results)。"""
    # ---- 向量检索 ----
    vector_results = []
    for coll, n in [
        (COLLECTION_TEXTBOOKS, cfg["vector_n_textbooks"]),
        (COLLECTION_EXAM,      cfg["vector_n_exam"]),
        (COLLECTION_KEYPOINTS, cfg["vector_n_keypoints"]),
    ]:
        for item in _query_collection(coll, query, n_results=n):
            item["score"] = max(0.0, 1.0 - item.get("distance", 1.0))
            vector_results.append(item)

    # ---- BM25 稀疏检索 ----
    bm25_results = []
    try:
        bm25 = get_bm25_retriever()
        n    = cfg["bm25_n_results"]
        for coll in [COLLECTION_TEXTBOOKS, COLLECTION_EXAM, COLLECTION_KEYPOINTS]:
            bm25_results.extend(bm25.search(query, coll, n_results=n))
    except Exception as e:
        logger.warning(f"  [BM25] 检索失败，降级为纯向量模式：{e}")

    return vector_results, bm25_results


def _fallback_with_rewrite(
    original_query: str,
    current_fused: list[dict],
    gate: "ScoreGate",
    cfg: dict,
) -> list[dict]:
    """评分门控未通过时，用 LLM 改写查询进行二次检索并重新融合。"""
    try:
        rewriter    = get_query_rewriter()
        all_rewrites = rewriter.expand(original_query, n=3)
        rewrites    = [q for q in all_rewrites if q != original_query][:2]

        if not rewrites:
            return current_fused
        logger.info(f"  [Query重写] 生成改写：{rewrites}")
        all_vector: list[dict] = []
        all_bm25:   list[dict] = []
        for rq in rewrites:
            vr, br = _dual_retrieve(rq, cfg)
            all_vector.extend(vr)
            all_bm25.extend(br)
        if not all_vector and not all_bm25:
            return current_fused
        new_fused = rrf_fusion(all_vector, all_bm25, k=cfg["rrf_k"],
                               collection_weights=cfg.get("collection_weights"))
        existing_keys = {item["text"][:100].strip() for item in new_fused}
        for item in current_fused:
            if item["text"][:100].strip() not in existing_keys:
                new_fused.append(item)
        new_fused.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
        logger.info(f"  [Query重写] 二次检索后共 {len(new_fused)} 条候选")
        return new_fused

    except Exception as e:
        logger.warning(f"  [Query重写] 二次检索失败，保持原结果：{e}")
        return current_fused


# ── RAG 管线核心实现 ──────────────────────────────────────────
def _run_pipeline(query: str, *, trace: bool = False) -> dict:
    """RAG 管线核心（单一实现）：双路检索→RRF融合→门控→Reranker→格式化。
    返回 {"context": str, "trace": list[dict]}，trace=False 时 trace 为空列表。"""
    pipeline_trace: list[dict] = []
    def _t(step: dict) -> None:  # 仅 trace 模式追加步骤
        if trace:
            pipeline_trace.append(step)

    try:
        cfg  = _get_pipeline_config()
        gate = ScoreGate()
        top_k = cfg["top_k"]

        # Step 1: 记录初始查询
        _t({"step": "query_rewrite", "original": query, "rewritten": [query]})

        # Step 2: 双路检索
        logger.info(f"[RAG] 双路检索：'{query[:30]}'")
        vector_results, bm25_results = _dual_retrieve(query, cfg)

        if not vector_results and not bm25_results:
            logger.info("  [RAG] 知识库为空")
            return {"context": "", "trace": pipeline_trace}
        # BM25 追踪
        _t({
            "step": "bm25_results",
            "count": len(bm25_results),
            "top_keywords": [
                item.get("metadata", {}).get("source", "")[:20]
                for item in bm25_results[:5]
                if item.get("metadata", {}).get("source")
            ][:5],
        })
        # 向量检索追踪
        if trace:
            vec_collections: dict[str, int] = {}
            for item in vector_results:
                meta = item.get("metadata", {})
                coll = meta.get("collection", meta.get("source", "unknown"))
                vec_collections[coll] = vec_collections.get(coll, 0) + 1
            _t({"step": "vector_results", "count": len(vector_results),
                "collections": vec_collections})

        # Step 3: RRF 融合
        fused = rrf_fusion(vector_results, bm25_results, k=cfg["rrf_k"],
                           collection_weights=cfg.get("collection_weights"))
        logger.info(f"  [RAG] RRF融合：向量{len(vector_results)} + BM25{len(bm25_results)} → {len(fused)}条")
        _t({"step": "rrf_fusion", "total_before": len(vector_results) + len(bm25_results),
            "total_after": len(fused), "top_score": round(fused[0].get("rrf_score", 0), 5) if fused else 0})
        # Step 4: 评分门控
        passed, best_score, reason = gate.check_by_mode(fused, mode=cfg["gate_mode"])
        logger.info(f"  [RAG] 门控：score={best_score:.4f}，{reason}")
        if not passed:
            logger.info("  [RAG] 门控未通过，触发二次检索...")
            fused = _fallback_with_rewrite(query, fused, gate, cfg)
            if trace and pipeline_trace:
                try:
                    rewriter     = get_query_rewriter()
                    all_rewrites = rewriter.expand(query, n=3)
                    rewrites     = [q for q in all_rewrites if q != query][:2]
                    pipeline_trace[0]["rewritten"] = [query] + rewrites
                except Exception:
                    pass
        fused     = gate.apply_gate_by_mode(fused, mode=cfg["gate_mode"])
        threshold = GATE_THRESHOLDS.get(cfg["gate_mode"], 0.02)
        _t({"step": "score_gate", "passed": passed,
            "threshold": threshold, "max_score": round(best_score, 5)})
        # Step 5: Reranker 精排（委托给 reranker.py）
        candidates            = fused[:min(20, len(fused))]
        reranked, rerank_method = _rerank(query, candidates, top_k=top_k)

        _t({
            "step": "rerank_scores",
            "method": rerank_method,
            "scores": [round(item.get("rerank_score", 0), 4) for item in reranked[:top_k]],
        })

        # Step 6: Auto-merging + 格式化 + 管线追踪日志
        top_results    = reranked[:top_k]
        merged_results = auto_merge_context(top_results)

        logger.info(f"[RAG Pipeline] query={query[:50]!r} "
                    f"vector={len(vector_results)} bm25={len(bm25_results)} "
                    f"fused={len(fused)} top_k={top_k}")

        return {"context": _format_results(merged_results), "trace": pipeline_trace}

    except Exception as e:
        logger.error(f"  [RAG 降级] _run_pipeline() 异常：{e}", exc_info=True)
        return {"context": "", "trace": pipeline_trace}


# ── 公开 API ─────────────────────────────────────────────────
def retrieve(query: str, top_k: int | None = None) -> str:
    """主 RAG 检索入口（向后兼容）。返回参考资料字符串，知识库空时返回 ""。"""
    return _run_pipeline(query, trace=False)["context"]


def retrieve_with_trace(query: str, top_k: int | None = None) -> dict:
    """带管线追踪的 RAG 检索入口。返回 {"context": str, "trace": list[dict]}。"""
    return _run_pipeline(query, trace=True)


def retrieve_exam_questions(topic: str, top_k: int = 3) -> str:
    """专门从 exam_questions 集合检索历年真题（用于 generate_quiz 工具）。"""
    try:
        results = _query_collection(COLLECTION_EXAM, topic, n_results=top_k)
        return _format_results(results) if results else ""
    except Exception as e:
        logger.warning(f"  [RAG 降级] retrieve_exam_questions() 失败：{e}")
        return ""