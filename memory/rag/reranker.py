"""
reranker.py — RAG 精排模块（独立、可单独测试）

职责：
    接收 RRF 融合后的候选文档列表，执行三级降级精排：
        Jina API → SiliconFlow API → LLM Rerank → 原序兜底

设计约束（违反即为 Bug）：
    - 不得直接实例化 ZhipuAI(api_key=...)，必须通过 get_llm_client()
    - 不得知道 AgentState 的存在
    - 不得直接操作 storage/ 目录
    - API Key 从 core.settings 读取，不硬编码
"""

import json
import re
import logging

from core.settings import get_settings
from core.llm_client import get_llm_client

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> tuple[list[dict], str]:
    """三级降级精排入口：Jina API → SiliconFlow API → LLM Rerank → 原序兜底。

    Returns:
        (reranked_list, method_name) 其中 method_name 为实际使用的精排方法：
        "jina_api" | "siliconflow_api" | "llm_rerank" | "none"
    """
    if not candidates:
        return candidates, "none"

    s = get_settings()

    if s.USE_RERANKER_API:
        reranked = _api_rerank(query, candidates, top_k=top_k)
        if reranked is not None:
            # 判断实际使用的 API
            method = "siliconflow_api" if (not s.JINA_API_KEY and s.SILICONFLOW_API_KEY) else "jina_api"
            return reranked, method
        logger.info("  [RAG] Reranker API 不可用，降级 LLM Rerank")

    reranked = _llm_rerank(query, candidates, top_k=top_k)
    return reranked, "llm_rerank"


def _api_rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict] | None:
    """调用外部 Reranker API（Jina / SiliconFlow）。失败时返回 None（触发降级）。

    优先使用 Jina API；Jina Key 不存在时尝试 SiliconFlow API。
    两者均不可用时返回 None。
    """
    s = get_settings()
    jina_key    = s.JINA_API_KEY
    silicon_key = s.SILICONFLOW_API_KEY

    if not jina_key and not silicon_key:
        return None

    import httpx
    texts = [item["text"][:512] for item in candidates]
    try:
        if jina_key:
            url     = "https://api.jina.ai/v1/rerank"
            headers = {"Authorization": f"Bearer {jina_key}", "Content-Type": "application/json"}
            payload = {
                "model": "jina-reranker-v2-base-multilingual",
                "query": query,
                "documents": texts,
                "top_n": top_k,
            }
        else:
            url     = "https://api.siliconflow.cn/v1/rerank"
            headers = {"Authorization": f"Bearer {silicon_key}", "Content-Type": "application/json"}
            payload = {
                "model": "Qwen/Qwen3-Reranker",
                "query": query,
                "documents": texts,
                "top_n": top_k,
            }

        resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        resp.raise_for_status()
        reranked = [
            {**candidates[r["index"]], "rerank_score": r.get("relevance_score", 0.0)}
            for r in resp.json().get("results", [])
            if r.get("index", 0) < len(candidates)
        ]
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        logger.info(f"  [Reranker API] ✅ 精排完成，返回 {len(reranked)} 条")
        return reranked
    except Exception as e:
        logger.warning(f"  [Reranker API] 调用失败，降级到 LLM Rerank：{e}")
        return None


def _llm_rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """使用 ZhipuAI LLM 对候选文档进行语义精排。内部调用 get_llm_client()。

    失败时返回原列表（原序兜底）。
    """
    if not candidates:
        return candidates

    candidate_lines = []
    for i, item in enumerate(candidates):
        snippet = item["text"][:200].replace("\n", " ")
        source  = item.get("metadata", {}).get("source", "未知来源")
        candidate_lines.append(f'  {{"index": {i}, "source": "{source}", "snippet": "{snippet}"}}')

    candidates_json = "[\n" + ",\n".join(candidate_lines) + "\n]"
    prompt = (
        f"你是一个408考研知识检索助手。用户查询：「{query}」\n\n"
        f"以下是检索到的候选片段，请对每个片段与用户查询的相关性打分（0-10分）。\n"
        f"0分=完全无关，10分=高度相关且直接回答查询。\n\n"
        f"候选片段：\n{candidates_json}\n\n"
        f"请只返回 JSON 数组，格式：[{{\"index\": 0, \"score\": 8}}, ...]，不要有任何其他文字。"
    )

    try:
        client   = get_llm_client()
        response = client.chat.completions.create(
            model=client.default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            raw = m.group(0) if m else (_ for _ in ()).throw(ValueError("无法提取 JSON"))
        scores_data = json.loads(raw)
        score_map   = {item["index"]: item["score"] for item in scores_data}
        scored = [
            {**item, "rerank_score": score_map.get(i, 0)}
            for i, item in enumerate(candidates)
        ]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored
    except Exception as e:
        logger.warning(f"  [Rerank 降级] LLM Rerank 失败，使用原顺序：{e}")
        return candidates
