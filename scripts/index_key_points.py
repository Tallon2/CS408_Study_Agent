"""
index_key_points.py — CS408 高质量 Markdown 笔记入库脚本

使用方法：
    cd e:\\DEMO
    python scripts/index_key_points.py

功能：
    将 E:\\408\\CS408 下四科完整 Markdown 笔记（DataStructure.md 等）
    按标题切片后写入 ChromaDB（集合：key_points）。
    这份笔记是精炼版考研总结，质量优于分章节版。
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.rag.indexer import index_markdown

# CS408 高质量 Markdown 笔记：(路径, 科目)
CS408_MARKDOWNS = [
    ("E:/408/CS408/DataStructure/DataStructure.md",               "数据结构"),
    ("E:/408/CS408/OperatingSystem/OperatingSystem.md",            "操作系统"),
    ("E:/408/CS408/ComputerOrganization/ComputerOrganization.md",  "计算机组成原理"),
    ("E:/408/CS408/ComputerNetwork/ComputerNetwork.md",            "计算机网络"),
]


def main():
    print("=" * 60)
    print("408 CS408 高质量 Markdown 笔记入库任务启动")
    print("来源：E:/408/CS408（四科完整精炼总结笔记）")
    print("=" * 60)

    total_start = time.time()
    success_count = 0
    fail_count = 0

    for idx, (md_path, subject) in enumerate(CS408_MARKDOWNS, start=1):
        fname = os.path.basename(md_path)
        print(f"\n[{idx}/{len(CS408_MARKDOWNS)}] {fname}（{subject}）")

        if not os.path.exists(md_path):
            print(f"  ⚠️  文件不存在，跳过")
            fail_count += 1
            continue

        try:
            index_markdown(md_path, subject)
            success_count += 1
        except Exception as e:
            print(f"  ❌ 入库失败：{e}")
            fail_count += 1

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print(f"✅ 入库完成！成功 {success_count} 个，失败 {fail_count} 个")
    print(f"⏱️  总耗时：{total_elapsed:.1f} 秒")
    print("数据已持久化到 storage/chroma_db（集合：key_points）")
    print("=" * 60)


if __name__ == "__main__":
    main()