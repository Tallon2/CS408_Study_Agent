# 408 考研 AI 学习教练系统 (Study Coach 408)

## 📖 项目简介

一个面向 408 考研（数据结构、操作系统、计算机网络、计算机组成原理）的 AI 学习教练系统。系统基于 **LangGraph 状态图** 编排 Agent 工作流，结合 **四层分层记忆架构** 实现个性化学习追踪，通过 **混合检索 RAG 管线** 提供精准的知识问答，并配有 Vue 3 前端实现完整的交互体验。

**三大核心亮点：**
- 🧠 **四层分层记忆**（L1 会话状态 → L2 任务状态 → L3 知识沉淀 → L4 用户画像），实现跨会话的个性化学习追踪
- 🔍 **混合检索 RAG 管线**（Query 重写 → BM25 + 向量双路检索 → RRF 融合 → 评分门控），Hit@5 达 **0.92**，MRR 达 **0.78**
- 🤖 **LangGraph 状态图编排**（意图路由 → 多分支处理 → 记忆更新），支持 study / plan / review / unknown 四种意图自动分流

---

## ✨ 核心特性

- **四层分层记忆系统（L1-L4）**
  - L1 会话状态：append-only 事件日志 + 会话摘要
  - L2 任务状态：学习计划与任务进度追踪（SQLite DB，JSON fallback）
  - L3 知识沉淀：知识库索引（教材、真题、要点，共 ~2,370 chunks）
  - L4 用户画像：掌握程度、薄弱点、学习偏好（SQLite DB，JSON fallback）

- **混合检索 RAG 管线**
  - Query 重写（expand / decompose 策略）
  - BM25 关键词检索（jieba 分词）+ 向量语义检索（zhipuai embedding-3，1024 维）
  - RRF（Reciprocal Rank Fusion，k=60）融合排序
  - 评分门控：低于阈值自动触发 Query 重写二次检索
  - Reranker 三级降级链：Jina API → SiliconFlow API → LLM Rerank → 原序兜底

- **LangGraph 状态图编排**
  - 意图路由（LLM 语义分类）→ 四分支条件路由
  - study: RAG → 工具执行 → 响应生成
  - plan: 工具执行 → 响应生成
  - review: RAG → 响应生成（已修复 review 无法获取 RAG 上下文的 bug）
  - unknown: 直接 LLM 响应
  - 所有分支汇聚 → 记忆更新 → END

- **FastAPI 后端 + Vue 3 前端**
  - JWT 认证、SSE 流式输出、学习计划 CRUD
  - Ant Design Vue UI、Markdown 渲染、代码高亮

- **RAG 过程实时可视化**
  - 前端 RAGProcessPanel 展示检索管线每一步的状态与结果

- **Docker 一键部署**
  - docker-compose 编排 API + Redis 服务

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Vue 3 前端 (Port 3000)                     │
│       Login / Chat / Plan / RAG 可视化面板                     │
└──────────────────────┬───────────────────────────────────────┘
                       │  HTTP / SSE
┌──────────────────────▼───────────────────────────────────────┐
│                FastAPI 后端 (Port 8000)                        │
│   /api/v1/auth/*   /api/v1/chat/*   /api/v1/plan/*           │
│   JWT 认证 ─── SSE 流式输出 ─── 学习计划 CRUD                  │
└──────────┬───────────────────────────────┬───────────────────┘
           │                               │
┌──────────▼───────────────────┐  ┌────────▼──────────────────┐
│   LangGraph 状态图 Agent      │  │   SQLAlchemy + SQLite     │
│                              │  │   用户 / 计划 / 任务表      │
│  START                       │  └───────────────────────────┘
│    ↓                         │
│  [intent_router] LLM 分类    │  ┌───────────────────────────┐
│    ├─ study  → [rag_node]    │  │   Redis (Port 6379)       │
│    │   → [tool_executor]     │  │   会话缓存 / 限流          │
│    │   → [response_gen]      │  └───────────────────────────┘
│    ├─ plan   → [tool_exec]   │
│    │   → [response_gen]      │
│    ├─ review → [rag_node]    │
│    │   → [response_gen]      │
│    └─ unknown→ [response_gen]│
│    ↓                         │
│  [memory_update] L2/L4 写入  │
│    ↓                         │
│  END                         │
└──────────┬───────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────┐
│                    混合检索 RAG 管线                            │
│  Query重写 → BM25(jieba) + 向量(embedding-3) → RRF融合        │
│  → 评分门控 → 未通过则重写后二次检索 → Reranker 精排            │
└──────────┬───────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────┐
│                    分层记忆存储                                 │
│  L1 会话状态 (JSONL)    L2 任务状态 (SQLite DB + JSON fallback) │
│  L3 知识沉淀 (ChromaDB + BM25 Index)                           │
│  L4 用户画像 (SQLite DB + JSON fallback)                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | ^3.5 | 前端框架 |
| Vite | ^8.0 | 构建工具 |
| TypeScript | ~6.0 | 类型系统 |
| Ant Design Vue | ^4.0 | UI 组件库 |
| Pinia | ^2.1 | 状态管理 |
| Vue Router | ^4.0 | 路由管理 |
| markdown-it | ^14.0 | Markdown 渲染 |
| highlight.js | ^11.0 | 代码高亮 |
| Axios | ^1.7 | HTTP 客户端 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 运行时 |
| FastAPI | ≥0.115.0 | Web 框架 |
| Uvicorn | ≥0.30.0 | ASGI 服务器 |
| Pydantic | ≥2.9.0 | 数据校验 |
| SSE-Starlette | ≥2.0.0 | SSE 流式输出 |
| SQLAlchemy | ≥2.0.0 | ORM |
| Alembic | ≥1.13.0 | 数据库迁移 |
| aiosqlite | ≥0.19.0 | 异步 SQLite |
| python-jose | ≥3.3.0 | JWT 认证 |
| passlib | ≥1.7.4 | 密码哈希 (bcrypt) |
| Redis | ≥5.0.0 | 会话缓存 / 限流 |
| Tenacity | ≥8.2.0 | 重试机制 |

### Agent / LLM
| 技术 | 版本 | 用途 |
|------|------|------|
| LangGraph | ≥0.2.0 | 状态图编排 |
| LangChain | ≥0.3.0 | LLM 工具链 |
| LangChain-Core | ≥0.3.0 | 核心抽象层 |
| LangChain-Community | ≥0.3.0 | 社区集成 |
| 智谱 AI (zhipuai) | ≥2.1.0 | LLM API (GLM-4-Flash) + Embedding-3 |

### RAG / 检索
| 技术 | 版本 | 用途 |
|------|------|------|
| ChromaDB | ≥0.5.0 | 向量数据库（持久化模式） |
| rank-bm25 | ≥0.2.2 | BM25 关键词检索 |
| jieba | ≥0.42.1 | 中文分词 |
| NumPy | ≥1.26.0 | 数值计算 |

### 部署
| 技术 | 版本 | 用途 |
|------|------|------|
| Docker | - | 容器化 |
| docker-compose | 3.8 | 多服务编排 |
| Redis | 7-alpine | 缓存服务 |

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（前端开发）
- Docker & Docker Compose（推荐部署方式）
- 智谱 AI API Key（[申请地址](https://open.bigmodel.cn/)）

### Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url> && cd DEMO

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入：
#   ZHIPU_API_KEY=your_key_here
#   JWT_SECRET_KEY=your_secret_here

# 3. 一键启动（API + Redis）
docker-compose up -d

# 4. 访问服务
#   API 文档：http://localhost:8000/docs
#   健康检查：http://localhost:8000/health
```

### 本地开发

```bash
# ── 后端 ──
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .   # 以可编辑模式安装项目包（消除 sys.path hack）

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 ZHIPU_API_KEY 和 JWT_SECRET_KEY

# 构建知识库索引（首次运行，约需 10-20 分钟）
python -m scripts.index_textbooks
python -m scripts.index_exam_questions
python -m scripts.index_key_points
python -m scripts.build_bm25_index

# （可选）迁移历史 JSON 数据到 SQLite
python -m scripts.migrate_json_to_db

# 启动后端
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# ── 前端 ──
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000
```

---

## 🧪 运行测试

```bash
# 运行全部单元测试（无需网络/数据库）
pytest tests/unit/ -v

# 运行集成测试（需要 ChromaDB 本地实例）
pytest tests/integration/ -v

# 运行端到端测试（需要后端服务已启动）
pytest tests/e2e/ -v

# 查看覆盖率报告
pytest tests/unit/ --cov=memory/rag --cov=agent/tools --cov-report=term-missing
```

**当前测试状态：** 单元测试 96 passed，覆盖 `hybrid_fusion`、`score_gate`、`reranker`、`quiz` 工具、`intent_router` 等核心模块。

---

## 📊 RAG 评估结果

基于 30 条测试用例（数据结构×8、操作系统×8、计算机网络×7、计算机组成原理×7），知识库规模约 2,370 chunks。

### 核心指标

| 指标 | 纯向量检索（baseline） | 混合检索（向量+BM25+RRF） | 提升 |
|------|----------------------|--------------------------|------|
| **Hit@1** | 0.58 | **0.72** | +24.1% |
| **Hit@3** | 0.75 | **0.87** | +16.0% |
| **Hit@5** | 0.80 | **0.92** | +15.0% |
| **MRR** | 0.64 | **0.78** | +21.9% |

### 与同类系统对比

| 系统 | Hit@5 | MRR |
|------|-------|-----|
| 纯向量 baseline | 0.80 | 0.64 |
| **本系统（混合检索）** | **0.92** | **0.78** |
| 同类教育 RAG 系统均值 | ~0.82 | ~0.68 |

### Query 重写效果

在 hard 难度 5 条用例中，3 条通过 expand/decompose 策略重写后从未命中转为命中，验证了 Query 重写对复杂查询的有效性。

> 详细报告见 [`evaluation/eval_report.md`](evaluation/eval_report.md)

---

## 📁 项目结构

```
DEMO/
├── server.py                  # FastAPI 后端入口（唯一生产入口）
├── config.py                  # 配置兼容层（委托给 core/settings.py）
├── pyproject.toml             # 包配置（pip install -e .）
├── requirements.txt           # Python 依赖
├── pytest.ini                 # pytest 配置
├── Dockerfile                 # Docker 镜像构建
├── docker-compose.yml         # 多服务编排
├── .env                       # 环境变量（不提交 git）
│
├── core/                      # 核心基础设施（无业务逻辑）
│   ├── settings.py            # 统一配置入口（get_settings）
│   ├── llm_client.py          # ZhipuAI 防腐层（get_llm_client 单例）
│   └── logging_config.py      # 日志配置
│
├── agent/                     # Agent 编排层
│   ├── main_agent.py          # LangGraphAgent 对外接口
│   ├── runtime.py             # 会话运行时（状态构建/记忆同步）
│   ├── legacy_agent.py        # 旧版 LearningAgent（向后兼容，只读）
│   ├── tools/                 # 工具层
│   │   ├── __init__.py        # 向后兼容入口
│   │   ├── quiz.py            # generate_quiz 工具
│   │   └── registry.py        # 工具注册表（TOOL_REGISTRY）
│   └── graph/                 # LangGraph 状态图
│       ├── graph.py           # 图构建与编译（build_graph）
│       ├── state.py           # AgentState TypedDict
│       └── nodes/             # 图节点
│           ├── intent_router.py    # 意图路由
│           ├── rag_node.py         # RAG 检索节点（study + review）
│           ├── tool_executor.py    # 工具执行节点
│           ├── response_generator.py # 响应生成节点（流式/非流式）
│           ├── memory_update.py    # 记忆更新节点
│           └── _utils.py           # 节点层公共工具函数
│
├── memory/                    # 分层记忆系统
│   ├── l1_session.py          # L1 会话状态（事件日志，append-only）
│   ├── l2_task.py             # L2 任务状态（DB优先 + JSON fallback）
│   ├── l3_knowledge.py        # L3 知识沉淀（LLM 提炼）
│   ├── l4_profile.py          # L4 用户画像（DB优先 + JSON fallback）
│   ├── hooks.py               # 生命周期钩子（on_session_stop）
│   ├── retrieval.py           # 记忆检索与 token 预算控制
│   └── rag/                   # RAG 检索管线
│       ├── retriever_rag.py   # 管线编排入口（_run_pipeline）
│       ├── reranker.py        # Reranker（Jina→SiliconFlow→LLM 降级链）
│       ├── bm25_retriever.py  # BM25 稀疏检索
│       ├── hybrid_fusion.py   # RRF 融合算法（纯函数）
│       ├── query_rewriter.py  # Query 重写器（expand/decompose/HyDE）
│       ├── score_gate.py      # 评分门控（纯函数）
│       ├── indexer.py         # 三级分块 + ChromaDB 入库
│       └── pdf_parser.py      # PDF 解析器
│
├── api/                       # FastAPI 路由层
│   ├── deps.py                # 依赖注入（get_agent / get_db）
│   ├── middleware/
│   │   ├── auth.py            # JWT 认证中间件
│   │   └── cors.py            # CORS 配置
│   └── v1/
│       ├── auth.py            # 认证（注册/登录/JWT）
│       ├── chat.py            # 对话（SSE流式/同步/历史）
│       ├── plan.py            # 学习计划（CRUD）
│       ├── knowledge.py       # 知识库管理
│
├── dao/                       # 数据访问层（SQLAlchemy ORM）
│   ├── database.py            # 引擎/Session/create_tables
│   ├── models.py              # ORM 模型（9张表）
│   └── crud/                  # CRUD 操作
│       ├── task_state.py      # L2 TaskState CRUD
│       ├── profile.py         # L4 UserProfile CRUD
│       ├── session.py         # ChatSession/Message CRUD
│       ├── user.py            # User CRUD
│       └── knowledge.py       # KnowledgeBase CRUD
│
├── tests/                     # 测试套件
│   ├── conftest.py            # pytest fixtures（mock LLM/内存DB/ChromaDB）
│   ├── unit/                  # 单元测试（96 passed）
│   │   ├── test_hybrid_fusion.py
│   │   ├── test_score_gate.py
│   │   ├── test_reranker.py
│   │   ├── test_quiz_tools.py
│   │   ├── test_intent_router.py
│   │   └── test_llm_client.py
│   ├── integration/           # 集成测试
│   │   └── test_rag_pipeline.py
│   └── e2e/                   # 端到端测试
│       ├── test_chat_stream.py
│       ├── test_api.py
│       └── test_validate.py
│
├── scripts/                   # 数据处理与运维脚本
│   ├── migrate_json_to_db.py  # L2/L4 JSON → SQLite 迁移（幂等）
│   ├── index_textbooks.py     # 教材索引构建
│   ├── index_exam_questions.py # 真题索引构建
│   ├── index_key_points.py    # 要点索引构建
│   ├── build_bm25_index.py    # BM25 索引构建
│   ├── show_questions.py      # 题目查看工具
│   ├── review_questions.py    # 复习题目工具
│   └── data/                  # 原始题目数据
│       ├── 2024_questions.txt
│       ├── q2024.txt
│       └── q2025.txt
│
├── evaluation/                # RAG 评估体系
│   ├── eval_retrieval.py      # 评估脚本
│   ├── test_cases.json        # 30条标准测试用例
│   └── eval_report.md         # 评估报告
│
├── frontend/                  # Vue 3 前端
│   └── src/
│       ├── views/             # Chat / Login / Plan / Knowledge
│       ├── components/        # ChatBubble / RAGProcessPanel
│       ├── stores/            # auth / chat (Pinia)
│       └── utils/             # http / sse
│
├── _legacy/                   # 已归档的旧版入口（不参与主运行链）
│   ├── app.py                 # Gradio UI（旧版）
│   └── main.py                # CLI 入口（旧版）
│
├── docs/                      # 设计文档
│   ├── architecture.md        # 系统架构设计
│   ├── refactoring_design.md  # 重构设计文档（Phase 0-8 已完成）
│   ├── week1_upgrade_report.md  # 第一周升级报告
│   ├── week2_upgrade_report.md  # 第二周升级报告
│   └── week3_upgrade_report.md  # 第三周升级报告
│
└── storage/                   # 运行时数据（不提交 git）
    ├── chroma_db/             # ChromaDB 向量库
    ├── bm25_index/            # BM25 稀疏索引
    ├── sessions/              # L1 会话日志
    ├── tasks/                 # L2 JSON 备份（已迁移至 DB）
    ├── user_profile/          # L4 JSON 备份（已迁移至 DB）
    └── studycoach.db          # SQLite 主数据库
```

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [系统架构设计](docs/architecture.md) | 整体架构、模块设计、数据流 |
| [重构设计文档](docs/refactoring_design.md) | Phase 0-8 重构方案（已完成） |
| [第一周升级报告](docs/week1_upgrade_report.md) | L1-L4 记忆系统实现 |
| [第二周升级报告](docs/week2_upgrade_report.md) | RAG 管线与混合检索 |
| [第三周升级报告](docs/week3_upgrade_report.md) | LangGraph 状态图集成 |
| [第四周升级报告](docs/week4_upgrade_report.md) | FastAPI + Vue 3 全栈 |
| [RAG 评估报告](evaluation/eval_report.md) | 检索质量评估与分析 |

---

## 🔧 API 接口

基础路径：`http://localhost:8000/api/v1`

### 认证 (`/auth`)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册新用户，返回 JWT token |
| POST | `/auth/login` | 登录，返回 JWT token |
| GET | `/auth/me` | 获取当前用户信息（需认证） |

### 对话 (`/chat`)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/stream` | 流式对话（SSE），支持 RAG 管线事件推送 |
| POST | `/chat/sync` | 同步对话，返回完整 JSON 响应 |
| GET | `/chat/history` | 获取当前会话历史 |
| DELETE | `/chat/session` | 重置会话（触发记忆保存） |

### 学习计划 (`/plan`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/plan/` | 获取用户所有学习计划 |
| POST | `/plan/` | 创建新计划 |
| GET | `/plan/{plan_id}` | 获取单个计划（含任务列表） |
| DELETE | `/plan/{plan_id}` | 删除计划 |
| POST | `/plan/{plan_id}/tasks` | 新增任务 |
| PATCH | `/plan/{plan_id}/tasks/{task_id}/done` | 标记任务完成 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger UI 文档 |
| GET | `/redoc` | ReDoc 文档 |

---

## 📝 License

MIT