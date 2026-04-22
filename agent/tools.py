# agent/tools.py - thin shim; all logic lives in agent/tools package
from agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    _get_rag_context,
    _save_study_plan,
    _read_study_plan,
    _complete_task,
    _format_plan,
    PLANS_DIR,
    generate_quiz,
    QUIZ_TOOL_DEFINITION,
)
