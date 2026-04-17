import gradio as gr
from agent.main_agent import LearningAgent

# 每个用户会话对应一个 Agent 实例，存在这里
# 类比 Java：相当于 HttpSession 里存的 Service 对象
_agent_store: dict[str, LearningAgent] = {}


def get_agent(session_state: dict) -> LearningAgent:
    """获取或创建当前会话的 Agent 实例"""
    uid = session_state.get("user_id", "student_001")
    if uid not in _agent_store:
        _agent_store[uid] = LearningAgent(user_id=uid)
    return _agent_store[uid]


def chat(user_message: str, history: list, session_state: dict):
    """
    Gradio 流式聊天回调（generator）。
    每 yield 一次，前端就刷新一次，实现逐字输出效果。
    """
    if not user_message.strip():
        yield "", history, session_state
        return

    agent = get_agent(session_state)
    history.append({"role": "user",      "content": user_message})
    history.append({"role": "assistant", "content": ""})

    # 逐 token 流式输出
    for partial_reply in agent.chat_stream(user_message):
        history[-1]["content"] = partial_reply
        yield "", history, session_state


def reset_session(session_state: dict):
    """重置会话，触发 on_session_end hook（阶段2后会自动保存摘要）"""
    uid = session_state.get("user_id", "student_001")
    if uid in _agent_store:
        _agent_store[uid].on_session_end()
        del _agent_store[uid]
    return [], session_state


# ============================================================
# Gradio UI 构建
# ============================================================
CUSTOM_CSS = """
/* ── 全局背景：天蓝渐变 ── */
body, .gradio-container {
    background: linear-gradient(135deg, #e0f4ff 0%, #c8e8f8 40%, #ddf0ff 100%) !important;
    min-height: 100vh;
}

/* ── 主卡片玻璃质感 ── */
.glass-card {
    background: rgba(255, 255, 255, 0.55) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255, 255, 255, 0.75) !important;
    border-radius: 20px !important;
    box-shadow: 0 8px 32px rgba(100, 180, 240, 0.18) !important;
    padding: 20px !important;
}

/* ── 标题区 ── */
.title-area h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #1a6ea8 !important;
    letter-spacing: -0.5px;
}
.title-area p {
    color: #4a90c4 !important;
}

/* ── 快捷提示卡片 ── */
.hint-card {
    background: linear-gradient(120deg, rgba(200,235,255,0.7) 0%, rgba(220,245,255,0.85) 100%) !important;
    backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(120, 195, 240, 0.45) !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 18px rgba(80, 160, 220, 0.13) !important;
    padding: 16px 20px !important;
    margin-bottom: 12px !important;
}
.hint-card p {
    color: #2b7ab5 !important;
    margin: 4px 0 !important;
    font-size: 0.95rem !important;
}
.hint-label {
    font-weight: 600 !important;
    color: #1565a0 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 6px !important;
}

/* ── 输入行整体垂直居中 ── */
.input-row {
    align-items: center !important;
    gap: 8px !important;
}
#send-btn {
    height: 46px !important;
    align-self: center !important;
}

/* ── 发送按钮：浅蓝高级感 ── */
#send-btn {
    background: linear-gradient(135deg, #56aee8 0%, #2e8fd4 100%) !important;
    border: none !important;
    border-radius: 12px !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    box-shadow: 0 4px 14px rgba(46, 143, 212, 0.35) !important;
    transition: all 0.2s ease !important;
}
#send-btn:hover {
    background: linear-gradient(135deg, #72c0f5 0%, #3da0e8 100%) !important;
    box-shadow: 0 6px 20px rgba(46, 143, 212, 0.5) !important;
    transform: translateY(-1px) !important;
}

/* ── 快捷按钮：浅蓝描边风格 ── */
.hint-btn button {
    background: rgba(220, 242, 255, 0.8) !important;
    border: 1.5px solid rgba(86, 174, 232, 0.6) !important;
    border-radius: 10px !important;
    color: #1a6ea8 !important;
    font-weight: 500 !important;
    backdrop-filter: blur(6px) !important;
    transition: all 0.18s ease !important;
    box-shadow: 0 2px 8px rgba(86, 174, 232, 0.12) !important;
}
.hint-btn button:hover {
    background: rgba(86, 174, 232, 0.2) !important;
    border-color: #2e8fd4 !important;
    box-shadow: 0 4px 14px rgba(46, 143, 212, 0.25) !important;
    transform: translateY(-1px) !important;
}

/* ── 结束按钮特殊色 ── */
.end-btn button {
    background: rgba(255, 235, 235, 0.8) !important;
    border: 1.5px solid rgba(240, 130, 130, 0.5) !important;
    color: #c0392b !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
}
.end-btn button:hover {
    background: rgba(240, 130, 130, 0.18) !important;
    transform: translateY(-1px) !important;
}

/* ── 输入框 ── */
.gr-textbox textarea, .gr-textbox input {
    border-radius: 12px !important;
    border: 1.5px solid rgba(86, 174, 232, 0.4) !important;
    background: rgba(255,255,255,0.8) !important;
    backdrop-filter: blur(8px) !important;
}
.gr-textbox textarea:focus, .gr-textbox input:focus {
    border-color: #2e8fd4 !important;
    box-shadow: 0 0 0 3px rgba(46, 143, 212, 0.15) !important;
}

/* ── 底部提示 ── */
.tool-tip {
    color: #6aabe0 !important;
    font-size: 0.82rem !important;
    text-align: center !important;
    margin-top: 8px !important;
}

footer { display: none !important; }
"""

with gr.Blocks(title="📚 个人学习助手 Agent") as demo:

    session_state = gr.State({"user_id": "student_001"})

    # ── 标题区 ──
    with gr.Column(elem_classes="glass-card title-area"):
        gr.Markdown("""
# 📚 个人学习助手 Agent
> **你的 AI 编程学习伙伴** · 基于智谱 GLM-4-Flash · 支持 Function Calling 工具调用
        """)

    # ── 快捷提示卡片 ──
    with gr.Column(elem_classes="hint-card"):
        gr.HTML('<p class="hint-label">💡 你可以这样开始</p>')
        gr.HTML("""
        <p>🐍 &nbsp;<b>我想学 Python 装饰器</b></p>
        <p>📝 &nbsp;<b>帮我出一道关于列表推导式的题</b></p>
        <p>✅ &nbsp;<b>我答完了，帮我检查一下</b></p>
        <p>🔍 &nbsp;<b>接下来我该学什么？</b></p>
        """)

    # ── 主聊天区 ──
    with gr.Column(elem_classes="glass-card"):
        chatbot = gr.Chatbot(
            value=[],
            label="对话区",
            height=460,
            render_markdown=True,
            buttons=["copy"],
            layout="bubble",
            avatar_images=(None, "https://api.dicebear.com/7.x/bottts/svg?seed=agent"),
        )

        # 输入行
        with gr.Row(equal_height=True):
            msg_input = gr.Textbox(
                placeholder="输入你想学的内容，或直接提问…",
                label="",
                scale=9,
                lines=1,
                autofocus=True,
                container=False,
            )
            send_btn = gr.Button("发送 ↩", scale=1, elem_id="send-btn", min_width=100)

        # 快捷按钮行
        with gr.Row():
            btn_decorator = gr.Button("🧩 学习装饰器",    size="sm", elem_classes="hint-btn")
            btn_quiz      = gr.Button("📝 出一道练习题",  size="sm", elem_classes="hint-btn")
            btn_next      = gr.Button("🔍 接下来学什么",  size="sm", elem_classes="hint-btn")
            btn_end       = gr.Button("🔄 结束并保存",    size="sm", elem_classes="end-btn")

        gr.HTML('<p class="tool-tip">当助手调用工具时，终端会显示 🔧 调用工具: xxx</p>')

    # ── 事件绑定 ──
    def quick_send(text, history, state):
        """快捷按钮也走流式"""
        yield from chat(text, history, state)

    send_btn.click(fn=chat,
                   inputs=[msg_input, chatbot, session_state],
                   outputs=[msg_input, chatbot, session_state])
    msg_input.submit(fn=chat,
                     inputs=[msg_input, chatbot, session_state],
                     outputs=[msg_input, chatbot, session_state])

    btn_decorator.click(fn=lambda h, s: chat("我想学 Python 装饰器", h, s),
                        inputs=[chatbot, session_state],
                        outputs=[msg_input, chatbot, session_state])
    btn_quiz.click(fn=lambda h, s: chat("帮我出一道 Python 练习题", h, s),
                   inputs=[chatbot, session_state],
                   outputs=[msg_input, chatbot, session_state])
    btn_next.click(fn=lambda h, s: chat("接下来我该学什么？", h, s),
                   inputs=[chatbot, session_state],
                   outputs=[msg_input, chatbot, session_state])
    btn_end.click(fn=reset_session,
                  inputs=[session_state],
                  outputs=[chatbot, session_state])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        inbrowser=True,
        css=CUSTOM_CSS,
    )
