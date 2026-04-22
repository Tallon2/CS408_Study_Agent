# E:\DEMO 项目重构计划（修订版）

> 基于 2026-04-21 源码逐文件阅读后的修正版本

---

## 1. 项目概览

本项目是一个 **408 考研学习助手**，基于 LangGraph 状态图编排，集成 RAG 混合检索、4 层记忆系统、Vue3 前端。

**技术栈：**
- 后端：FastAPI + LangGraph + ZhipuAI (GLM-4-Flash) + ChromaDB + SQLAlchemy
- 前端：Vue3 + TypeScript + Pinia + Vite
- 存储：SQLite (ORM) + ChromaDB (向量) + JSON 文件 (BM25/会话/画像)

---

## 2. 完整目录树（实际结构）

```
E:\DEMO/
├── agent/                         — LangGraph Agent 核心
│   ├── __init__.py
│   ├── main_agent.py              (614 行) 🔴 LearningAgent + LangGraphAgent
│   ├── tools.py                   (564 行) 🔴 工具定义 + 执行
│   ├── lc_tools.py                — LangChain 工具封装
│   └── graph/                     — 状态图定义
│       ├── __init__.py
│       ├── graph.py               (176 行) ✓ 清晰
│       ├── state.py               (50 行) ✓ AgentState TypedDict
│       └── nodes/                 — 5 个节点
│           ├── __init__.py
│           ├── intent_router.py   (167 行) ✓
│           ├── rag_node.py        (59 行) ✓ 但有 review bug
│           ├── tool_executor.py   (99 行) ✓
│           ├── response_generator.py (330 行) 🟠 逻辑重复
│           └── memory_update.py   (75 行) ✓
│
├── api/                           — FastAPI 路由
│   ├── __init__.py
│   ├── deps.py                    (75 行) ✓ 依赖注入
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── cors.py
│   └── v1/
│       ├── __init__.py
│       ├── auth.py                (146 行) ✓ 精简，不需要重构
│       ├── chat.py                (169 行) ✓
│       ├── plan.py
│       └── knowledge.py
│
├── dao/                           — 数据访问层
│   ├── __init__.py
│   ├── database.py                (38 行) ✓
│   ├── models.py                  (193 行) ✓ 9 个 ORM Model
│   └── crud/
│       ├── __init__.py
│       ├── user.py
│       ├── session.py
│       ├── knowledge.py
│       └── profile.py
│
├── memory/                        — 4 层记忆系统 + RAG
│   ├── __init__.py
│   ├── l1_session.py              (60 行) ✓ SessionManager
│   ├── l2_task.py                 (47 行) ✓ 任务状态 JSON
│   ├── l3_knowledge.py            (111 行) ✓ 知识提炼
│   ├── l4_profile.py              (70 行) ✓ 用户画像
│   ├── retrieval.py               (147 行) ✓ 记忆检索 + MemoryRetriever
│   ├── hooks.py                   (117 行) ✓ 会话生命周期 Hook
│   └── rag/                       — 混合检索管线
│       ├── __init__.py
│       ├── retriever_rag.py       (709 行) 🔴🔴 项目最大文件！
│       ├── indexer.py             — 索引管理
│       ├── bm25_retriever.py      — BM25 稀疏检索
│       ├── hybrid_fusion.py       (252 行) ✓ RRF 融合 (含自测)
│       ├── query_rewriter.py      (368 行) ✓ Query 重写 (含自测)
│       ├── score_gate.py          (303 行) ✓ 评分门控 (含自测)
│       └── pdf_parser.py          — PDF 解析
│
├── core/                          — 配置与日志
│   ├── __init__.py
│   ├── settings.py                (70 行) ⚠️ 已存在但未被集成！
│   └── logging_config.py
│
├── frontend/                      — Vue3 + TS 前端
│   ├── src/
│   │   ├── views/                 — Chat.vue, Plan.vue, Knowledge.vue, Profile.vue, Login.vue
│   │   ├── components/            — ChatBubble.vue, RAGProcessPanel.vue
│   │   ├── stores/                — chat.ts (122 行) ✓, auth.ts
│   │   ├── utils/                 — sse.ts (92 行) ✓, http.ts
│   │   ├── types/index.ts
│   │   ├── router/index.ts
│   │   └── main.ts, App.vue
│   ├── vite.config.ts
│   └── package.json
│
├── scripts/                       — 索引构建脚本 (7+ 文件)
├── storage/                       — 本地存储
│   ├── chroma_db/                 — ChromaDB 向量数据库
│   ├── bm25_index/                — BM25 稀疏索引 (3 个 JSON)
│   ├── sessions/                  — 会话日志 (JSONL)
│   ├── plans/                     — 学习计划 (JSON)
│   ├── tasks/task_state.json      — L2 任务状态
│   ├── user_profile/profile.json  — L4 用户画像
│   ├── knowledge_base/            — L3 知识沉淀
│   └── studycoach.db              — SQLite 数据库
├── tests/                         — 测试 (覆盖率 ~0%)
├── evaluation/                    — 评估脚本
├── docs/                          — 文档
│
├── server.py                      (74 行) ✓ FastAPI 入口
├── config.py                      (10 行) ⚠️ 旧配置，与 core/settings.py 冲突
├── app.py                         (291 行) ⚠️ Gradio UI (废弃)
├── main.py                        (~20 行) 旧入口
├── requirements.txt               ✓
├── Dockerfile, docker-compose.yml ✓
└── .env                           API_KEY 配置
```

---

## 3. 核心问题清单（按真实优先级排列）

### P0 — 必须优先解决

#### 3.1 🔴 `memory/rag/retriever_rag.py` — 709 行，项目最大文件

**问题：**
- `retrieve()` 和 `retrieve_with_trace()` 逻辑重复 >70%（对比第 457-525 行 vs 第 531-679 行）
- `_llm_rerank()` + `_api_rerank()` 共 130 行 Reranker 逻辑应独立
- `_PIPELINE_CONFIG` 硬编码 11 个参数，`core/settings.py` 已定义但未使用

**重构方案：**
```
memory/rag/
├── retriever_rag.py    → 精简至 ~200 行（合并 retrieve + retrieve_with_trace）
├── reranker.py         → 新建，提取 _llm_rerank + _api_rerank (~130 行)
├── (其余文件不动)
```

具体步骤：
1. 合并 `retrieve()` 和 `retrieve_with_trace()` 为：
   ```python
   def retrieve(query: str, top_k: int = 5, with_trace: bool = False) -> str | dict:
   ```
2. 提取 `_llm_rerank()` + `_api_rerank()` → `memory/rag/reranker.py`
3. 将 `_PIPELINE_CONFIG` 改为从 `get_settings()` 读取

---

#### 3.2 🔴 `agent/main_agent.py` — 614 行，双 Agent 混合

**问题：**
- `LearningAgent`（第 34-260 行）和 `LangGraphAgent`（第 266-614 行）混在同一文件
- `chat_stream_async()` 内嵌套两层闭包函数（`_graph_worker` → `_run_graph_sync`）
- `SYSTEM_PROMPT` 被两个 Agent 共用但定义在模块顶层

**重构方案：**
```
agent/
├── main_agent.py       → 仅保留 LangGraphAgent (~350 行)
├── legacy_agent.py     → 移入 LearningAgent + SYSTEM_PROMPT
```

注意：`api/v1/chat.py` 有兼容逻辑 `if hasattr(agent, 'chat_stream_async')`，移动后需确认兼容路径仍工作。

---

#### 3.3 🔴 `config.py` vs `core/settings.py` — 双配置系统冲突

**现状：**
- `config.py`（10 行）被 **全部核心模块** import：
  ```python
  from config import API_KEY, MODEL
  ```
  存在于：`main_agent.py`, `intent_router.py`, `response_generator.py`, `retriever_rag.py`, `query_rewriter.py`, `hooks.py`, `l4_profile.py`

- `core/settings.py`（70 行）已完整定义了所有配置项，但 **零使用率**

**重构方案：**
1. 在 `config.py` 中改为委托：
   ```python
   # config.py — 兼容层，逐步废弃
   from core.settings import get_settings
   _s = get_settings()
   API_KEY = _s.ZHIPU_API_KEY
   MODEL = _s.MODEL_NAME
   ```
2. 后续各模块逐步迁移为直接使用 `get_settings()`
3. `retriever_rag.py` 的 `_PIPELINE_CONFIG` 改为从 settings 读取

---

### P1 — 重要但可稳步推进

#### 3.4 🟠 全项目 `sys.path` hack（11 处）

**问题：** 几乎每个子模块都有：
```python
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
```

**存在于：** `graph.py`, `intent_router.py`, `rag_node.py`, `tool_executor.py`, `response_generator.py`, `memory_update.py`, `retriever_rag.py`, `query_rewriter.py`, `auth.py`, `chat.py`, `deps.py`

**根因：** 缺少 `pyproject.toml`，项目未注册为 Python 包。

**重构方案：**
1. 创建 `pyproject.toml`：
   ```toml
   [project]
   name = "study-agent"
   version = "2.0.0"
   requires-python = ">=3.10"

   [tool.setuptools.packages.find]
   where = ["."]
   ```
2. 执行 `pip install -e .`
3. 移除所有 `sys.path` hack

---

#### 3.5 🟠 ZhipuAI 客户端重复初始化（7 处）

**问题：** 每次 LLM 调用都 `ZhipuAI(api_key=API_KEY)` 新建实例

**存在于：**
- `intent_router.py:126`
- `response_generator.py:163` + `response_generator_stream():297`
- `retriever_rag.py:_llm_rerank():163`
- `hooks.py:37`
- `l4_profile.py:49`
- `query_rewriter.py:QueryRewriter.__init__`

**重构方案：** 创建 `core/llm_client.py`：
```python
from functools import lru_cache
from zhipuai import ZhipuAI
from core.settings import get_settings

@lru_cache
def get_llm_client() -> ZhipuAI:
    return ZhipuAI(api_key=get_settings().ZHIPU_API_KEY)
```

---

#### 3.6 🟠 `response_generator.py` — 代码重复

**问题：** `response_generator_node()`（第 70-196 行）内部有完整的消息构建逻辑，而 `build_llm_messages()`（第 203-273 行）是其提取副本。但 node 函数没有调用 `build_llm_messages()`。

**重构方案：**
```python
def response_generator_node(state: AgentState) -> AgentState:
    llm_messages, temperature = build_llm_messages(state)  # 复用！
    # ... 调用 LLM + 写回 state
```

---

#### 3.7 🟠 `agent/tools.py` — 564 行，generate_quiz 分支过长

**问题：** `generate_quiz` 分支（第 229-363 行，约 135 行）包含：
- RAG 检索 + 距离过滤
- 已出题去重 + 随机打散
- 题目文本解析（`_parse_exam_text` 内部函数）
- 来源标签构建
- 隐藏答案标记生成

**重构方案：**
```
agent/
├── tools.py            → 精简至 ~300 行（保留 schemas + 简单工具）
└── tools/
    └── quiz.py         → 提取 generate_quiz 逻辑 (~150 行)
```

---

### P2 — 功能 Bug 修复

#### 3.8 ⚠️ `rag_node.py` — review intent RAG 失效

**Bug：** `graph.py` 中 review intent 会路由到 `rag_node`，但 `rag_node` 第 23-24 行：
```python
if state.get("intent") != "study":
    return {**state, "rag_context": ""}
```
导致 **review 分支永远拿不到 RAG 上下文**。

**修复：**
```python
if state.get("intent") not in ("study", "review"):
    return {**state, "rag_context": ""}
```

---

#### 3.9 ⚠️ `database.py` create_tables 导入不完整

**Bug：** 只导入了 5/9 个 Model，虽然功能不受影响（SQLAlchemy 通过 Base.metadata 自动发现），但导入列表应完整。

**修复：**
```python
def create_tables():
    from dao.models import (User, ChatSession, ChatMessage, StudyPlan, StudyTask,
                            TaskState, UserProfile, LearningRecord, KnowledgeBase, KnowledgeDoc)
    Base.metadata.create_all(bind=engine)
```

---

### P3 — 后续改进

#### 3.10 数据持久化迁移

**现状：** `dao/models.py` 已定义了完整的 DB Model（TaskState, UserProfile 等），但 `l2_task.py` 和 `l4_profile.py` 仍在读写 JSON 文件。

| 数据 | 当前存储 | 已有 DB Model | 迁移难度 |
|------|---------|-------------|---------|
| L2 任务状态 | `storage/tasks/task_state.json` | `TaskState` | 低 |
| L4 用户画像 | `storage/user_profile/profile.json` | `UserProfile` | 低 |
| 会话历史 | `storage/sessions/*/journal.jsonl` | `ChatSession` + `ChatMessage` | 中 |
| L3 知识沉淀 | `storage/knowledge_base/*.md` | `LearningRecord` | 中 |

---

#### 3.11 测试覆盖

**现状：** 零单元测试，只有手动 API 测试脚本。

**建议测试优先级：**
1. `memory/rag/hybrid_fusion.py` — 纯函数，最容易测试
2. `memory/rag/score_gate.py` — 纯函数，已有自测代码可转为 pytest
3. `agent/tools.py` 的 `_parse_exam_text` + 标记清洗逻辑
4. `agent/graph/nodes/intent_router.py` 的 `_is_quiz_answer` + `_extract_user_choice`
5. 端到端：`api/v1/chat.py` SSE 流式测试

---

#### 3.12 根目录散落文件清理

以下文件应该移除或归档：

| 文件 | 说明 | 建议 |
|------|------|------|
| `app.py` (291 行) | 旧版 Gradio UI | 删除或移入 `_legacy/` |
| `main.py` | 旧版入口 | 删除 |
| `fix_all.py`, `fix_questions.py` | 一次性修复脚本 | 删除 |
| `show_questions.py`, `review_questions.py` | 调试脚本 | 移入 `scripts/` |
| `test_api.py`, `test_validate.py` | 散落测试 | 移入 `tests/` |
| `append_corrections.py` | 一次性脚本 | 删除 |
| `tmp_out.txt`, `1.26.0` | 临时文件 | 删除 |
| `2024_questions.txt`, `q2024.txt`, `q2025.txt` | 原始数据 | 移入 `data/` 或 `scripts/data/` |

---

## 4. 模块依赖关系（精确版）

```
[FastAPI Server]
    server.py
        ├─ api/v1/auth.py     → dao/models.py, api/deps.py
        ├─ api/v1/chat.py     → api/deps.py → agent/main_agent.py
        ├─ api/v1/plan.py
        └─ api/v1/knowledge.py

[Agent 核心]
    api/deps.py
        └─ get_agent() → LangGraphAgent.__init__()
            ├─ memory/l2_task.py         (JSON 文件读取)
            ├─ memory/l4_profile.py      (JSON 文件读取)
            ├─ memory/retrieval.py       (build_memory_context → l2 + l4 + MemoryRetriever)
            └─ agent/graph/graph.py      (get_graph, get_prep_graph)
                └─ 编译 StateGraph (5 nodes)

[对话流程 (一次请求)]
    intent_router_node     → ZhipuAI (分类)
        ↓
    rag_node               → retriever_rag.retrieve_with_trace()
        ↓                      ├─ _dual_retrieve() → ChromaDB + BM25
    tool_executor_node         ├─ rrf_fusion()
        ↓                      ├─ score_gate.check()
    response_generator_node    ├─ _fallback_with_rewrite() → query_rewriter
        ↓                      └─ _llm_rerank() / _api_rerank()
    memory_update_node     → l2_task.load_task_state() + l4_profile.load_profile()

[会话结束]
    on_session_end() → memory/hooks.py
        ├─ ZhipuAI (生成摘要)
        ├─ l2_task.update_task_state()
        ├─ l4_profile.update_profile_from_digest()
        ├─ MemoryRetriever.index_session()
        └─ l3_knowledge.maybe_extract_knowledge()  (每 5 次触发)
```

**关键依赖链（一次请求涉及的 LLM 调用）：**
1. `intent_router` — 1 次 LLM (意图分类)
2. `retriever_rag._llm_rerank()` — 1 次 LLM (Rerank)
3. `response_generator` — 1 次 LLM (生成回复)
4. （可选）`_fallback_with_rewrite()` → `query_rewriter.expand()` — 1 次 LLM

**最坏情况：一次用户消息触发 4 次 LLM 调用。**

---

## 5. 原文档错误勘误表

| 原文描述 | 实际情况 | 影响 |
|---------|---------|------|
| `api/v1/auth.py` "~300 行，JWT 实现混杂业务逻辑" | **146 行**，结构清晰，不需要重构 | 错误标记为 P1 |
| `agent/tools.py` "600+ 行" | **564 行** | 轻微高估 |
| `memory/rag/retriever_rag.py` "300+ 行" | **709 行**，项目最大文件 | 严重低估，应为 P0 |
| `memory/hooks.py` "~200 行" | **117 行** | 高估，不需要重构 |
| `memory/l3_knowledge.py` "150+" | **111 行** | 高估 |
| "chat_stream_async 超 430 行" | **~183 行** (第 348-531 行) | 夸大 |
| "各节点动态添加 key" | `state.py` 已完整定义所有字段 | 错误，AgentState 定义完整 |
| "缺少 config/ 目录" | `core/settings.py` 已存在（但未集成） | 方向错误，应集成而非新建 |
| "RAG Query 重写额外开销每次 3x" | 仅在门控未通过时才触发二次检索 | 误解逻辑 |
| 建议 "auth.py 抽取到 core/security.py" | auth.py 仅 146 行，已很精简 | 不必要的拆分 |

---

## 6. 执行计划（修订版，4 周）

### Week 1: 基础设施修复 ⚡
- [ ] 创建 `pyproject.toml`，移除全部 `sys.path` hack (11 处)
- [ ] 统一配置：`config.py` 委托到 `core/settings.py`
- [ ] 创建 `core/llm_client.py`，ZhipuAI 单例
- [ ] 修复 `rag_node.py` review intent bug
- [ ] 修复 `database.py` create_tables 导入
- [ ] 清理根目录散落文件

### Week 2: 最大文件拆分 🔧
- [ ] `retriever_rag.py` 709→~350 行：合并 retrieve + 提取 reranker.py
- [ ] `main_agent.py` 614→~350 行：LearningAgent → legacy_agent.py
- [ ] `response_generator.py`：去除 build_llm_messages 重复

### Week 3: 工具重构 + 测试 🧪
- [ ] `tools.py` 564→~300 行：提取 generate_quiz → tools/quiz.py
- [ ] 为 hybrid_fusion、score_gate 编写 pytest 单元测试
- [ ] 为 intent_router 的快速路径编写测试
- [ ] 为 markers/标记清洗逻辑编写测试

### Week 4: 数据迁移 + 收尾 📦
- [ ] l2_task.py → 读写 DB (TaskState model)
- [ ] l4_profile.py → 读写 DB (UserProfile model)
- [ ] 端到端 API 测试 (chat/stream endpoint)
- [ ] 更新 README.md 和 docs/architecture.md

---

## 7. 不建议做的事（避免过度工程化）

| 原文建议 | 为什么不做 |
|---------|----------|
| 建立 `agent/markers/` 目录 (3 个文件) | 标记清洗只有 ~20 行正则，一个 `markers.py` 文件足矣 |
| 建立 `agent/services/` 层 | Agent 本身就是编排层，再加一层 service 只会增加调用链 |
| 建立 `core/config/` 多文件结构 | `core/settings.py` 已存在且支持嵌套 model，无需拆文件 |
| `ToolBase` 抽象类 + Factory 模式 | 只有 7 个工具，字典映射 + 独立函数就够了 |
| 迁移 ChromaDB → Pinecone/Weaviate | 开发阶段无扩展需求，ChromaDB 本地够用 |
| 独立的 `async_orchestrator.py` | `chat_stream_async` 的逻辑是连贯流程，拆文件反而增加跳转 |
| 建立 `interfaces/` 或 `schemas/` 目录 | `agent/graph/state.py` 已是完整的 TypedDict 定义 |

---

## 8. 风险点提醒

1. **`LearningAgent` 不能直接删除** — `api/v1/chat.py` 有 `hasattr(agent, 'chat_stream_async')` 兼容判断，说明可能有非 LangGraph 的使用场景
2. **`_PIPELINE_CONFIG` 迁移到 settings 后** — 需确保 `retriever_rag.py` 中的默认值与 `core/settings.py` 一致
3. **`pyproject.toml` 添加后** — 需确保 Docker 构建流程更新（Dockerfile 中 `pip install -e .`）
4. **数据迁移** — JSON → DB 需要编写迁移脚本，不能直接删除 JSON 文件
