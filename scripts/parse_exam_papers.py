"""
parse_exam_papers.py — 408 历年真题 PDF 解析脚本（含答案合并版）

使用方法：
    cd e:\\DEMO
    python scripts/parse_exam_papers.py              # 解析所有年份
    python scripts/parse_exam_papers.py --debug 2023 # 调试单年，打印前3题详情

功能：
    1. 从 E:\\408\\cs-408\\408真题\\2009-2023真题\\ 读取试题 PDF
    2. 从 E:\\408\\cs-408\\408真题\\2009-2023答案\\ 读取答案 PDF
    3. 解析选择题（1-40题）+ 对应答案/解析
    4. 合并输出到 storage/knowledge_base/exam_questions.jsonl

输出 JSONL 格式（每行一个 JSON 对象）：
    {
        "year": 2023,
        "number": 1,
        "subject": "待标注",
        "chapter": "待标注",
        "topic": "待标注",
        "type": "选择题",
        "question": "题目文字...",
        "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "answer": "D",
        "explanation": "线性表的顺序存储结构...",
        "difficulty": "medium",
        "knowledge_points": []
    }
"""

import os
import re
import sys
import json
import glob

# ============================================================
# 配置常量
# ============================================================

# 试题 PDF 所在目录
# 试题来源：papers-rebuild 目录（2009-2025全部文字版，质量更高）
PAPER_DIR = r"E:\408\408-exam-paper\papers-rebuild"

# 答案 PDF 所在目录
ANSWER_DIR = r"E:\408\cs-408\408真题\2009-2023答案"

# 解析年份范围
YEAR_START = 2009
YEAR_END = 2025   # papers-rebuild 目录有到 2025 年

# 输出文件路径（相对于项目根目录）
OUTPUT_JSONL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "knowledge_base", "exam_questions.jsonl"
)

# ============================================================
# 水印/页眉清洗模式
# ============================================================

# 页眉行：含「计算机学科专业基础综合」或「年全国硕士」的行整行删除
_HEADER_LINE_PATS = [
    re.compile(r'[^\n]*\d{4}\s*年全国硕士[^\n]*', re.UNICODE),
    re.compile(r'[^\n]*计算机学科专业基础综合[^\n]*', re.UNICODE),
    re.compile(r'[^\n]*计算机学科专业基础[^\n]*', re.UNICODE),
    # 页码：- 数字 - 或 第X页
    re.compile(r'(?m)^\s*-\s*\d+\s*-\s*$'),
    re.compile(r'(?m)^\s*第\s*\d+\s*页\s*$'),
]

# 水印文字（答案 PDF 中常见，整段替换为空）
_WATERMARK_PATS = [
    re.compile(r'研芝士计算机考研[^\n]*', re.UNICODE),
    re.compile(r'芝士[^\n]{0,20}考研[^\n]*', re.UNICODE),
    re.compile(r'版权所有[^\n]*', re.UNICODE),
]


# ============================================================
# 文字清洗工具函数
# ============================================================

def clean_text(raw: str, remove_watermarks: bool = False) -> str:
    """
    清洗从 PDF 提取的原始文字：
    1. 去除页眉/页脚（含年份考试名称的行）
    2. 可选去除答案 PDF 中的水印文字
    3. 统一换行符、压缩多余空白
    4. 去除每行首尾空格
    """
    text = raw

    # 去除页眉/页脚行
    for pat in _HEADER_LINE_PATS:
        text = pat.sub('', text)

    # 可选：去除水印（答案 PDF）
    if remove_watermarks:
        for pat in _WATERMARK_PATS:
            text = pat.sub('', text)

    # 统一换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # 压缩连续多个换行为最多两个
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 压缩行内连续空白（保留换行）
    text = re.sub(r'[^\S\n]+', ' ', text)

    # 去除每行首尾空格
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


def normalize_punctuation(text: str) -> str:
    """
    将全角句点（．\uFF0E）统一成半角句点（.），方便后续正则匹配题号和选项。
    注意：不替换中文句号（。）——题目内容里的句号保持原样。
    """
    text = text.replace('\uff0e', '.')   # ．→ .
    text = text.replace('\uff0c', ',')   # ，→ ,（选项分隔有时用全角逗号）
    return text


def clean_inline(text: str) -> str:
    """
    清洗单题/选项内联文字：
    - 换行替换为空格（题目/选项不跨段落）
    - 压缩连续空白为单个空格
    - 去除首尾空白
    """
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ============================================================
# PDF 文字提取
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    用 PyMuPDF (fitz) 提取 PDF 所有页面文字，合并为单个字符串。
    各页之间插入双换行作为视觉分隔。

    Args:
        pdf_path: PDF 文件的绝对路径

    Returns:
        合并后的原始文字

    Raises:
        ImportError: 未安装 PyMuPDF
        FileNotFoundError: 文件不存在
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("未找到 PyMuPDF，请先安装：pip install pymupdf")

    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    pages_text = []
    doc = fitz.open(pdf_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            # "text" 模式：保留换行，按阅读顺序排列
            page_text = page.get_text("text")
            pages_text.append(page_text)
    finally:
        doc.close()

    return '\n\n'.join(pages_text)


# ============================================================
# 试题 PDF 文件名模糊匹配
# ============================================================

def find_paper_pdf(year: int) -> str:
    """
    用 glob 模糊匹配试题 PDF 路径，兼容两种文件名格式：
      - {year}计算机考研408真题.pdf
      - {year}年计算机考研408真题.pdf

    Args:
        year: 年份整数

    Returns:
        匹配到的第一个 PDF 绝对路径，未找到返回空字符串
    """
    patterns = [
        os.path.join(PAPER_DIR, f"{year}.pdf"),
        os.path.join(PAPER_DIR, f"{year}计算机考研408真题.pdf"),
        os.path.join(PAPER_DIR, f"{year}年计算机考研408真题.pdf"),
        # 兜底：年份开头的任意 pdf
        os.path.join(PAPER_DIR, f"{year}*.pdf"),
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return ''


def find_answer_pdf(year: int) -> str:
    """
    用 glob 模糊匹配答案 PDF 路径，兼容：
      - {year}答案.pdf
      - {year}年答案.pdf
      - {year}*.pdf（兜底）

    Args:
        year: 年份整数

    Returns:
        匹配到的第一个 PDF 绝对路径，未找到返回空字符串
    """
    patterns = [
        os.path.join(ANSWER_DIR, f"{year}答案.pdf"),
        os.path.join(ANSWER_DIR, f"{year}年答案.pdf"),
        os.path.join(ANSWER_DIR, f"{year}*.pdf"),
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return ''


# ============================================================
# 试题解析函数
# ============================================================

def extract_choice_section(full_text: str) -> str:
    """
    从完整试卷文字中截取「单项选择题」区域。

    策略：
    1. 找「一、单项选择题」（或变体）的位置
    2. 截取到「二、」（下一大题标题）之前

    Returns:
        选择题区域文字，找不到返回空字符串
    """
    # 选择题标题：支持「一、单项选择题」「一,单项选择题」等变体
    start_pat = re.compile(
        r'(?:一[、，,.]|（一）|[\(（]\s*一\s*[\)）])\s*单[项]?选择题[^\n]*',
        re.UNICODE
    )

    # 下一大题标题（二、）作为截止标志
    end_pat = re.compile(
        r'(?:二[、，,.]|（二）|[\(（]\s*二\s*[\)）])\s*[^\n]{0,40}',
        re.UNICODE
    )

    start_match = start_pat.search(full_text)
    if not start_match:
        # 兜底：直接找「单项选择题」
        start_pat2 = re.compile(r'单项选择题[^\n]*', re.UNICODE)
        start_match = start_pat2.search(full_text)
        if not start_match:
            return ''

    start_pos = start_match.end()
    search_area = full_text[start_pos:]

    end_match = end_pat.search(search_area)
    if end_match:
        choice_section = search_area[:end_match.start()]
    else:
        # 找不到「二、」，截取前 10000 字符（约 40 题的合理上限）
        choice_section = search_area[:10000]

    return choice_section


def split_questions(choice_text: str) -> list:
    """
    将选择题区域文字按题号分割，返回 (题号, 原始文字块) 列表。

    题号模式：行首 1-40 的数字 + ．或 . 或 、
    只取题号在 1-40 范围内的条目。

    Returns:
        list of (num: int, raw_block: str)，按题号升序
    """
    # 题号正则：行首（允许少量缩进），数字1-40，后跟 ．.、
    # 支持前导零格式：01. 02. 等（2021/2022年试卷）
    question_split_pat = re.compile(
        r'(?m)(?:^|\n)\s{0,4}(0?(?:[1-9]|[1-3][0-9]|40))[．\.、]\s*',
        re.UNICODE
    )

    matches = list(question_split_pat.finditer(choice_text))
    if not matches:
        return []

    questions = []
    for i, m in enumerate(matches):
        try:
            num = int(m.group(1).lstrip('0') or '0')
        except ValueError:
            continue

        # 只处理 1-40 题
        if not (1 <= num <= 40):
            continue

        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(choice_text)
        raw_block = choice_text[content_start:content_end]
        questions.append((num, raw_block))

    return questions


def parse_options(block: str) -> tuple:
    """
    从单题文字块中分离题目正文和 ABCD 四个选项。

    选项标识模式：行首（允许少量缩进）的 A/B/C/D，后跟 ．.、 或至少两个空格。

    Args:
        block: 单题文字块（已去除题号前缀）

    Returns:
        (question_text: str, options: dict{'A':..., 'B':..., 'C':..., 'D':...})
        缺失的选项键填空字符串
    """
    # 选项分隔符正则：行首字母 A/B/C/D + ．.、 或 2+空格
    option_pat = re.compile(
        r'(?:^|\n)\s{0,4}([ABCD])[．\.、]\s*|(?:^|\n)\s{0,4}([ABCD])\s{2,}',
        re.UNICODE
    )

    opt_matches = []
    for m in option_pat.finditer(block):
        letter = m.group(1) or m.group(2)
        if letter in ('A', 'B', 'C', 'D'):
            opt_matches.append((letter, m.start(), m.end()))

    options = {'A': '', 'B': '', 'C': '', 'D': ''}

    if not opt_matches:
        # 没找到选项，整个 block 当作题目
        return clean_inline(block), options

    # 题目正文 = 第一个选项之前的内容
    question_text = clean_inline(block[:opt_matches[0][1]])

    # 依次提取每个选项内容
    for idx, (letter, _, content_start) in enumerate(opt_matches):
        content_end = opt_matches[idx + 1][1] if idx + 1 < len(opt_matches) else len(block)
        options[letter] = clean_inline(block[content_start:content_end])

    return question_text, options


# ============================================================
# 答案解析函数
# ============================================================

def parse_answer_pdf(year: int) -> dict:
    """
    解析单年答案 PDF，返回 {题号(int): {'answer': str, 'explanation': str}} 的映射。

    支持的答案格式：
      主格式：数字[．.、] 【参考答案】X  + 【解析】...
      兼容1：数字. X（如 "1. A"）
      兼容2：答案：X 在某些版本中出现

    答案 PDF 结构：通常只含选择题部分，但也可能混有大题答案，
    只取题号 1-40 范围内的条目。

    Returns:
        dict，键为题号(int)，值为 {'answer': str, 'explanation': str}
        解析失败返回空 dict
    """
    answer_path = find_answer_pdf(year)
    if not answer_path:
        print(f"  ⚠️  [{year}] 未找到答案 PDF，answer/explanation 字段留空。")
        return {}

    try:
        raw_text = extract_text_from_pdf(answer_path)
    except Exception as e:
        print(f"  ⚠️  [{year}] 读取答案 PDF 失败：{e}")
        return {}

    # 清洗：去页眉 + 去水印
    cleaned = clean_text(raw_text, remove_watermarks=True)
    normalized = normalize_punctuation(cleaned)

    # 截取选择题答案部分（「一、单项选择题」之后）
    # 答案 PDF 通常结构和试卷类似，先尝试截取
    choice_ans_section = _extract_answer_choice_section(normalized)

    # 在选择题区域内提取答案
    answers = _extract_answers_from_text(choice_ans_section or normalized)

    return answers


def _extract_answer_choice_section(full_text: str) -> str:
    """
    从答案 PDF 全文中截取选择题答案区域。
    策略：找「一、单项选择题」到「二、」之间，找不到就返回全文。

    Returns:
        选择题答案区域文字
    """
    # 先找选择题标题
    start_pat = re.compile(
        r'(?:一[、，,.]|（一）)\s*单[项]?选择题[^\n]*',
        re.UNICODE
    )
    start_match = start_pat.search(full_text)

    if not start_match:
        # 有些答案 PDF 直接从 "1." 开始，不含大题标题
        return full_text

    start_pos = start_match.end()
    search_area = full_text[start_pos:]

    # 截止：「二、」大题
    end_pat = re.compile(
        r'(?:二[、，,.]|（二）)\s*[^\n]{0,40}',
        re.UNICODE
    )
    end_match = end_pat.search(search_area)
    if end_match:
        return search_area[:end_match.start()]
    return search_area


def _extract_answers_from_text(text: str) -> dict:
    """
    从答案文字中提取题号→答案字母和解析文字。

    支持三种格式（按优先级尝试）：

    格式A（主格式）：
        1．【参考答案】D
        【解析】线性表的...

    格式B（精简格式）：
        1. D
        或 1．D
        后跟解析文字（不含「【参考答案】」）

    格式C（混合格式）：
        1. 答案：D  解析：...

    Returns:
        {题号(int): {'answer': str, 'explanation': str}}
    """
    results = {}

    # ── 格式A：【参考答案】标记格式 ──
    # 先尝试提取所有「N．【参考答案】X」位置
    ans_pat_a = re.compile(
        r'(\d+)[．\.、]\s*【参考答案】\s*([ABCD])',
        re.UNICODE
    )
    # 解析段提取：【解析】后的内容，到下一道题的「N．【参考答案】」或文本末尾
    expl_pat_a = re.compile(
        r'【解析】(.*?)(?=\d+[．\.、]\s*【参考答案】|\Z)',
        re.UNICODE | re.DOTALL
    )

    ans_matches_a = list(ans_pat_a.finditer(text))

    if ans_matches_a:
        # 构建解析映射（题号 → 解析文字）
        expl_map = {}
        expl_matches = list(expl_pat_a.finditer(text))
        for i, ans_m in enumerate(ans_matches_a):
            num = int(ans_m.group(1))
            if not (1 <= num <= 40):
                continue
            answer_letter = ans_m.group(2).strip().upper()

            # 找对应的解析（在答案位置之后、下一个答案之前的【解析】）
            ans_end = ans_m.end()
            ans_next_start = ans_matches_a[i + 1].start() if i + 1 < len(ans_matches_a) else len(text)
            segment = text[ans_end:ans_next_start]

            expl_text = ''
            expl_m = re.search(r'【解析】(.*)', segment, re.DOTALL | re.UNICODE)
            if expl_m:
                expl_text = clean_inline(expl_m.group(1))

            results[num] = {'answer': answer_letter, 'explanation': expl_text}

        if results:
            return results

    # ── 格式B：简洁格式「N. X」或「N．X」，每题一行 ──
    # 匹配：数字 + 分隔符 + 空格* + 单字母答案（后跟空格/换行/解析）
    ans_pat_b = re.compile(
        r'(?m)^(\d+)[．\.、]\s*([ABCD])(?:\s|$)',
        re.UNICODE
    )
    ans_matches_b = list(ans_pat_b.finditer(text))

    if ans_matches_b:
        for i, m in enumerate(ans_matches_b):
            num = int(m.group(1))
            if not (1 <= num <= 40):
                continue
            answer_letter = m.group(2).strip().upper()

            # 尝试提取该条目后的解析（到下一条目之前）
            seg_start = m.end()
            seg_end = ans_matches_b[i + 1].start() if i + 1 < len(ans_matches_b) else len(text)
            segment = text[seg_start:seg_end]

            expl_text = ''
            # 格式B中解析可能跟在答案后面（无【解析】标记）
            expl_inline = re.search(r'【解析】(.*)', segment, re.DOTALL | re.UNICODE)
            if expl_inline:
                expl_text = clean_inline(expl_inline.group(1))
            elif segment.strip():
                expl_text = clean_inline(segment.strip())

            results[num] = {'answer': answer_letter, 'explanation': expl_text}

        if results:
            return results

    # ── 格式C：「答案：X」形式 ──
    ans_pat_c = re.compile(
        r'(\d+)[．\.、][^\n]*答案[：:]\s*([ABCD])',
        re.UNICODE
    )
    for m in ans_pat_c.finditer(text):
        num = int(m.group(1))
        if not (1 <= num <= 40):
            continue
        results[num] = {'answer': m.group(2).strip().upper(), 'explanation': ''}
    if results:
        return results

    # ── 格式D：「01. B。【解析】...」（2022/2021年格式，答案后接中文句号）──
    ans_pat_d = re.compile(
        r'(?m)^(0?\d+)[\.、]\s*([ABCD])[。．]',
        re.UNICODE
    )
    matches_d = list(ans_pat_d.finditer(text))
    if matches_d:
        for i, m in enumerate(matches_d):
            num_str = m.group(1).lstrip('0') or '0'
            num = int(num_str)
            if not (1 <= num <= 40):
                continue
            seg_start = m.end()
            seg_end = matches_d[i + 1].start() if i + 1 < len(matches_d) else len(text)
            segment = text[seg_start:seg_end]
            expl_m = re.search(r'【解析】(.*)', segment, re.DOTALL | re.UNICODE)
            expl_text = expl_m.group(1).strip() if expl_m else segment.strip()
            # 清洗解析文字
            expl_text = re.sub(r'\s+', ' ', expl_text).strip()
            results[num] = {'answer': m.group(2).upper(), 'explanation': expl_text}

    return results


# ============================================================
# 单年合并解析入口
# ============================================================

def parse_year(year: int, debug: bool = False) -> list:
    """
    解析单个年份的试题 PDF + 答案 PDF，返回合并后的结构化记录列表。

    流程：
    1. 用 glob 模糊匹配找到试题 PDF
    2. 提取文字 → 清洗 → 定位选择题区域 → 按题号分割 → 解析选项
    3. 解析答案 PDF，得到答案+解析映射
    4. 按题号合并，生成最终记录

    Args:
        year: 考试年份（如 2023）
        debug: 调试模式，打印详细信息

    Returns:
        list of dict，每个 dict 对应一道选择题
    """
    # ── 1. 找到试题 PDF ──
    paper_path = find_paper_pdf(year)
    if not paper_path:
        print(f"  ⚠️  [{year}] 未找到试题 PDF，跳过。")
        return []

    if debug:
        print(f"  [DEBUG] 试题 PDF：{paper_path}")

    # ── 2. 提取并清洗试题文字 ──
    try:
        raw_text = extract_text_from_pdf(paper_path)
    except Exception as e:
        print(f"  ❌  [{year}] 读取试题 PDF 失败：{e}")
        return []

    cleaned = clean_text(raw_text)
    normalized = normalize_punctuation(cleaned)

    if debug:
        print(f"  [DEBUG] 原始文字长度：{len(raw_text)}，清洗后：{len(normalized)}")

    # ── 3. 定位选择题区域 ──
    choice_section = extract_choice_section(normalized)
    if not choice_section:
        print(f"  ⚠️  [{year}] 未找到「单项选择题」区域，跳过。")
        return []

    if debug:
        print(f"  [DEBUG] 选择题区域长度：{len(choice_section)}")
        print(f"  [DEBUG] 选择题区域前200字符：\n{choice_section[:200]}\n")

    # ── 4. 按题号分割 ──
    raw_questions = split_questions(choice_section)
    if not raw_questions:
        print(f"  ⚠️  [{year}] 未能分割出任何题目，跳过。")
        return []

    if debug:
        print(f"  [DEBUG] 分割出 {len(raw_questions)} 个题目块")

    # ── 5. 解析答案 PDF ──
    answers_map = parse_answer_pdf(year)
    if debug:
        print(f"  [DEBUG] 答案 PDF 解析结果：{len(answers_map)} 道题有答案")

    # ── 6. 逐题解析并合并 ──
    results = []
    for (num, block) in raw_questions:
        try:
            question_text, options = parse_options(block)

            # 跳过题目内容为空的记录（可能是误匹配）
            if not question_text:
                continue

            # 从答案映射中取该题的答案和解析
            ans_data = answers_map.get(num, {})
            answer_letter = ans_data.get('answer', '')
            explanation = ans_data.get('explanation', '')

            record = {
                "year": year,
                "number": num,
                "subject": "待标注",
                "chapter": "待标注",
                "topic": "待标注",
                "type": "选择题",
                "question": question_text,
                "options": {
                    "A": options.get("A", ""),
                    "B": options.get("B", ""),
                    "C": options.get("C", ""),
                    "D": options.get("D", ""),
                },
                "answer": answer_letter,
                "explanation": explanation,
                "difficulty": "medium",
                "knowledge_points": []
            }
            results.append(record)

            # 调试模式：打印前3题完整内容
            if debug and num <= 3:
                print(f"\n  [DEBUG] === 第{num}题 ===")
                print(f"  题目：{question_text[:100]}...")
                print(f"  A: {options.get('A', '')[:60]}")
                print(f"  B: {options.get('B', '')[:60]}")
                print(f"  C: {options.get('C', '')[:60]}")
                print(f"  D: {options.get('D', '')[:60]}")
                print(f"  答案：{answer_letter}")
                print(f"  解析：{explanation[:100]}...")

        except Exception as e:
            # 单题解析失败：保存已有字段，跳过报错继续
            print(f"  ⚠️  [{year}] 第{num}题解析异常，已跳过：{e}")
            continue

    return results


# ============================================================
# 调试模式入口
# ============================================================

def debug_single_year(year: int):
    """
    调试单个年份，打印详细的解析过程和前3题完整内容。
    触发方式：python scripts/parse_exam_papers.py --debug YEAR
    """
    print("=" * 60)
    print(f"调试模式：解析 {year} 年试卷")
    print("=" * 60)

    records = parse_year(year, debug=True)

    print()
    print(f"共解析 {len(records)} 道选择题")
    has_answer = sum(1 for r in records if r['answer'])
    print(f"有答案：{has_answer} 道，无答案：{len(records) - has_answer} 道")
    print()

    if records:
        print("── 前3题完整记录 ──")
        for rec in records[:3]:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            print()


# ============================================================
# 主函数
# ============================================================

def main():
    """
    主流程：解析 2009-2023 年所有试题和答案 PDF，合并输出 JSONL。
    """
    print("=" * 60)
    print("408 真题解析任务启动（含答案解析）")
    print("=" * 60)
    print(f"试题目录：{PAPER_DIR}")
    print(f"答案目录：{ANSWER_DIR}")
    print(f"解析年份：{YEAR_START}-{YEAR_END}（共 {YEAR_END - YEAR_START + 1} 年）")
    print(f"输出文件：{OUTPUT_JSONL}")
    print()

    # ── 检查 PyMuPDF ──
    try:
        import fitz
        print(f"PyMuPDF 版本：{fitz.version[0]}")
    except ImportError:
        print("❌ 错误：未安装 PyMuPDF，请先运行：pip install pymupdf")
        sys.exit(1)

    print()

    # ── 创建输出目录 ──
    output_dir = os.path.dirname(OUTPUT_JSONL)
    os.makedirs(output_dir, exist_ok=True)

    all_records = []
    success_years = []
    failed_years = []

    years = list(range(YEAR_START, YEAR_END + 1))

    for year in years:
        paper_path = find_paper_pdf(year)
        if not paper_path:
            print(f"[{year}] ⚠️  未找到试题 PDF，跳过")
            failed_years.append((year, "试题 PDF 不存在"))
            continue

        print(f"[{year}] 处理中 ... ", end="", flush=True)

        try:
            records = parse_year(year, debug=False)
            if records:
                all_records.extend(records)
                success_years.append(year)
                has_ans = sum(1 for r in records if r['answer'])
                print(f"✅ 解析 {len(records)} 道，其中有答案 {has_ans} 道")
            else:
                failed_years.append((year, "未解析到任何题目"))
                print("⚠️  未解析到任何题目")
        except Exception as e:
            print(f"❌ 解析失败：{e}")
            failed_years.append((year, str(e)))

    # ── 写出 JSONL ──
    print()
    print(f"正在写出 {len(all_records)} 条记录 → {OUTPUT_JSONL}")

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── 汇总统计 ──
    total_q = len(all_records)
    has_answer_count = sum(1 for r in all_records if r['answer'])
    no_answer_count = total_q - has_answer_count

    print()
    print("=" * 60)
    print("408 真题解析完成（含答案解析）")
    print(f"来源：E:\\408\\cs-408\\408真题")
    print(f"年份：{YEAR_START}-{YEAR_END}（共 {YEAR_END - YEAR_START + 1} 年）")
    print(f"成功解析：{total_q} 道选择题（含答案 {has_answer_count} 道，无答案 {no_answer_count} 道）")
    print(f"输出文件：{OUTPUT_JSONL}")
    if failed_years:
        print(f"失败/跳过年份（{len(failed_years)} 年）：")
        for y, reason in failed_years:
            print(f"    {y}: {reason}")
    print("=" * 60)


# ============================================================
# 脚本入口
# ============================================================

if __name__ == "__main__":
    # 支持 --debug YEAR 参数
    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--debug":
        try:
            debug_year = int(args[1])
        except ValueError:
            print(f"❌ 无效的年份参数：{args[1]}")
            sys.exit(1)
        debug_single_year(debug_year)
    else:
        main()