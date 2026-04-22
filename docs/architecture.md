# 408 考研 AI 学习教练系统 — 系统架构文档

> 版本：2.0.0 | 最后更新：基于源码实际实现

---

## 1. 项目概述

本项目是一个面向 408 计算机考研的 **AI 学习教练系统**，覆盖数据结构、操作系统、计算机网络、计算机组成原理四科。系统基于 LangGraph 状态图实现 Agent 编排，集成混合 RAG 检索管线与 L1-L4 四层记忆架构，能够为用户提供个性化、有记忆、有依据的学习辅导体验。

### 核心能力

| 能力 | 说明 |
|------|------|
| 智能问答 | 基于 RAG 检索教材/真题/考点，生成有据可依的回答 |
| 意图路由 | LLM 语义分类（study / plan / review / unknown）驱动不同处理分支 |
| 学习规划 | 自动生成和调整学习计划 |
| 记忆系统 | L1-L4 四层记忆，跨会话追踪学习进度和薄弱点 |
| 知识沉淀 | 自动提炼学习模式和踩坑记录 |
| 用户画像 | 知识图谱 + 学习偏好动态建模 |

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                            │
│    Vue3 + Ant Design + Vite + Pinia + SSE 实时流                    │
│    views: Chat.vue / Login.vue / Plan.vue                          │
│    components: ChatBubble.vue / RAGProcessPanel.vue                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API 层 (FastAPI)                             │
│    server.py → uvicorn                                             │
│    路由: /api/v1/auth  /api/v1/chat  /api/v1/plan                  │
│    中间件: CORS / JWT 认证                                          │
│    数据库: dao/ (SQLite + SQLAlchemy)                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Agent 编排层 (LangGraph)                          │
│                                                                     │
│    START → [intent_router] ──条件路由──┬─ study  → rag → tool → resp│
│                                        ├─ plan   → tool → resp      │
│                                        ├─ review → rag → resp       │
│                                        └─ unknown→ resp             │
│                            所有分支 → [memory_update] → END         │
│                                                                     │
│    状态对象: AgentState (TypedDict)                                  │
└──────────────┬───────────────────────────────┬──────────────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────────────┐
│    RAG 检索层             │   │         记忆层 (L1-L4)               │
│                          │   │                                      │
│  Query重写(3策略)        │   │  L1 会话: journal.jsonl (append-only)│
│  向量检索(ChromaDB)      │   │  L2 任务: task_state.json            │
│  BM25稀疏检索(jieba)     │   │  L3 知识: LLM提炼 patterns/pitfalls │
│  RRF融合(k=60)           │   │  L4 画像: profile.json (知识图谱)   │
│  Reranker三级降级        │   │                                      │
│  评分门控(3档)           │   │  注入: build_memory_context()        │
│  Auto-merging            │   │  钩子: on_session_stop()             │
└──────────────────────────┘   └──────────────────────────────────────┘
               │                               │
               ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        数据层 (Storage)                             │
│                                                                     │
│  ChromaDB (storage/chroma_db/)    — 向量索引：textbooks /           │
│                                     exam_questions / key_points     │
│  BM25 JSON (storage/bm25_index/) — jieba 分词后的 BM25 索引        │
│  SQLite (storage/studycoach.db)  — 用户/认证数据                    │
│  Redis (docker redis:7-alpine)   — 会话缓存 & 限流                 │
│  File System (storage/)          — sessions / tasks / user_profile  │
│                                    knowledge_base / plans           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | Vue 3 + TypeScript + Vite | SPA 应用，SSE 实时流式展示 |
| | Ant Design Vue | UI 组件库 |
| | Pinia | 状态管理（auth.ts / chat.ts） |
| **API** | FastAPI + Uvicorn | 异步 HTTP 服务，自动生成 Swagger 文档 |
| | SQLAlchemy + SQLite | 用户数据持久化 |
| | JWT | 无状态认证 |
| **Agent** | LangGraph (StateGraph) | 状态图编排，条件路由，节点流水线 |
| | 智谱 GLM (ZhipuAI) | LLM 推理（意图分类 / 回复生成 / Rerank / Query重写） |
| **RAG** | ChromaDB | 向量数据库（持久化模式） |
| | 智谱 embedding-3 | 1024 维文本嵌入，入库+检索统一向量空间 |
| | rank-bm25 + jieba | BM25Okapi 稀疏检索 |
| | Jina / SiliconFlow Reranker | 外部 Cross-Encoder 精排 API |
| **记忆** | L1-L4 分层架构 | 会话日志 / 任务状态 / 知识沉淀 / 用户画像 |
| **基础设施** | Docker Compose | 一键部署 api + gradio + redis |
| | Redis 7 Alpine | 会话缓存与限流 |

---

## 4. 各层职责说明

### 4.1 前端层 (`frontend/`)

- **框架**：Vue 3 + TypeScript + Vite，Pinia 状态管理
- **核心页面**：
  - `Chat.vue` — 主聊天界面，支持 SSE 流式输出
  - `Login.vue` — 用户登录/注册
  - `Plan.vue` — 学习计划管理
- **SSE 实时流**：`utils/sse.ts` 处理服务端推送的 RAG 管线追踪事件
- **RAG 可视化**：`RAGProcessPanel.vue` 展示检索过程（向量/BM25/融合/Rerank 各步骤）

### 4.2 API 层 (`server.py` + `api/`)

- **入口**：`server.py` 创建 FastAPI 应用，挂载路由
- **路由模块**：
  - `api/v1/auth.py` — 注册、登录、JWT 签发
  - `api/v1/chat.py` — 对话接口（调用 Agent Graph）
  - `api/v1/plan.py` — 学习计划 CRUD
- **数据层**：`dao/database.py`（SQLAlchemy）+ `dao/models.py`（ORM 模型）
- **启动事件**：自动建表 `create_tables()`

### 4.3 Agent 编排层 (`agent/graph/`)

- **状态定义**：`state.py` → `AgentState(TypedDict)`，包含 messages、intent、rag_context、memory_l2/l4、session_events 等字段
- **状态图**：`graph.py` → `build_graph()` 构建 LangGraph StateGraph
- **节点列表**：

| 节点 | 文件 | 职责 |
|------|------|------|
| `intent_router` | `nodes/intent_router.py` | LLM 语义分类：study / plan / review / unknown |
| `rag_node` | `nodes/rag_node.py` | 调用 RAG 管线检索知识库 |
| `tool_executor` | `nodes/tool_executor.py` | 执行工具调用（如 generate_quiz） |
| `response_generator` | `nodes/response_generator.py` | 综合 RAG 上下文 + 记忆生成最终回复 |
| `memory_update` | `nodes/memory_update.py` | 更新 L2 任务状态和 L4 用户画像快照 |

- **路由逻辑**：
  - `route_by_intent()` — 根据 intent 分四个分支
  - `route_after_rag()` — study 分支走 tool_executor，review 直接走 response_generator

### 4.4 RAG 检索层 (`memory/rag/`)

详见 [rag_pipeline.md](./rag_pipeline.md)。

核心模块：

| 模块 | 职责 |
|------|------|
| `retriever_rag.py` | 主检索入口 `retrieve()`，编排完整管线 |
| `query_rewriter.py` | Query 重写（expand / decompose / hyde 三策略） |
| `bm25_retriever.py` | BM25 稀疏检索（jieba + BM25Okapi） |
| `hybrid_fusion.py` | RRF 融合算法 |
| `score_gate.py` | 评分门控（strict / normal / loose） |
| `indexer.py` | 三级分块 + ChromaDB 入库 + Auto-merging |
| `pdf_parser.py` | PDF 解析（PyMuPDF） |

### 4.5 记忆层 (`memory/`)

详见 [memory_system.md](./memory_system.md)。

| 层级 | 文件 | 存储 | 触发时机 |
|------|------|------|---------|
| L1 会话 | `l1_session.py` | `journal.jsonl` | 每次用户/助手消息 |
| L2 任务 | `l2_task.py` | `task_state.json` | 会话结束时 |
| L3 知识 | `l3_knowledge.py` | `patterns/*.md` / `pitfalls/*.md` | 每 5 次会话 |
| L4 画像 | `l4_profile.py` | `profile.json` | 会话结束时 / 每 3 次偏好提炼 |

### 4.6 数据层 (`storage/`)

```
storage/
├── chroma_db/           # ChromaDB 向量索引（textbooks / exam_questions / key_points）
├── bm25_index/          # BM25 JSON 索引（jieba 分词后的语料）
├── studycoach.db        # SQLite 主数据库（用户/认证）
├── sessions/            # L1 会话日志（每个会话一个目录）
│   └── YYYYMMDD_HHMMSS/
│       ├── journal.jsonl       # 事件流日志
│       ├── digest.json         # 会话摘要（LLM 生成）
│       └── session_notes.md    # 可读摘要
├── tasks/               # L2 任务状态
│   └── task_state.json
├── user_profile/        # L4 用户画像
│   └── profile.json
├── knowledge_base/      # L3 知识沉淀
│   ├── patterns/        # 学习模式
│   └── pitfalls/        # 踩坑记录
├── plans/               # 学习计划
├── vector_db/           # 记忆向量索引（会话摘要语义检索）
└── ...
```

---

## 5. 关键设计决策及理由

### 5.1 LangGraph 状态图 vs 简单 Chain

**决策**：采用 LangGraph StateGraph 实现 Agent 编排。

**理由**：
- 意图路由需要条件分支（study/plan/review/unknown 四路），Chain 不支持动态路由
- 状态在节点间共享（如 `rag_context` 由 rag_node 写入，response_generator 读取），StateGraph 天然支持
- 易于扩展新节点（如增加 quiz_node），只需 `add_node()` + `add_edge()`

### 5.2 混合检索 (向量 + BM25 + RRF) vs 纯向量检索

**决策**：双路检索 + RRF 融合。

**理由**：
- 408 考研有大量精确术语（如"KMP"、"B+树"、"partition"），纯向量语义检索对精确词匹配能力不足
- BM25 关键词匹配弥补向量短板，RRF 融合后 Hit@5 从 0.80 提升至 0.92（+15%）
- RRF 算法无需训练，k=60 为论文推荐默认值，开箱即用

### 5.3 三级分块 + Auto-merging vs 单级 Chunk

**决策**：L1(2000字符)/L2(600字符)/L3(150字符) 三级分块，检索用子块，返回给 LLM 用父块。

**理由**：
- 小粒度子块（600字符）向量检索更精准，大粒度父块（2000字符）提供给 LLM 上下文更完整
- Auto-merging 自动按 parent_index 去重，同一父块下多个命中子块只返回一次

### 5.4 L1-L4 分层记忆 vs 单一对话历史

**决策**：四层记忆架构（会话/任务/知识/画像）。

**理由**：
- L1 提供当前会话上下文（append-only，不丢失任何事件）
- L2 跨会话追踪学习进度和薄弱点，实现任务连续性
- L3 通过 LLM 提炼学习模式，构建可复用知识
- L4 构建知识图谱和学习偏好，实现个性化辅导

### 5.5 Reranker 三级降级链

**决策**：Jina API → SiliconFlow API → LLM Rerank → 保持原序。

**理由**：
- 外部 Reranker API（Cross-Encoder）精排效果最佳，但可能因网络/限额不可用
- LLM Rerank 作为 fallback 质量仍优于原序
- 最差情况保持 RRF 原排序，确保系统始终可用

---

## 6. Docker 部署说明

### docker-compose.yml 服务

| 服务 | 镜像/构建 | 端口 | 说明 |
|------|----------|------|------|
| `api` | 本地 Dockerfile | 8000 | FastAPI 后端 |
| `gradio` | 本地 Dockerfile | 7861 | Gradio 交互前端（原有 app.py） |
| `redis` | redis:7-alpine | 6379 | 缓存与限流，密码 `redis123` |

### 环境变量

| 变量 | 说明 |
|------|------|
| `ZHIPU_API_KEY` | 智谱 AI API 密钥 |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产环境必须修改） |
| `DATABASE_URL` | 数据库连接字符串，默认 `sqlite:///./storage/studycoach.db` |
| `REDIS_URL` | Redis 连接，默认 `redis://:redis123@redis:6379/0` |
| `JINA_API_KEY` | （可选）Jina Reranker API 密钥 |
| `SILICONFLOW_API_KEY` | （可选）SiliconFlow Reranker API 密钥 |

### 启动命令

```bash
# 开发环境：直接运行
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# Docker 部署
docker-compose up -d
```

---

## 7. 目录结构说明

```
DEMO/
├── server.py                  # FastAPI 后端入口
├── app.py                     # Gradio 交互入口（原有）
├── main.py                    # CLI 入口
├── config.py                  # 全局配置（API_KEY, MODEL）
├── docker-compose.yml         # Docker 编排
├── Dockerfile                 # 容器构建
├── requirements.txt           # Python 依赖
│
├── api/                       # API 层
│   ├── v1/
│   │   ├── auth.py            # 认证路由
│   │   ├── chat.py            # 对话路由
│   │   └── plan.py            # 计划路由
│   ├── middleware/             # 中间件
│   └── deps.py                # 依赖注入
│
├── agent/                     # Agent 编排层
│   ├── graph/
│   │   ├── state.py           # AgentState 定义
│   │   ├── graph.py           # LangGraph 状态图构建
│   │   └── nodes/             # 图节点实现
│   │       ├── intent_router.py
│   │       ├── rag_node.py
│   │       ├── tool_executor.py
│   │       ├── response_generator.py
│   │       └── memory_update.py
│   ├── tools.py               # 工具函数定义
│   ├── lc_tools.py            # LangChain Tools 封装
│   └── main_agent.py          # Agent 主逻辑
│
├── memory/                    # 记忆系统
│   ├── l1_session.py          # L1 会话记忆
│   ├── l2_task.py             # L2 任务状态
│   ├── l3_knowledge.py        # L3 知识沉淀
│   ├── l4_profile.py          # L4 用户画像
│   ├── retrieval.py           # 记忆检索 + build_memory_context
│   ├── hooks.py               # 生命周期钩子 (on_session_stop)
│   └── rag/                   # RAG 检索管线
│       ├── retriever_rag.py   # 主检索入口
│       ├── query_rewriter.py  # Query 重写
│       ├── bm25_retriever.py  # BM25 检索
│       ├── hybrid_fusion.py   # RRF 融合
│       ├── score_gate.py      # 评分门控
│       ├── indexer.py         # 分块 & 入库
│       └── pdf_parser.py      # PDF 解析
│
├── dao/                       # 数据访问层
│   ├── database.py            # SQLAlchemy 引擎
│   ├── models.py              # ORM 模型
│   └── crud/                  # CRUD 操作
│
├── frontend/                  # Vue3 前端
│   ├── src/
│   │   ├── views/             # 页面组件
│   │   ├── components/        # 通用组件
│   │   ├── stores/            # Pinia 状态
│   │   ├── utils/             # HTTP/SSE 工具
│   │   └── router/            # Vue Router
│   ├── package.json
│   └── vite.config.ts
│
├── scripts/                   # 运维脚本
│   ├── index_textbooks.py     # PDF 教材入库
│   ├── index_exam_questions.py# 真题入库
│   ├── index_key_points.py    # 考点笔记入库
│   ├── build_bm25_index.py    # BM25 索引构建
│   └── test_rag.py            # RAG 测试
│
├── evaluation/                # 评估体系
│   ├── eval_retrieval.py      # 检索质量评估脚本
│   ├── test_cases.json        # 30 条评测用例
│   └── eval_report.md         # 评估报告
│
├── storage/                   # 运行时数据（持久化）
│   ├── chroma_db/             # ChromaDB 向量索引
│   ├── bm25_index/            # BM25 JSON 索引
│   ├── sessions/              # L1 会话日志
│   ├── tasks/                 # L2 任务状态
│   ├── user_profile/          # L4 用户画像
│   ├── knowledge_base/        # L3 知识库
│   ├── plans/                 # 学习计划
│   ├── vector_db/             # 记忆向量索引
│   └── studycoach.db          # SQLite 主数据库
│
├── tests/                     # 测试
└── docs/                      # 项目文档
```
