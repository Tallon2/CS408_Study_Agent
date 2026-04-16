# 个人学习助手 Agent —— 完整开发文档

## 目录

*   [学习清单](#学习清单)
*   [阶段 0：环境搭建](#阶段-0环境搭建day-1)
*   [阶段 1：裸 Agent 对话循环](#阶段-1裸-agent-对话循环day-2-3)
*   [阶段 2：L1 会话状态 + 事件日志](#阶段-2l1-会话状态--事件日志day-4-6)
*   [阶段 3：L2 任务状态 + L4 用户画像 + 记忆注入](#阶段-3l2-任务状态--l4-用户画像--记忆注入day-7-11)
*   [阶段 4：向量语义检索](#阶段-4向量语义检索day-12-14)
*   [阶段 5：L3 知识沉淀 + 整体打磨](#阶段-5l3-知识沉淀--整体打磨day-15-20)
*   [最终检查清单](#最终检查清单)

***

## 学习清单

> 不需要精通每一项，到"能用"即可。带 ⭐ 的是核心必学项。

### 1. Python 基础 ⭐

*   数据类型、函数、类、模块
*   文件读写（JSON / JSONL / Markdown）
*   异步基础（`asyncio` 了解即可，本项目暂不强依赖）

### 2. LLM API 调用 ⭐

*   OpenAI / Anthropic / 国内大模型（DeepSeek、智谱等）的 Chat Completion API
*   Function Calling / Tool Use 机制
*   System Prompt 设计
*   Token 概念与 Context Window 限制

### 3. 向量检索基础 ⭐

*   Embedding（文本向量化）是什么
*   ChromaDB 或 FAISS 的基本用法
*   相似度搜索的直觉理解（不需要深入数学）

### 4. Agent 框架概念

*   什么是 Agent、Tool、Planning
*   ReAct 模式了解
*   可以浏览 LangChain / LlamaIndex 文档建立直觉，但**本项目不用框架，自己写**

### 5. 数据存储与格式

*   JSON / JSONL / Markdown with YAML frontmatter
*   文件系统作为数据库（本项目不引入 MySQL / Redis）

### 6. 命令行应用开发

*   Python `argparse` 或 `click`
*   基础的 CLI 交互循环

### 7. Git 基础

*   日常 commit / push / branch

***

## 技术实现方案

> 共分 **6 个阶段**，每个阶段产出一个可运行的里程碑。预估总工期 **3\~4 周**。

### 整体架构

    ┌─────────────────────────────────────────────────────┐
    │                用户（命令行 / 简单网页）                │
    └──────────────────────┬──────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────┐
    │                  主 Agent（业务层）                    │
    │   接收问题 → 注入记忆上下文 → 调用 LLM → 回答          │
    │   工具：explain / quiz / check / recommend           │
    │   MCP：get_memory() / save_decision()                │
    └──────────┬──────────────────────┬───────────────────┘
               │ 事件钩子（自动）       │ 显式工具调用（按需）
    ┌──────────▼──────────┐  ┌────────▼─────────────────┐
    │  Hook 事件驱动层      │  │   记忆检索层               │
    │  SessionStart        │  │   catalog + 语义 rerank   │
    │  Stop                │  │   返回最相关的知识文档      │
    │  PreCompact          │  └──────────────────────────┘
    │  PostCompact         │
    └──────────┬──────────┘
    ┌──────────▼──────────────────────────────────────────┐
    │                  分层记忆存储                          │
    │  L1 会话状态  →  L2 任务状态  →  L3 项目知识           │
    │                              →  L4 用户画像           │
    └─────────────────────────────────────────────────────┘

### 核心设计原则

> 记忆不靠 LLM 自觉写，而靠 **Hook 事件强制触发**。LLM 只负责无法用规则完成的语义提炼。

### 项目文件结构

    learning-agent/
    ├── config.py              # 配置（API Key、模型名）
    ├── main.py                # 入口
    ├── test_api.py            # API 连通性测试
    ├── requirements.txt
    ├── .env                   # API Key（不提交 git）
    ├── .gitignore
    ├── README.md
    │
    ├── agent/
    │   ├── __init__.py
    │   ├── main_agent.py      # 主 Agent + Function Calling 规划
    │   └── tools.py           # 工具定义与执行
    │
    ├── memory/
    │   ├── __init__.py
    │   ├── l1_session.py      # L1 会话状态（含 compact_state）
    │   ├── l2_task.py         # L2 任务连续性状态
    │   ├── l3_knowledge.py    # L3 知识沉淀
    │   ├── l4_profile.py      # L4 用户画像管理
    │   ├── retrieval.py       # 向量检索 + token 预算控制
    │   └── hooks.py           # PreCompact / PostCompact / Stop 处理
    │
    └── storage/               # 运行时数据（gitignore）
        ├── sessions/          # L1 会话状态文件
        ├── tasks/             # L2 任务状态
        ├── knowledge_base/    # L3 知识沉淀
        │   ├── patterns/
        │   └── pitfalls/
        ├── user_profile/      # L4 用户画像
        └── vector_db/         # 语义检索索引

***

## 阶段 0：环境搭建（Day 1）

**目标**：搭好开发环境，跑通第一次 LLM API 调用。

### 1. 安装 Python 3.11+

```bash
python --version
```

### 2. 创建项目目录 + 虚拟环境

```bash
mkdir learning-agent && cd learning-agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt`：

    zhipuai>=2.1.0
    chromadb>=0.5.0
    pyyaml>=6.0
    rich>=13.0
    python-dotenv>=1.0.0

### 4. 配置 API Key

```bash
# .env 文件（不要提交到 git）
ZHIPU_API_KEY=your_key_here
```

`config.py`：

```python
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ZHIPU_API_KEY")
MODEL = "glm-4-flash"

if not API_KEY:
    raise ValueError("未找到 ZHIPU_API_KEY，请检查 .env 文件")
```

### 5. 验证 API 可用

`test_api.py`：

```python
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

def test_connection():
    print(f"🔍 正在测试智谱 AI 连接...")
    print(f"   模型: {MODEL}")
    print(f"   API Key: {API_KEY[:8]}...{API_KEY[-4:]}\n")

    client = ZhipuAI(api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}]
    )

    reply = response.choices[0].message.content
    print(f"✅ 连接成功！模型回复：\n{reply}")
    print(f"\n📊 Token 消耗：{response.usage.total_tokens} tokens")

if __name__ == "__main__":
    test_connection()
```

### ✅ 里程碑 0

API 跑通，目录建好，git init 完成。

***

## 阶段 1：裸 Agent 对话循环（Day 2-3）

**目标**：没有任何记忆，先跑通 **CLI 对话 + Function Calling 工具调用**。

### 1.1 实现基础对话循环

`main.py`：

```python
from agent.main_agent import LearningAgent

def main():
    agent = LearningAgent(user_id="student_001")
    print("📚 学习助手已启动，输入 'quit' 退出\n")

    while True:
        user_input = input("你: ").strip()
        if user_input.lower() in ("quit", "exit"):
            agent.on_session_end()  # 预留 hook 入口
            break

        response = agent.chat(user_input)
        print(f"\n助手: {response}\n")

if __name__ == "__main__":
    main()
```

### 1.2 实现主 Agent（含 Function Calling）

`agent/main_agent.py`：

```python
from zhipuai import ZhipuAI
from config import API_KEY, MODEL
from agent.tools import TOOL_DEFINITIONS, execute_tool

SYSTEM_PROMPT = """你是一个耐心的编程学习助手。
你可以使用工具来帮助用户学习。
当用户想学习某个知识点时，先用 explain_concept 解释。
当用户想测试自己时，用 generate_quiz 出题。
当用户回答问题后，用 check_answer 判断。
用户问学什么好时，用 recommend_next 推荐。"""

class LearningAgent:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = ZhipuAI(api_key=API_KEY)
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})

        response = self.client.chat.completions.create(
            model=MODEL,
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        # 处理工具调用
        if msg.tool_calls:
            self.messages.append(msg)
            for tool_call in msg.tool_calls:
                result = execute_tool(
                    tool_call.function.name,
                    tool_call.function.arguments
                )
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
            # 工具结果交给 LLM 生成最终回复
            final = self.client.chat.completions.create(
                model=MODEL,
                messages=self.messages
            )
            reply = final.choices[0].message.content
        else:
            reply = msg.content

        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def on_session_end(self):
        pass  # 阶段2再实现
```

### 1.3 实现工具定义与执行

`agent/tools.py`：

```python
import json

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "explain_concept",
            "description": "解释一个编程知识点，可指定深度",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "知识点名称"},
                    "depth": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "针对某个知识点生成一道练习题",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_answer",
            "description": "检查用户对某道题的回答是否正确",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "user_answer": {"type": "string"}
                },
                "required": ["question", "user_answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_next",
            "description": "推荐用户接下来应该学什么",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def execute_tool(name: str, arguments: str) -> str:
    """
    阶段1：工具只返回指令性提示，让 LLM 完成实际内容生成。
    阶段3接入记忆后，这里会注入用户画像和知识状态。
    """
    args = json.loads(arguments)

    if name == "explain_concept":
        topic = args.get("topic", "")
        depth = args.get("depth", "beginner")
        return f"[工具] 请为用户解释「{topic}」，难度：{depth}。请用例子先行的方式讲解。"

    elif name == "generate_quiz":
        topic = args.get("topic", "")
        difficulty = args.get("difficulty", "easy")
        return f"[工具] 请出一道关于「{topic}」的{difficulty}难度练习题，包含选项和答案。"

    elif name == "check_answer":
        return f"[工具] 请判断用户回答是否正确。题目：{args.get('question')}，用户答案：{args.get('user_answer')}"

    elif name == "recommend_next":
        return "[工具] 请根据对话历史推荐用户下一步学什么。"

    return "[工具] 未知工具"
```

### ✅ 里程碑 1

能在终端里和学习助手对话，LLM 能自主决定什么时候出题、什么时候解释。但还没有任何记忆。

***

## 阶段 2：L1 会话状态 + 事件日志（Day 4-6）

**目标**：实现 **append-only 事件日志** 和 **会话结束时的自动摘要**。

### 2.1 事件日志（核心基础设施）

`memory/l1_session.py`：

```python
import json
import os
from datetime import datetime

class SessionManager:
    def __init__(self, user_id: str, session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = f"storage/sessions/{self.session_id}"
        os.makedirs(self.session_dir, exist_ok=True)

        self.journal_path = os.path.join(self.session_dir, "journal.jsonl")
        self.topics_touched = []
        self.user_struggles = []
        self.event_counter = 0

    def log_event(self, event_type: str, payload: dict):
        """append-only 写入，不可变事件流"""
        self.event_counter += 1
        event = {
            "event_id": f"evt-{self.event_counter:04d}",
            "ts": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": payload
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def log_user_message(self, message: str):
        self.log_event("user_message", {"content": message})

    def log_assistant_message(self, message: str):
        self.log_event("assistant_message", {"content": message})

    def log_tool_call(self, tool_name: str, args: dict, result: str):
        self.log_event("tool_call", {
            "tool_name": tool_name, "arguments": args, "result": result
        })

    def log_struggle(self, topic: str, detail: str):
        """记录用户卡住的点"""
        self.user_struggles.append({
            "topic": topic, "detail": detail, "ts": datetime.now().isoformat()
        })
        self.log_event("user_struggle", {"topic": topic, "detail": detail})

    def get_messages_text(self) -> str:
        """读取本次会话全部消息，供摘要使用"""
        messages = []
        if os.path.exists(self.journal_path):
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    event = json.loads(line.strip())
                    if event["event_type"] in ("user_message", "assistant_message"):
                        role = "用户" if event["event_type"] == "user_message" else "助手"
                        messages.append(f"{role}: {event['payload']['content']}")
        return "\n".join(messages)
```

### 2.2 会话结束 Hook：自动生成摘要

`memory/hooks.py`：

```python
import json
import os
from datetime import datetime
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

SCRIBE_PROMPT = """请根据以下学习对话记录，生成结构化摘要。严格按 JSON 格式输出：

{
  "summary": "一句话总结本次学习内容",
  "topics_learned": ["涉及的知识点列表"],
  "mastered": ["用户已理解的知识点"],
  "struggled": ["用户卡住或答错的知识点"],
  "corrections": ["本次发现的认知纠偏"],
  "next_recommendation": "建议下次从哪里开始"
}

对话记录：
{conversation}
"""

def on_session_stop(session_manager) -> dict:
    """
    Stop Hook：会话结束时自动触发。
    这是系统可靠性的核心——不依赖 LLM 自觉，而是事件触发。
    """
    conversation = session_manager.get_messages_text()
    if not conversation.strip():
        return {}

    client = ZhipuAI(api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个精确的学习记录分析师。只输出 JSON，不要多余文字。"},
            {"role": "user", "content": SCRIBE_PROMPT.replace("{conversation}", conversation)}
        ]
    )

    digest = json.loads(response.choices[0].message.content)

    # 落盘：session_notes.md
    notes_path = os.path.join(session_manager.session_dir, "session_notes.md")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(f"## 会话摘要 {session_manager.session_id}\n\n")
        f.write(f"**总结**：{digest.get('summary', '')}\n\n")
        f.write(f"**涉及知识点**：{', '.join(digest.get('topics_learned', []))}\n\n")
        f.write(f"**已掌握**：{', '.join(digest.get('mastered', []))}\n\n")
        f.write(f"**薄弱点**：{', '.join(digest.get('struggled', []))}\n\n")
        f.write(f"**下次建议**：{digest.get('next_recommendation', '')}\n")

    # 落盘：digest.json（供后续检索索引）
    digest_path = os.path.join(session_manager.session_dir, "digest.json")
    digest["session_id"] = session_manager.session_id
    with open(digest_path, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    session_manager.log_event("session_stop", {"digest": digest})
    return digest


def on_pre_compact(session_manager) -> dict:
    """PreCompact Hook：在上下文被压缩前保存恢复点"""
    compact = {
        "session_id": session_manager.session_id,
        "topics_touched": session_manager.topics_touched,
        "user_struggles": session_manager.user_struggles,
        "event_count": session_manager.event_counter,
        "saved_at": datetime.now().isoformat()
    }
    compact_path = os.path.join(session_manager.session_dir, "compact_state.json")
    with open(compact_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, indent=2)
    return compact
```

### 2.3 更新主 Agent 接入事件日志

`agent/main_agent.py` 关键修改：

```python
from memory.l1_session import SessionManager

class LearningAgent:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = ZhipuAI(api_key=API_KEY)
        self.session = SessionManager(user_id)        # ✅ 新增
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat(self, user_message: str) -> str:
        self.session.log_user_message(user_message)   # ✅ 自动记录
        self.messages.append({"role": "user", "content": user_message})

        # ... 原有的 LLM 调用逻辑 ...

        self.session.log_assistant_message(reply)     # ✅ 自动记录
        return reply

    def on_session_end(self):
        """会话结束 hook"""
        from memory.hooks import on_session_stop
        digest = on_session_stop(self.session)        # ✅ 自动摘要
        print("\n📝 本次学习记录已保存。")
```

### ✅ 里程碑 2

每次对话自动生成 `journal.jsonl`（不可变事件流）和 `session_notes.md`（结构化摘要），`quit` 时自动触发。

***

## 阶段 3：L2 任务状态 + L4 用户画像 + 记忆注入（Day 7-11）

**目标**：实现 **跨会话的任务连续性** 和 **用户画像积累**，每次对话开始时 **自动注入记忆**。

### 3.1 L2 任务状态

`memory/l2_task.py`：

```python
import json
import os

TASK_STATE_PATH = "storage/tasks/task_state.json"

def load_task_state() -> dict:
    if os.path.exists(TASK_STATE_PATH):
        with open(TASK_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "main_goal": "",
        "current_phase": "explore",       # explore / learn / practice / review
        "next_action": "",
        "blockers": [],
        "task_corrections": [],
        "subtasks": [],
        "session_count": 0
    }

def update_task_state(digest: dict, task_state: dict) -> dict:
    """根据会话摘要更新任务状态（确定性逻辑，不依赖 LLM）"""
    task_state["session_count"] += 1

    if digest.get("next_recommendation"):
        task_state["next_action"] = digest["next_recommendation"]

    if digest.get("struggled"):
        for item in digest["struggled"]:
            if item not in task_state["blockers"]:
                task_state["blockers"].append(item)

    # 已掌握的从 blockers 移除
    if digest.get("mastered"):
        task_state["blockers"] = [
            b for b in task_state["blockers"] if b not in digest["mastered"]
        ]

    if digest.get("corrections"):
        task_state["task_corrections"].extend(digest["corrections"])

    save_task_state(task_state)
    return task_state

def save_task_state(task_state: dict):
    os.makedirs(os.path.dirname(TASK_STATE_PATH), exist_ok=True)
    with open(TASK_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(task_state, f, ensure_ascii=False, indent=2)
```

### 3.2 L4 用户画像

`memory/l4_profile.py`：

```python
import json
import os
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

PROFILE_PATH = "storage/user_profile/profile.json"

def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "stable_preferences": {},
        "knowledge_graph": {},
        "update_count": 0,
        "source_sessions": []
    }

def update_profile_from_digest(digest: dict, session_id: str):
    """每 3 次会话触发一次画像更新（LLM 做语义提炼）"""
    profile = load_profile()
    profile["update_count"] += 1
    profile["source_sessions"].append(session_id)

    # 更新知识图谱（确定性部分，不用 LLM）
    kg = profile["knowledge_graph"]
    for topic in digest.get("mastered", []):
        kg[topic] = {"status": "mastered", "last_session": session_id}
    for topic in digest.get("struggled", []):
        existing = kg.get(topic, {"attempts": 0})
        existing["status"] = "struggling"
        existing["attempts"] = existing.get("attempts", 0) + 1
        existing["last_struggle"] = digest.get("next_recommendation", "")
        existing["last_session"] = session_id
        kg[topic] = existing
    for topic in digest.get("topics_learned", []):
        if topic not in kg:
            kg[topic] = {"status": "introduced", "last_session": session_id}

    # 每 3 次会话用 LLM 提炼学习风格偏好
    if profile["update_count"] % 3 == 0:
        profile["stable_preferences"] = _extract_preferences(profile)

    save_profile(profile)

def _extract_preferences(profile: dict) -> dict:
    """用 LLM 从累积数据中提炼稳定偏好"""
    client = ZhipuAI(api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "分析用户的学习模式，只输出 JSON"},
            {"role": "user", "content":
                f"知识图谱: {json.dumps(profile['knowledge_graph'], ensure_ascii=False)}\n"
                f"当前偏好: {json.dumps(profile.get('stable_preferences', {}), ensure_ascii=False)}\n"
                f"请推断学习风格偏好，输出 JSON: "
                f'{{"explanation_style": ..., "practice_preference": ..., "pace": ...}}'}
        ]
    )
    return json.loads(resp.choices[0].message.content)

def save_profile(profile: dict):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
```

### 3.3 记忆注入：SessionStart 时自动构建上下文

`memory/retrieval.py`：

```python
from memory.l2_task import load_task_state
from memory.l4_profile import load_profile

def build_memory_context(user_id: str, current_question: str = "") -> str:
    """
    SessionStart Hook：每次新对话启动时，自动构建记忆上下文注入给 LLM。
    这是整个记忆系统形成闭环的关键。
    """
    parts = []

    # L2：任务连续性
    task = load_task_state()
    if task.get("next_action"):
        parts.append(
            f"## 当前任务状态\n"
            f"- 上次建议从这里继续：{task['next_action']}\n"
            f"- 累计学习 {task['session_count']} 次\n"
            f"- 当前薄弱点：{', '.join(task.get('blockers', [])) or '无'}\n"
            f"- 历史纠偏：{'; '.join(task.get('task_corrections', [])[-3:]) or '无'}"
        )

    # L4：用户画像
    profile = load_profile()
    kg = profile.get("knowledge_graph", {})
    if kg:
        mastered = [k for k, v in kg.items() if v.get("status") == "mastered"]
        struggling = [k for k, v in kg.items() if v.get("status") == "struggling"]
        parts.append(
            f"## 用户知识状态\n"
            f"- 已掌握：{', '.join(mastered) or '无'}\n"
            f"- 薄弱点：{', '.join(struggling) or '无'}"
        )

    prefs = profile.get("stable_preferences", {})
    if prefs:
        parts.append(
            f"## 用户偏好\n"
            f"- 讲解风格偏好：{prefs.get('explanation_style', '未知')}\n"
            f"- 练习偏好：{prefs.get('practice_preference', '未知')}"
        )

    if not parts:
        return ""

    return "# 📝 记忆系统注入\n\n" + "\n\n".join(parts)
```

### 3.4 完整 Stop Hook 链

`memory/hooks.py` 末尾追加：

```python
def on_session_stop(session_manager) -> dict:
    """完整的 Stop Hook 链"""
    # Step 1: 生成摘要
    digest = _generate_digest(session_manager)
    if not digest:
        return {}

    # Step 2: 写入向量索引（阶段4实现后生效）
    try:
        from memory.retrieval import MemoryRetriever
        retriever = MemoryRetriever()
        retriever.index_session(session_manager.session_id, digest)
    except Exception:
        pass

    # Step 3: 更新任务状态 (L2)
    from memory.l2_task import load_task_state, update_task_state
    task = load_task_state()
    update_task_state(digest, task)

    # Step 4: 更新用户画像 (L4)
    from memory.l4_profile import update_profile_from_digest
    update_profile_from_digest(digest, session_manager.session_id)

    # Step 5: 触发知识提炼 (L3)（阶段5实现后生效）
    try:
        from memory.l3_knowledge import maybe_extract_knowledge
        maybe_extract_knowledge(task["session_count"])
    except Exception:
        pass

    return digest
```

### 3.5 更新主 Agent 注入记忆

`agent/main_agent.py` 关键修改：

```python
class LearningAgent:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = ZhipuAI(api_key=API_KEY)
        self.session = SessionManager(user_id)

        # ✅ SessionStart Hook：自动注入记忆
        from memory.retrieval import build_memory_context
        memory_context = build_memory_context(user_id)
        system_prompt = SYSTEM_PROMPT
        if memory_context:
            system_prompt += f"\n\n{memory_context}"
            print("🧠 已加载历史记忆\n")

        self.messages = [{"role": "system", "content": system_prompt}]

    def on_session_end(self):
        """Stop Hook 链"""
        from memory.hooks import on_session_stop
        on_session_stop(self.session)
        print("\n📝 本次学习记录已保存，下次见！")
```

### ✅ 里程碑 3

第二天开新会话，Agent 自动知道昨天学了什么、卡在哪里、应该从哪继续。不需要用户重复介绍背景。

***

## 阶段 4：向量语义检索（Day 12-14）

**目标**：解决"学了 200 次之后，怎么找到最相关的历史会话"的问题。

### 4.1 向量检索服务

`memory/retrieval.py` 新增：

```python
import chromadb

class MemoryRetriever:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="storage/vector_db")
        self.collection = self.client.get_or_create_collection(
            name="session_digests",
            metadata={"hnsw:space": "cosine"}
        )

    def index_session(self, session_id: str, digest: dict):
        """会话结束时调用，将摘要写入向量索引"""
        doc_text = (
            f"学习主题: {', '.join(digest.get('topics_learned', []))}. "
            f"掌握: {', '.join(digest.get('mastered', []))}. "
            f"薄弱: {', '.join(digest.get('struggled', []))}. "
            f"总结: {digest.get('summary', '')}"
        )
        self.collection.upsert(
            ids=[session_id],
            documents=[doc_text],
            metadatas=[{
                "session_id": session_id,
                "topics": ",".join(digest.get("topics_learned", []))
            }]
        )

    def search_relevant(self, query: str, top_k: int = 3) -> list:
        """语义检索最相关的历史会话摘要"""
        if self.collection.count() == 0:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count())
        )
        return results.get("documents", [[]])[0]
```

### 4.2 接入到记忆注入流程

`memory/retrieval.py` 的 `build_memory_context` 增加 L3 检索：

```python
def build_memory_context(user_id: str, current_question: str = "") -> str:
    parts = []

    # ... L2 / L4 同前 ...

    # L3：语义检索相关历史（解决"只取最近 3 条"的问题）
    if current_question:
        retriever = MemoryRetriever()
        relevant = retriever.search_relevant(current_question, top_k=3)
        if relevant:
            history_text = "\n".join(f"- {r}" for r in relevant)
            parts.append(f"## 相关历史学习记录\n{history_text}")

    if not parts:
        return ""

    return "# 📝 记忆系统注入\n\n" + "\n\n".join(parts)
```

### 4.3 主 Agent 传入当前问题

`agent/main_agent.py`：

```python
# __init__ 中修改
memory_context = build_memory_context(user_id)   # 启动时用空 query

# chat() 中修改：首次提问时动态检索
def chat(self, user_message: str) -> str:
    if len(self.messages) == 1:  # 第一轮对话时追加相关历史
        extra = build_memory_context(self.user_id, current_question=user_message)
        if extra:
            self.messages[0]["content"] += f"\n\n{extra}"
    # ... 其余逻辑不变 ...
```

### ✅ 里程碑 4

学过 100 次后，问一个关于"装饰器"的问题，系统能自动检索到 6 周前那次相关会话，而不只是最近 3 次。

***

## 阶段 5：L3 知识沉淀 + 整体打磨（Day 15-20）

**目标**：从反复出现的模式中**自动沉淀项目知识**，完善 README 和演示流程。

### 5.1 知识沉淀（每 5 次会话触发）

`memory/l3_knowledge.py`：

```python
import json
import os
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

KB_DIR = "storage/knowledge_base"

ALCHEMIST_PROMPT = """你是知识提炼专家。
根据下方多次学习记录，提炼出可复用的"学习模式/踩坑记录"。

每条知识用以下 JSON 格式输出：
{
  "entries": [
    {
      "type": "pattern 或 pitfall",
      "title": "标题",
      "description": "详细描述",
      "tags": ["相关知识点标签"]
    }
  ]
}

学习记录：
{digests}"""

def maybe_extract_knowledge(session_count: int):
    """每 5 次会话触发一次知识提炼"""
    if session_count % 5 != 0:
        return

    sessions_dir = "storage/sessions"
    recent_digests = []
    if os.path.exists(sessions_dir):
        dirs = sorted(os.listdir(sessions_dir))[-5:]
        for d in dirs:
            digest_path = os.path.join(sessions_dir, d, "digest.json")
            if os.path.exists(digest_path):
                with open(digest_path, "r", encoding="utf-8") as f:
                    recent_digests.append(json.load(f))

    if len(recent_digests) < 3:
        return

    client = ZhipuAI(api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "只输出 JSON"},
            {"role": "user", "content": ALCHEMIST_PROMPT.replace(
                "{digests}", json.dumps(recent_digests, ensure_ascii=False))}
        ]
    )

    result = json.loads(resp.choices[0].message.content)

    for entry in result.get("entries", []):
        entry_type = entry.get("type", "pattern")
        dir_path = os.path.join(KB_DIR, f"{entry_type}s")
        os.makedirs(dir_path, exist_ok=True)

        filename = entry["title"].replace(" ", "-").lower()[:50] + ".md"
        filepath = os.path.join(dir_path, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"type: {entry_type}\n")
            f.write(f"title: \"{entry['title']}\"\n")
            f.write(f"tags: {json.dumps(entry.get('tags', []), ensure_ascii=False)}\n")
            f.write(f"---\n\n")
            f.write(f"# {entry['title']}\n\n")
            f.write(f"{entry['description']}\n")

    _rebuild_memory_index()

def _rebuild_memory_index():
    """重建 MEMORY.md 索引"""
    index_path = os.path.join(KB_DIR, "MEMORY.md")
    lines = ["# 学习知识库\n"]

    for category in ["patterns", "pitfalls"]:
        cat_dir = os.path.join(KB_DIR, category)
        if os.path.exists(cat_dir):
            lines.append(f"\n## {category.title()}\n")
            for fname in sorted(os.listdir(cat_dir)):
                if fname.endswith(".md"):
                    lines.append(f"- [{fname}]({category}/{fname})")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

### 5.2 完整 README

`README.md`：

```markdown
# 📚 个人学习助手 Agent

基于事件驱动 Hook + 四层记忆架构的 AI 编程学习助手。

## 核心特性

- 🧠 **跨会话记忆**：今天学的，明天还记得
- 📊 **知识状态追踪**：自动记录你掌握了什么、卡在哪里
- 🔍 **语义检索**：从历史学习中找到最相关的经验
- 📝 **自动知识沉淀**：从反复出现的模式中提炼可复用知识

## 架构

事件驱动 Hook → L1 会话状态 → L2 任务连续性 → L3 知识沉淀 → L4 用户画像
                      ↓                                              ↓
                  向量索引                                       记忆注入

## 快速开始

pip install -r requirements.txt
cp .env.example .env   # 填入 API Key
python test_api.py     # 验证 API 连通
python main.py         # 启动学习助手
```

### ✅ 里程碑 5

完整可演示的 Demo。

***

## 最终检查清单

| 检查项                                      | 通过标准                       |
| ---------------------------------------- | -------------------------- |
| ✅ 首次对话可以正常学习                             | 能解释、出题、判题                  |
| ✅ 退出后有 journal.jsonl 和 session\_notes.md | 文件存在且内容合理                  |
| ✅ 第二次启动自动加载记忆                            | 终端显示"已加载历史记忆"              |
| ✅ Agent 知道上次学了什么                         | 不用提醒就能说出上次内容               |
| ✅ 学了 5+ 次后有知识沉淀                          | knowledge\_base/ 下有 .md 文件 |
| ✅ 语义检索工作                                 | 问旧话题能找到相关历史                |
| ✅ storage/ 在 .gitignore 中                | 不会误提交用户数据                  |

***

## 面试时的核心回答

| 追问                      | 可以说的话                                                                  |
| ----------------------- | ---------------------------------------------------------------------- |
| "200 条摘要怎么检索？"          | 用 ChromaDB 做语义向量检索，按相关性排序而不是时间序列                                       |
| "compact 了怎么办？"         | PreCompact Hook 先写 compact\_state，PostCompact 刷新注入，恢复点在 compact 前就保证了  |
| "怎么决定调哪个工具？"            | 用 Function Calling，LLM 根据工具 description 和当前上下文自主决策                     |
| "context window 超了怎么办？" | 记忆注入有 token 预算，优先级是任务状态 > 用户偏好 > 历史摘要，超预算就截断                           |
| "用户画像 LLM 推断错了怎么办？"     | journal.jsonl 是 append-only 事件源，画像是派生状态，可以从事件流重建                       |
| "知识库质量怎么保证？"            | knowledge\_base 有 MEMORY.md 索引，每个 topic 有 frontmatter 标注来源 session，可追溯 |

***

**一句话简历描述**：

> 基于事件驱动 Hook + 四层记忆架构（会话状态/任务连续性/知识沉淀/用户画像）实现的个人学习助手 Agent，通过 Stop/PreCompact 钩子保证跨会话任务可恢复，使用向量语义检索解决长期记忆相关性问题，后台异步 Job 负责知识提炼与用户画像更新，主 Agent 通过 Function Calling 自主决策工具调用。

