import gradio as gr
from agent.main_agent import LangGraphAgent as LearningAgent

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
    history.append({"role": "assistant", "content": "⏳ 正在思考中…"})

    # 先立即刷新前端，显示占位符
    yield "", history, session_state

    # 逐 token 流式输出（兼容新版 dict yield 和旧版 str yield）
    for chunk in agent.chat_stream(user_message):
        # 兼容新版 dict yield 和旧版 str yield
        if isinstance(chunk, dict):
            if chunk.get("type") == "token":
                response = chunk["content"]
                history[-1]["content"] = response
                yield "", history, session_state
            elif chunk.get("type") == "done":
                response = chunk["content"]
                history[-1]["content"] = response
                yield "", history, session_state
            # pipeline 事件不影响 Gradio 显示，忽略
        else:
            # 旧版 str yield，直接用
            history[-1]["content"] = chunk
            yield "", history, session_state


def reset_session(session_state: dict):
    """重置会话，触发 on_session_end hook（阶段2后会自动保存摘要）"""
    uid = session_state.get("user_id", "student_001")
    if uid in _agent_store:
        _agent_store[uid].on_session_end()
        del _agent_store[uid]
    return [], session_state


# ============================================================
# Gradio UI — CS408 考研学习助手
# ============================================================
CUSTOM_CSS = """
/* ── 全局背景：天蓝渐变 ── */
body, .gradio-container {
    background: linear-gradient(135deg, #e0f4ff 0%, #c8e8f8 40%, #ddf0ff 100%) !important;
    min-height: 100vh;
    font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
}

/* ── 顶部标题卡片：玻璃质感 ── */
.title-card {
    background: rgba(255,255,255,0.55) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255,255,255,0.75) !important;
    border-radius: 20px !important;
    padding: 20px 28px !important;
    margin-bottom: 4px !important;
    box-shadow: 0 8px 32px rgba(100,180,240,0.18) !important;
}
.title-card h1 {
    font-size: 1.7rem !important;
    font-weight: 700 !important;
    color: #1a6ea8 !important;
    margin: 0 0 6px 0 !important;
    letter-spacing: 0.5px !important;
}
.title-card p {
    color: #4a90c4 !important;
    font-size: 0.88rem !important;
    margin: 0 !important;
}

/* ── 科目标签 ── */
.subject-bar { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
.subject-tag { display:inline-block; padding:4px 14px; border-radius:20px; font-size:0.82rem; font-weight:600; }
.tag-ds  { background:rgba(255,90,70,0.12);  border:1px solid rgba(255,90,70,0.45);  color:#c03020; }
.tag-os  { background:rgba(30,160,80,0.12);  border:1px solid rgba(30,160,80,0.45);  color:#1a6a35; }
.tag-co  { background:rgba(200,130,0,0.12);  border:1px solid rgba(200,130,0,0.45);  color:#8a5800; }
.tag-cn  { background:rgba(30,110,210,0.12); border:1px solid rgba(30,110,210,0.45); color:#1a55a0; }
.tag-rag { background:rgba(120,50,200,0.12); border:1px solid rgba(120,50,200,0.45); color:#5a28a0; }

/* ── 主聊天区卡片：玻璃质感 ── */
.chat-card {
    background: rgba(255,255,255,0.55) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255,255,255,0.75) !important;
    border-radius: 20px !important;
    padding: 16px !important;
    box-shadow: 0 8px 32px rgba(100,180,240,0.18) !important;
}

/* ── 输入框 ── */
#msg-input textarea {
    background: rgba(255,255,255,0.8) !important;
    border: 1.5px solid rgba(86,174,232,0.4) !important;
    border-radius: 12px !important;
    color: #1a3a5a !important;
    backdrop-filter: blur(8px) !important;
    caret-color: #2e8fd4 !important;
}
#msg-input textarea:focus {
    border-color: #2e8fd4 !important;
    box-shadow: 0 0 0 3px rgba(46,143,212,0.15) !important;
}
#msg-input textarea::placeholder { color: #7ab0d0 !important; }

/* ── 发送按钮 ── */
#send-btn {
    background: linear-gradient(135deg, #56aee8 0%, #2e8fd4 100%) !important;
    border: none !important;
    border-radius: 12px !important;
    color: white !important;
    font-weight: 600 !important;
    height: 46px !important;
    box-shadow: 0 4px 14px rgba(46,143,212,0.35) !important;
    transition: all 0.2s ease !important;
}
#send-btn:hover {
    background: linear-gradient(135deg, #72c0f5 0%, #3da0e8 100%) !important;
    box-shadow: 0 6px 20px rgba(46,143,212,0.5) !important;
    transform: translateY(-1px) !important;
}

/* ── 快捷按钮 ── */
.hint-btn button {
    background: rgba(220,242,255,0.8) !important;
    border: 1.5px solid rgba(86,174,232,0.6) !important;
    border-radius: 10px !important;
    color: #1a6ea8 !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    backdrop-filter: blur(6px) !important;
    transition: all 0.18s ease !important;
    box-shadow: 0 2px 8px rgba(86,174,232,0.12) !important;
}
.hint-btn button:hover {
    background: rgba(86,174,232,0.2) !important;
    border-color: #2e8fd4 !important;
    box-shadow: 0 4px 14px rgba(46,143,212,0.25) !important;
    transform: translateY(-1px) !important;
}

/* ── 结束按钮 ── */
.end-btn button {
    background: rgba(255,235,235,0.8) !important;
    border: 1.5px solid rgba(240,130,130,0.5) !important;
    color: #c0392b !important;
    border-radius: 10px !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
}
.end-btn button:hover {
    background: rgba(240,130,130,0.18) !important;
    transform: translateY(-1px) !important;
}

/* ── 底部状态栏 ── */
.status-bar {
    color: #6aabe0 !important;
    font-size: 0.78rem !important;
    margin-top: 8px !important;
    display: flex;
    justify-content: space-between;
}

footer { display: none !important; }
"""

with gr.Blocks(title="🎯 CS408 考研学习助手") as demo:

    session_state = gr.State({"user_id": "student_001"})

    # ── 顶部标题 ──
    with gr.Column(elem_classes="title-card"):
        gr.HTML("""
        <h1>🎯 CS408 考研学习助手</h1>
        <p>基于 RAG 知识库 · 智谱 GLM-4-Flash · 覆盖数据结构 / 操作系统 / 计算机组成原理 / 计算机网络</p>
        <div class="subject-bar">
            <span class="subject-tag tag-ds">📊 数据结构</span>
            <span class="subject-tag tag-os">⚙️ 操作系统</span>
            <span class="subject-tag tag-co">🖥️ 计算机组成原理</span>
            <span class="subject-tag tag-cn">🌐 计算机网络</span>
            <span class="subject-tag tag-rag">🔍 RAG 知识检索</span>
        </div>
        """)

    # ── 主聊天区 ──
    with gr.Column(elem_classes="chat-card"):
        chatbot = gr.Chatbot(
            value=[],
            label="",
            height=480,
            render_markdown=True,
            layout="bubble",
            show_label=False,
            avatar_images=(None, "https://api.dicebear.com/7.x/bottts/svg?seed=cs408"),
        )

        # 输入行
        with gr.Row(equal_height=True):
            msg_input = gr.Textbox(
                placeholder="输入知识点、直接提问，或点击下方快捷入口…",
                label="",
                scale=9,
                lines=1,
                autofocus=True,
                container=False,
                elem_id="msg-input",
            )
            send_btn = gr.Button("发送 ↩", scale=1, elem_id="send-btn", min_width=90)

        # 快捷按钮 —— 第一行：四科入口
        with gr.Row():
            btn_ds  = gr.Button("📊 数据结构考点",   size="sm", elem_classes="hint-btn")
            btn_os  = gr.Button("⚙️ 操作系统考点",   size="sm", elem_classes="hint-btn")
            btn_co  = gr.Button("🖥️ 组成原理考点",   size="sm", elem_classes="hint-btn")
            btn_cn  = gr.Button("🌐 计算机网络考点", size="sm", elem_classes="hint-btn")

        # 快捷按钮 —— 第二行：常用操作
        with gr.Row():
            btn_quiz = gr.Button("📝 出一道选择题",   size="sm", elem_classes="hint-btn")
            btn_weak = gr.Button("🔥 高频易错考点",   size="sm", elem_classes="hint-btn")
            btn_next = gr.Button("� 接下来复习什么", size="sm", elem_classes="hint-btn")
            btn_end  = gr.Button("🔄 结束本次会话",   size="sm", elem_classes="end-btn")

        gr.HTML("""
        <div class="status-bar">
            <span>� 支持追问 · 出题 · 解析 · 知识推荐</span>
            <span>🔍 知识库：CS408 精炼笔记 + 教材 PDF · 共 1939 条片段</span>
        </div>
        """)

    # ── 事件绑定 ──
    send_btn.click(fn=chat,
                   inputs=[msg_input, chatbot, session_state],
                   outputs=[msg_input, chatbot, session_state])
    msg_input.submit(fn=chat,
                     inputs=[msg_input, chatbot, session_state],
                     outputs=[msg_input, chatbot, session_state])

    def send_ds(h, s):   yield from chat("帮我梳理数据结构的核心高频考点，按章节列出重点", h, s)
    def send_os(h, s):   yield from chat("帮我梳理操作系统的核心高频考点，按章节列出重点", h, s)
    def send_co(h, s):   yield from chat("帮我梳理计算机组成原理的核心高频考点，按章节列出重点", h, s)
    def send_cn(h, s):   yield from chat("帮我梳理计算机网络的核心高频考点，按章节列出重点", h, s)
    def send_quiz(h, s): yield from chat("随机出一道408风格的选择题，给出四个选项和详细解析", h, s)
    def send_weak(h, s): yield from chat("408考试中最容易混淆和出错的知识点有哪些？帮我列出来", h, s)
    def send_next(h, s): yield from chat("根据我们的对话，接下来我应该重点复习哪些内容？", h, s)

    btn_ds.click(fn=send_ds,     inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_os.click(fn=send_os,     inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_co.click(fn=send_co,     inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_cn.click(fn=send_cn,     inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_quiz.click(fn=send_quiz, inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_weak.click(fn=send_weak, inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_next.click(fn=send_next, inputs=[chatbot, session_state], outputs=[msg_input, chatbot, session_state])
    btn_end.click(fn=reset_session, inputs=[session_state], outputs=[chatbot, session_state])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        inbrowser=True,
        css=CUSTOM_CSS,
    )
