"""
build_bm25_index.py — 一键构建 BM25 稀疏检索索引

使用方法：
    cd /d E:\\DEMO
    python scripts/build_bm25_index.py

功能：
    从 ChromaDB 三个集合（textbooks / exam_questions / key_points）
    读取全量文档，用 jieba 分词构建 BM25 索引，持久化到：
        storage/bm25_index/textbooks.json
        storage/bm25_index/exam_questions.json
        storage/bm25_index/key_points.json

注意：
    - 每次新增/更新知识库文档后需重新运行本脚本
    - 首次运行时会自动下载 jieba 词典（约 3-5 秒）
    - 索引构建完成后 RAG 管线自动切换到混合检索模式
"""

import sys
import os
import time

# 将项目根目录加入 sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    print("=" * 60)
    print("🔧 BM25 稀疏检索索引构建工具")
    print("=" * 60)

    # 检查依赖
    try:
        import jieba
        from rank_bm25 import BM25Okapi
        print("✅ 依赖检查：rank-bm25 + jieba 已安装")
    except ImportError as e:
        print(f"❌ 缺少依赖：{e}")
        print("   请运行：pip install rank-bm25>=0.2.2 jieba>=0.42.1")
        sys.exit(1)

    # 检查 ChromaDB
    try:
        from memory.rag.indexer import get_chroma_client, COLLECTION_TEXTBOOKS
        client = get_chroma_client()
        print("✅ ChromaDB 连接正常")
    except Exception as e:
        print(f"❌ ChromaDB 连接失败：{e}")
        sys.exit(1)

    # 检查集合数量
    try:
        from memory.rag.indexer import (
            COLLECTION_TEXTBOOKS, COLLECTION_EXAM, COLLECTION_KEYPOINTS,
            _get_embedding_fn
        )
        collections_info = {}
        for coll_name in [COLLECTION_TEXTBOOKS, COLLECTION_EXAM, COLLECTION_KEYPOINTS]:
            try:
                coll = client.get_collection(coll_name, embedding_function=_get_embedding_fn())
                count = coll.count()
                collections_info[coll_name] = count
                print(f"  📚 {coll_name}: {count} 条文档")
            except Exception:
                collections_info[coll_name] = 0
                print(f"  ⚠️  {coll_name}: 集合不存在（跳过）")
    except Exception as e:
        print(f"❌ 获取集合信息失败：{e}")
        sys.exit(1)

    total_docs = sum(collections_info.values())
    if total_docs == 0:
        print("\n⚠️  所有集合均为空，请先运行入库脚本（如 scripts/index_textbooks.py）")
        print("   BM25 索引将构建空索引文件（不影响使用，但 BM25 路不会有结果）")

    # 构建索引
    print(f"\n🚀 开始构建 BM25 索引（共 {total_docs} 条文档）...")
    start_time = time.time()

    from memory.rag.bm25_retriever import BM25Retriever
    retriever = BM25Retriever()
    retriever.build_all()

    elapsed = time.time() - start_time

    # 验证索引文件
    index_dir = os.path.join(_ROOT, "storage", "bm25_index")
    print(f"\n📁 索引文件（{index_dir}）：")
    for fname in os.listdir(index_dir):
        fpath = os.path.join(index_dir, fname)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  {fname}  ({size_kb:.1f} KB)")

    print(f"\n✅ BM25 索引构建完成！耗时 {elapsed:.1f} 秒")
    print("   RAG 管线已自动启用混合检索模式（向量 + BM25 + RRF 融合）")
    print("\n💡 提示：每次更新知识库后，请重新运行本脚本以同步 BM25 索引")


if __name__ == "__main__":
    main()
