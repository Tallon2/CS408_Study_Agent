# -*- coding: utf-8 -*-
"""
agent/tools 包入口 — 原 agent/tools.py 内容已合并至此

该包将 agent/tools.py 中的工具逐步拆分为独立模块，
对外保持向后兼容的导入接口。

已提取的子模块：
  - agent.tools.quiz     → generate_quiz 工具及其 Schema 定义
  - agent.tools.registry → TOOL_REGISTRY + execute_tool_from_registry

向后兼容：
  from agent.tools import TOOL_DEFINITIONS, execute_tool  ✓
  from agent.tools.quiz import generate_quiz, QUIZ_TOOL_DEFINITION  ✓
"""

# ── 子模块导入（quiz 与 registry 均为独立模块，本文件不重复实现）──
from agent.tools.quiz import generate_quiz, QUIZ_TOOL_DEFINITION
from agent.tools.registry import (
    TOOL_REGISTRY,
    execute_tool_from_registry,
    PLANS_DIR,
    _get_rag_context,
    _save_study_plan,
    _read_study_plan,
    _complete_task,
    _format_plan,
)

import json

# ============================================================
# 工具定义：告诉 LLM "你有哪些工具可以用，每个工具是干什么的"
# ============================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "explain_concept",
            "description": "解释一个编程知识点，可指定难度深度",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "知识点名称，例如：装饰器、闭包、列表推导式"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced"],
                        "description": "讲解深度"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "针对某个知识点生成一道练习题，帮助用户检验掌握程度",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "出题的知识点"
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "题目难度"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_answer",
            "description": "检查用户对某道题的回答是否正确，给出详细反馈",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "题目内容"
                    },
                    "user_answer": {
                        "type": "string",
                        "description": "用户的回答"
                    }
                },
                "required": ["question", "user_answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_next",
            "description": "根据当前学习情况，推荐用户接下来应该学什么",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_study_plan",
            "description": "保存或更新用户的学习/复习计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "计划名称，如：408总复习计划、数据结构第一轮"
                    },
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "任务内容"},
                                "deadline": {"type": "string", "description": "截止日期，如 2026-05-01"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                            },
                            "required": ["task"]
                        },
                        "description": "任务列表"
                    }
                },
                "required": ["plan_name", "tasks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_study_plan",
            "description": "读取用户当前的学习计划，查看进度",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "要查看的计划名称，不填则查看所有计划"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "将学习计划中的某个任务标记为已完成",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {"type": "string", "description": "计划名称"},
                    "task_index": {"type": "integer", "description": "任务序号（从1开始）"}
                },
                "required": ["plan_name", "task_index"]
            }
        }
    }
]


# ============================================================
# 工具执行入口：委托给 registry.execute_tool_from_registry
# 单一真实来源原则：所有工具实现均在 registry.py / quiz.py 中
# ============================================================
def execute_tool(name: str, arguments: str, state: dict = None) -> str:
    """
    执行工具调用，返回结果字符串给 LLM。

    向后兼容入口：将 JSON 字符串 arguments 解析后委托给
    execute_tool_from_registry()，实现集中在 registry.py。

    Args:
        name      : 工具名
        arguments : JSON 格式的参数字符串
        state     : 当前 AgentState 字典（可为 None）
    """
    args = json.loads(arguments) if arguments else {}
    return execute_tool_from_registry(name, args, state)


__all__ = [
    # 核心导出
    "TOOL_DEFINITIONS",
    "execute_tool",
    # registry 透传（向后兼容）
    "TOOL_REGISTRY",
    "execute_tool_from_registry",
    "_get_rag_context",
    "_save_study_plan",
    "_read_study_plan",
    "_complete_task",
    "_format_plan",
    "PLANS_DIR",
    # quiz 子模块（向后兼容）
    "generate_quiz",
    "QUIZ_TOOL_DEFINITION",
]