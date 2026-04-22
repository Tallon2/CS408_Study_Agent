# 408 考研学习助手 — 重构 Architecture Design 文档

> **版本**：1.0.0  
> **日期**：2026-04-21  
> **状态**：设计稿（待评审）  
> **适用范围**：`E:\DEMO` 仓库全量重构

---

## 目录

1. [概述](#1-概述)
2. [设计原则](#2-设计原则)
3. [当前问题诊断](#3-当前问题诊断)
4. [目标架构图](#4-目标架构图)
5. [目标目录结构](#5-目标目录结构)
6. [模块边界定义](#6-模块边界定义)
7. [接口契约](#7-接口契约)
8. [分阶段重构计划](#8-分阶段重构计划)
9. [测试策略](#9-测试策略)
10. [风险与回滚](#10-风险与回滚)

---

## 1. 概述

### 1.1 项目背景

本项目是一个面向 **408 计算机考研**（数据结构、操作系统、计算机网络、计算机组成原理）的 AI 学习教练系统。系统基于 LangGraph 状态图进行 Agent 编排，集成混合 RAG 检索管线与 L1-L4 四层记忆架构，支持个性化、有记忆、有依据的学习辅导体验。

**技术栈总览：**

| 层次 | 技术 |
|------|------|
| 前端 | Vue3 + TypeScript + Pinia + Vite |
| API 层 | FastAPI + Uvicorn + JWT + SQLAlchemy |
| Agent 编排 | LangGraph (StateGraph) |
| LLM | ZhipuAI GLM-4-Flash + embedding-3 |
| 向量存储 | ChromaDB（持久化模式） |
| 稀疏检索 | BM25Okapi + jieba 分词 |
| 关系数据库 | SQLite（ORM via SQLAlchemy） |
| 缓存 | Redis 7 |
| 容器化 | Docker Compose |

### 1.2 重构动机

当前仓库**能够运行**，但存在以下结构性技术债，导致演进成本持续升高：

| 问题类别 | 具体表现 | 影响 |
|---------|---------|------|
| 超大文件 | `retriever_rag.py` 709 行、`main_agent.py` 614 行、`tools.py` 564 行 | 阅读/维护/测试困难 |
| 双配置系统 | `config.py`（10 行）与 `core/settings.py`（70 行）并存冲突 | 新配置项无处安放 |
| 路径 hack | 11 处 `sys.path.insert` 补丁 | 测试/部署行为不一致 |
| LLM 重复实例化 | 7 处 `ZhipuAI(api_key=...)` 散落各模块 | 无法统一超时/重试/切换策略 |
| 逻辑重复 | `retrieve()` 与 `retrieve_with_trace()` 代码重复 >70% | 改 bug 必须改两处 |
| 状态存储分裂 | L2/L4 仍用 JSON 文件，但 ORM Model 已定义 | 无法多用户并发、无法统计 |
| 功能 Bug | `rag_node.py` review intent 无法获取 RAG 上下文 | review 功能降级 |
| 零测试覆盖 | 无单元测试，仅有手动 API 脚本 | 重构无安全网 |

### 1.3 重构目标

1. **建立稳定模块边界**：每个模块职责单一，边界清晰，改动不会牵连全局
2. **统一技术基础设施**：配置、LLM 客户端、日志、存储均有唯一入口
3. **提升可测试性**：核心逻辑可脱离网络/数据库独立单测
4. **保持主链路不回退**：所有重构在功能等价的前提下进行
5. **为长期演进预留扩展点**：新增 intent、新增工具、切换 LLM Provider 代价最小化

---

## 2. 设计原则

### 2.1 核心原则总览

| 原则 | 说明 | 典型约束示例 |
|------|------|------------|
| **高内聚低耦合** | 每个模块只做一件事，模块间通过明确接口通信 | `retriever_rag.py` 不得直接操作 DB |
| **单一真实来源** | 配置/状态/数据各有唯一权威来源 | 配置只从 `core/settings.py` 读取 |
| **依赖倒置** | 业务逻辑依赖抽象接口，不依赖具体实现 | Agent 节点通过 `get_llm_client()` 获取 LLM |
| **显式优于隐式** | 依赖关系和副作用显式传入，不依赖全局状态 | 函数参数传入 settings，不在函数内直接调用 |
| **可测试性优先** | 核心业务逻辑必须可脱离 I/O 独立测试 | 纯函数不得依赖 `ZhipuAI` 实例 |
| **防腐层原则** | 对外部 API/库的调用集中在适配层 | ZhipuAI SDK 调用只在 `core/llm_client.py` 内 |
| **渐进式演进** | 重构分阶段进行，每阶段有独立验收标准 | 不能一次性删除所有 `sys.path` hack |
| **不过度工程化** | 拒绝为了"架构漂亮"引入不必要的抽象层 | 7 个工具不需要 `ToolBase` 抽象类 |

### 2.2 模块设计的三条硬性规则

**规则 1：禁止跨层调用**

```
前端 → API层 → Agent编排层 → [RAG层 | 记忆层] → 数据层
```

- API 层不得直接操作 ChromaDB 或 BM25 索引
- Agent 节点不得直接读写 SQLite 文件（必须通过 DAO 层）
- RAG 层不得知道 `AgentState` 的存在

**规则 2：对外接口一旦稳定，不得随意变更**

以下接口在重构期间保持签名不变：
- `LangGraphAgent.chat(message, session_id, user_id) -> str`
- `LangGraphAgent.chat_stream_async(message, ...) -> AsyncGenerator`
- `/api/v1/chat/stream` SSE 事件格式（`start` / `token` / `rag_*` / `done`）
- `AgentState` TypedDict 关键字段结构

**规则 3：新增配置只在 `core/settings.py` 定义**

任何新配置项必须：
1. 在 `core/settings.py` 的 `Settings` 类中定义（带类型注解和默认值）
2. 通过 `get_settings()` 访问
3. 禁止在业务模块中硬编码配置值

### 2.3 扩展性约定

| 扩展场景 | 预留方式 |
|---------|---------|
| 新增意图（如 `debug`） | 在 `graph.py` 的 `route_by_intent()` 加条件分支 + 新增对应节点 |
| 新增检索工具 | 在 `agent/tools/` 新增独立文件，注册到 `TOOL_REGISTRY` |
| 切换 LLM Provider | 修改 `core/llm_client.py`，其他模块无需改动 |
| 新增 Reranker 策略 | 在 `memory/rag/reranker.py` 新增降级链节点 |
| 替换向量数据库 | 修改 `memory/rag/retriever_rag.py` 的 `_vector_retrieve()` 方法 |

---

## 3. 当前问题诊断

### 3.1 问题全景地图

```
E:\DEMO/
│
├── [P0-BUG]  agent/graph/nodes/rag_node.py
│             └── review intent 永远拿不到 RAG 上下文（第 23-24 行 intent != "study" 判断错误）
│
├── [P0-配置] config.py (10行) ←── 被 7+ 模块 import
│             core/settings.py (70行) ←── 零使用率，已完整定义所有配置项
│             └── 双配置系统冲突，新配置无处安放
│
├── [P0-重复] memory/rag/retriever_rag.py (709行)
│             ├── retrieve() L457-525
│             └── retrieve_with_trace() L531-679
│                 └── 代码重复 >70%，修改 bug 必须同步两处
│
├── [P1-大文件] agent/main_agent.py (614行)
│              ├── LearningAgent (L34-260)  ← legacy，应隔离
│              └── LangGraphAgent (L266-614) ← 主用，但承载太多职责
│
├── [P1-大文件] agent/tools.py (564行)
│              └── generate_quiz 分支 L229-363 (~135行)，含 RAG + 解析 + 去重 + 格式化
│
├── [P1-散落] 7 处 ZhipuAI(api_key=API_KEY) 重复初始化
│             └── intent_router.py, response_generator.py(×2), retriever_rag.py,
│                 hooks.py, l4_profile.py, query_rewriter.py
│
├── [P1-包化] 11 处 sys.path.insert hack
│             └── 每个子模块文件顶部手动注入根路径
│
├── [P2-存储] memory/l2_task.py → storage/tasks/task_state.json
│             memory/l4_profile.py → storage/user_profile/profile.json
│             └── ORM Model (TaskState, UserProfile) 已定义但未使用
│
├── [P2-重复] agent/graph/nodes/response_generator.py
│             ├── response_generator_node() L70-196 ← 完整消息构建逻辑
│             └── build_llm_messages() L203-273    ← 前者提取副本，但未被调用
│
├── [P3-清理] 根目录散落文件
│             ├── app.py (291行 Gradio 旧UI)、main.py (旧入口)
│             ├── fix_all.py、fix_questions.py、append_corrections.py (一次性脚本)
│             └── test_api.py、test_validate.py (散落测试)
│
└── [P3-测试] tests/ 目录测试覆盖率 ~0%
              └── 仅有手动 API 测试脚本，无 pytest 单元测试
```

### 3.2 优先级矩阵

| 优先级 | 问题 | 风险 | 收益 | 操作难度 |
|-------|------|------|------|---------|
| **P0** | rag_node review bug | 低 | 高（修复线上功能） | 1行修改 |
| **P0** | 双配置系统统一 | 低 | 高（消除歧义） | 兼容层委托 |
| **P0** | retriever_rag.py 逻辑去重 | 中 | 高（减少维护成本） | 重构内部实现 |
| **P1** | ZhipuAI 单例化 | 低 | 高（统一切换入口） | 新建文件 |
| **P1** | main_agent.py 拆分 | 中 | 中（职责清晰） | 物理隔离 |
| **P1** | tools.py generate_quiz 提取 | 低 | 中（降低复杂度） | 提取到子目录 |
| **P2** | sys.path hack 移除 | 中 | 中（标准化部署） | 分阶段包化 |
| **P2** | L2/L4 迁移到 DB | 高（需迁移脚本） | 高（并发/统计能力） | 双写过渡 |
| **P3** | 测试覆盖 | 低 | 极高（安全网） | 从纯函数开始 |
| **P3** | 根目录清理 | 低 | 低（整洁） | 最后阶段 |

---

## 4. 目标架构图

### 4.1 整体分层架构

```
╔══════════════════════════════════════════════════════════════════════╗
║                       前端层 (Vue3 + TS)                            ║
║  Chat.vue / Plan.vue / Login.vue / Profile.vue                      ║
║  Pinia Store: auth.ts / chat.ts                                     ║
║  utils/sse.ts (SSE 流式接收)   utils/http.ts (axios)               ║
║  components: ChatBubble.vue / RAGProcessPanel.vue                   ║
╚═══════════════════════════════╤══════════════════════════════════════╝
                                │ HTTP / SSE
                                ▼
╔══════════════════════════════════════════════════════════════════════╗
║                        API 层 (FastAPI)                             ║
║  server.py (入口)    middleware: CORS / JWT                         ║
║  /api/v1/auth  ──►  dao/crud/user.py                                ║
║  /api/v1/chat  ──►  api/deps.py → get_agent()                      ║
║  /api/v1/plan  ──►  dao/crud/session.py                             ║
║  /api/v1/knowledge ─► dao/crud/knowledge.py                         ║
╚═══════════════════════════════╤══════════════════════════════════════╝
                                │
                                ▼
╔══════════════════════════════════════════════════════════════════════╗
║                 Agent 编排层 (LangGraph StateGraph)                 ║
║                                                                      ║
║   agent/main_agent.py  ←────── 对外统一入口                         ║
║   agent/legacy_agent.py ←───── 历史实现隔离区                       ║
║   agent/runtime.py ←────────── 会话态/内存快照管理                  ║
║                                                                      ║
║   agent/graph/state.py  ←───── AgentState TypedDict                 ║
║   agent/graph/graph.py  ←───── build_graph()                        ║
║                                                                      ║
║   START → [intent_router]                                           ║
║               │ study   ──► [rag_node] ──► [tool_executor] ──►┐     ║
║               │ review  ──► [rag_node] ────────────────────►  │     ║
║               │ plan    ──────────────► [tool_executor] ────►  │     ║
║               │ unknown ───────────────────────────────────►  │     ║
║                                                                │     ║
║               [response_generator] ◄────────────────────────┘      ║
║                       │                                             ║
║               [memory_update] → END                                 ║
║                                                                      ║
║   agent/tools/                                                      ║
║     tools.py (路由 + 简单工具)   tools/quiz.py (出题逻辑)           ║
╚══════════════╤═══════════════════════╤══════════════════════════════╝
               │                       │
               ▼                       ▼
╔═════════════════════╗    ╔═══════════════════════════════════════════╗
║   RAG 检索层        ║    ║          记忆层 (L1-L4)                   ║
║   memory/rag/       ║    ║  L1 l1_session.py → journal.jsonl        ║
║                     ║    ║  L2 l2_task.py    → TaskState (DB)       ║
║ retriever_rag.py    ║    ║  L3 l3_knowledge.py→ patterns/pitfalls   ║
║  ├─ _run_pipeline() ║    ║  L4 l4_profile.py → UserProfile (DB)     ║
║  └─ retrieve()      ║    ║                                           ║
║     retrieve_with_  ║    ║  retrieval.py ← build_memory_context()   ║
║       trace()       ║    ║  hooks.py     ← on_session_stop()        ║
║                     ║    ╚═══════════════════════════════════════════╝
║ reranker.py         ║
║  ├─ llm_rerank()    ║
║  └─ api_rerank()    ║    ╔═══════════════════════════════════════════╗
║                     ║    ║         基础设施层 (core/)                ║
║ query_rewriter.py   ║    ║  settings.py    ← 唯一配置来源            ║
║ bm25_retriever.py   ║    ║  llm_client.py  ← ZhipuAI 单例入口        ║
║ hybrid_fusion.py    ║    ║  logging_config.py ← 日志配置             ║
║ score_gate.py       ║    ╚═══════════════════════════════════════════╝
╚═════════════════════╝
               │                       │
               ▼                       ▼
╔══════════════════════════════════════════════════════════════════════╗
║                         数据层                                      ║
║  dao/database.py  dao/models.py  dao/crud/                          ║
║  SQLite: studycoach.db (用户/会话/计划/知识/画像/任务状态)            ║
║  ChromaDB: storage/chroma_db/ (textbooks/exam_questions/key_points) ║
║  BM25 JSON: storage/bm25_index/ (jieba分词后语料)                   ║
║  File: storage/sessions/ (L1 journal.jsonl)                         ║
║         storage/knowledge_base/ (L3 patterns/pitfalls)              ║
╚══════════════════════════════════════════════════════════════════════╝
```

### 4.2 一次对话请求数据流

```
用户消息
   │
   ▼
POST /api/v1/chat/stream
   │
   ├─ JWT 验证 (middleware/auth.py)
   ├─ get_agent() (api/deps.py)
   │
   ▼
LangGraphAgent.chat_stream_async()
   │
   ├─① 构建 AgentState (runtime.py)
   │    └─ build_memory_context() ← L2 TaskState + L4 UserProfile
   │
   ├─② LangGraph 图执行
   │    │
   │    ├─ intent_router_node
   │    │    └─ LLM 调用 #1：意图分类 → study/plan/review/unknown
   │    │
   │    ├─ rag_node (study 或 review 分支)
   │    │    └─ retrieve_with_trace(query)
   │    │         ├─ _dual_retrieve()  → ChromaDB + BM25
   │    │         ├─ rrf_fusion()      → RRF 算法融合
   │    │         ├─ score_gate()      → 评分门控过滤
   │    │         ├─ [fallback]        → query_rewriter + 二次检索
   │    │         ├─ reranker()        → LLM/API 精排（LLM 调用 #2，可选）
   │    │         └─ formatter()       → 格式化为 context string
   │    │
   │    ├─ tool_executor_node (study/plan 分支)
   │    │    └─ 执行工具（如 generate_quiz）
   │    │         └─ tools/quiz.py
   │    │
   │    ├─ response_generator_node
   │    │    └─ build_llm_messages()   → 拼接系统提示 + 记忆 + RAG
   │    │    └─ LLM 调用 #3：生成最终回复（流式）
   │    │         └─ SSE 推送 token 事件
   │    │
   │    └─ memory_update_node
   │         ├─ L2 TaskState 更新
   │         └─ L4 UserProfile 快照同步
   │
   └─③ on_session_stop() (hooks.py)
        ├─ LLM 调用 #4：生成会话摘要（异步，不阻塞响应）
        ├─ L2/L4 持久化到 DB
        ├─ MemoryRetriever.index_session()
        └─ [可选] l3_knowledge.maybe_extract_knowledge() (每5次)
```

### 4.3 模块依赖关系（目标态）

```
┌────────────────────────────────────────────────────┐
│ core/ (最底层，被所有层使用，自身不依赖任何业务模块) │
│  settings.py  llm_client.py  logging_config.py      │
└─────────────────────┬──────────────────────────────┘
                      │ 被依赖
         ┌────────────┼────────────┐
         ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   dao/       │ │  memory/rag/ │ │  memory/     │
│  database.py │ │ retriever_   │ │  l1/l2/l3/l4 │
│  models.py   │ │  rag.py      │ │  retrieval.py│
│  crud/       │ │ reranker.py  │ │  hooks.py    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        │ 被依赖
                        ▼
               ┌──────────────────┐
               │  agent/          │
               │  graph/nodes/    │
               │  tools/          │
               │  main_agent.py   │
               └────────┬─────────┘
                        │ 被依赖
                        ▼
               ┌──────────────────┐
               │  api/            │
               │  server.py       │
               └──────────────────┘
```

---

## 5. 目标目录结构

重构完成后的目标目录树（`~` 标注为新增，`→` 标注为迁移/重命名，其余为现有保留）：

```
E:\DEMO/
│
├── pyproject.toml                  ~ 新增：包描述，使项目可安装 (pip install -e .)
├── server.py                         FastAPI 主入口（保留）
├── config.py                         兼容层委托→ core/settings.py（逐步废弃）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env
│
├── core/                             基础设施层（统一入口）
│   ├── __init__.py
│   ├── settings.py                   唯一配置来源（Pydantic Settings，已存在）
│   ├── llm_client.py               ~ 新增：ZhipuAI 单例工厂
│   └── logging_config.py             日志配置（已存在）
│
├── api/                              API 路由层（基本保留）
│   ├── __init__.py
│   ├── deps.py                       依赖注入（保留）
│   ├── middleware/
│   │   ├── auth.py
│   │   └── cors.py
│   └── v1/
│       ├── auth.py
│       ├── chat.py
│       ├── plan.py
│       └── knowledge.py
│
├── agent/                            Agent 编排层（重构重点）
│   ├── __init__.py
│   ├── main_agent.py                 精简：仅保留 LangGraphAgent (~350 行)
│   ├── legacy_agent.py             ~ 新增：LearningAgent 隔离区（从 main_agent.py 迁移）
│   ├── runtime.py                  ~ 新增：会话态 + 内存快照管理（从 main_agent.py 提取）
│   ├── lc_tools.py                   LangChain Tools 封装（保留）
│   │
│   ├── tools/                      ~ 新增目录（从 tools.py 提取）
│   │   ├── __init__.py
│   │   ├── registry.py             ~ 工具注册表 TOOL_REGISTRY
│   │   └── quiz.py                 ~ generate_quiz 逻辑（从 tools.py L229-363 提取）
│   ├── tools.py                      精简：路由分发 + 简单工具 (~250 行)
│   │
│   └── graph/
│       ├── __init__.py
│       ├── state.py                  AgentState TypedDict（保留）
│       ├── graph.py                  build_graph()（保留）
│       └── nodes/
│           ├── __init__.py
│           ├── intent_router.py      修复：使用 get_llm_client()
│           ├── rag_node.py           修复：review intent bug
│           ├── tool_executor.py      保留
│           ├── response_generator.py 修复：复用 build_llm_messages()
│           └── memory_update.py      保留
│
├── memory/                           记忆层（局部重构）
│   ├── __init__.py
│   ├── l1_session.py                 会话日志（保留）
│   ├── l2_task.py                    迁移：JSON → TaskState DB
│   ├── l3_knowledge.py               知识沉淀（保留）
│   ├── l4_profile.py                 迁移：JSON → UserProfile DB
│   ├── retrieval.py                  记忆检索（保留）
│   ├── hooks.py                      生命周期钩子（修复：使用 get_llm_client()）
│   │
│   └── rag/                          RAG 检索管线（重构重点）
│       ├── __init__.py
│       ├── retriever_rag.py          重构：~350 行，公开 retrieve() + retrieve_with_trace()
│       │                             内部：统一 _run_pipeline() → RetrievalResult
│       ├── reranker.py             ~ 新增：提取 _llm_rerank() + _api_rerank() (~130 行)
│       ├── query_rewriter.py         保留（修复：使用 get_llm_client()）
│       ├── bm25_retriever.py         保留
│       ├── hybrid_fusion.py          保留（纯函数，高可测性）
│       ├── score_gate.py             保留（纯函数，高可测性）
│       ├── indexer.py                保留
│       └── pdf_parser.py             保留
│
├── dao/                              数据访问层（补全）
│   ├── __init__.py
│   ├── database.py                   修复：create_tables() 完整导入
│   ├── models.py                     ORM 模型（保留，TaskState/UserProfile 已定义）
│   └── crud/
│       ├── __init__.py
│       ├── user.py
│       ├── session.py
│       ├── knowledge.py
│       ├── profile.py                修复：迁移为 DB 主读写路径
│       └── task_state.py           ~ 新增：TaskState CRUD 操作
│
├── tests/                            测试（补充）
│   ├── __init__.py
│   ├── conftest.py                 ~ 新增：pytest fixtures
│   ├── unit/
│   │   ├── test_hybrid_fusion.py   ~ 纯函数单元测试
│   │   ├── test_score_gate.py      ~ 纯函数单元测试
│   │   ├── test_intent_router.py   ~ 意图路由规则测试
│   │   └── test_quiz_tools.py      ~ 出题工具测试
│   ├── integration/
│   │   ├── test_rag_pipeline.py    ~ RAG 管线集成测试
│   │   └── test_agent_graph.py     ~ Agent Graph 集成测试
│   └── e2e/
│       └── test_chat_stream.py     ~ SSE 流式端到端测试
│
├── scripts/                          运维脚本（保留，清理后整洁）
│   ├── build_bm25_index.py
│   ├── index_textbooks.py
│   ├── index_exam_questions.py
│   ├── index_key_points.py
│   ├── migrate_json_to_db.py       ~ 新增：L2/L4 数据迁移脚本
│   └── test_rag.py
│
├── evaluation/                       评估体系（保留）
│   ├── eval_retrieval.py
│   ├── test_cases.json
│   └── eval_report.md
│
├── frontend/                         前端（不参与后端重构）
│   └── ...
│
├── storage/                          运行时数据（目录结构保留）
│   ├── chroma_db/
│   ├── bm25_index/
│   ├── sessions/
│   ├── tasks/                        迁移后降级为备份（保留向后兼容读取）
│   ├── user_profile/                 迁移后降级为备份（保留向后兼容读取）
│   ├── knowledge_base/
│   ├── plans/
│   ├── vector_db/
│   └── studycoach.db
│
├── docs/                             文档
│   ├── architecture.md
│   ├── refactoring_design.md       ← 本文档
│   └── ...
│
└── _legacy/                        ~ 新增：归档区（不参与主运行链）
    ├── app.py                        旧 Gradio UI
    ├── main.py                       旧 CLI 入口
    └── ...
```

---

## 6. 模块边界定义

### 6.1 `core/` — 基础设施层

**职责边界：** 提供全局基础设施（配置、LLM 客户端、日志），不包含任何业务逻辑。

**对外接口：**
- `get_settings() -> Settings` — 全局配置单例
- `get_llm_client() -> ZhipuAI` — LLM 客户端单例
- `setup_logging()` — 初始化日志系统

**依赖关系：**
- 不依赖项目内任何其他模块
- 依赖：`pydantic-settings`、`zhipuai`、`logging`

**禁止事项：**
- ❌ 不得包含 Agent、RAG、记忆等业务逻辑
- ❌ 不得直接操作 `storage/` 目录下的任何文件
- ❌ 不得在 `settings.py` 以外定义配置项

---

### 6.2 `dao/` — 数据访问层

**职责边界：** 所有数据库读写操作的唯一入口，封装 SQLAlchemy ORM 操作。

**对外接口（代表性）：**
- `crud/user.py` — `get_user_by_username()`, `create_user()`
- `crud/session.py` — `create_session()`, `get_session_messages()`
- `crud/profile.py` — `get_user_profile()`, `upsert_user_profile()`
- `crud/task_state.py` — `get_task_state()`, `update_task_state()`

**依赖关系：**
- 依赖：`core/settings.py`（数据库 URL）、`sqlalchemy`
- 不依赖：`agent/`、`memory/`、`api/`

**禁止事项：**
- ❌ 不得包含业务逻辑（如意图路由、RAG 管线）
- ❌ 不得直接读写 `storage/` 下的 JSON 文件（这属于记忆层的职责边界内，迁移后同样不应在 dao 层做文件 I/O）
- ❌ 不得知道 `AgentState` 的存在

---

### 6.3 `memory/rag/` — RAG 检索层

**职责边界：** 混合检索管线的完整实现，从查询输入到排序后检索结果输出。

**子模块职责：**

| 子模块 | 职责 | 类型 |
|-------|------|------|
| `retriever_rag.py` | 管线编排入口，协调各子组件 | 编排器 |
| `reranker.py` | LLM/API 精排，三级降级链 | 适配器 |
| `query_rewriter.py` | Query 扩展/分解/HyDE 三策略 | 工具 |
| `bm25_retriever.py` | BM25 稀疏检索 | 检索器 |
| `hybrid_fusion.py` | RRF 融合算法（纯函数） | 算法 |
| `score_gate.py` | 评分门控过滤（纯函数） | 算法 |
| `indexer.py` | 三级分块 + ChromaDB 入库 | 索引器 |

**对外接口：**
- `retrieve(query: str, top_k: int) -> str` — 返回格式化的检索上下文字符串
- `retrieve_with_trace(query: str, top_k: int) -> dict` — 同上，附带完整过程追踪信息

**依赖关系：**
- 依赖：`core/settings.py`、`core/llm_client.py`、`chromadb`、`rank_bm25`
- 不依赖：`agent/`、`api/`、`dao/`

**禁止事项：**
- ❌ 不得知道 `AgentState` 的存在
- ❌ 不得直接操作 `storage/sessions/`（这是 L1 记忆层职责）
- ❌ `retriever_rag.py` 不得超过 400 行（超出部分应提取到子模块）
- ❌ 不得在 `retriever_rag.py` 中硬编码任何 pipeline 参数（必须从 settings 读取）

---

### 6.4 `memory/` — 记忆层（非 RAG 部分）

**职责边界：** 管理系统的四层记忆（L1-L4），提供跨会话的状态持久化和上下文构建。

**子模块职责：**

| 子模块 | 层级 | 职责 | 存储（目标态） |
|-------|------|------|-------------|
| `l1_session.py` | L1 | 会话事件日志，append-only | `storage/sessions/*/journal.jsonl` |
| `l2_task.py` | L2 | 任务进度与薄弱点跟踪 | `dao/crud/task_state.py` → SQLite |
| `l3_knowledge.py` | L3 | LLM 提炼知识模式与踩坑 | `storage/knowledge_base/` |
| `l4_profile.py` | L4 | 用户知识图谱与学习偏好 | `dao/crud/profile.py` → SQLite |
| `retrieval.py` | 横切 | `build_memory_context()`，注入会话前记忆 | — |
| `hooks.py` | 横切 | 会话生命周期钩子 `on_session_stop()` | — |

**对外接口：**
- `build_memory_context(user_id, session_id) -> str` — 构建注入 Agent 的记忆上下文
- `on_session_stop(session_id, messages) -> None` — 会话结束处理（异步）

**依赖关系：**
- 依赖：`core/llm_client.py`、`dao/crud/`（迁移后）
- 不依赖：`agent/graph/state.py`、`api/`

**禁止事项：**
- ❌ 迁移完成后，L2/L4 不得再以 JSON 文件为主存储
- ❌ `hooks.py` 不得直接调用 `ZhipuAI(api_key=...)` 初始化（必须通过 `get_llm_client()`）
- ❌ 不得知道 `AgentState` 中具体字段的业务语义

---

### 6.5 `agent/` — Agent 编排层

**职责边界：** 基于 LangGraph 的意图路由与多步编排，是系统对话处理的核心控制流。

**子模块职责：**

| 子模块 | 职责 |
|-------|------|
| `main_agent.py` | 对外统一入口，暴露 `chat()` / `chat_stream_async()` |
| `legacy_agent.py` | 历史 `LearningAgent` 隔离区（只读，不再修改） |
| `runtime.py` | 会话状态构建、内存快照 I/O、消息历史管理 |
| `graph/state.py` | `AgentState` TypedDict 定义（单一来源） |
| `graph/graph.py` | `build_graph()` 状态图构建与路由逻辑 |
| `graph/nodes/` | 各图节点（意图路由/RAG/工具/响应/记忆更新） |
| `tools.py` | 工具函数路由分发入口 + 简单工具实现 |
| `tools/quiz.py` | `generate_quiz()` 完整实现 |

**对外接口（对 `api/` 层）：**
- `LangGraphAgent.chat(message, session_id, user_id) -> str`
- `LangGraphAgent.chat_stream(message, ...) -> Generator[str, None, None]`
- `LangGraphAgent.chat_stream_async(message, ...) -> AsyncGenerator[str, None]`
- `LangGraphAgent.on_session_end(session_id) -> None`

**依赖关系：**
- 依赖：`core/`、`memory/`（`build_memory_context`、`on_session_stop`）、`memory/rag/`
- 不依赖：`api/`、`dao/`（通过 `memory/` 间接访问数据）

**禁止事项：**
- ❌ 图节点不得直接调用 `ZhipuAI(api_key=...)` 初始化
- ❌ `main_agent.py` 不得直接操作文件系统或数据库
- ❌ 不得在 `tools.py` 中混合业务逻辑超过 100 行的子功能（提取到 `tools/` 子目录）
- ❌ `legacy_agent.py` 只读归档，不得在其中新增业务逻辑

---

### 6.6 `api/` — API 层

**职责边界：** HTTP 请求接收、认证校验、参数序列化/反序列化、Agent 调用代理、SSE 推流。

**依赖关系：**
- 依赖：`agent/main_agent.py`（通过 `deps.py` 的依赖注入）、`dao/crud/`
- 不依赖：`memory/rag/`、`memory/l1-l4`

**禁止事项：**
- ❌ 不得在路由函数中包含 RAG 逻辑或记忆更新逻辑
- ❌ 不得直接实例化 `LangGraphAgent`（必须通过 `api/deps.py` 的 `get_agent()` 依赖注入）
- ❌ 不得绕过 `api/middleware/auth.py` 进行无鉴权操作

---

## 7. 接口契约

### 7.1 `core/llm_client.py` — LLM 客户端单例

```python
# core/llm_client.py
from functools import lru_cache
from zhipuai import ZhipuAI
from core.settings import get_settings


@lru_cache(maxsize=1)
def get_llm_client() -> ZhipuAI:
    """
    返回全局唯一的 ZhipuAI 客户端实例。
    
    使用方式（替换所有 ZhipuAI(api_key=...) 散落调用）：
        from core.llm_client import get_llm_client
        client = get_llm_client()
        resp = client.chat.completions.create(...)
    
    注意：lru_cache 保证进程内单例，测试时可通过 get_llm_client.cache_clear() 重置。
    """
    settings = get_settings()
    return ZhipuAI(api_key=settings.ZHIPU_API_KEY)
```

---

### 7.2 `memory/rag/retriever_rag.py` — RAG 检索入口

```python
# memory/rag/retriever_rag.py（重构后目标接口）
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalResult:
    """RAG 管线的内部统一结果对象。"""
    context: str                          # 格式化的上下文文本（供 LLM 使用）
    sources: list[dict[str, Any]]         # 原始文档来源列表
    scores: list[float]                   # 每个文档的最终得分
    trace: dict[str, Any] = field(default_factory=dict)  # 过程追踪信息（仅 with_trace 时填充）
    rewrite_queries: list[str] = field(default_factory=list)  # 重写后的查询列表


def retrieve(
    query: str,
    top_k: int = 5,
    subject: str | None = None,
) -> str:
    """
    标准检索接口，返回格式化的上下文字符串。
    
    Args:
        query: 用户查询
        top_k: 最终返回文档数量
        subject: 可选的学科限定（"数据结构"/"操作系统"/"计算机网络"/"组成原理"）
    
    Returns:
        格式化的检索上下文字符串，供 response_generator 直接拼入 prompt
    
    Raises:
        RetrievalError: 当所有检索策略均失败时抛出
    """
    result = _run_pipeline(query, top_k=top_k, subject=subject, include_trace=False)
    return result.context


def retrieve_with_trace(
    query: str,
    top_k: int = 5,
    subject: str | None = None,
) -> dict[str, Any]:
    """
    带过程追踪的检索接口，返回包含完整管线追踪信息的字典。
    
    Returns:
        {
            "context": str,         # 格式化上下文
            "sources": list[dict],  # 文档来源
            "trace": {
                "vector_results": [...],
                "bm25_results": [...],
                "rrf_scores": [...],
                "gate_mode": str,
                "rerank_method": str,
                "rewrite_queries": [...],
                "fallback_triggered": bool,
            }
        }
    """
    result = _run_pipeline(query, top_k=top_k, subject=subject, include_trace=True)
    return {
        "context": result.context,
        "sources": result.sources,
        "trace": result.trace,
    }


def _run_pipeline(
    query: str,
    top_k: int,
    subject: str | None,
    include_trace: bool,
) -> RetrievalResult:
    """
    RAG 管线核心实现（内部方法，retrieve/retrieve_with_trace 共用）。
    
    流程：
    1. _dual_retrieve(query) → vector + bm25 原始结果
    2. rrf_fusion(vector, bm25) → 融合排序列表
    3. score_gate.check(fused) → 过滤低质量结果
    4. [可选] _fallback_with_rewrite(query) → 门控未通过时二次检索
    5. reranker.rerank(candidates, query) → 精排（降级链）
    6. _format_context(top_k_docs) → 格式化输出
    """
    ...  # 内部实现
```

---

### 7.3 `memory/rag/reranker.py` — 精排模块

```python
# memory/rag/reranker.py（新增文件）
from typing import Any


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    三级降级精排入口：Jina API → SiliconFlow API → LLM Rerank → 原序兜底。
    
    Args:
        query: 检索查询
        candidates: 待排序的候选文档列表
        top_k: 返回数量
    
    Returns:
        排序后的文档列表（取前 top_k 个）
    """
    ...


def _api_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]] | None:
    """
    调用外部 Reranker API（Jina / SiliconFlow）。
    失败时返回 None（触发降级）。
    """
    ...


def _llm_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """
    使用 ZhipuAI LLM 对候选文档进行语义精排。
    内部调用 get_llm_client()，不直接实例化 ZhipuAI。
    """
    ...
```

---

### 7.4 `agent/main_agent.py` — Agent 对外接口

```python
# agent/main_agent.py（重构后目标接口）
from typing import AsyncGenerator, Generator
from agent.graph.state import AgentState


class LangGraphAgent:
    """
    408 学习助手 Agent 的对外统一入口。
    
    使用方式：
        agent = LangGraphAgent(user_id="user_001")
        # 同步调用
        response = agent.chat("解释一下 KMP 算法", session_id="sess_001")
        # 异步流式调用（供 FastAPI SSE）
        async for chunk in agent.chat_stream_async("出一道操作系统题", session_id="sess_001"):
            yield chunk
    """

    def __init__(self, user_id: str) -> None: ...

    def chat(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
    ) -> str:
        """同步对话，返回完整回复字符串。"""
        ...

    def chat_stream(
        self,
        message: str,
        session_id: str,
    ) -> Generator[str, None, None]:
        """同步流式对话，逐 token yield 字符串。"""
        ...

    async def chat_stream_async(
        self,
        message: str,
        session_id: str,
        on_rag_trace: callable | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        异步流式对话，逐 token yield 字符串。
        
        Args:
            message: 用户输入
            session_id: 当前会话 ID
            on_rag_trace: 可选回调，接收 RAG 追踪信息用于 SSE 推送
        
        Yields:
            str: 逐个 token 的响应文本
        """
        ...

    async def on_session_end(self, session_id: str) -> None:
        """会话结束回调，触发记忆持久化。"""
        ...
```

---

### 7.5 `agent/graph/state.py` — AgentState TypedDict

```python
# agent/graph/state.py（目标态，字段语义注释）
from typing import TypedDict, Any


class AgentState(TypedDict):
    """LangGraph 状态图的全局状态对象。所有图节点共享此状态。"""
    
    # ── 输入字段（由 runtime.py 初始化）──
    messages: list[dict[str, str]]   # 对话历史 [{"role": "user/assistant", "content": "..."}]
    user_id: str                     # 当前用户 ID
    session_id: str                  # 当前会话 ID
    
    # ── 节点写入字段 ──
    intent: str                      # 意图分类结果："study"/"plan"/"review"/"unknown"
    rag_context: str                 # RAG 检索结果（格式化文本），由 rag_node 写入
    rag_trace: dict[str, Any]        # RAG 过程追踪信息，由 rag_node 写入
    tool_result: str                 # 工具执行结果，由 tool_executor 写入
    response: str                    # 最终回复文本，由 response_generator 写入
    
    # ── 记忆注入字段（由 runtime.py 从持久化存储读取后注入）──
    memory_l2: dict[str, Any]        # L2 任务状态快照
    memory_l4: dict[str, Any]        # L4 用户画像快照
    
    # ── 会话事件（用于 SSE 推送）──
    session_events: list[dict]       # 流式事件队列
```

---

### 7.6 `dao/crud/task_state.py` — TaskState CRUD（新增）

```python
# dao/crud/task_state.py（新增文件）
from sqlalchemy.orm import Session
from dao.models import TaskState


def get_task_state(db: Session, user_id: str) -> TaskState | None:
    """获取用户当前任务状态。"""
    return db.query(TaskState).filter(TaskState.user_id == user_id).first()


def upsert_task_state(
    db: Session,
    user_id: str,
    state_data: dict,
) -> TaskState:
    """
    插入或更新任务状态。
    
    Args:
        db: SQLAlchemy Session
        user_id: 用户 ID
        state_data: 任务状态数据字典（包含 current_topic, weak_points, progress 等）
    
    Returns:
        更新后的 TaskState ORM 对象
    """
    task_state = get_task_state(db, user_id)
    if task_state is None:
        task_state = TaskState(user_id=user_id)
        db.add(task_state)
    # 更新字段
    for key, value in state_data.items():
        setattr(task_state, key, value)
    db.commit()
    db.refresh(task_state)
    return task_state


def delete_task_state(db: Session, user_id: str) -> bool:
    """删除用户任务状态（用于重置）。"""
    task_state = get_task_state(db, user_id)
    if task_state:
        db.delete(task_state)
        db.commit()
        return True
    return False
```

---

### 7.7 `config.py` — 兼容层（过渡期）

```python
# config.py — 兼容层，逐步废弃，勿在新代码中引用
# 所有模块应迁移为直接使用 from core.settings import get_settings
"""
⚠️ 已废弃：此文件仅作为向后兼容层存在
   新代码请使用：from core.settings import get_settings
   预计在 Phase 6 完成后彻底移除
"""
from core.settings import get_settings

_s = get_settings()

API_KEY: str = _s.ZHIPU_API_KEY    # 兼容旧 import: from config import API_KEY
MODEL: str = _s.MODEL_NAME          # 兼容旧 import: from config import MODEL
```

---

## 8. 分阶段重构计划

> **原则：先稳定边界，后收敛实现；先补验证，后做迁移；每阶段有独立 DoD。**

### 阶段总览

| 阶段 | 名称 | 周期 | 核心目标 | 风险等级 |
|-----|------|------|---------|---------|
| **Phase 0** | 建立最小回归保护 | 1~2 天 | 补回归基线，确保重构有安全网 | 🟢 低 |
| **Phase 1** | 修复确定性问题 + 统一配置 | 2~3 天 | bug 修复、config 统一、重复消除 | 🟢 低 |
| **Phase 2** | 统一 LLM 客户端边界 | 2~4 天 | ZhipuAI 单例化，消除 7 处重复初始化 | 🟢 低 |
| **Phase 3** | 收敛 Agent 运行时边界 | 4~6 天 | main_agent.py 拆分，legacy 隔离 | 🟡 中 |
| **Phase 4** | 重构 RAG 主管线 | 5~7 天 | retriever_rag.py 职责分离，reranker 独立 | 🟡 中 |
| **Phase 5** | 工具层与节点层热点治理 | 3~5 天 | tools.py 拆分，节点层公共行为收敛 | 🟡 中 |
| **Phase 6** | 分阶段包化 + 移除 sys.path hack | 4~6 天 | pyproject.toml，标准包安装 | 🟠 中高 |
| **Phase 7** | L2/L4 状态存储迁移到 DB | 5~8 天 | JSON → SQLite，双写过渡 | 🟠 中高 |
| **Phase 8** | 目录清理 + 文档收尾 | 2~3 天 | 历史文件归档，README 更新 | 🟢 低 |

---

### Phase 0：建立最小回归保护（1~2 天）

**目标：** 在任何重构前，先建立可重复执行的验证基线。

**任务清单：**

| 任务 | 方式 |
|------|------|
| 记录当前手工验证用例列表 | 文档 |
| 服务启动验证脚本 | `python -m uvicorn server:app` 无报错 |
| `/health` 端点检查 | `curl localhost:8000/health` → 200 |
| 登录接口验证 | `POST /api/v1/auth/login` → token |
| `/api/v1/chat/sync` 验证 | 返回非空字符串 |
| SSE 流验证 | `GET /api/v1/chat/stream` → 收到 `start/token/done` 事件 |
| study intent 走 RAG | 问题含 "解释" 等词，RAG trace 非空 |
| 为 `hybrid_fusion.py` 补 pytest 测试 | `tests/unit/test_hybrid_fusion.py` |
| 为 `score_gate.py` 补 pytest 测试 | `tests/unit/test_score_gate.py` |

**DoD（Definition of Done）：**
- [ ] 存在可一键执行的回归验证清单
- [ ] 至少 2 个纯函数模块具备 pytest 单元测试（`hybrid_fusion`、`score_gate`）
- [ ] 服务启动方式文档化，无需口头传递

---

### Phase 1：修复确定性问题 + 统一配置（2~3 天）

**目标：** 解决低风险高收益的 bug 和结构问题，为后续重构铺路。

**任务清单：**

#### 1.1 修复 `rag_node.py` review intent bug

```python
# agent/graph/nodes/rag_node.py — 修复前
if state.get("intent") != "study":
    return {**state, "rag_context": ""}

# 修复后
RAG_INTENTS = {"study", "review"}
if state.get("intent") not in RAG_INTENTS:
    return {**state, "rag_context": ""}
```

#### 1.2 统一配置入口

```python
# config.py — 改造为兼容层
from core.settings import get_settings
_s = get_settings()
API_KEY = _s.ZHIPU_API_KEY
MODEL = _s.MODEL_NAME
```

#### 1.3 修复 `database.py` create_tables 导入不完整

```python
# dao/database.py — 修复完整导入
def create_tables():
    from dao.models import (
        User, ChatSession, ChatMessage, StudyPlan, StudyTask,
        TaskState, UserProfile, LearningRecord, KnowledgeBase
    )
    Base.metadata.create_all(bind=engine)
```

#### 1.4 消除 `response_generator.py` 重复逻辑

- 让 `response_generator_node()` 直接调用 `build_llm_messages()`，不再维护两份消息构建逻辑

**DoD：**
- [ ] `review` 意图请求可以获得非空 `rag_context`（可通过回归脚本验证）
- [ ] 全仓库只有一个配置读取入口，新代码统一使用 `get_settings()`
- [ ] `create_tables()` 涵盖全部 ORM 模型
- [ ] `response_generator` 消息构建逻辑只有一处
- [ ] SSE 流式 + study/review/plan 主链路无行为回退

---

### Phase 2：统一 LLM 客户端边界（2~4 天）

**目标：** 消除 7 处分散的 `ZhipuAI(api_key=...)` 初始化。

**任务清单：**

1. **新建** `core/llm_client.py`，实现 `get_llm_client()` 单例工厂
2. **逐一替换**以下文件中的 `ZhipuAI(api_key=API_KEY)` 调用：

| 文件 | 位置 | 替换方式 |
|------|------|---------|
| `agent/graph/nodes/intent_router.py` | L126 | `client = get_llm_client()` |
| `agent/graph/nodes/response_generator.py` | L163, L297 | `client = get_llm_client()` |
| `memory/rag/retriever_rag.py` | `_llm_rerank()` 内 | 传入 `get_llm_client()` |
| `memory/hooks.py` | L37 | `client = get_llm_client()` |
| `memory/l4_profile.py` | L49 | `client = get_llm_client()` |
| `memory/rag/query_rewriter.py` | `__init__` | `self._client = get_llm_client()` |

**DoD：**
- [ ] 全仓库无 `ZhipuAI(api_key=...)` 直接初始化（除 `core/llm_client.py` 本身）
- [ ] 可通过替换 `get_llm_client()` 返回值来 mock LLM，不影响其他模块
- [ ] 现有功能无回退

---

### Phase 3：收敛 Agent 运行时边界（4~6 天）

**目标：** 将 `main_agent.py` 承载的多重职责分离，建立清晰的 Agent 边界。

**任务清单：**

1. **新建** `agent/legacy_agent.py`，将 `LearningAgent`（L34-260）及 `SYSTEM_PROMPT` 迁移入内
   - 保留 `main_agent.py` 中的兼容 import（`from agent.legacy_agent import LearningAgent`）
2. **新建** `agent/runtime.py`，提取以下逻辑：
   - `_build_initial_state()` — 初始 AgentState 构建
   - `_sync_memory_snapshot()` — L2/L4 读取注入
   - `_handle_session_end()` — 会话结束生命周期
3. **精简** `main_agent.py` → 仅保留 `LangGraphAgent` 的对外接口调度（目标约 250 行）
4. **验证** `api/v1/chat.py` 的 `hasattr(agent, 'chat_stream_async')` 兼容判断仍然工作

**文件行数目标：**
- `main_agent.py`：614 → ~250 行
- `legacy_agent.py`：新建 ~250 行
- `runtime.py`：新建 ~150 行

**DoD：**
- [ ] `LearningAgent` 不再在 `main_agent.py` 中定义
- [ ] `api/v1/chat.py` 的兼容逻辑仍然可工作（`hasattr` 判断通过）
- [ ] SSE 流式端到端行为与现状一致
- [ ] `main_agent.py` 行数不超过 300 行

---

### Phase 4：重构 RAG 主管线（5~7 天）

**目标：** 将 709 行的 `retriever_rag.py` 收敛为清晰的编排入口，职责不再交叉。

**任务清单：**

1. **引入** `RetrievalResult` dataclass（内部统一结果类型）
2. **提取** `reranker.py`（新建）：
   - 从 `retriever_rag.py` 中提取 `_llm_rerank()`（L163-232 约 70 行）
   - 从 `retriever_rag.py` 中提取 `_api_rerank()`（约 60 行）
   - 暴露 `rerank(query, candidates, top_k)` 统一接口
3. **重构** `retriever_rag.py` 核心逻辑：
   - 合并 `retrieve()` 和 `retrieve_with_trace()` 的重复实现为 `_run_pipeline(include_trace: bool)`
   - 保持两个公开函数签名不变（仅调用 `_run_pipeline` 并做格式转换）
4. **迁移** `_PIPELINE_CONFIG` 硬编码 → 从 `get_settings()` 读取所有 RAG 参数
5. **保证** 前端 RAGProcessPanel.vue 所依赖的 trace 字段结构语义兼容

**文件行数目标：**
- `retriever_rag.py`：709 → ~350 行
- `reranker.py`：新建 ~150 行

**DoD：**
- [ ] `retrieve()` 与 `retrieve_with_trace()` 无代码重复（共享 `_run_pipeline()`）
- [ ] Reranker 逻辑在独立模块，可独立测试
- [ ] 所有 RAG 参数来自 `core/settings.py`，无硬编码
- [ ] 前端 RAG 过程展示（RAGProcessPanel）无功能回退
- [ ] 单元测试覆盖 reranker 降级逻辑

---

### Phase 5：工具层与节点层热点治理（3~5 天）

**目标：** 降低 `tools.py` 复杂度，统一节点层的公共行为。

**任务清单：**

1. **新建** `agent/tools/` 目录
   - `agent/tools/__init__.py`
   - `agent/tools/quiz.py`：迁移 `generate_quiz` 分支（L229-363，约 135 行）
   - `agent/tools/registry.py`：工具名 → 处理函数的 dict 映射
2. **精简** `agent/tools.py` → ~250 行（仅保留路由分发 + 简单工具）
3. **节点层公共行为收敛**：
   - 各节点统一使用 `get_llm_client()` 和 `get_settings()`（Phase 2 已完成部分）
   - 提取 `agent/graph/nodes/_utils.py`：轻量公共工具（消息格式化、标记清洗等）

**DoD：**
- [ ] `agent/tools.py` 行数不超过 300 行
- [ ] `generate_quiz` 逻辑在 `agent/tools/quiz.py` 中，独立可测试
- [ ] 新增工具只需在 `tools/` 创建新文件 + 注册，不需要修改 `tools.py` 主体
- [ ] 节点层无散落的 `sys.path` hack（为 Phase 6 铺垫）

---

### Phase 6：分阶段包化 + 移除 sys.path hack（4~6 天）

**目标：** 项目从脚本式工程过渡为标准 Python 包。

**任务清单：**

1. **创建** `pyproject.toml`：

```toml
[project]
name = "study-agent"
version = "2.0.0"
requires-python = ">=3.10"
description = "408考研AI学习助手"

[tool.setuptools.packages.find]
where = ["."]
exclude = ["_legacy*", "storage*", "frontend*"]
```

2. **执行** `pip install -e .`，验证各模块均可直接 import
3. **分批移除** `sys.path.insert` hack（按风险从低到高）：
   - 批次 A（低风险）：`api/`、`agent/graph/`（4 处）
   - 批次 B（中风险）：`memory/rag/`、`memory/`（4 处）
   - 批次 C（后处理）：`scripts/`、`evaluation/` 零散脚本（3 处）
4. **更新** `Dockerfile`：添加 `RUN pip install -e .`

**DoD：**
- [ ] `pyproject.toml` 存在且 `pip install -e .` 无报错
- [ ] 核心运行链（`api/`、`agent/`、`memory/`）无 `sys.path.insert`
- [ ] Docker / 本地 / pytest 三种场景 import 行为一致
- [ ] `scripts/` 脚本仍可通过 `python -m scripts.xxx` 执行

---

### Phase 7：L2/L4 状态存储迁移到 DB（5~8 天）

**目标：** 消除 "已有 ORM model，但真实状态仍依赖 JSON 文件" 的长期维护问题。

**任务清单：**

**第一优先级（L2 TaskState）：**
1. 新建 `dao/crud/task_state.py`（接口见 §7.6）
2. 修改 `memory/l2_task.py`：
   - `load_task_state(user_id)` → 优先从 DB 读取，JSON 文件作为 fallback
   - `save_task_state(user_id, state)` → 写入 DB（同时保留 JSON 备份直到迁移完成）
3. 新建 `scripts/migrate_json_to_db.py`：将现有 `task_state.json` 中的数据导入 DB

**第二优先级（L4 UserProfile）：**
1. 修改 `dao/crud/profile.py`，完善 `upsert_user_profile()` 接口
2. 修改 `memory/l4_profile.py`：读写路径切换到 DB
3. 迁移脚本支持 `profile.json` → DB

**迁移策略（双写过渡）：**

```
阶段A: 双写  - 同时写 DB 和 JSON，读优先 DB，JSON 作 fallback
阶段B: 验证  - 持续运行两周，确认 DB 数据完整性
阶段C: 收敛  - 读写均走 DB，JSON 文件只读（备份）
阶段D: 清理  - JSON 文件归档到 _legacy/
```

**DoD：**
- [ ] L2/L4 有明确单一真实数据源（SQLite DB）
- [ ] 迁移脚本可重复执行、幂等
- [ ] 现有 JSON 文件数据无丢失（迁移前自动备份）
- [ ] 多用户场景下 L2/L4 数据不互相干扰（user_id 隔离）

---

### Phase 8：目录清理 + 文档收尾（2~3 天）

**目标：** 在核心结构稳定后，清理历史遗留，让仓库对新人友好。

**根目录散落文件处理方案：**

| 文件 | 处理方式 |
|------|---------|
| `app.py`（Gradio 旧 UI） | 移入 `_legacy/app.py` |
| `main.py`（旧 CLI 入口） | 移入 `_legacy/main.py` |
| `fix_all.py`、`fix_questions.py`、`append_corrections.py` | 删除（一次性脚本，任务已完成） |
| `show_questions.py`、`review_questions.py` | 移入 `scripts/` |
| `test_api.py`、`test_validate.py` | 移入 `tests/e2e/` |
| `tmp_out.txt`、`1.26.0` | 删除 |
| `2024_questions.txt`、`q2024.txt`、`q2025.txt` | 移入 `scripts/data/` |

**文档更新：**
- 更新 `README.md`（启动方式、目录说明）
- 更新 `docs/architecture.md`（与目标态一致）
- 归档旧重构文档（`refactoring_plan.md` 标注为历史版本）

**DoD：**
- [ ] 根目录只保留应用入口与配置文件（`server.py`、`pyproject.toml`、`config.py`、`Dockerfile` 等）
- [ ] 新成员看目录即可理解主要模块职责
- [ ] `README.md` 包含完整的本地启动步骤

---

## 9. 测试策略

### 9.1 测试分层

```
┌─────────────────────────────────────────────────────────────┐
│ E2E 测试 (tests/e2e/)                                       │
│  - test_chat_stream.py：SSE 流式对话全链路                  │
│  - 覆盖：study/review/plan 三条主意图分支                   │
│  - 工具：httpx + pytest-asyncio                             │
├─────────────────────────────────────────────────────────────┤
│ 集成测试 (tests/integration/)                               │
│  - test_rag_pipeline.py：RAG 管线（需 ChromaDB 实例）       │
│  - test_agent_graph.py：LangGraph 图执行（mock LLM）        │
│  - 工具：pytest + pytest-asyncio + unittest.mock            │
├─────────────────────────────────────────────────────────────┤
│ 单元测试 (tests/unit/)          ← 优先建立                  │
│  - test_hybrid_fusion.py：RRF 算法（纯函数）                │
│  - test_score_gate.py：评分门控（纯函数）                   │
│  - test_intent_router.py：快速路径判断（纯函数）            │
│  - test_quiz_tools.py：题目解析、标记清洗                   │
│  - test_reranker.py：Reranker 降级逻辑（mock API）          │
│  - test_settings.py：配置加载与默认值                       │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 测试优先级

| 优先级 | 模块 | 理由 | 类型 |
|-------|------|------|------|
| **P0** | `memory/rag/hybrid_fusion.py` | 纯函数，0 依赖，最易测试 | 单元 |
| **P0** | `memory/rag/score_gate.py` | 纯函数，评分逻辑关键 | 单元 |
| **P1** | `agent/graph/nodes/intent_router.py` | `_is_quiz_answer`、`_extract_user_choice` 快速路径 | 单元 |
| **P1** | `agent/tools/quiz.py` | `_parse_exam_text` 解析逻辑，回归风险高 | 单元 |
| **P1** | `memory/rag/reranker.py` | 降级链逻辑，需 mock API 调用 | 单元 |
| **P2** | `memory/rag/retriever_rag.py` | `_run_pipeline` 端到端管线（需 ChromaDB mock） | 集成 |
| **P2** | `agent/graph/graph.py` | 图路由逻辑正确性（mock 所有节点） | 集成 |
| **P3** | `/api/v1/chat/stream` | SSE 流式格式正确性 | E2E |

### 9.3 关键测试用例示例

#### 纯函数测试（`tests/unit/test_hybrid_fusion.py`）

```python
import pytest
from memory.rag.hybrid_fusion import rrf_fusion, reciprocal_rank_score


def test_rrf_fusion_empty_inputs():
    """空输入应返回空列表。"""
    result = rrf_fusion(vector_results=[], bm25_results=[], k=60)
    assert result == []


def test_rrf_fusion_prefers_items_in_both_lists():
    """同时出现在两个列表中的文档应得到更高 RRF 分数。"""
    doc_both = {"doc_id": "A", "text": "在两个列表中都出现"}
    doc_vector_only = {"doc_id": "B", "text": "只在向量列表中"}
    doc_bm25_only = {"doc_id": "C", "text": "只在 BM25 列表中"}

    result = rrf_fusion(
        vector_results=[doc_both, doc_vector_only],
        bm25_results=[doc_both, doc_bm25_only],
        k=60,
    )
    
    scores = {doc["doc_id"]: doc["rrf_score"] for doc in result}
    assert scores["A"] > scores["B"]   # 双列表出现得分更高
    assert scores["A"] > scores["C"]


def test_rrf_fusion_k_parameter_effect():
    """k 值越大，排名差异对分数影响越平滑。"""
    ...
```

#### mock LLM 测试（`tests/unit/test_reranker.py`）

```python
from unittest.mock import patch, MagicMock
from memory.rag.reranker import rerank, _llm_rerank


def test_rerank_falls_back_to_llm_when_api_fails():
    """当外部 Reranker API 失败时，应降级到 LLM Rerank。"""
    candidates = [
        {"doc_id": "A", "text": "文档 A"},
        {"doc_id": "B", "text": "文档 B"},
    ]

    with patch("memory.rag.reranker._api_rerank", return_value=None):
        with patch("memory.rag.reranker._llm_rerank") as mock_llm:
            mock_llm.return_value = candidates[::-1]  # 反序
            result = rerank("测试查询", candidates, top_k=2)
            mock_llm.assert_called_once()
            assert result[0]["doc_id"] == "B"  # LLM 重排序后 B 在前


def test_rerank_returns_original_order_when_all_fail():
    """当所有排序策略均失败时，返回原始顺序。"""
    candidates = [{"doc_id": "A"}, {"doc_id": "B"}]
    
    with patch("memory.rag.reranker._api_rerank", return_value=None):
        with patch("memory.rag.reranker._llm_rerank", side_effect=Exception("LLM 超时")):
            result = rerank("查询", candidates, top_k=2)
            assert result[0]["doc_id"] == "A"  # 保持原序
```

### 9.4 Mock 策略

| 外部依赖 | Mock 方式 | 适用范围 |
|---------|---------|---------|
| ZhipuAI LLM | `patch("core.llm_client.get_llm_client")` | 所有需要 LLM 的单元/集成测试 |
| ChromaDB | 内存模式 `chromadb.EphemeralClient()` | RAG 管线集成测试 |
| SQLAlchemy DB | 内存 SQLite `sqlite:///` | DAO 层单元测试 |
| Jina/SiliconFlow API | `requests_mock` 或 `patch` | Reranker 测试 |
| BM25 索引 | 构造小型测试 corpus | BM25 检索测试 |

### 9.5 测试基础设施（`tests/conftest.py`）

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dao.database import Base


@pytest.fixture
def mock_llm_client():
    """提供 mock ZhipuAI 客户端，避免真实 API 调用。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="mock 回复内容"))]
    )
    return mock_client


@pytest.fixture
def in_memory_db():
    """提供内存 SQLite 数据库 Session，用于 DAO 层测试。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def chroma_ephemeral():
    """提供 ChromaDB 内存实例，用于 RAG 管线测试。"""
    import chromadb
    return chromadb.EphemeralClient()
```

---

## 10. 风险与回滚

### 10.1 各阶段主要风险

| 阶段 | 主要风险 | 缓解措施 |
|-----|---------|---------|
| Phase 1 | config.py 兼容层未完全覆盖旧 import | 全量 `grep -r "from config import"` 确认替换 |
| Phase 2 | `lru_cache` 在测试间共享状态 | 测试 teardown 调用 `get_llm_client.cache_clear()` |
| Phase 3 | LearningAgent 移走后，旧 hasattr 判断失效 | 在 `main_agent.py` 保留 `from agent.legacy_agent import LearningAgent` |
| Phase 4 | trace 字段重命名导致前端 RAGProcessPanel 渲染异常 | 保持字段名兼容，新字段使用新名，旧字段先别名再废弃 |
| Phase 5 | `agent/tools/quiz.py` 提取后，`tools.py` 中的路由分发失效 | 先提取，更新路由映射，再运行回归测试 |
| Phase 6 | `sys.path` hack 移除后，某些脚本无法导入 | 分批移除，每批提交后运行 CI；scripts 最后处理 |
| Phase 7 | JSON 数据迁移后部分字段丢失 | 迁移脚本干运行（dry-run）模式，人工核查后再执行 |
| Phase 8 | 移走旧文件后 docker-compose.yml 中的 gradio 服务引用失效 | Phase 8 同时更新 docker-compose.yml |

### 10.2 受保护的不可变约定

以下内容在整个重构期间**绝对不能破坏**：

```
1. /api/v1/chat/stream SSE 事件格式
   - 必须推送：{"type": "start"}
   - 必须推送：{"type": "token", "content": "..."}
   - 必须推送：{"type": "done"}
   - RAG trace 事件：{"type": "rag_*", ...}（字段名保持兼容）

2. LangGraphAgent 的对外接口签名
   - chat(message, session_id, user_id) -> str
   - chat_stream_async(message, session_id, ...) -> AsyncGenerator

3. AgentState 关键字段
   - messages、intent、rag_context、response 字段不得删除或重命名

4. storage/ 目录下的数据兼容性
   - 现有 sessions/ journal.jsonl 格式不变（append-only）
   - ChromaDB 数据不重建（使用现有 collection_name）
   - 迁移期间 JSON 文件仍可作为 fallback 读取
```

### 10.3 回滚策略

#### 代码回滚

每个 Phase 在独立 Git 分支完成，合并前必须：
1. 通过 Phase 0 建立的回归验证清单
2. 至少一名开发者 Code Review
3. 主分支保持随时可部署状态

```bash
# 快速回滚到上一个稳定版本
git revert --no-commit <phase-commit-hash>
git commit -m "revert: rollback phase X due to <issue>"
```

#### 数据回滚（Phase 7 专属）

```python
# scripts/migrate_json_to_db.py 支持 --dry-run 和 --rollback 参数
python scripts/migrate_json_to_db.py --dry-run      # 验证迁移内容
python scripts/migrate_json_to_db.py --execute      # 执行迁移（自动备份 JSON）
python scripts/migrate_json_to_db.py --rollback     # 从备份恢复 JSON 文件
```

#### 配置回滚（Phase 1 专属）

Phase 1 的配置统一是最低风险的变更。如需回滚：

```python
# config.py — 快速回滚为原始版本
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ZHIPU_API_KEY", "")
MODEL = os.getenv("MODEL_NAME", "glm-4-flash")
```

### 10.4 绝不建议做的事

根据项目规模和实际问题，以下过度工程化操作**不在重构范围内**：

| 诱惑性操作 | 为何不做 |
|-----------|---------|
| 为 7 个工具建立 `ToolBase` 抽象类 + Factory | 工具数量不多，dict 映射足够，抽象类徒增理解成本 |
| 建立 `agent/services/` 服务层 | Agent 本身就是编排层，再加一层 service 只增加跳转链路 |
| 迁移 ChromaDB → Pinecone/Weaviate | 开发阶段本地 ChromaDB 完全足够，迁移成本不值当 |
| 为 Agent 建立 `interfaces/` 协议包 | TypedDict `AgentState` 已是完整状态定义，无需另立接口层 |
| 一次性删除所有 sys.path hack | 高概率破坏运行环境，必须分批验证 |
| config 和 core 合并为 `config/` 多文件结构 | `core/settings.py` 单文件已足够，拆分只增加 import 路径 |
| 在 RAG 层引入 LlamaIndex 或 Haystack 框架 | 自研管线结构清晰，引入大框架会导致维护复杂度骤增 |

---

## 附录：关键文件变更速查表

| 文件 | 当前行数 | 目标行数 | 变更类型 | 所在 Phase |
|------|---------|---------|---------|-----------|
| `config.py` | 10 | 10 | 改为兼容层委托 | Phase 1 |
| `agent/graph/nodes/rag_node.py` | ~60 | ~60 | 修复 review bug | Phase 1 |
| `dao/database.py` | 38 | 40 | 修复 create_tables 导入 | Phase 1 |
| `agent/graph/nodes/response_generator.py` | 330 | ~280 | 消除重复逻辑 | Phase 1 |
| `core/llm_client.py` | — | ~25 | 新增 | Phase 2 |
| `agent/main_agent.py` | 614 | ~250 | 拆分（legacy 迁移到新文件） | Phase 3 |
| `agent/legacy_agent.py` | — | ~250 | 新增（legacy 迁入） | Phase 3 |
| `agent/runtime.py` | — | ~150 | 新增（会话态管理） | Phase 3 |
| `memory/rag/retriever_rag.py` | 709 | ~350 | 重构（去重 + 配置统一） | Phase 4 |
| `memory/rag/reranker.py` | — | ~150 | 新增（从 retriever 提取） | Phase 4 |
| `agent/tools.py` | 564 | ~250 | 拆分（quiz 迁移到子目录） | Phase 5 |
| `agent/tools/quiz.py` | — | ~150 | 新增（generate_quiz 迁入） | Phase 5 |
| `agent/tools/registry.py` | — | ~30 | 新增（工具注册表） | Phase 5 |
| `pyproject.toml` | — | ~20 | 新增（包化配置） | Phase 6 |
| `memory/l2_task.py` | 47 | ~70 | 修改（DB 主路径 + JSON fallback） | Phase 7 |
| `memory/l4_profile.py` | 70 | ~90 | 修改（DB 主路径 + JSON fallback） | Phase 7 |
| `dao/crud/task_state.py` | — | ~60 | 新增（TaskState CRUD） | Phase 7 |
| `scripts/migrate_json_to_db.py` | — | ~120 | 新增（数据迁移脚本） | Phase 7 |

---

*文档由重构分析自动生成，基于 2026-04-21 源码实际状态。*  
*如发现与当前代码不符之处，请以实际代码为准并更新本文档。*
