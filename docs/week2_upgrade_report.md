# 408学习Agent — 第二周 LangGraph 编排升级报告

> **项目**：408考研学习助手 | **阶段**：Week 2 — LangGraph 状态图编排  
> **日期**：2025-04-17 | **验证状态**：✅ 全部通过

---

## 0. 启动验证结果

```
✅ StateGraph 编译成功
✅ AgentState 构造成功，消息数=2
✅ 关键词映射："出题"→generate_quiz（预期 generate_quiz）
✅ get_tool_by_name: name=explain_concept_tool
✅ LangGraphAgent 类已定义

🎉 第二周全部验证通过！
```

> 验证方式：不启动完整 App，仅测试 LangGraphAgent 核心模块初始化，
> 覆盖图编译、状态构造、意图路由、工具注册、Agent 类定义五个维度。

---

## 1. 升级目标

第一周完成了 RAG 检索管线（ChromaDB 向量检索 + BM25 混合融合）和 L1–L4 四层记忆系统的搭建。  
第二周的核心目标是**将 Agent 的控制流从自研 while-loop Function Calling 循环升级为 LangGraph 声明式状态图编排**，同时完整保留原有的 L1–L4 记忆系统，并对外维持相同接口（`chat()` / `chat_stream()` / `on_session_end()`），做到对 Gradio 前端层零改动。

具体升级内容：

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 控制流 | Python while 循环 + 手工判断 tool_calls | LangGraph StateGraph 声明式节点图 |
| 路由逻辑 | 系统提示词约束 LLM 自主选工具 | 意图路由节点 → 条件边 → 多分支并行 |
| 状态管理 | 实例变量（self.messages 列表） | AgentState TypedDict + add_messages Reducer |
| 工具适配 | 原生 ZhipuAI tools 格式 | LangChain @tool 装饰器双轨制 |
| 记忆集成 | System Prompt 注入 | AgentState 字段传递 + memory_update_node |

---

## 2. 架构变化对比

### 2.1 改造前（自研 Function Calling 循环）

```
用户输入
   │
   ▼
┌─────────────────────────────────────┐
│  LearningAgent.chat()               │
│                                     │
│  1. append user message             │
│  2. LLM 请求（带 TOOL_DEFINITIONS） │
│         │                           │
│         ▼                           │
│  msg.tool_calls?                    │
│    ├─ YES ──► execute_tool()        │
│    │          append tool result    │
│    │          LLM 第二次请求        │
│    │          → 得到 final reply    │
│    │                                │
│    └─ NO  ──► 直接使用 msg.content  │
│                                     │
│  3. session.log_assistant_message() │
│  4. append assistant message        │
└─────────────────────────────────────┘
   │
   ▼
返回 reply 字符串

特点：
- 单路线性，无分支
- 工具由 LLM 自主决定（tool_choice="auto"）
- 记忆通过 system prompt 字符串拼接注入
- while 循环最多支持多轮工具调用（实际为单轮）
```

### 2.2 改造后（LangGraph 状态图）

```
用户输入（HumanMessage）
   │
   ▼
┌──────────────────────────────────────────────────────┐
│                  LangGraph StateGraph                │
│                                                      │
│  START                                               │
│    │                                                 │
│    ▼                                                 │
│  [intent_router] ── LLM 语义分类 + 关键词映射        │
│    │                                                 │
│    ├─ intent="study"  ──► [rag_node]                │
│    │                         │                      │
│    │                         ▼ (route_after_rag)    │
│    │                      [tool_executor]            │
│    │                         │                      │
│    ├─ intent="plan"   ──► [tool_executor]            │
│    │                         │                      │
│    ├─ intent="review" ──► [rag_node]                │
│    │                         │                      │
│    │                         ▼ (route_after_rag)    │
│    │                      [response_generator]       │
│    │                         ▲                      │
│    └─ intent="unknown"───────┘                      │
│                              │                      │
│    [tool_executor] ──────► [response_generator]     │
│                              │                      │
│                              ▼                      │
│                        [memory_update]               │
│                              │                      │
│                             END                     │
└──────────────────────────────────────────────────────┘
   │
   ▼
state["final_response"]

特点：
- 声明式图，节点职责单一
- 意图驱动的三分支路由
- 状态在节点间以不可变 dict 传递
- 所有分支最终汇聚到 memory_update → END
```

---

## 3. 核心技术详情

### 3.1 AgentState 设计（TypedDict + Reducer）

```python
class AgentState(TypedDict):
    messages:        Annotated[list[BaseMessage], add_messages]  # ① 对话历史
    intent:          Literal["study","plan","review","unknown"]  # ② 路由决策
    rag_context:     str                                          # ③ RAG检索结果
    tool_name:       str                                          # ④ 待执行工具名
    tool_args:       dict                                         # ⑤ 工具参数
    tool_result:     str                                          # ⑥ 工具返回值
    memory_l2:       dict                                         # ⑦ L2任务状态快照
    memory_l4:       dict                                         # ⑧ L4用户画像快照
    session_events:  list[dict]                                   # ⑨ L1事件流缓冲
    final_response:  str                                          # ⑩ 最终回复文本
    error:           str                                          # ⑪ 节点错误信息
```

**各字段用途说明：**

| 字段 | 写入节点 | 用途 |
|------|----------|------|
| `messages` | intent_router / response_generator | 完整多轮对话历史，add_messages reducer 自动追加去重 |
| `intent` | intent_router | 路由决策依据，决定走哪条分支 |
| `rag_context` | rag_node | 检索到的知识库文本，注入 response_generator |
| `tool_name` | intent_router | 关键词映射或 intent 默认值确定的工具名 |
| `tool_args` | intent_router / tool_executor | 工具参数，topic 由 LLM 语义分类时提取 |
| `tool_result` | tool_executor | 工具执行结果，注入 response_generator |
| `memory_l2` | LangGraphAgent.__init__ / memory_update_node | L2 任务状态快照（计划、卡点、进度） |
| `memory_l4` | LangGraphAgent.__init__ / memory_update_node | L4 用户画像快照（知识图谱、薄弱点） |
| `session_events` | tool_executor | L1 事件流，用于会话结束时生成摘要 |
| `final_response` | response_generator | 最终返回给用户的文本 |
| `error` | tool_executor / response_generator | 节点执行失败时的错误信息 |

**为什么 `messages` 要用 `add_messages` Reducer？**

LangGraph 的状态更新默认是"覆盖语义"——节点返回的新 state 会替换旧值。  
如果 messages 用普通 `list[BaseMessage]`，每个节点只要返回新 messages 就会**清空历史**。  
`add_messages` 是 LangGraph 内置的 Reducer 函数，它的语义是**追加合并**：
- 新消息按 `id` 去重后追加到已有列表
- 任何节点都可以安全地只返回"本节点新增的消息"
- 多轮对话历史在整个图执行过程中始终完整保留

```python
# 没有 Reducer：节点返回新消息会覆盖全部历史
messages: list[BaseMessage]                          # ❌

# 有 Reducer：节点返回新消息会追加到历史
messages: Annotated[list[BaseMessage], add_messages] # ✅
```

---

### 3.2 意图路由节点（Intent Router）

**双层决策架构：**

```
用户消息
   │
   ▼
Layer 1: LLM 语义粗分类（GLM-4-Flash）
   输入：用户消息
   输出：{"intent": "study", "confidence": 0.95, "topic": "快速排序"}
   分类：study / plan / review / unknown
   │
   ▼
Layer 2: 关键词精确映射（12个关键词）
   命中 → 覆盖 tool_name（优先级高于 intent 默认）
   未命中 → 使用 intent 默认工具
   │
   ▼
写入 state["intent"] + state["tool_name"] + state["tool_args"]["topic"]
```

**12个关键词映射表：**

```python
_KEYWORD_TOOL_MAP = {
    "出题": "generate_quiz",   "练习": "generate_quiz",   "做题": "generate_quiz",
    "判断": "check_answer",    "对吗": "check_answer",    "答案": "check_answer",
    "计划": "save_study_plan", "安排": "save_study_plan",
    "推荐": "recommend_next",  "接下来": "recommend_next",
    "进度": "read_study_plan", "完成": "complete_task",
}
```

**intent → 默认工具映射：**

```python
_INTENT_TOOL_MAP = {
    "study":   "explain_concept",  # 知识讲解
    "plan":    "read_study_plan",  # 查看计划
    "review":  "recommend_next",   # 复习推荐
    "unknown": "",                 # 无工具
}
```

**降级策略：** LLM 调用失败（网络超时、解析异常）→ `except Exception` → `intent = "study"`，保证系统永不崩溃。

---

### 3.3 三分支路由设计

#### 条件边定义（`route_by_intent`）

```python
def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    if intent == "study":   return "rag_then_tool"
    elif intent == "plan":  return "plan_branch"
    elif intent == "review":return "review_branch"
    else:                   return "direct_response"
```

#### 分支一：study（知识问答主链路）

```
[intent_router] ──"rag_then_tool"──► [rag_node]
                                         │
                                    检索 ChromaDB+BM25
                                    写入 rag_context
                                         │
                                  route_after_rag()
                                  intent=="study" → "tool_executor"
                                         │
                                    [tool_executor]
                                    执行工具（explain/quiz/check）
                                    写入 tool_result
                                         │
                                    [response_generator]
                                    整合 rag_context + tool_result
                                    调用 GLM → final_response
```

**适用场景**：讲解知识点、出题、判断答案——需要 RAG 检索作为参考资料，也需要工具调用执行具体操作。

#### 分支二：plan（计划管理）

```
[intent_router] ──"plan_branch"──► [tool_executor]
                                       │
                                  直接执行计划工具
                                  （save/read/complete_task）
                                       │
                                  [response_generator]
                                  整合 tool_result
                                  调用 GLM → final_response
```

**适用场景**：创建/查看/更新学习计划——计划数据存储在本地 JSON 文件，不需要 RAG 检索知识库。

#### 分支三：review（复习推荐）

```
[intent_router] ──"review_branch"��─► [rag_node]
                                          │
                                     检索 ChromaDB+BM25
                                     写入 rag_context
                                          │
                                   route_after_rag()
                                   intent=="review" → "response_generator"
                                          │
                                     [response_generator]
                                     整合 rag_context + memory_l4（薄弱点）
                                     调用 GLM → 个性化复习建议
```

**适用场景**：复习推荐——需要检索知识库了解考点，结合 L4 用户画像中的薄弱点，直接生成个性化建议，不需要独立的工具节点。

#### `route_after_rag` 条件边的设计意图

`rag_node` 被 study 和 review 两个分支共享复用。但两者在 RAG 之后的走向不同：
- study → 还需要执行具体工具（出题/讲解/判答）
- review → RAG 结果已足够，直接生成回复

`route_after_rag` 通过读取 `state["intent"]` 来区分这两种情况，实现了**一个节点、两条出路**的复用设计，避免了重复定义 rag_node。

---

### 3.4 工具层双轨制（tools.py + lc_tools.py）

#### 原版 `agent/tools.py`（执行层，Week 1 保留）

```python
# 工具定义：ZhipuAI Function Calling 格式
TOOL_DEFINITIONS = [{"type": "function", "function": {...}}, ...]

# 统一执行入口
def execute_tool(tool_name: str, arguments_json: str) -> str:
    ...  # 调用 RAG 检索 + LLM 生成工具结果
```

- 维护 ZhipuAI 原生 Function Calling 格式的工具 schema
- `execute_tool()` 是统一分发入口，根据 tool_name 路由到对应实现
- 工具实现内部仍然调用 RAG 检索和 GLM 生成

#### 新增 `agent/lc_tools.py`（适配层，Week 2 新增）

```python
@tool
def explain_concept_tool(topic: str, depth: str = "beginner") -> str:
    """讲解408考研知识点。"""
    from agent.tools import execute_tool
    return execute_tool("explain_concept", json.dumps({"topic": topic, "depth": depth}))
```

- 用 LangChain `@tool` 装饰器将每个工具包装为 `StructuredTool`
- 函数 docstring 作为工具描述，参数类型注解自动生成 JSON Schema
- **内部直接调用 `agent/tools.py` 的 `execute_tool()`**，不重复实现逻辑

**两者关系总结：**

```
lc_tools.py  ←──── 适配层（LangChain StructuredTool 格式）
    │  调用
    ▼
tools.py     ←──── 执行层（业务逻辑 + RAG + GLM）
```

`lc_tools.py` 是 `tools.py` 的 LangChain 包装层，所有工具的真实执行逻辑仍然在 `tools.py` 中，Week 2 只增加了一个薄薄的适配层，做到最小改动。

---

### 3.5 记忆系统在 LangGraph 中的整合

#### 四层记忆架构回顾（Week 1）

```
L1 (Session)  : 当前会话的完整事件流（journal.jsonl）
L2 (Task)     : 跨会话任务状态（学习计划、卡点、进度）
L3 (Knowledge): 知识库（ChromaDB 向量 + BM25 索引）
L4 (Profile)  : 用户长期画像（知识图谱、掌握度分布）
```

#### LangGraph 中的整合方式

**① AgentState 承载 L2/L4 快照**

```python
class AgentState(TypedDict):
    memory_l2: dict   # L2 任务状态快照（load_task_state() 的结果）
    memory_l4: dict   # L4 用户画像快照（load_profile() 的结果）
    session_events: list[dict]  # L1 事件流缓冲（本轮积累）
```

快照在 `LangGraphAgent.__init__()` 时从磁盘加载一次，随后跟随 state 在节点间传递。

**② response_generator_node 消费 L2/L4**

```python
# 从 L2 读取卡点
blockers = memory_l2.get("blockers", [])
# 从 L4 读取薄弱知识点
weak_nodes = [k for k,v in knowledge_graph.items() if v < 0.5]
# 注入到 system prompt 的补充信息中
supplement_parts.append(f"【用户当前学习卡点（L2）】\n{blockers_text}")
supplement_parts.append(f"【用户薄弱知识点（L4）】\n{', '.join(weak_nodes)}")
```

**③ memory_update_node 每轮刷新快照**

每轮对话结束（`response_generator` → `memory_update` → `END`）时执行：
1. 从磁盘重新 `load_task_state()` → 刷新 `memory_l2`
2. 从磁盘重新 `load_profile()` → 刷新 `memory_l4`
3. 将本轮 `intent` + `topic` + `events_count` 追加到 `memory_l2["session_events_buffer"]`

**④ tool_executor_node 写入 L1 事件流**

```python
session_events.append({
    "type": "tool_call",
    "tool_name": tool_name,
    "tool_args": tool_args,
    "tool_result_preview": tool_result[:200],
    "timestamp": datetime.now().isoformat(),
})
```

**⑤ on_session_end() 仍走完整 Hook 链**

```python
def on_session_end(self):
    from memory.hooks import on_session_stop
    digest = on_session_stop(self.session)
    # hooks.py 内部：L1 原始日志 → LLM 生成摘要 → L2 更新卡点
    #              → L3 知识库索引 → L4 更新用户画像
```

会话结束时，完整的 L1→L2→L3→L4 更新链条与原版完全一致，LangGraph 改造对记忆系统的持久化逻辑**零侵入**。

---

### 3.6 向后兼容设计

**核心原则：新增，不替换。**

```python
# agent/main_agent.py 中两个类共存
class LearningAgent:      # ← Week 1 原版，完整保留，未删除任何代码
    def chat(self, ...): ...
    def chat_stream(self, ...): ...
    def on_session_end(self): ...

class LangGraphAgent:     # ← Week 2 新增
    def chat(self, ...): ...        # 相同接口签名
    def chat_stream(self, ...): ... # 相同接口签名
    def on_session_end(self): ...   # 相同接口签名
```

**app.py 仅需修改一行 import：**

```python
# Week 1
from agent.main_agent import LearningAgent as Agent

# Week 2（只改这一行）
from agent.main_agent import LangGraphAgent as Agent
```

Gradio 前端代码、`app.py` 中的所有调用点（`agent.chat()`、`agent.chat_stream()`、`agent.on_session_end()`）**完全不需要修改**。

---

## 4. 文件变更清单

| 文件路径 | 变更类型 | 说明 |
|----------|----------|------|
| `agent/graph/state.py` | 🆕 新增 | AgentState TypedDict 定义，含 add_messages reducer |
| `agent/graph/graph.py` | 🆕 新增 | StateGraph 构建函数，5个节点 + 2个条件边 |
| `agent/graph/nodes/intent_router.py` | 🆕 新增 | 意图路由节点，LLM分类 + 关键词映射双层决策 |
| `agent/graph/nodes/rag_node.py` | 🆕 新增 | RAG检索节点，study/review分支共享 |
| `agent/graph/nodes/tool_executor.py` | 🆕 新增 | 工具执行节点，含L1事件流写入 |
| `agent/graph/nodes/response_generator.py` | 🆕 新增 | 回复生成节点，整合RAG+工具结果+L2/L4记忆 |
| `agent/graph/nodes/memory_update.py` | 🆕 新增 | 记忆更新节点，每轮刷新L2/L4快照 |
| `agent/lc_tools.py` | 🆕 新增 | LangChain @tool 适配层，7个工具包装 |
| `agent/main_agent.py` | ✏️ 修改 | 新增 LangGraphAgent 类，保留 LearningAgent |

---

## 5. 面试问答参考

### Q1：为什么用 LangGraph 而不是继续自研循环？

**A：** 自研 while-loop 的本质问题是**控制流与业务逻辑耦合**——工具选择、RAG 检索、记忆注入全部堆在 `chat()` 方法里，复杂度随功能增长呈线性膨胀，难以扩展和测试。

LangGraph 解决了三个具体问题：
1. **可观测性**：每个节点是独立函数，可以单独断点调试、单独单测
2. **可扩展性**：增加新分支只需 `add_node` + `add_conditional_edges`，不修改现有节点
3. **状态显式化**：AgentState 让每轮对话的中间状态（rag_context、tool_result、intent）都有明确的字段追踪，调试时一目了然

此外，LangGraph 是行业标准（LangChain 官方，被 Anthropic/Google 广泛使用），使用它意味着可以对接 LangSmith 可观测平台、Checkpoint 持久化等生态工具。

---

### Q2：三个分支怎么设计的，为什么这么分？

**A：** 分支设计的依据是**信息需求的差异**：

| 分支 | RAG? | 工具? | 原因 |
|------|------|-------|------|
| study | ✅ | ✅ | 讲解/出题需要知识库参考资料（RAG）+ 工具执行具体操作 |
| plan | ❌ | ✅ | 计划数据在本地文件系统，不需要检索知识库 |
| review | ✅ | ❌ | 复习推荐需要知识库了解考点，结合画像直接生成建议，不需要独立工具 |

本质上是**按数据流需求划分路径**，避免每次对话都做所有操作（节省 latency 和 token 消耗）。

---

### Q3：add_messages reducer 是什么，为什么需要它？

**A：** LangGraph 图执行时，节点返回的 state 片段会被**合并**回全局状态。  
默认合并语义是字段级覆盖：节点返回 `{"messages": [...]}` 就会替换掉原来的整个 messages 列表。

这对多轮对话是灾难性的——每个节点只想追加一条新消息，却会把历史全部清空。

`add_messages` 是 LangGraph 提供的内置 Reducer，它将合并语义改为**按消息 id 去重追加**：

```python
# 全局 state: messages = [SystemMsg, HumanMsg]
# intent_router 返回: {"messages": [HumanMsg(已有)]}
# 使用 add_messages 后: messages = [SystemMsg, HumanMsg]  ← 去重，不重复追加
# response_generator 返回: {"messages": [AIMessage("回复")]}
# 合并后: messages = [SystemMsg, HumanMsg, AIMessage]    ← 正确追加
```

通过 `Annotated[list[BaseMessage], add_messages]` 类型注解声明，LangGraph 自动识别并使用该 Reducer。

---

### Q4：route_after_rag 条件边解决了什么问题？

**A：** `rag_node` 被 study 和 review 两个分支共用——如果没有 `route_after_rag`，就需要定义两个几乎完全相同的 rag_node，违反 DRY 原则。

但 study 在 RAG 之后还需要 tool_executor，review 在 RAG 之后直接进 response_generator。

`route_after_rag` 通过读取 `state["intent"]` 来动态决定下游节点：

```python
def route_after_rag(state: AgentState) -> str:
    return "tool_executor" if state["intent"] == "study" else "response_generator"
```

这样 `rag_node` 成为一个**无状态的纯函数节点**（只做检索，不关心后续流程），两条分支都能正确复用它，体现了 LangGraph 条件边的核心价值：**路由逻辑与节点逻辑分离**。

---

### Q5：LangGraph 引入后，原来的 L1–L4 记忆系统怎么了？

**A：** 四层记忆系统**完全保留，零侵入**，只是集成方式发生了变化：

| 记忆层 | 原版 | LangGraph 版 | 变化 |
|--------|------|--------------|------|
| L1 Session | `session.log_*()` 手动调用 | `tool_executor_node` 写入 `session_events`；`LangGraphAgent.chat()` 调用 `session.log_*()` | 写入时机一致，多了 state 内缓冲 |
| L2 Task | 手动调用 `load_task_state()` 注入 system | `memory_l2` 字段在 state 中传递；`memory_update_node` 每轮刷新 | 从 system 注入改为 state 传递 |
| L3 Knowledge | RAG 检索在工具内部调用 | 独立的 `rag_node` 显式调用 `retrieve()` | 职责更清晰 |
| L4 Profile | 手动调用 `load_profile()` 注入 system | `memory_l4` 字段在 state 中传递；`response_generator_node` 读取薄弱点 | 从 system 注入改为 state 传递 |
| on_session_end | `memory/hooks.py` on_session_stop | **完全一致**，`LangGraphAgent.on_session_end()` 直接调用 `on_session_stop()` | **零改动** |

持久化层（磁盘文件读写、ChromaDB 操作）完全没有改动，LangGraph 改造只影响了**运行时的数据流动方式**。

---

## 6. 两周总体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户交互层                                   │
│                                                                     │
│   用户浏览器  ──HTTP──►  Gradio Web UI (app.py)                     │
│                              │                                      │
│                    agent = LangGraphAgent(user_id)                  │
│                    agent.chat_stream(user_input)                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    LangGraph 状态图（Week 2）                        │
│                                                                     │
│  AgentState {messages, intent, rag_context, tool_name,              │
│              tool_args, tool_result, memory_l2, memory_l4,          │
│              session_events, final_response, error}                 │
│                                                                     │
│  START → [intent_router] ──────────────────────────────────────    │
│               │ LLM分类+关键词映射                                   │
│               ├─ study  ──► [rag_node] ──► [tool_executor] ──►┐    │
│               ├─ plan   ────────────────► [tool_executor] ──►┤    │
│               ├─ review ──► [rag_node] ──────────────────────►┤    │
│               └─ unknown ─────────────────────────────────────►┤    │
│                                                                 │   │
│                                              [response_generator]   │
│                                                    │ GLM-4-Flash    │
│                                              [memory_update] ──END  │
└─────────────────────────────────────────────────────────────────────┘
         │ rag_node调用              │ response_generator读取
┌────────▼─────────────┐   ┌────────▼──────────────────────────────┐
│   RAG 管线（Week 1）  │   │        L1–L4 记忆系统（Week 1）        │
│                      │   │                                        │
│  Query Rewriter      │   │  L1: SessionManager (journal.jsonl)   │
│       │              │   │       ↕ 每轮写入事件流                  │
│  ┌────▼───────────┐  │   │  L2: TaskState (plans/*.json)         │
│  │ Hybrid Fusion  │  │   │       ↕ memory_update_node 刷新        │
│  │                │  │   │  L3: KnowledgeBase (ChromaDB+BM25)    │
│  │ ┌────────────┐ │  │   │       ↕ rag_node 检索                  │
│  │ │ ChromaDB   │ │  │   │  L4: UserProfile (user_profile/)      │
│  │ │ 向量检索   │ │  │   │       ↕ memory_update_node 刷新        │
│  │ └────────────┘ │  │   │                                        │
│  │ ┌────────────┐ │  │   │  on_session_end() → hooks.py          │
│  │ │ BM25索引   │ │  │   │  L1→摘要→L2更新→L3索引→L4更新         │
│  │ └────────────┘ │  │   └────────────────────────────────────────┘
│  │   RRF融合      │  │
│  │   Score Gate   │  │
│  └────────────────┘  │
│                      │
│  存储：              │
│  storage/chroma_db/  │
│  storage/bm25_index/ │
└──────────────────────┘
```

**数据流说明：**
- 用户每发一条消息 → LangGraph 图执行一次（START → END）
- `rag_node` 在每次图执行时调用 RAG 管线（study/review 分支）
- `memory_update_node` 在每次图执行结束时刷新 L2/L4 快照
- 用户关闭会话时 `on_session_end()` 触发完整的 L1→L4 更新链

---

## 7. 下周计划（第三周：后端服务化）

### 目标：将 Gradio 原型升级为生产级 REST API 服务

| 技术组件 | 用途 | 关键点 |
|----------|------|--------|
| **FastAPI** | HTTP API 框架 | 替换 Gradio，提供标准 RESTful 接口 |
| **PostgreSQL** | 持久化存储 | 用户数据、会话记录、学习计划迁移到关系型数据库 |
| **Redis** | 缓存 + 会话状态 | LangGraph State 的跨请求持久化，避免重复加载 |
| **JWT** | 身份认证 | Bearer Token 鉴权，支持多用户隔离 |
| **SSE** | 流式输出 | 真正的服务端 Server-Sent Events，替换当前模拟流式 |

### 核心接口设计（预计）

```
POST   /api/v1/auth/login          # JWT 登录
POST   /api/v1/chat                # 同步对话
GET    /api/v1/chat/stream         # SSE 流式对话
POST   /api/v1/session/end         # 触发 on_session_end()
GET    /api/v1/plan                # 读取学习计划
PUT    /api/v1/plan/{plan_name}    # 更新学习计划
GET    /api/v1/profile             # 读取用户画像
```

### LangGraph Stream 集成（Week 2 遗留）

当前 `chat_stream()` 是用同步 `chat()` 的结果模拟流式（按标点分句 yield）。  
Week 3 将接入 LangGraph 原生 `.stream()` API，实现真正的节点级流式输出：

```python
# Week 3 目标实现
async def chat_stream_sse(user_message: str):
    async for event in self._graph.astream(initial_state):
        if "response_generator" in event:
            token = event["response_generator"].get("final_response", "")
            yield f"data: {token}\n\n"  # SSE 格式
```

---

*报告生成时间：2025-04-17 | 验证环境：Python 3.11 + LangGraph 0.2.x + LangChain Core*  
*项目路径：E:\DEMO | 验证命令：见第 0 节启动验证结果*
