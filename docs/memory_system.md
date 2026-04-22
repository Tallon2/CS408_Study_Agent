# L1-L4 分层记忆系统设计

> 模块路径：`memory/` | 版本 v2.0

---

## 1. 分层记忆架构概述

本系统采用 **四层记忆架构**，模拟人类记忆的短期/长期分层，实现跨会话的学习追踪和个性化辅导。

### 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                       记忆系统 (memory/)                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L1 会话记忆 (l1_session.py)                              │   │
│  │  ● append-only 事件日志                                    │   │
│  │  ● journal.jsonl — 用户消息/助手回复/工具调用/困惑点       │   │
│  │  ● 每个会话一个目录: storage/sessions/YYYYMMDD_HHMMSS/    │   │
│  │  ● 生命周期: 单次会话                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │ on_session_stop                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L2 任务状态 (l2_task.py)                                 │   │
│  │  ● 薄弱点追踪 (blockers)                                  │   │
│  │  ● 纠偏记录 (task_corrections)                            │   │
│  │  ● 任务连续性 (next_action / session_count)                │   │
│  │  ● 存储: storage/tasks/task_state.json                    │   │
│  │  ● 生命周期: 跨会话累积                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │ 每5次会话                            │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L3 知识沉淀 (l3_knowledge.py)                            │   │
│  │  ● LLM 提炼学习模式 (patterns) 和踩坑记录 (pitfalls)     │   │
│  │  ● Markdown 文件: storage/knowledge_base/{patterns,pitfalls}/│  │
│  │  ● MEMORY.md 索引文件                                     │   │
│  │  ● 生命周期: 长期累积                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │ 每次会话                            │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L4 用户画像 (l4_profile.py)                              │   │
│  │  ● 知识图谱: {topic → {status, attempts, last_session}}  │   │
│  │  ● 学习偏好: {explanation_style, practice_preference, pace}│  │
│  │  ● 存储: storage/user_profile/profile.json                │   │
│  │  ● 偏好提炼: 每3次会话触发 LLM 推断                       │   │
│  │  ● 生命周期: 长期累积                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  记忆注入 (retrieval.py → build_memory_context)           │   │
│  │  ● L2 任务状态 + L4 画像 + L3 语义检索 → 拼接为系统提示  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  生命周期钩子 (hooks.py)                                   │   │
│  │  ● on_session_stop: LLM摘要 → L2更新 → L4更新             │   │
│  │                      → 向量索引 → L3提炼(每5次)           │   │
│  │  ● on_pre_compact: 会话中间快照                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. L1 会话记忆

> 源码：`memory/l1_session.py → SessionManager`

### 设计原则

**Append-only 事件日志**：所有会话事件以 JSONL 格式追加写入，不修改、不删除，保证完整审计轨迹。

### 核心类：SessionManager

```python
class SessionManager:
    def __init__(self, user_id: str, session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = f"storage/sessions/{self.session_id}"
        self.journal_path = os.path.join(self.session_dir, "journal.jsonl")
        self.topics_touched = []      # 涉及的知识点
        self.user_struggles = []      # 用户困惑点
        self.event_counter = 0        # 事件计数器
```

### journal.jsonl 事件格式

每行一个 JSON 对象：

```json
{
  "event_id": "evt-0001",
  "ts": "2025-04-17T11:05:48.123456",
  "session_id": "20260417_110548",
  "event_type": "user_message",
  "payload": {
    "content": "请解释进程和线程的区别"
  }
}
```

### 事件类型

| 事件类型 | 触发方法 | payload 字段 |
|---------|---------|-------------|
| `user_message` | `log_user_message(message)` | `content` |
| `assistant_message` | `log_assistant_message(message)` | `content` |
| `tool_call` | `log_tool_call(name, args, result)` | `tool_name`, `arguments`, `result` |
| `user_struggle` | `log_struggle(topic, detail)` | `topic`, `detail` |
| `session_stop` | `on_session_stop()` | `digest` |

### 会话目录结构

```
storage/sessions/20260417_110548/
├── journal.jsonl       # 事件流日志（核心，append-only）
├── digest.json         # 会话摘要（on_session_stop 生成）
├── session_notes.md    # 人类可读的摘要（on_session_stop 生成）
└── compact_state.json  # 中间快照（on_pre_compact 生成）
```

### get_messages_text()

读取 journal.jsonl，提取 `user_message` 和 `assistant_message` 事件，拼接为"用户: xxx\n助手: xxx"的纯文本格式，供 `on_session_stop()` 生成摘要时使用。

---

## 3. L2 任务状态

> 源码：`memory/l2_task.py`

### 设计目标

**跨会话任务连续性**：追踪用户的学习进度、薄弱点、纠偏记录，使每次新会话可以"接上上次的进度"。

### 数据结构

`storage/tasks/task_state.json`：

```json
{
  "main_goal": "",
  "current_phase": "explore",
  "next_action": "建议从操作系统的死锁检测开始",
  "blockers": ["死锁检测算法", "银行家算法"],
  "task_corrections": ["之前混淆了死锁预防和死锁避免"],
  "subtasks": [],
  "session_count": 12
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `main_goal` | string | 主学习目标 |
| `current_phase` | string | 当前学习阶段（explore / practice / review） |
| `next_action` | string | 上次会话建议的下一步（任务连续性核心） |
| `blockers` | list[str] | 当前薄弱点列表（从 digest.struggled 累积） |
| `task_corrections` | list[str] | 历史纠偏记录（从 digest.corrections 累积） |
| `subtasks` | list | 子任务列表 |
| `session_count` | int | 累计会话次数 |

### 更新逻辑 (update_task_state)

```python
def update_task_state(digest: dict, task_state: dict) -> dict:
    task_state["session_count"] += 1

    # 更新下一步建议
    if digest.get("next_recommendation"):
        task_state["next_action"] = digest["next_recommendation"]

    # 累积薄弱点
    if digest.get("struggled"):
        for item in digest["struggled"]:
            if item not in task_state["blockers"]:
                task_state["blockers"].append(item)

    # 已掌握的知识点从薄弱列表移除
    if digest.get("mastered"):
        task_state["blockers"] = [
            b for b in task_state["blockers"] if b not in digest["mastered"]
        ]

    # 累积纠偏记录
    if digest.get("corrections"):
        task_state["task_corrections"].extend(digest["corrections"])
```

**关键特性**：确定性逻辑，不依赖 LLM，确保更新可预测、可调试。

---

## 4. L3 知识沉淀

> 源码：`memory/l3_knowledge.py`

### 设计目标

**将短期学习记录提炼为长期可复用知识**：通过 LLM 从多次会话摘要中提炼"学习模式"和"踩坑记录"。

### 触发条件

```python
def maybe_extract_knowledge(session_count: int):
    if session_count % 5 != 0 or session_count == 0:
        return  # 每5次会话触发一次
```

### 提炼流程

1. **收集输入**：读取最近 5 个会话的 `digest.json`（至少需要 3 个有效摘要）
2. **LLM 提炼**：调用智谱 GLM，使用 `ALCHEMIST_PROMPT` 提示词
3. **输出解析**：JSON 格式，包含 `entries` 数组
4. **落盘存储**：每条知识保存为独立 Markdown 文件

### LLM Prompt

```
你是知识提炼专家。
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
```

### 知识条目类型

| 类型 | 目录 | 说明 |
|------|------|------|
| `pattern` | `storage/knowledge_base/patterns/` | 学习模式（如"通过类比理解抽象概念"） |
| `pitfall` | `storage/knowledge_base/pitfalls/` | 踩坑记录（如"死锁预防 vs 死锁避免混淆"） |

### 知识文件格式

```markdown
---
type: pattern
title: "通过类比法理解进程调度"
tags: ["操作系统", "进程调度"]
---

# 通过类比法理解进程调度

用户在学习进程调度算法时，通过将 CPU 调度类比为排队问题...
```

### 索引重建

每次提炼完成后调用 `_rebuild_memory_index()` 重建 `storage/knowledge_base/MEMORY.md` 索引文件：

```markdown
# 学习知识库

## Patterns
- [pattern1.md](patterns/pattern1.md)

## Pitfalls
- [pitfall1.md](pitfalls/pitfall1.md)
```

---

## 5. L4 用户画像

> 源码：`memory/l4_profile.py`

### 设计目标

**构建用户知识图谱和学习偏好模型**，实现个性化辅导。

### 数据结构

`storage/user_profile/profile.json`：

```json
{
  "stable_preferences": {
    "explanation_style": "通过类比和实例讲解",
    "practice_preference": "先理论后练习",
    "pace": "稳步推进，每次聚焦1-2个知识点"
  },
  "knowledge_graph": {
    "快速排序": {
      "status": "mastered",
      "last_session": "20260417_130711"
    },
    "死锁检测": {
      "status": "struggling",
      "attempts": 3,
      "last_session": "20260420_142742"
    },
    "B+树": {
      "status": "introduced",
      "last_session": "20260417_165714"
    }
  },
  "update_count": 12,
  "source_sessions": ["20260416_163725", "20260417_110020", "..."]
}
```

### 知识图谱状态

| status | 含义 | 更新逻辑 |
|--------|------|---------|
| `mastered` | 已掌握 | digest.mastered 中的知识点 |
| `struggling` | 薄弱/困惑 | digest.struggled 中的知识点，累计 attempts |
| `introduced` | 已接触但未评估 | digest.topics_learned 中的知识点（首次出现） |

### 更新逻辑 (update_profile_from_digest)

每次会话结束时调用：

```python
def update_profile_from_digest(digest: dict, session_id: str):
    profile = load_profile()
    profile["update_count"] += 1
    profile["source_sessions"].append(session_id)

    kg = profile["knowledge_graph"]

    # 已掌握的知识点 → status = "mastered"
    for topic in digest.get("mastered", []):
        kg[topic] = {"status": "mastered", "last_session": session_id}

    # 薄弱知识点 → status = "struggling", attempts++
    for topic in digest.get("struggled", []):
        existing = kg.get(topic, {"attempts": 0})
        existing["status"] = "struggling"
        existing["attempts"] = existing.get("attempts", 0) + 1
        existing["last_session"] = session_id
        kg[topic] = existing

    # 新接触的知识点 → status = "introduced"（仅首次出现时标记）
    for topic in digest.get("topics_learned", []):
        if topic not in kg:
            kg[topic] = {"status": "introduced", "last_session": session_id}

    # 每3次会话触发偏好提炼
    if profile["update_count"] % 3 == 0:
        profile["stable_preferences"] = _extract_preferences(profile)
```

### 偏好提炼 (_extract_preferences)

每 3 次会话触发一次 LLM 推断，基于知识图谱和历史偏好数据，输出学习风格偏好：

```json
{
  "explanation_style": "喜欢通过类比和图解理解概念",
  "practice_preference": "倾向先做题再看解析",
  "pace": "快速浏览后深入重点"
}
```

---

## 6. 记忆注入机制

> 源码：`memory/retrieval.py → build_memory_context()`

### 设计目标

每次新对话启动时，自动将 L2-L4 记忆拼接为结构化上下文，注入给 LLM 系统提示。

### 注入内容

```python
def build_memory_context(user_id: str, current_question: str = "") -> str:
```

**输出格式**：

```markdown
# 📝 记忆系统注入

## 当前任务状态
- 上次建议从这里继续：学习操作系统死锁检测算法
- 累计学习 12 次
- 当前薄弱点：死锁检测算法, 银行家算法
- 历史纠偏：之前混淆了死锁预防和死锁避免

## 用户知识状态
- 已掌握：快速排序, 链表操作, TCP三次握手
- 薄弱点：死锁检测, B+树
- 已接触：计算机网络分层模型

## 用户偏好
- 讲解风格：通过类比和实例讲解
- 练习偏好：先理论后练习
- 学习节奏：稳步推进，每次聚焦1-2个知识点

## 相关历史学习记录
- 学习主题: 死锁的四个必要条件. 掌握: 死锁定义...
- 学习主题: 进程同步与互斥. 薄弱: PV操作...
```

### 注入组件详解

| 部分 | 数据来源 | 条件 |
|------|---------|------|
| 当前任务状态 | L2 `task_state.json` | `session_count > 0` 或 `next_action` 非空 |
| 用户知识状态 | L4 `profile.json → knowledge_graph` | 知识图谱非空 |
| 用户偏好 | L4 `profile.json → stable_preferences` | 偏好数据非空 |
| 相关历史记录 | 向量语义检索（`MemoryRetriever`） | 有 `current_question` 且向量库非空 |

### 语义检索 (MemoryRetriever)

> 源码：`memory/retrieval.py → MemoryRetriever`

使用独立的 ChromaDB 集合 `session_digests`（存储在 `storage/vector_db/`）索引会话摘要。

**入库**：

```python
def index_session(self, session_id: str, digest: dict):
    doc_text = (
        f"学习主题: {', '.join(digest.get('topics_learned', []))}. "
        f"掌握: {', '.join(digest.get('mastered', []))}. "
        f"薄弱: {', '.join(digest.get('struggled', []))}. "
        f"总结: {digest.get('summary', '')}"
    )
    self.collection.upsert(ids=[session_id], documents=[doc_text], ...)
```

**检索**：使用 ChromaDB 默认 embedding（cosine 距离），返回最相关的历史会话摘要文本。

**Query 重写增强**：检索前先调用 `rewrite_query()` 生成多个改写查询，合并去重结果（最多 5 条）。

---

## 7. 生命周期钩子

> 源码：`memory/hooks.py`

### on_session_stop(session_manager) → dict

会话结束时的核心钩子，触发完整的记忆更新管线：

```
会话结束
    │
    ▼
┌───────────────────────────────────────┐
│ Step 1: LLM 生成会话摘要 (digest)     │
│ Prompt: SCRIBE_PROMPT                 │
│ 输出: JSON {summary, topics_learned,  │
│        mastered, struggled,           │
│        corrections, next_recommendation}│
└────────────────┬──────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌────────┐ ┌────────┐ ┌────────────┐
│落盘:    │ │落盘:    │ │ Log event: │
│notes.md │ │digest  │ │ session_stop│
│         │ │.json   │ │             │
└────────┘ └────────┘ └────────────┘
                 │
                 ▼
┌───────────────────────────────────────┐
│ Step 2: 更新 L2 任务状态               │
│ load_task_state() → update_task_state()│
│ session_count++, blockers 累积/清除    │
└────────────────┬──────────────────────┘
                 │
                 ▼
┌───────────────────────────────────────┐
│ Step 3: 更新 L4 用户画像               │
│ update_profile_from_digest()           │
│ 知识图谱更新，每3次触发偏好提炼        │
└────────────────┬──────────────────────┘
                 │
                 ▼
┌───────────────────────────────────────┐
│ Step 4: 写入向量索引                   │
│ MemoryRetriever.index_session()        │
│ 摘要文本 → ChromaDB session_digests    │
└────────────────┬──────────────────────┘
                 │
                 ▼
┌───────────────────────────────────────┐
│ Step 5: 触发 L3 知识提炼（条件）       │
│ session_count % 5 == 0 时触发          │
│ maybe_extract_knowledge()              │
└───────────────────────────────────────┘
```

### 会话摘要 Prompt (SCRIBE_PROMPT)

```
请根据以下学习对话记录，生成结构化摘要。严格按 JSON 格式输出：

{
  "summary": "一句话总结本次学习内容",
  "topics_learned": ["涉及的知识点列表"],
  "mastered": ["用户已理解的知识点"],
  "struggled": ["用户卡住或答错的知识点"],
  "corrections": ["本次发现的认知纠偏"],
  "next_recommendation": "建议下次从哪里开始"
}
```

### 容错设计

每个 Step 独立 try/except，单个步骤失败不影响其他步骤：

```python
# Step 2: 更新任务状态 (L2)
try:
    task = load_task_state()
    update_task_state(digest, task)
except Exception as e:
    print(f"⚠️  L2 任务状态更新失败: {e}")

# Step 3: 更新用户画像 (L4)
try:
    update_profile_from_digest(digest, session_manager.session_id)
except Exception as e:
    print(f"⚠️  L4 用户画像更新失败: {e}")
```

### on_pre_compact(session_manager) → dict

会话中间快照，保存当前会话的轻量状态：

```json
{
  "session_id": "20260417_130711",
  "topics_touched": ["进程调度", "FCFS"],
  "user_struggles": [{"topic": "FCFS", "detail": "..."}],
  "event_count": 15,
  "saved_at": "2025-04-17T13:07:11"
}
```

存储路径：`storage/sessions/{session_id}/compact_state.json`

---

## 8. 与 LangGraph State 的集成

> 源码：`agent/graph/state.py` + `agent/graph/nodes/memory_update.py`

### AgentState 中的记忆字段

```python
class AgentState(TypedDict):
    # ... 消息和路由字段 ...

    # L2 任务状态快照（由 memory_update_node 填充）
    memory_l2: dict

    # L4 用户画像快照
    memory_l4: dict

    # 本次会话事件流（L1，用于会话结束时生成摘要）
    session_events: list[dict]
```

### 集成方式

```
                    LangGraph 状态图
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
    ▼                     ▼                     ▼
┌─────────┐      ┌──────────────┐      ┌───────────────┐
│rag_node │      │response_     │      │memory_update  │
│         │      │generator     │      │               │
│读取:    │      │读取:         │      │更新:          │
│rag_context│    │memory_l2     │      │memory_l2      │
│(RAG管线) │     │memory_l4     │      │memory_l4      │
│         │      │rag_context   │      │session_events │
└─────────┘      └──────────────┘      └───────────────┘
```

### 数据流

1. **会话开始**：`build_memory_context()` 读取 L2+L4 → 注入系统提示
2. **会话进行中**：`session_events` 在 State 中累积
3. **response_generator**：读取 `memory_l2` + `memory_l4` + `rag_context` 生成个性化回复
4. **memory_update 节点**：更新 L2 任务快照和 L4 画像快照到 State
5. **会话结束**：`on_session_stop()` 触发完整的记忆持久化管线

---

## 9. 数据流总图

```
用户消息
    │
    ├───────────────────────────────┐
    ▼                               ▼
┌────────────┐              ┌──────────────┐
│ L1: 记录到  │              │ Agent Graph   │
│ journal.jsonl│             │               │
│ (append)    │              │  intent_router│
└────────────┘              │  → rag_node   │
                            │  → tool_exec  │
┌────────────┐              │  → resp_gen   │
│ 记忆注入    │─────────────→│  → mem_update │
│ (启动时)   │ L2+L4+L3     │               │
│ build_     │ 上下文        └───────┬───────┘
│ memory_    │                       │
│ context()  │                       │ 最终回复
└────────────┘                       ▼
      ▲                        用户收到回复
      │
      │                     会话结束信号
      │                          │
      │                          ▼
      │                  ┌──────────────────┐
      │                  │ on_session_stop() │
      │                  │                   │
      │                  │ 1. LLM 生成摘要    │
      │                  │ 2. L2 任务更新     │◀─── task_state.json
      │                  │ 3. L4 画像更新     │◀─── profile.json
      │                  │ 4. 向量索引写入    │◀─── vector_db/
      │                  │ 5. L3 知识提炼     │◀─── knowledge_base/
      │                  │    (每5次会话)     │
      │                  └──────────────────┘
      │                          │
      └──────────────────────────┘
           下次会话启动时读取
```

---

## 10. 存储路径汇总

| 层级 | 存储路径 | 格式 | 更新频率 |
|------|---------|------|---------|
| L1 会话 | `storage/sessions/{session_id}/journal.jsonl` | JSONL (append-only) | 每条消息 |
| L1 摘要 | `storage/sessions/{session_id}/digest.json` | JSON | 会话结束 |
| L1 笔记 | `storage/sessions/{session_id}/session_notes.md` | Markdown | 会话结束 |
| L2 任务 | `storage/tasks/task_state.json` | JSON | 会话结束 |
| L3 知识 | `storage/knowledge_base/patterns/*.md` | Markdown + frontmatter | 每5次会话 |
| L3 知识 | `storage/knowledge_base/pitfalls/*.md` | Markdown + frontmatter | 每5次会话 |
| L3 索引 | `storage/knowledge_base/MEMORY.md` | Markdown | 每5次会话 |
| L4 画像 | `storage/user_profile/profile.json` | JSON | 会话结束 |
| 向量索引 | `storage/vector_db/` | ChromaDB | 会话结束 |
