"""
index_exam_questions.py — 历年真题 JSONL 入库脚本

使用方法：
    cd e:\\DEMO
    python scripts/index_exam_questions.py

功能：
    读取 storage/knowledge_base/exam_questions.jsonl 文件，
    将历年真题写入 ChromaDB（集合：exam_questions）。

JSONL 格式要求（每行一个 JSON 对象）：
    {
        "year": 2023,              // 年份（整数）
        "number": 15,              // 题号（整数）
        "subject": "数据结构",     // 科目
        "chapter": "第三章 栈和队列",  // 章节
        "topic": "栈的基本操作",   // 考点
        "type": "单选题",          // 题型：单选题/多选题/填空题/大题
        "difficulty": "medium",    // 难度：easy/medium/hard
        "question": "题目内容...", // 题目
        "options": {               // 选项（选择题必填，大题可为 {}）
            "A": "选项A内容",
            "B": "选项B内容",
            "C": "选项C内容",
            "D": "选项D内容"
        },
        "answer": "A",             // 答案
        "explanation": "解析..."   // 解析
    }

如果文件不存在，脚本将打印格式说明并退出，不会报错。
"""

import sys
import os
import time

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.rag.indexer import index_exam_jsonl

# ============================================================
# 真题 JSONL 文件路径（相对于项目根目录）
# ============================================================
EXAM_JSONL_PATH = "storage/knowledge_base/exam_questions.jsonl"


def print_format_guide():
    """打印 JSONL 格式说明，帮助用户准备数据。"""
    print("\n" + "=" * 60)
    print("📋 exam_questions.jsonl 格式说明")
    print("=" * 60)
    print("每行一个 JSON 对象，示例：")
    print("""
{
    "year": 2023,
    "number": 15,
    "subject": "数据结构",
    "chapter": "第三章 栈和队列",
    "topic": "栈的基本操作",
    "type": "单选题",
    "difficulty": "medium",
    "question": "以下关于栈的描述，正确的是？",
    "options": {
        "A": "栈是先进先出的数据结构",
        "B": "栈是后进先出的数据结构",
        "C": "栈只能用数组实现",
        "D": "栈的插入和删除可以在任意位置进行"
    },
    "answer": "B",
    "explanation": "栈是一种后进先出（LIFO）的线性数据结构..."
}
""")
    print("字段说明：")
    print("  year        : 考试年份（整数）")
    print("  number      : 题号（整数）")
    print("  subject     : 科目（数据结构/操作系统/计算机组成原理/计算机网络）")
    print("  chapter     : 所属章节")
    print("  topic       : 核心考点（用于检索匹配）")
    print("  type        : 题型（单选题/多选题/填空题/大题）")
    print("  difficulty  : 难度（easy/medium/hard）")
    print("  question    : 题目内容")
    print("  options     : 选项字典（大题可为空 {}）")
    print("  answer      : 答案")
    print("  explanation : 详细解析")
    print("=" * 60)
    print(f"\n请将文件放置在：{os.path.abspath(EXAM_JSONL_PATH)}")
    print("然后重新运行本脚本。\n")


def main():
    print("=" * 60)
    print("408 历年真题 JSONL 入库任务")
    print("=" * 60)

    # 检查文件是否存在
    jsonl_path = os.path.abspath(EXAM_JSONL_PATH)

    if not os.path.exists(jsonl_path):
        print(f"\n⚠️  真题文件不存在：{jsonl_path}")
        print("请先准备真题数据文件。")
        print_format_guide()
        sys.exit(0)  # 正常退出（不是错误），等待用户准备数据

    # 文件存在，开始入库
    file_size_kb = os.path.getsize(jsonl_path) / 1024
    print(f"\n找到真题文件：{jsonl_path}")
    print(f"文件大小：{file_size_kb:.1f} KB")

    # 统计行数（预览）
    with open(jsonl_path, "r", encoding="utf-8") as f:
        line_count = sum(1 for line in f if line.strip())
    print(f"有效数据行：约 {line_count} 条\n")

    start = time.time()
    try:
        index_exam_jsonl(jsonl_path)
        elapsed = time.time() - start
        print(f"\n⏱️  总耗时：{elapsed:.1f} 秒")
        print("✅ 历年真题入库完成！")
        print("数据已持久化到 storage/chroma_db（集合：exam_questions）")
    except Exception as e:
        print(f"\n❌ 入库失败：{e}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
