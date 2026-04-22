"""
pdf_parser.py — PDF 文档解析模块
使用 PyMuPDF (fitz) 逐页提取文本，返回带结构的字典列表。

依赖：pip install pymupdf
"""

import os
import fitz  # PyMuPDF


def parse_pdf(pdf_path: str) -> list[dict]:
    """
    解析 PDF 文件，逐页提取文字内容。

    Args:
        pdf_path: PDF 文件的完整路径

    Returns:
        list[dict]，每个元素包含：
            - page   (int)  : 页码，从 1 开始
            - text   (str)  : 该页的文本内容（已去除首尾空白）
            - source (str)  : 文件名（不含路径），作为文档来源标识

    示例返回：
        [
            {"page": 1, "text": "第一章 绪论...", "source": "2025王道数据结构.pdf"},
            {"page": 2, "text": "...", "source": "2025王道数据结构.pdf"},
        ]
    """
    # 检查文件是否存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    # 提取文件名（不含目录路径），用作 source 字段
    source_name = os.path.basename(pdf_path)

    results = []

    try:
        # 打开 PDF 文档
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"  [PDF解析] 文件：{source_name}，共 {total_pages} 页")

        for page_num in range(total_pages):
            page = doc[page_num]

            # 提取该页文本，使用 "text" 模式（保留换行，去除图片）
            text = page.get_text("text")

            # 去除首尾空白，跳过空页
            text = text.strip()
            if not text:
                continue

            results.append({
                "page": page_num + 1,   # 页码从 1 开始，更符合习惯
                "text": text,
                "source": source_name
            })

        doc.close()
        print(f"  [PDF解析] 完成，有效页数：{len(results)} 页")

    except fitz.FileDataError as e:
        raise ValueError(f"PDF 文件损坏或格式不支持：{pdf_path}\n错误：{e}")
    except Exception as e:
        raise RuntimeError(f"解析 PDF 时发生未知错误：{pdf_path}\n错误：{e}")

    return results
