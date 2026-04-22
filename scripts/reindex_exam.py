"""
reindex_exam.py
重新将 exam_questions.jsonl 索引进 ChromaDB。
先删除旧集合（如存在），再全量写入。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from memory.rag.indexer import (
    CHROMA_PATH,
    COLLECTION_EXAM,
    index_exam_jsonl,
    _get_collection,
)

JSONL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "knowledge_base", "exam_questions.jsonl"
)

def main():
    # 1. 删除旧集合（幂等）
    try:
        client = chromadb.PersistentClient(CHROMA_PATH)
        client.delete_collection(COLLECTION_EXAM)
        print(f"[清理] 已删除旧集合 [{COLLECTION_EXAM}]")
    except Exception as e:
        print(f"[清理] 集合不存在或删除失败（忽略）：{e}")

    # 2. 重新入库
    print(f"\n[重索引] 开始写入：{JSONL_PATH}")
    index_exam_jsonl(JSONL_PATH)
    print("\n[完成] exam_questions 集合已重建。")


if __name__ == "__main__":
    main()
