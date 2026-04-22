"""
bm25_retriever.py — BM25 稀疏检索模块

功能：
1. 从 ChromaDB 三个集合读取所有文档，用 jieba 分词构建 BM25 索引
2. 将语料（分词结果 + 文档 ID）序列化为 JSON 持久化到 storage/bm25_index/
3. BM25Retriever.search() 返回与 retriever_rag._query_collection() 完全兼容的格式

依赖：
    pip install rank-bm25>=0.2.2 jieba>=0.42.1 chromadb
"""

import os
import json
import logging
from typing import List, Dict, Any

# BM25 索引持久化目录（相对于本文件的路径）
_BM25_INDEX_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../storage/bm25_index")
)

# ChromaDB 集合名称（与 indexer.py 保持一致）
COLLECTIONS = ["textbooks", "exam_questions", "key_points"]

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    BM25 稀疏检索器。

    使用 jieba 中文分词 + rank-bm25 的 BM25Okapi 算法，
    对 ChromaDB 中存储的三个集合做全文检索。

    索引以 JSON 形式持久化（存储 corpus_tokenized + ids + metadatas），
    避免每次启动都重新从 ChromaDB 拉取全量数据。
    """

    def __init__(self, index_dir: str = _BM25_INDEX_DIR):
        """
        Args:
            index_dir: BM25 索引文件存放目录，默认 storage/bm25_index/
        """
        self.index_dir = index_dir
        os.makedirs(self.index_dir, exist_ok=True)

        # 内存中缓存已加载的索引：{collection_name: {"bm25": BM25Okapi, "ids": [...], "texts": [...], "metadatas": [...]}}
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 私有工具方法
    # ------------------------------------------------------------------

    def _index_path(self, collection_name: str) -> str:
        """返回指定集合的 JSON 索引文件路径。"""
        return os.path.join(self.index_dir, f"{collection_name}.json")

    def _tokenize(self, text: str) -> List[str]:
        """
        用 jieba 精确模式分词，过滤空 token。

        Args:
            text: 待分词的原始字符串

        Returns:
            token 列表，例如 ["操作系统", "进程", "调度"]
        """
        import jieba
        # cut_all=False → 精确模式，适合检索场景
        tokens = [t.strip() for t in jieba.cut(text, cut_all=False) if t.strip()]
        return tokens

    def _load_index(self, collection_name: str) -> bool:
        """
        从 JSON 文件加载 BM25 索引到内存缓存。

        Returns:
            True 表示加载成功，False 表示索引文件不存在或为空。
        """
        from rank_bm25 import BM25Okapi

        path = self._index_path(collection_name)
        if not os.path.exists(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[BM25] 加载索引失败 {path}：{e}")
            return False

        corpus_tokenized: List[List[str]] = data.get("corpus_tokenized", [])
        ids: List[str] = data.get("ids", [])
        texts: List[str] = data.get("texts", [])
        metadatas: List[dict] = data.get("metadatas", [])

        if not corpus_tokenized:
            # 集合为空，缓存空标记避免重复读取
            self._cache[collection_name] = {
                "bm25": None, "ids": [], "texts": [], "metadatas": []
            }
            return True

        bm25 = BM25Okapi(corpus_tokenized)
        self._cache[collection_name] = {
            "bm25": bm25,
            "ids": ids,
            "texts": texts,
            "metadatas": metadatas,
        }
        return True

    def _save_index(
        self,
        collection_name: str,
        corpus_tokenized: List[List[str]],
        ids: List[str],
        texts: List[str],
        metadatas: List[dict],
    ) -> None:
        """
        将语料数据序列化为 JSON 保存到磁盘。

        BM25Okapi 对象无法直接 pickle，因此只保存
        corpus_tokenized（已分词语料）和原始文档信息，
        下次加载时重建 BM25Okapi。
        """
        path = self._index_path(collection_name)
        data = {
            "collection": collection_name,
            "doc_count": len(ids),
            "corpus_tokenized": corpus_tokenized,
            "ids": ids,
            "texts": texts,
            "metadatas": metadatas,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[BM25] 索引已保存：{path}（{len(ids)} 条文档）")

    def _ensure_index(self, collection_name: str) -> bool:
        """
        确保指定集合的索引已在内存中可用。
        优先从缓存获取，其次从磁盘加载。

        Returns:
            True 表示索引可用（可能为空集合），False 表示无法获取。
        """
        if collection_name in self._cache:
            return True
        return self._load_index(collection_name)

    def _build_index_from_chroma(self, collection_name: str) -> None:
        """
        从 ChromaDB 拉取指定集合的全量文档，构建 BM25 索引并持久化。

        如果集合不存在或为空，保存空索引文件（后续调用会返回空列表）。
        """
        from memory.rag.indexer import get_chroma_client, _get_embedding_fn

        print(f"[BM25] 正在从 ChromaDB 集合 [{collection_name}] 构建索引...")

        ids: List[str] = []
        texts: List[str] = []
        metadatas: List[dict] = []

        try:
            client = get_chroma_client()
            collection = client.get_collection(
                collection_name,
                embedding_function=_get_embedding_fn()
            )
            # 获取集合文档总数
            total = collection.count()
            if total == 0:
                print(f"  [BM25] 集合 [{collection_name}] 为空，跳过构建。")
                self._save_index(collection_name, [], [], [], [])
                self._cache[collection_name] = {
                    "bm25": None, "ids": [], "texts": [], "metadatas": []
                }
                return

            print(f"  [BM25] 集合共 {total} 条文档，开始拉取...")

            # ChromaDB get() 支持分批拉取，每批 500 条
            BATCH = 500
            offset = 0
            while offset < total:
                result = collection.get(
                    limit=BATCH,
                    offset=offset,
                    include=["documents", "metadatas"]
                )
                batch_docs = result.get("documents") or []
                batch_ids = result.get("ids") or []
                batch_metas = result.get("metadatas") or []

                ids.extend(batch_ids)
                texts.extend(batch_docs)
                # metadata 可能为 None，统一转为空字典
                metadatas.extend([m if m else {} for m in batch_metas])
                offset += BATCH

            print(f"  [BM25] 拉取完成，共 {len(ids)} 条，开始分词构建索引...")

        except Exception as e:
            print(f"  [BM25] 从 ChromaDB 读取失败（集合可能未创建）：{e}")
            # 保存空索引，后续检索返回空列表
            self._save_index(collection_name, [], [], [], [])
            self._cache[collection_name] = {
                "bm25": None, "ids": [], "texts": [], "metadatas": []
            }
            return

        # 对所有文档分词，构建 BM25 语料库
        corpus_tokenized: List[List[str]] = []
        for i, text in enumerate(texts):
            tokens = self._tokenize(text or "")
            # 空文档用占位符，避免 BM25Okapi 报错
            corpus_tokenized.append(tokens if tokens else ["__empty__"])
            if (i + 1) % 500 == 0:
                print(f"  [BM25] 已分词 {i + 1}/{len(texts)} 条...")

        # 保存到磁盘
        self._save_index(collection_name, corpus_tokenized, ids, texts, metadatas)

        # 更新内存缓存
        from rank_bm25 import BM25Okapi
        self._cache[collection_name] = {
            "bm25": BM25Okapi(corpus_tokenized),
            "ids": ids,
            "texts": texts,
            "metadatas": metadatas,
        }
        print(f"  [BM25] ✅ 集合 [{collection_name}] 索引构建完成！")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def build_all(self) -> None:
        """
        从三个 ChromaDB 集合重建所有 BM25 索引并持久化。

        通常在数据入库后调用一次，后续检索直接使用磁盘缓存。
        """
        print("[BM25] 开始重建全部索引...")
        for collection_name in COLLECTIONS:
            self._build_index_from_chroma(collection_name)
        print("[BM25] ✅ 全部索引重建完成！")

    def search(
        self,
        query: str,
        collection_name: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        在指定集合上执行 BM25 检索。

        返回格式与 retriever_rag._query_collection() 完全兼容：
            [{"text": str, "metadata": dict, "score": float, "collection": str}]

        其中 score 已归一化到 [0, 1] 区间（score / max_score）。

        Args:
            query           : 用户查询字符串
            collection_name : 目标集合名称（textbooks / exam_questions / key_points）
            n_results       : 返回结果数量，默认 5

        Returns:
            检索结果列表，按相关性降序排列；集合为空或无匹配时返回 []。
        """
        # 1. 确保索引已加载
        if not self._ensure_index(collection_name):
            logger.warning(f"[BM25] 集合 [{collection_name}] 无索引文件，请先调用 build_all()。")
            return []

        cache = self._cache.get(collection_name, {})
        bm25 = cache.get("bm25")
        texts = cache.get("texts", [])
        metadatas = cache.get("metadatas", [])

        # 2. 空集合直接返回
        if bm25 is None or not texts:
            return []

        # 3. 对 query 分词
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # 4. 计算 BM25 分数
        scores = bm25.get_scores(query_tokens)

        # 5. 取 top-n 索引（降序）
        import numpy as np
        top_n = min(n_results, len(scores))
        top_indices = np.argsort(scores)[::-1][:top_n]

        # 6. 归一化：score / max_score，防止除零
        max_score = float(scores[top_indices[0]]) if len(top_indices) > 0 else 1.0
        if max_score <= 0:
            # 所有分数均为 0，说明无相关文档
            return []

        # 7. 组装返回结果
        results: List[Dict[str, Any]] = []
        for idx in top_indices:
            raw_score = float(scores[idx])
            if raw_score <= 0:
                # 分数为 0 的文档不返回（与查询完全不相关）
                continue
            normalized_score = raw_score / max_score  # 归一化到 [0, 1]
            results.append({
                "text": texts[idx],
                "metadata": metadatas[idx] if idx < len(metadatas) else {},
                "score": normalized_score,
                "collection": collection_name,
            })

        return results


# ============================================================
# 模块级便捷实例（懒加载，供外部直接 import 使用）
# ============================================================
_default_retriever: BM25Retriever | None = None


def get_bm25_retriever() -> BM25Retriever:
    """获取全局 BM25Retriever 单例。"""
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = BM25Retriever()
    return _default_retriever


# ============================================================
# 简单自测（不依赖真实数据）
# ============================================================
if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("BM25Retriever 自测（不依赖真实 ChromaDB 数据）")
    print("=" * 60)

    # 使用临时目录避免污染正式索引
    with tempfile.TemporaryDirectory() as tmpdir:
        retriever = BM25Retriever(index_dir=tmpdir)

        # 构造模拟语料
        mock_texts = [
            "操作系统是管理计算机硬件与软件资源的系统软件",
            "进程是程序的一次执行过程，是系统进行资源分配的基本单位",
            "页式存储管理将内存划分为固定大小的页框",
            "文件系统负责管理磁盘上的文件和目录结构",
            "死锁是指多个进程相互等待对方释放资源的僵局状态",
        ]
        mock_ids = [f"doc_{i}" for i in range(len(mock_texts))]
        mock_metas = [{"subject": "操作系统", "source": "test.pdf", "page": i + 1} for i in range(len(mock_texts))]

        # 手动构建分词语料并保存，模拟 build_all() 的结果
        import jieba
        corpus_tokenized = [
            [t.strip() for t in jieba.cut(text, cut_all=False) if t.strip()]
            for text in mock_texts
        ]
        retriever._save_index("textbooks", corpus_tokenized, mock_ids, mock_texts, mock_metas)

        # 测试检索
        results = retriever.search("进程和操作系统", "textbooks", n_results=3)
        print(f"\n查询「进程和操作系统」→ 返回 {len(results)} 条结果：")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] score={r['score']:.4f} | {r['text'][:40]}...")

        # 测试空集合
        empty_results = retriever.search("测试", "exam_questions", n_results=5)
        print(f"\n空集合 exam_questions 查询 → 结果数：{len(empty_results)}（预期 0）")

        # 测试不存在集合
        no_results = retriever.search("网络", "key_points", n_results=3)
        print(f"未构建索引的集合 key_points 查询 → 结果数：{len(no_results)}（预期 0）")

    print("\n✅ BM25Retriever 自测通过！")
