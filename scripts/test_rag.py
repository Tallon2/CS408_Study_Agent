"""
test_rag.py — RAG 管线端到端测试脚本
测试向量检索、Rerank、以及完整的 retrieve() 函数
"""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb

SEP = "=" * 60

# ── 1. 基础连通性 ──
print(SEP)
print("【测试1】ChromaDB 集合状态")
print(SEP)
try:
    c = chromadb.PersistentClient(path="storage/chroma_db")
    cols = c.list_collections()
    if not cols:
        print("❌ 没有任何集合，请先运行入库脚本")
        sys.exit(1)
    for col in cols:
        print(f"  ✅ {col.name}: {col.count()} 条")
except Exception:
    traceback.print_exc()
    sys.exit(1)

# ── 2. Embedding 函数测试 ──
print()
print(SEP)
print("【测试2】智谱 embedding-3 向量化")
print(SEP)
try:
    from memory.rag.indexer import _get_embedding_fn
    fn = _get_embedding_fn()
    vec = fn(["快速排序的时间复杂度"])
    print(f"  ✅ 向量维度：{len(vec[0])}，前5维：{[round(v,4) for v in vec[0][:5]]}")
except Exception:
    traceback.print_exc()
    print("  ❌ embedding 调用失败，检查 API_KEY 和网络")
    sys.exit(1)

# ── 3. 单集合检索 ──
print()
print(SEP)
print("【测试3】单集合检索（key_points）")
print(SEP)
try:
    from memory.rag.retriever_rag import _query_collection
    hits = _query_collection("key_points", "快速排序时间复杂度", n_results=3)
    if not hits:
        print("  ⚠️  返回空，可能 embedding 不匹配或集合为空")
    for i, h in enumerate(hits):
        print(f"  [{i+1}] dist={h['distance']:.3f} | {h['metadata'].get('section','')[:35]}")
        print(f"       {h['text'][:100]}")
except Exception:
    traceback.print_exc()

# ── 4. 真题检索 ──
print()
print(SEP)
print("【测试4】真题集合检索（exam_questions）")
print(SEP)
try:
    hits = _query_collection("exam_questions", "快速排序", n_results=3)
    if not hits:
        print("  ⚠️  返回空")
    for i, h in enumerate(hits):
        print(f"  [{i+1}] dist={h['distance']:.3f} | {h['metadata'].get('year','')}年 {h['metadata'].get('subject','')}")
        print(f"       {h['text'][:120]}")
except Exception:
    traceback.print_exc()

# ── 5. 完整 retrieve() 含 Rerank ──
print()
print(SEP)
print("【测试5】完整 retrieve()（多集合 + LLM Rerank）")
print(SEP)
try:
    from memory.rag.retriever_rag import retrieve
    result = retrieve("快速排序最坏情况的时间复杂度是多少", top_k=3)
    if not result:
        print("  ⚠️  返回空字符串")
    else:
        print(result[:600])
except Exception:
    traceback.print_exc()

# ── 6. 真题专项检索 ──
print()
print(SEP)
print("【测试6】真题专项检索 retrieve_exam_questions()")
print(SEP)
try:
    from memory.rag.retriever_rag import retrieve_exam_questions
    result = retrieve_exam_questions("TCP三次握手", top_k=2)
    if not result:
        print("  ⚠️  返回空字符串")
    else:
        print(result[:500])
except Exception:
    traceback.print_exc()

print()
print(SEP)
print("测试完成")
print(SEP)
