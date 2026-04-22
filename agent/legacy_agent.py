"""
agent/legacy_agent.py — 旧版 Function Calling Agent（已废弃，仅供向后兼容）

⚠️  DEPRECATED：本模块保留旧版 LearningAgent（直接调 LLM 的 Function Calling 实现）。
    新代码请使用 agent.main_agent.LangGraphAgent，
    或通过 agent.runtime.get_or_create_session() 获取会话实例。

迁移来源：agent/main_agent.py 第 33-259 行
"""

import warnings
import json
from core.llm_client import get_llm_client
from agent.tools import TOOL_DEFINITIONS, execute_tool
from memory.l1_session import SessionManager

# SYSTEM_PROMPT 原定义在 main_agent.py，此处复用相同内容保持一致
SYSTEM_PROMPT = """你是一个专业的计算机考研（408）学习助手，帮助用户备考数据结构、操作系统、计算机组成原理、计算机网络四门科目。

你的行为规范：
1. 当用户想了解某个知识点、请求解释或梳理考点时 → 必须调用 explain_concept 工具
2. 当用户想做题、测试自己、出题时 → 必须调用 generate_quiz 工具
3. 当用户回答了题目 → 必须调用 check_answer 工具判断对错
4. 当用户问"接下来复习什么"或需要学习建议时 → 必须调用 recommend_next 工具

严格禁止：
- 禁止在回复文本中写出任何工具名称（如 generate_quiz、explain_concept 等）
- 禁止在回复文本中输出 JSON 格式内容
- 禁止模拟工具调用，必须通过 Function Calling 机制真正调用工具
- 禁止在 explain_concept 回答末尾自行附加"相关真题"、"练习题"等内容，出题必须由用户主动触发 generate_quiz
- 在工具返回结果之前，不要提前输出题目或解释内容

其他注意事项：
- 回答基于工具返回的【参考资料】，内容要严谨准确，符合408考试风格
- 如果参考资料中有历年真题，优先展示真实真题而非自编题目
- 语气友好，鼓励为主，适当提醒易错点
- 可以用类比帮助理解，但结论必须以参考资料为准
"""


class LearningAgent:
    """
    旧版主 Agent 类，负责：
    1. 维护对话历史（messages 列表）
    2. 调用 LLM（智谱 AI）
    3. 处理 Function Calling 工具调用
    4. 预留 hook 入口供后续阶段扩展

    类比 Java：这是一个有状态的 Service 类

    .. deprecated::
        LearningAgent 已废弃，请改用 agent.main_agent.LangGraphAgent。
        该类保留仅为向后兼容，后续版本可能移除。

        迁移方式::

            # 旧用法（已废弃）
            from agent.legacy_agent import LearningAgent
            agent = LearningAgent(user_id)

            # 新用法
            from agent.runtime import get_or_create_session
            session = get_or_create_session(user_id)
            reply = session.agent.chat(user_message)
    """

    def __init__(self, user_id: str):
        warnings.warn(
            "LearningAgent 已废弃，请改用 agent.main_agent.LangGraphAgent "
            "或 agent.runtime.get_or_create_session()。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.user_id = user_id
        self.client = get_llm_client()
        self.session = SessionManager(user_id)

        # ✅ SessionStart Hook：自动注入记忆
        from memory.retrieval import build_memory_context
        memory_context = build_memory_context(user_id)
        system_prompt = SYSTEM_PROMPT
        if memory_context:
            system_prompt = SYSTEM_PROMPT + f"\n\n{memory_context}"
            print("🧠 已加载历史记忆\n")

        # messages 是对话历史，LLM 每次都能看到完整上下文
        # 类比 Java：这是一个 List<Message>，贯穿整个会话
        self.messages = [{"role": "system", "content": system_prompt}]
        print(f"🤖 Agent 初始化完成，用户：{user_id}")

    def chat(self, user_message: str) -> str:
        """
        核心对话方法：
        1. 把用户消息加入历史
        2. 请求 LLM（带工具定义）
        3. 如果 LLM 决定调用工具 → 执行工具 → 把结果再给 LLM → 得到最终回复
        4. 如果 LLM 直接回答 → 直接返回

        这个"工具调用 → 再次请求 LLM"的模式就是 Function Calling 的核心流程
        """
        # Step 1: 记录用户消息
        self.session.log_user_message(user_message)
        self.messages.append({"role": "user", "content": user_message})

        # 第一轮对话时，用用户问题做语义检索补充相关历史
        if len(self.messages) == 2:  # system + 第一条user
            try:
                from memory.retrieval import build_memory_context
                extra = build_memory_context(self.user_id, current_question=user_message)
                if extra:
                    # 追加到 system prompt
                    self.messages[0]["content"] += f"\n\n{extra}"
            except Exception:
                pass

        # Step 2: 第一次请求 LLM（带工具列表）
        response = self.client.chat.completions.create(
            model=self.client.default_model,
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"   # auto = LLM 自己决定要不要用工具
        )

        msg = response.choices[0].message

        # Step 3: 判断 LLM 是否决定调用工具
        if msg.tool_calls:
            # LLM 决定调用工具，把这条消息加入历史
            # ⚠️ 必须转成字典格式，不能直接 append SDK 对象
            self.messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })

            # 执行所有工具调用（LLM 可能同时调用多个工具）
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments
                print(f"   🔧 调用工具: {tool_name}")

                result = execute_tool(tool_name, tool_args)
                self.session.log_tool_call(tool_name, json.loads(tool_args) if tool_args else {}, result)

                # 把工具结果加入历史，role 必须是 "tool"
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            # Step 4: 带着工具结果，第二次请求 LLM 生成最终回复
            final_response = self.client.chat.completions.create(
                model=self.client.default_model,
                messages=self.messages
            )
            reply = final_response.choices[0].message.content

        else:
            # LLM 直接回答，不调用工具
            reply = msg.content

        # Step 5: 把助手回复加入历史，供下一轮对话使用
        self.session.log_assistant_message(reply)
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def chat_stream(self, user_message: str):
        """
        流式对话方法（SSE）：逐字返回 LLM 回复，用于 Gradio 前端。

        与 chat() 逻辑一致，但最终回复使用 stream=True。
        类比 Java：相当于返回 Flux<String> 而不是 Mono<String>。
        """
        # Step 1: 记录用户消息
        self.session.log_user_message(user_message)
        self.messages.append({"role": "user", "content": user_message})

        # 第一轮对话时，用用户问题做语义检索补充相关历史
        if len(self.messages) == 2:
            try:
                from memory.retrieval import build_memory_context
                extra = build_memory_context(self.user_id, current_question=user_message)
                if extra:
                    self.messages[0]["content"] += f"\n\n{extra}"
            except Exception:
                pass

        # Step 2: 先 yield 占位符，让前端立即有反馈，避免空白等待
        yield "⏳ 正在思考中…"

        # Step 2: 第一次请求 LLM（非流式，因为需要判断是否工具调用）
        response = self.client.chat.completions.create(
            model=self.client.default_model,
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        # Step 3: 处理工具调用
        if msg.tool_calls:
            self.messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments
                print(f"   🔧 调用工具: {tool_name}")

                result = execute_tool(tool_name, tool_args)
                self.session.log_tool_call(tool_name, json.loads(tool_args) if tool_args else {}, result)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            # Step 4: 带工具结果，流式请求最终回复
            stream = self.client.chat.completions.create(
                model=self.client.default_model,
                messages=self.messages,
                stream=True
            )

            full_reply = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply += token
                    yield full_reply  # 逐步返回累积文本

        else:
            # 无工具调用，直接流式返回
            # 重新请求一次用流式模式
            stream = self.client.chat.completions.create(
                model=self.client.default_model,
                messages=self.messages,
                stream=True
            )

            full_reply = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply += token
                    yield full_reply

        # Step 5: 记录完整回复
        self.session.log_assistant_message(full_reply)
        self.messages.append({"role": "assistant", "content": full_reply})

    def on_session_end(self):
        """
        会话结束 Hook，阶段 2 实现自动摘要功能。
        类比 Java：这是一个生命周期回调方法（类似 @PreDestroy）
        """
        from memory.hooks import on_session_stop
        digest = on_session_stop(self.session)
        if digest:
            print("\n📝 本次学习记录已保存！")
            print(f"   📁 路径：storage/sessions/{self.session.session_id}/")
