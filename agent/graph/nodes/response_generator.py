"""
response_generator.py — 回复生成节点

功能：整合 RAG 上下文 + 工具结果 + 记忆上下文，调用 LLM 生成最终回复。
回复写入 state["final_response"]，同时追加到 state["messages"]。
"""

from core.llm_client import get_llm_client
from agent.graph.state import AgentState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


_BASE_SYSTEM = (
    "你是一个专业的计算机408考研学习助手，擅长数据结构、操作系统、计算机组成原理和计算机网络。\n"
    "请根据用户的问题，结合提供的参考资料（如有），给出准确、清晰、有教学价值的回答。\n"
    "语言风格：亲切而专业，适合备考学生。\n"
    "【重要规则】当收到包含「[工具指令]」的消息时，必须严格按照指令内容执行，不得自行发挥或改编。"
)

# 判断 tool_result 是否是出题类指令（需要严格遵守原文）
def _is_quiz_tool(tool_result: str) -> bool:
    return "[工具指令]" in tool_result and "展示内容" in tool_result

# 判断 tool_result 是否是判答类指令（需要严格遵守对错判断）
def _is_check_answer_tool(tool_name: str, tool_result: str) -> bool:
    return tool_name == "check_answer" and "[工具指令]" in tool_result

# 从 tool_result 中提取隐藏的正确答案
def _extract_hidden_answer(tool_result: str) -> str:
    import re
    m = re.search(r'\[隐藏-仅供判答\]正确答案=([A-D])\[/隐藏\]', tool_result)
    return m.group(1) if m else ""


def _strip_hidden_markers(text: str) -> str:
    """从 tool_result 中移除不应展示给用户的元标记，只保留展示内容。"""
    import re
    # 移除隐藏答案行（如 [隐藏-仅供判答]正确答案=D[/隐藏]）
    text = re.sub(r'\[隐藏-仅供判答\].*?\[/隐藏\]', '', text)
    # 移除展示内容边界标记
    text = re.sub(r'===展示内容(?:开始|结束)===\s*', '', text)
    return text.strip()


def _clean_final_response(text: str) -> str:
    """兜底清洗 LLM 输出，移除可能泄露的内部标记。"""
    import re
    # 移除隐藏答案标记
    text = re.sub(r'\[隐藏-仅供判答\].*?\[/隐藏\]', '', text)
    # 移除展示内容边界标记
    text = re.sub(r'===展示内容(?:开始|结束)===\s*', '', text)
    # 移除工具指令标记
    text = re.sub(r'\[工具指令\].*?\n', '', text)
    # 移除隐藏答案的其他变体（如 [隐藏答案]...[/隐藏答案]）
    text = re.sub(r'\[隐藏答案\].*?\[/隐藏答案\]', '', text)
    # 清理多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ============================================================
# 消息构建（核心实现，被 response_generator_node 和 response_generator_stream 共用）
# ============================================================

def build_llm_messages(state: AgentState) -> tuple[list[dict], float]:
    """
    从 state 构建 LLM 消息列表和 temperature。

    这是消息构建的唯一实现。response_generator_node（非流式）和
    response_generator_stream（流式）均调用此函数，不再维护两份逻辑。

    Returns:
        (llm_messages, temperature) 二元组：
            - llm_messages : list[dict]，符合 ZhipuAI chat API 格式的消息列表
            - temperature  : float，推荐的采样温度（出题时 0.1，其他 0.7）
    """
    rag_context = state.get("rag_context", "") or ""
    tool_result = state.get("tool_result", "") or ""
    tool_name   = state.get("tool_name", "") or ""
    memory_l2 = state.get("memory_l2") or {}
    memory_l4 = state.get("memory_l4") or {}

    is_strict_quiz = _is_quiz_tool(tool_result)
    supplement_parts = []

    if rag_context:
        supplement_parts.append(f"【知识库参考资料（RAG检索）】\n{rag_context}")

    is_check_answer = _is_check_answer_tool(tool_name, tool_result)

    if tool_result and not is_strict_quiz and not is_check_answer:
        supplement_parts.append(f"【工具执行结果】\n{tool_result}")

    blockers = memory_l2.get("blockers", [])
    if blockers:
        blockers_text = "；".join(str(b) for b in blockers[:5])
        supplement_parts.append(f"【用户当前学习卡点（L2）】\n{blockers_text}")

    knowledge_graph = memory_l4.get("knowledge_graph", {})
    if knowledge_graph:
        weak_nodes = [k for k, v in knowledge_graph.items() if isinstance(v, (int, float)) and v < 0.5]
        if weak_nodes:
            supplement_parts.append(f"【用户薄弱知识点（L4）】\n{', '.join(weak_nodes[:10])}")

    system_content = _BASE_SYSTEM
    if supplement_parts:
        system_content += "\n\n" + "\n\n".join(supplement_parts)

    llm_messages = [{"role": "system", "content": system_content}]

    for msg in state.get("messages", []):
        if isinstance(msg, HumanMessage):
            llm_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            llm_messages.append({"role": "assistant", "content": msg.content})

    if is_strict_quiz and tool_result:
        clean_tool_result = _strip_hidden_markers(tool_result)
        llm_messages.append({
            "role": "user",
            "content": (
                f"【系统指令 - 必须严格执行，不得自行创作】\n"
                f"{clean_tool_result}\n\n"
                f"再次强调：请直接展示上方真题原文，第一行必须是来源标签，不允许自己编题或改编。"
                f"不要输出任何内部标记、隐藏答案或分隔符。"
            )
        })

    if is_check_answer and tool_result:
        llm_messages.append({
            "role": "user",
            "content": (
                f"【系统指令 - 判答结果已由系统确定，你必须严格遵守以下判断，不得更改对错结论】\n\n"
                f"{tool_result}\n\n"
                f"再次强调：对错判断已经确定，你只需要按照上面的要求生成友好的解释回复。"
                f'如果上面说"回答错误"，你绝对不能说"回答正确"或"恭喜"。'
                f'如果上面说"回答正确"，你绝对不能说"回答错误"。'
            )
        })

    temperature = 0.1 if is_strict_quiz else 0.7
    return llm_messages, temperature


# ============================================================
# 图节点（非流式）
# ============================================================

def response_generator_node(state: AgentState) -> AgentState:
    """回复生成节点：整合上下文调用 LLM 生成最终回复，写入 state['final_response']。

    消息构建逻辑统一委托给 build_llm_messages()，避免代码重复。
    """
    # ── 委托 build_llm_messages 构建消息列表（单一实现）────────
    llm_messages, temperature = build_llm_messages(state)

    # ── 提取辅助状态（用于 quiz_answer 管理）────────────────────
    tool_result = state.get("tool_result", "") or ""
    tool_name   = state.get("tool_name", "") or ""
    is_strict_quiz = _is_quiz_tool(tool_result)

    # ── 调用 GLM ──────────────────────────────────────────────
    final_response = ""
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=client.default_model,
            messages=llm_messages,
            temperature=temperature,
            stream=False,
        )
        final_response = resp.choices[0].message.content.strip()
        # 兜底清洗：移除 LLM 可能泄露的内部标记
        final_response = _clean_final_response(final_response)
    except Exception as e:
        final_response = f"抱歉，生成回复时出现错误：{e}"

    # ── 写回 state ────────────────────────────────────────────
    new_messages = list(state.get("messages", [])) + [AIMessage(content=final_response)]

    # 出题后把正确答案存入 state，供下一轮 check_answer 使用
    # 判答后清空答案，防止后续消息被误判为答题
    quiz_answer = state.get("current_quiz_answer", "")
    if is_strict_quiz and tool_result:
        # 出题：提取并保存正确答案
        extracted = _extract_hidden_answer(tool_result)
        if extracted:
            quiz_answer = extracted
    elif tool_name == "check_answer":
        # 判答完成：清空正确答案（一题一答，用完即弃）
        quiz_answer = ""

    return {
        **state,
        "final_response": final_response,
        "messages": new_messages,
        "current_quiz_answer": quiz_answer,
    }


# ============================================================
# 流式生成函数（供 chat_stream 使用，逐 token yield）
# ============================================================

def response_generator_stream(state: AgentState):
    """
    流式回复生成器（generator）：逐 token yield 字符串。
    
    与 response_generator_node 逻辑完全一致，区别在于使用 stream=True，
    逐个 token yield，让前端实时显示打字效果。
    
    Yields:
        str: 每个 LLM 输出的 token 片段
    
    最终返回时 yield 一个特殊 dict 信号标记完成：
        {"__done__": True, "full_response": str, "quiz_answer": str}
    """
    llm_messages, temperature = build_llm_messages(state)
    
    tool_result = state.get("tool_result", "") or ""
    tool_name   = state.get("tool_name", "") or ""
    is_strict_quiz = _is_quiz_tool(tool_result)

    full_response = ""
    try:
        client = get_llm_client()
        stream = client.chat.completions.create(
            model=client.default_model,
            messages=llm_messages,
            temperature=temperature,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield token  # 逐 token yield

    except Exception as e:
        error_msg = f"抱歉，生成回复时出现错误：{e}"
        full_response = error_msg
        yield error_msg

    # 兜底清洗
    full_response = _clean_final_response(full_response)

    # 计算 quiz_answer
    quiz_answer = state.get("current_quiz_answer", "")
    if is_strict_quiz and tool_result:
        extracted = _extract_hidden_answer(tool_result)
        if extracted:
            quiz_answer = extracted
    elif tool_name == "check_answer":
        quiz_answer = ""

    # 最后 yield 完成信号
    yield {"__done__": True, "full_response": full_response, "quiz_answer": quiz_answer}
