"""
lc_tools.py — LangChain Tool 规范的工具定义

使用 @tool 装饰器将所有工具包装为 LangChain StructuredTool，
供 LangGraph 节点识别和调用。

原工具实现逻辑仍在 agent/tools.py 中，本文件只做适配层。
"""

import json
from typing import Optional
from langchain_core.tools import tool


@tool
def explain_concept_tool(topic: str, depth: str = "beginner") -> str:
    """讲解408考研知识点。适用于用户提问知识点解释、概念理解的场景。"""
    from agent.tools import execute_tool
    return execute_tool("explain_concept", json.dumps({"topic": topic, "depth": depth}))


@tool
def generate_quiz_tool(topic: str, difficulty: str = "easy") -> str:
    """针对某个知识点生成练习题。适用于用户要求出题、练习、测验的场景。"""
    from agent.tools import execute_tool
    return execute_tool("generate_quiz", json.dumps({"topic": topic, "difficulty": difficulty}))


@tool
def check_answer_tool(question: str, user_answer: str, correct_answer: str = "") -> str:
    """检查用户对某道题的回答是否正确，给出详细反馈。适用于用户提交答案、判断对错的场景。"""
    from agent.tools import execute_tool
    return execute_tool(
        "check_answer",
        json.dumps({"question": question, "user_answer": user_answer, "correct_answer": correct_answer})
    )


@tool
def recommend_next_tool() -> str:
    """根据当前学习情况推荐接下来应该学什么。适用于用户询问复习建议、接下来学什么的场景。"""
    from agent.tools import execute_tool
    return execute_tool("recommend_next", json.dumps({}))


@tool
def save_study_plan_tool(plan_name: str, tasks: list) -> str:
    """保存或更新用户的学习/复习计划。适用于用户要创建、制定、安排学习计划的场景。"""
    from agent.tools import execute_tool
    return execute_tool("save_study_plan", json.dumps({"plan_name": plan_name, "tasks": tasks}))


@tool
def read_study_plan_tool(plan_name: str = "") -> str:
    """读取用户当前的学习计划，查看进度。适用于用户查看计划、查询进度的场景。"""
    from agent.tools import execute_tool
    return execute_tool("read_study_plan", json.dumps({"plan_name": plan_name}))


@tool
def complete_task_tool(plan_name: str, task_index: int) -> str:
    """将学习计划中的某个任务标记为已完成。适用于用户完成任务、更新进度的场景。"""
    from agent.tools import execute_tool
    return execute_tool("complete_task", json.dumps({"plan_name": plan_name, "task_index": task_index}))


# 所有工具列表，供图节点注册和绑定
TOOLS_LIST = [
    explain_concept_tool,
    generate_quiz_tool,
    check_answer_tool,
    recommend_next_tool,
    save_study_plan_tool,
    read_study_plan_tool,
    complete_task_tool,
]

# 工具名称到工具实例的映射（工具函数名 → 工具对象）
_TOOL_NAME_MAP: dict = {
    "explain_concept":  explain_concept_tool,
    "generate_quiz":    generate_quiz_tool,
    "check_answer":     check_answer_tool,
    "recommend_next":   recommend_next_tool,
    "save_study_plan":  save_study_plan_tool,
    "read_study_plan":  read_study_plan_tool,
    "complete_task":    complete_task_tool,
}


def get_tool_by_name(name: str):
    """通过工具名称（原始名称，如 'explain_concept'）查找对应的 LangChain Tool 对象。

    Args:
        name: 工具名称，支持原始名称（explain_concept）或带 _tool 后缀（explain_concept_tool）

    Returns:
        LangChain Tool 对象；未找到时返回 None。
    """
    # 先按原始名称查（explain_concept → explain_concept_tool）
    tool_obj = _TOOL_NAME_MAP.get(name)
    if tool_obj is not None:
        return tool_obj
    # 再尝试带 _tool 后缀的名称（向后兼容）
    bare = name.removesuffix("_tool")
    return _TOOL_NAME_MAP.get(bare)
