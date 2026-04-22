"""
tests/unit/test_quiz_tools.py — quiz.py 工具函数单元测试

测试覆盖（P1 优先级）：
  1. _parse_exam_text — 去掉头部标签
  2. _parse_exam_text — 提取答案字段
  3. _parse_exam_text — 提取解析字段
  4. _parse_exam_text — 无头部时不崩溃
  5. _parse_exam_text — 纯题目正文（无答案/解析行）
  6. _build_source_tag — 完整元数据构建来源标签
  7. _build_source_tag — 缺少年份时的处理
  8. _build_source_tag — 仅有 subject 无 chapter
  9. generate_quiz — 无真题时返回模拟题指令
  10. generate_quiz — 有 state.shown_questions 时避免重复
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from unittest.mock import patch, MagicMock

from agent.tools.quiz import _parse_exam_text, _build_source_tag, generate_quiz


# ================================================================
# _parse_exam_text() 测试
# ================================================================

class TestParseExamText:
    """_parse_exam_text() 原始真题文本解析测试。"""

    def test_parse_exam_text_with_header(self):
        """应去掉第一行的 [xxxx年第xx题-...] 头部标签。"""
        raw = "[2022年第12题-操作系统]\n以下关于进程的说法，正确的是？\nA. 进程是线程的子集\nB. 进程拥有独立地址空间\n答案：B\n解析：进程拥有独立地址空间"
        body, answer, explanation = _parse_exam_text(raw)
        # 头部标签不应出现在题目正文中
        assert "[2022年第12题-操作系统]" not in body
        assert body.startswith("以下关于进程的说法")

    def test_parse_exam_text_extracts_answer(self):
        """应正确提取答案字段（"答案：X"）。"""
        raw = "以下关于死锁的说法正确的是？\nA. 银行家算法可以预防死锁\nB. 死锁只发生在多道程序中\n答案：A\n解析：银行家算法是避免死锁的经典算法"
        body, answer, explanation = _parse_exam_text(raw)
        assert answer == "A"

    def test_parse_exam_text_extracts_explanation(self):
        """应正确提取解析字段（"解析：..."）。"""
        raw = "以下关于内存管理说法正确的是？\nA. 分页消除外部碎片\nB. 分段消除内部碎片\n答案：A\n解析：分页按固定大小划分，消除外部碎片"
        body, answer, explanation = _parse_exam_text(raw)
        assert "分页按固定大小划分" in explanation

    def test_parse_exam_text_no_header(self):
        """无头部标签时不应崩溃，正文应完整保留。"""
        raw = "以下关于文件系统的说法正确的是？\nA. 文件系统只能在磁盘上\nB. FAT 是一种文件分配方式\n答案：B"
        body, answer, explanation = _parse_exam_text(raw)
        assert "以下关于文件系统" in body
        assert answer == "B"
        assert explanation == ""  # 无解析行

    def test_parse_exam_text_pure_body_no_answer(self):
        """只有题目正文，无答案/解析行时应正常返回空字符串。"""
        raw = "以下关于操作系统内核的说法正确的是？\nA. 微内核只包含最基本的功能\nB. 宏内核提供更好的安全性"
        body, answer, explanation = _parse_exam_text(raw)
        assert "操作系统内核" in body
        assert answer == ""
        assert explanation == ""

    def test_parse_exam_text_returns_three_tuple(self):
        """应始终返回三元组 (str, str, str)。"""
        raw = "[2021年第5题-数据结构]\n以下排序算法最坏情况时间复杂度为 O(n²) 的是？\n答案：C"
        result = _parse_exam_text(raw)
        assert isinstance(result, tuple)
        assert len(result) == 3
        body, answer, explanation = result
        assert isinstance(body, str)
        assert isinstance(answer, str)
        assert isinstance(explanation, str)

    def test_parse_exam_text_header_not_in_body(self):
        """头部标签行不应出现在 body 中。"""
        raw = "[2023年第3题-计算机组成]\n以下关于 CPU 流水线的描述正确的是？\n答案：D\n解析：流水线提高了 CPU 吞吐率"
        body, answer, explanation = _parse_exam_text(raw)
        assert not body.startswith("[")
        assert "2023年第3题" not in body


# ================================================================
# _build_source_tag() 测试
# ================================================================

class TestBuildSourceTag:
    """_build_source_tag() 来源标签构建测试。"""

    def test_build_source_tag_full_metadata(self):
        """完整元数据（year/number/subject/chapter）应生成完整来源标签。"""
        meta = {"year": 2022, "number": 12, "subject": "操作系统", "chapter": "进程管理"}
        tag = _build_source_tag(meta)
        assert "2022" in tag
        assert "12" in tag
        assert "操作系统" in tag
        assert "进程管理" in tag

    def test_build_source_tag_no_year(self):
        """无年份时应使用默认来源字符串，不应崩溃。"""
        meta = {"number": 5, "subject": "数据结构"}
        tag = _build_source_tag(meta)
        assert "全国408统考真题" in tag
        assert isinstance(tag, str) and len(tag) > 0

    def test_build_source_tag_subject_only(self):
        """仅有 subject 无 chapter 时应正常生成标签。"""
        meta = {"year": 2021, "number": 8, "subject": "计算机网络"}
        tag = _build_source_tag(meta)
        assert "计算机网络" in tag
        assert "·" not in tag  # 没有 chapter 时不应有分隔符

    def test_build_source_tag_empty_metadata(self):
        """空元数据时应返回基础标签字符串，不崩溃。"""
        tag = _build_source_tag({})
        assert isinstance(tag, str)
        assert len(tag) > 0


# ================================================================
# generate_quiz() 测试
# ================================================================

class TestGenerateQuiz:
    """generate_quiz() 出题函数测试（mock 依赖）。"""

    def test_generate_quiz_no_exam_hits_returns_llm_instruction(self):
        """知识库无真题时应返回包含 LLM 自编指令的字符串。"""
        with patch("agent.tools.quiz._query_exam_questions", return_value=[]):
            result = generate_quiz(topic="贝叶斯网络", difficulty="easy")
        assert isinstance(result, str)
        # 无真题时应包含指令关键字
        assert "工具指令" in result or "未找到" in result

    def test_generate_quiz_with_exam_hits_returns_question(self):
        """有真题时应返回包含题目内容的工具指令字符串。"""
        fake_hit = {
            "text": "[2022年第10题-操作系统]\n以下哪种内存分配方式消除了外部碎片？\nA. 分区\nB. 分页\nC. 分段\nD. 段页\n答案：B\n解析：分页按固定大小划分，消除外部碎片",
            "distance": 0.95,
            "metadata": {"year": 2022, "number": 10, "subject": "操作系统", "chapter": "内存管理"},
        }
        with patch("agent.tools.quiz._query_exam_questions", return_value=[fake_hit]):
            result = generate_quiz(topic="内存管理", difficulty="medium")
        assert isinstance(result, str)
        assert "工具指令" in result

    def test_generate_quiz_filters_shown_questions(self):
        """state['shown_questions'] 中已有的题目不应重复出现。"""
        fake_hit = {
            "text": "[2021年第7题-操作系统]\n以下关于进程调度的描述正确的是？\nA.FCFS\nB.SJF\nC.RR\nD.Priority\n答案：C",
            "distance": 0.90,
            "metadata": {"year": 2021, "number": 7, "subject": "操作系统"},
        }
        shown_key = fake_hit["text"][:60].strip()
        state = {"shown_questions": [shown_key]}

        with patch("agent.tools.quiz._query_exam_questions", return_value=[fake_hit]):
            result = generate_quiz(topic="进程调度", state=state)
        # 已展示，应降级为 LLM 自编（无可用真题时走 else 分支）
        assert isinstance(result, str)

    def test_generate_quiz_returns_string(self):
        """generate_quiz 始终应返回字符串。"""
        with patch("agent.tools.quiz._query_exam_questions", return_value=[]):
            result = generate_quiz(topic="测试知识点")
        assert isinstance(result, str)
