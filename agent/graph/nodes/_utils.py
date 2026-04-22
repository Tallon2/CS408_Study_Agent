"""
agent/graph/nodes/_utils.py — 图节点公共工具函数

职责：
  - 清洗 LLM 回复中的特殊标记（[隐藏答案]、[工具指令] 等）
  - 格式化消息历史
  - 被多个节点 import 使用

设计约束：
  - 纯函数，无副作用
  - 不依赖任何外部 API（不调用 LLM、DB、文件系统）
  - 不得 import agent/ 以外的 memory/rag/ 模块（保持节点层内聚）
"""
from __future__ import annotations

import re
from typing import Any


def clean_llm_reply(text: str) -> str:
    """清洗 LLM 回复中的内部标记，返回用户可见的干净文本。

    处理的标记类型：
      - [隐藏答案]...[/隐藏答案]  — 测验答案占位块
      - [隐藏-仅供判答]...[/隐藏] — 供判答节点读取的隐藏答案
      - [工具指令]...              — 工具分发指令前缀行
    """
    # 移除 [隐藏答案]...[/隐藏答案] 整块
    text = re.sub(r'\[隐藏答案\].*?\[/隐藏答案\]', '', text, flags=re.DOTALL)
    # 移除 [隐藏-仅供判答]...[/隐藏] 整块
    text = re.sub(r'\[隐藏-仅供判答\].*?\[/隐藏\]', '', text, flags=re.DOTALL)
    # 移除 [工具指令] 前缀行（行首出现，移除整行）
    text = re.sub(r'^\[工具指令\][^\n]*\n?', '', text, flags=re.MULTILINE)
    return text.strip()


def extract_correct_answer(tool_result: str) -> str:
    """从工具结果中提取正确答案标记。

    Args:
        tool_result: 工具返回的原始字符串，可能包含
                     [隐藏-仅供判答]正确答案=X[/隐藏] 标记。

    Returns:
        提取到的选项字母（'A'~'D'），未找到时返回空字符串 ""。
    """
    m = re.search(r'\[隐藏-仅供判答\]正确答案=([A-D])\[/隐藏\]', tool_result)
    return m.group(1) if m else ""


def format_rag_context_for_prompt(rag_context: str) -> str:
    """将 RAG 上下文包装为 prompt 中的引用块格式。

    Args:
        rag_context: RAG 检索返回的原始文本，可以为空字符串。

    Returns:
        包装后的引用块字符串；若输入为空则返回空字符串 ""。
    """
    if not rag_context:
        return ""
    return (
        f"\n\n【以下是来自知识库的参考资料，请基于这些内容回答】\n"
        f"{rag_context}\n"
    )


def format_messages_for_display(messages: list[dict[str, Any]]) -> str:
    """将消息历史列表格式化为可读的多行文本（调试/日志用途）。

    Args:
        messages: [{"role": "user"|"assistant"|"tool", "content": "..."}, ...]

    Returns:
        格式化后的多行字符串。
    """
    role_label = {"user": "👤 用户", "assistant": "🤖 助手", "tool": "🔧 工具"}
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        label = role_label.get(role, role)
        # 内容过长时截断，避免日志爆炸
        preview = content[:200] + ("…" if len(content) > 200 else "")
        lines.append(f"[{label}] {preview}")
    return "\n".join(lines)
