"""
index_textbooks.py — 王道 PPT（PDF格式）批量入库脚本

使用方法：
    cd e:\\DEMO
    python scripts/index_textbooks.py

功能：
    将 E:\\408\\408 下各科目的章节 PPT PDF 文件批量解析入库 ChromaDB。
    王道教材大PDF为扫描图片版，无法提取文字，改用章节PPT PDF（文字版）。
    入库路径：storage/chroma_db（集合：textbooks）

注意：
    - 首次运行需要 ChromaDB 下载本地 embedding 模型（约几百MB），请确保网络畅通。
    - 入库完成后数据持久化，后续无需重复运行。
"""

import sys
import os
import time
import glob

# 将项目根目录加入 sys.path，使得 memory.rag 等包可以被 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.rag.indexer import index_pdf

# CS408 高质量笔记 PDF：(路径, 科目)
CS408_PDFS = [
    ("E:/408/CS408/DataStructure/数据结构.pdf",         "数据结构"),
    ("E:/408/CS408/OperatingSystem/操作系统.pdf",        "操作系统"),
    ("E:/408/CS408/ComputerOrganization/计算机组成原理.pdf", "计算机组成原理"),
    ("E:/408/CS408/ComputerNetwork/计算机网络.pdf",      "计算机网络"),
]


def main():
    print("=" * 60)
    print("408 CS408 高质量笔记 PDF 入库任务启动")
    print("来源：E:/408/CS408（文字版精炼总结笔记）")
    print("=" * 60)

    total_start = time.time()
    success_count = 0
    fail_count = 0

    for idx, (pdf_path, subject) in enumerate(CS408_PDFS, start=1):
        fname = os.path.basename(pdf_path)
        print(f"\n[{idx}/{len(CS408_PDFS)}] {fname}（{subject}）")

        if not os.path.exists(pdf_path):
            print(f"  ⚠️  文件不存在，跳过")
            fail_count += 1
            continue

        start = time.time()
        try:
            index_pdf(pdf_path, subject, collection_name="textbooks")
            elapsed = time.time() - start
            print(f"  ⏱️  {elapsed:.1f}s")
            success_count += 1
        except Exception as e:
            print(f"  ❌ 失败：{e}")
            fail_count += 1

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print(f"✅ 入库完成！成功 {success_count} 个，失败 {fail_count} 个")
    print(f"⏱️  总耗时：{total_elapsed:.1f} 秒")
    print("数据已持久化到 storage/chroma_db（集合：textbooks）")
    print("=" * 60)


if __name__ == "__main__":
    main()
