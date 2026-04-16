import json
from zhipuai import ZhipuAI
from config import API_KEY, MODEL
from agent.tools import TOOL_DEFINITIONS, execute_tool
from memory.l1_session import SessionManager

# ============================================================
# System Prompt：给 LLM 定角色 + 行为规范
# 类比 Java：这是构造函数里注入的"行为策略配置"
# ============================================================
SYSTEM_PROMPT = """你是一个耐心专业的编程学习助手，专门帮助用户学习 Python。

你的行为规范：
1. 当用户想了解某个知识点时 → 调用 explain_concept 工具
2. 当用户学完一个知识点，想测试自己 → 调用 generate_quiz 工具
3. 当用户回答了题目 → 调用 check_answer 工具判断对错
4. 当用户问"接下来学什么"或对话结束时 → 调用 recommend_next 工具

注意：
- 优先调用工具，而不是直接回答
- 语气友好，鼓励为主
- 如果用户有 Java 基础，可以用 Java 类比解释 Python 概念
"""


class LearningAgent:
    """
    主 Agent 类，负责：
    1. 维护对话历史（messages 列表）
    2. 调用 LLM（智谱 AI）
    3. 处理 Function Calling 工具调用
    4. 预留 hook 入口供后续阶段扩展

    类比 Java：这是一个有状态的 Service 类
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = ZhipuAI(api_key=API_KEY)
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
            model=MODEL,
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
                model=MODEL,
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
