# 408学习Agent — 第三周 FastAPI 后端服务化升级报告

> **项目**：408考研学习助手 | **阶段**：Week 3 — FastAPI 后端服务化  
> **日期**：2025-04-24 | **验证状态**：✅ API 测试 12/12 全部通过

---

## 0. 验证结果速览

```
✅ GET  /health                     → 200
✅ POST /auth/register              → 201 + JWT
✅ POST /auth/login                 → 200 + JWT
✅ GET  /auth/me（Bearer Token）    → 200 用户信息
✅ GET  /chat/history               → 200 历史列表
✅ POST /auth/register（重复）      → 409 Conflict
✅ POST /auth/login（错误密码）     → 401 Unauthorized
✅ POST /plan/                      → 201 新建计划
✅ GET  /plan/                      → 200 计划列表
✅ POST /plan/{id}/tasks            → 201 新增任务
✅ PATCH /tasks/{id}/done          → 200 标记完成
✅ GET  /chat/history（无token）   → 401 Unauthorized

🎉 第三周全部 12 项 API 测试通过！
```

---

## 1. 升级目标

第二周完成了 LangGraph 状态图编排升级，Agent 具备了声明式多节点路由与流式输出能力。  
第三周的核心目标是**将原本的 Gradio 单体应用拆分为 FastAPI 后端服务 + Gradio 前端双服务架构**，对外暴露标准 REST API，并引入持久化数据库、JWT 认证体系与 SSE 流式对话通道。

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 服务形态 | Gradio 单体（app.py） | FastAPI（port 8000）+ Gradio（port 7860）双服务 |
| 对话接口 | Gradio WebSocket 内部流 | REST SSE `/chat/stream` + 同步 `/chat/sync` |
| 认证机制 | 无认证 | JWT Bearer Token（7天过期） |
| 数据持久化 | 内存 / 临时文件 | SQLAlchemy + SQLite（5张表） |
| 用户隔离 | 无 | 按 user_id 隔离 Agent 实例缓存 |
| 部署方式 | 直接运行脚本 | Docker Compose 三服务编排 |

---

## 2. 系统架构变化

### 2.1 升级前（Gradio 单体架构）

```
┌─────────────────────────────────────────────┐
│                  app.py                     │
│                                             │
│   Browser ──► Gradio UI (port 7860)         │
│                   │                         │
│                   ▼                         │
│         LangGraphAgent.chat_stream()        │
│                   │                         │
│         ┌─────────┴──────────┐              │
│         ▼                    ▼              │
│    ChromaDB / BM25      ZhipuAI LLM         │
│    (内存 RAG 检索)      (GLM-4 API)         │
│                                             │
│   ✗ 无认证  ✗ 无持久化  ✗ 无标准API        │
└─────────────────────────────────────────────┘
```

### 2.2 升级后（FastAPI + Gradio 双服务架构）

```
                        ┌──────────────────┐
  Browser / Client      │   Gradio UI      │
       │                │   port 7860      │
       │                │   app.py         │
       │                └────────┬─────────┘
       │                         │ HTTP / SSE
       ▼                         ▼
┌──────────────────────────────────────────────────────┐
│                  FastAPI  server.py  port 8000        │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  /auth      │  │  /chat       │  │  /plan     │  │
│  │  register   │  │  stream(SSE) │  │  CRUD      │  │
│  │  login      │  │  sync        │  │  tasks     │  │
│  │  me         │  │  history     │  │            │  │
│  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘  │
│         │                │                │         │
│         └────────────────┼────────────────┘         │
│                          │                          │
│              ┌───────────┴────────────┐             │
│              │   api/deps.py          │             │
│              │   get_db               │             │
│              │   get_current_user     │             │
│              │   get_agent            │             │
│              └───────────┬────────────┘             │
│                          │                          │
│         ┌────────────────┼────────────────┐         │
│         ▼                ▼                ▼         │
│   SQLite DB       LangGraphAgent     _agent_cache   │
│   (5张表)         .chat_stream()     {user_id:agent} │
│   dao/models.py   LangGraph stream                  │
└──────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────┐
  │   Redis (可选缓存)  │
  │   docker-compose    │
  └─────────────────────┘
```

---

## 3. API 接口全景

> 所有认证接口均需在 Header 中携带 `Authorization: Bearer <token>`

| # | Method | Path | 功能说明 | 需要认证 |
|---|--------|------|----------|----------|
| 1 | GET | `/health` | 服务健康检查 | ❌ |
| 2 | POST | `/auth/register` | 用户注册，返回 JWT | ❌ |
| 3 | POST | `/auth/login` | 用户登录，返回 JWT | ❌ |
| 4 | GET | `/auth/me` | 获取当前用户信息 | ✅ |
| 5 | GET | `/chat/history` | 获取当前用户对话历史 | ✅ |
| 6 | POST | `/chat/stream` | SSE 流式对话（推荐） | ✅ |
| 7 | POST | `/chat/sync` | 同步对话（一次性返回） | ✅ |
| 8 | DELETE | `/chat/reset` | 清空对话历史 | ✅ |
| 9 | POST | `/plan/` | 创建学习计划 | ✅ |
| 10 | GET | `/plan/` | 获取用户计划列表 | ✅ |
| 11 | GET | `/plan/{plan_id}` | 获取单个计划详情 | ✅ |
| 12 | POST | `/plan/{plan_id}/tasks` | 为计划新增任务 | ✅ |
| 13 | PATCH | `/tasks/{task_id}/done` | 标记任务为已完成 | ✅ |

---

## 4. 核心技术详情

### 4.1 JWT 认证体系

**Token 生成与验证流程：**

```python
# create_token — 签发 JWT
def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=7)  # 7天过期
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

# verify_token — 验证并解码
def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token 已过期")
    except jwt.JWTError:
        raise HTTPException(401, "Token 无效")
```

**关键修复：JWT_SECRET_KEY 固定 fallback**

```python
# ❌ 修复前：每次重启生成新密钥，已签发 token 全部失效
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))

# ✅ 修复后：固定 fallback 值，重启不影响已签发 token
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "408-agent-secret-key-fixed-fallback")
```

**Bearer Token 依赖注入链路：**

```
HTTP Request Header
  Authorization: Bearer eyJhbGci...
          │
          ▼
  oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
          │
          ▼
  get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db))
    │  verify_token(token) → payload → user_id
    │  db.query(User).filter(User.id == user_id).first()
    └─ 返回 User ORM 对象 或 抛出 401
          │
          ▼
  路由函数参数：current_user: User = Depends(get_current_user)
```

---

### 4.2 数据库模型（5张表）

**表关系图（ASCII ER 图）：**

```
┌────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   users    │ 1   N │  chat_sessions   │ 1   N │  chat_messages   │
│────────────│───────│──────────────────│───────│──────────────────│
│ id (PK)    │       │ id (PK)          │       │ id (PK)          │
│ username   │       │ user_id (FK)     │       │ session_id (FK)  │
│ email      │       │ title            │       │ role             │
│ hashed_pwd │       │ created_at       │       │ content          │
│ created_at │       │ updated_at       │       │ created_at       │
└────────────┘       └──────────────────┘       └──────────────────┘
      │
      │ 1
      │
      │ N
┌─────┴──────┐       ┌──────────────────┐
│ study_plans│ 1   N │  study_tasks     │
│────────────│───────│──────────────────│
│ id (PK)    │       │ id (PK)          │
│ user_id(FK)│       │ plan_id (FK)     │
│ title      │       │ title            │
│ subject    │       │ description      │
│ start_date │       │ is_done          │
│ end_date   │       │ due_date         │
│ created_at │       │ created_at       │
└────────────┘       └──────────────────┘
```

**各表关键字段说明：**

| 表名 | 主键 | 外键 | 特殊字段 |
|------|------|------|----------|
| `users` | id | — | hashed_password（bcrypt 4.0.1） |
| `chat_sessions` | id | user_id | title、updated_at |
| `chat_messages` | id | session_id | role（user/assistant）、content |
| `study_plans` | id | user_id | subject、start_date、end_date |
| `study_tasks` | id | plan_id | is_done（Bool）、due_date |

---

### 4.3 SSE 流式对话管线

**实现方式（EventSourceResponse）：**

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, current_user=Depends(get_current_user),
                      agent=Depends(get_agent)):
    async def event_generator():
        yield {"event": "start", "data": json.dumps({"status": "thinking"})}
        try:
            async for chunk in agent.chat_stream(req.message):
                yield {"event": chunk["type"], "data": json.dumps(chunk)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        yield {"event": "done", "data": json.dumps({"status": "finished"})}

    return EventSourceResponse(event_generator())
```

**5 种 SSE 事件类型：**

| 事件类型 | 触发时机 | data 字段示例 |
|----------|----------|---------------|
| `start` | 请求开始，LLM 推理前 | `{"status": "thinking"}` |
| `pipeline` | 节点切换（intent/rag/tool） | `{"stage": "rag", "info": "检索中..."}` |
| `token` | LLM 逐 token 流式输出 | `{"content": "操作系统"}` |
| `done` | 全部节点完成 | `{"status": "finished"}` |
| `error` | 任意节点抛出异常 | `{"message": "LLM timeout"}` |

**LangGraph stream_mode="values" 逐节点事件流：**

```
graph.stream(state, stream_mode="values")
      │
      ├─► intent_router 完成 → pipeline event (stage="intent")
      ├─► rag_node 完成      → pipeline event (stage="rag")
      ├─► tool_executor 完成 → pipeline event (stage="tool")
      ├─► response_generator → token events (逐字符 yield)
      └─► memory_update 完成 → done event
```

---

### 4.4 LangGraphAgent.chat_stream() 升级

**从模拟分句 → 真实 LangGraph stream：**

```python
# ❌ 升级前：模拟流式（将完整回复按句子切割 yield）
async def chat_stream(self, message: str):
    reply = self.chat(message)
    for sentence in reply.split("。"):
        yield sentence + "。"
        await asyncio.sleep(0.05)

# ✅ 升级后：真实 LangGraph stream
async def chat_stream(self, message: str):
    state = self._build_initial_state(message)
    async for event in self.graph.astream(state, stream_mode="values"):
        node_name = list(event.keys())[-1]
        if node_name == "intent_router":
            yield {"type": "pipeline", "stage": "intent",
                   "intent": event[node_name].get("intent")}
        elif node_name == "rag_node":
            yield {"type": "pipeline", "stage": "rag"}
        elif node_name == "tool_executor":
            yield {"type": "pipeline", "stage": "tool",
                   "tool": event[node_name].get("tool_name")}
        elif node_name == "response_generator":
            content = event[node_name].get("final_response", "")
            for char in content:
                yield {"type": "token", "content": char}
```

**3 种 pipeline 事件（节点切换通知）：**

| pipeline.stage | 对应节点 | 前端展示建议 |
|----------------|----------|-------------|
| `intent` | intent_router | 显示"正在理解意图..." |
| `rag` | rag_node | 显示"正在检索知识库..." |
| `tool` | tool_executor | 显示"正在调用工具..." |

**Gradio 兼容层（dict yield → str 提取）：**

```python
# app.py 中的 Gradio 兼容适配
async def gradio_stream_wrapper(message, history):
    response = ""
    async for chunk in agent.chat_stream(message):
        # 新版 chat_stream yield dict，Gradio 需要 str
        if isinstance(chunk, dict):
            if chunk.get("type") == "token":
                response += chunk.get("content", "")
                yield response          # Gradio 需要累积字符串
        elif isinstance(chunk, str):
            response += chunk           # 兼容旧版 str yield
            yield response
```

---

### 4.5 依赖注入设计

**三级依赖链：**

```
FastAPI 路由函数
    │
    ├── db: Session = Depends(get_db)
    │       └─ 每次请求创建 SQLAlchemy Session
    │          请求结束自动 close（yield + finally）
    │
    ├── current_user: User = Depends(get_current_user)
    │       └─ Depends(get_db) → 查询 users 表
    │          Depends(oauth2_scheme) → 解析 Bearer Token
    │          验证失败 → 抛出 HTTPException(401)
    │
    └── agent: LangGraphAgent = Depends(get_agent)
            └─ Depends(get_current_user) → 获取 user_id
               _agent_cache.get(user_id) → 命中则复用
               未命中 → 新建 LangGraphAgent 并缓存
```

**Agent 按用户 ID 缓存（_agent_cache）：**

```python
_agent_cache: dict[int, LangGraphAgent] = {}

def get_agent(current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    if user_id not in _agent_cache:
        _agent_cache[user_id] = LangGraphAgent(user_id=user_id)
    return _agent_cache[user_id]
```

> ⚠️ **线程安全说明**：当前 `_agent_cache` 为进程级全局 dict，  
> FastAPI 默认使用 uvicorn 单进程 + asyncio 事件循环，  
> 异步路由函数不存在真正的多线程竞争，**单进程下是安全的**。  
> 多进程部署（workers > 1）时应改用 Redis 或 DB 存储 Agent 状态。

---

## 5. 文件变更清单（17个文件）

### 新增文件（12个）

| 文件 | 类型 | 说明 |
|------|------|------|
| `server.py` | 主入口 | FastAPI app、CORS 中间件、startup 事件、路由注册 |
| `api/__init__.py` | 包初始化 | — |
| `api/v1/__init__.py` | 包初始化 | — |
| `api/middleware/__init__.py` | 包初始化 | — |
| `api/deps.py` | 依赖注入 | get_db / get_current_user / get_agent 三级依赖 |
| `api/v1/auth.py` | 认证路由 | register / login / me，3 个端点 |
| `api/v1/chat.py` | 对话路由 | stream / sync / history / reset，4 个端点 |
| `api/v1/plan.py` | 计划路由 | CRUD + 任务管理，6 个端点 |
| `dao/__init__.py` | 包初始化 | — |
| `dao/crud/__init__.py` | 包初始化 | — |
| `dao/database.py` | 数据库配置 | SQLAlchemy SQLite 引擎、SessionLocal、create_tables() |
| `dao/models.py` | ORM 模型 | users / chat_sessions / chat_messages / study_plans / study_tasks |

### 修改文件（3个）

| 文件 | 改动要点 |
|------|----------|
| `agent/main_agent.py` | `chat_stream()` 从模拟分句升级为真实 LangGraph `astream()` |
| `app.py` | 新增 Gradio 兼容层，支持 `dict` yield 格式的 chunk 提取 |
| `requirements.txt` | 新增 14 个依赖（fastapi、uvicorn、sqlalchemy、python-jose 等） |

### 新增配置文件（2个）

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | api（port 8000）+ gradio（port 7860）+ redis 三服务编排 |
| `Dockerfile` | python:3.11-slim 基础镜像，分层构建 |

---

## 6. 依赖修复记录

### 6.1 bcrypt 4.x vs passlib 兼容性问题

**问题现象：**

```
AttributeError: module 'bcrypt' has no attribute '__about__'
```

passlib 1.7.x 在初始化时会读取 `bcrypt.__about__.__version__`，  
而 bcrypt 4.0+ 移除了 `__about__` 模块，导致 passlib 无法正常工作。

**修复方案：**

```bash
# 降级 bcrypt 到兼容版本
pip install bcrypt==4.0.1
```

```txt
# requirements.txt 中固定版本
bcrypt==4.0.1        # passlib 1.7.x 兼容上限
passlib[bcrypt]==1.7.4
```

> 长远方案：迁移到 `argon2-cffi` 或等待 passlib 2.0 正式发布。

### 6.2 JWT_SECRET_KEY 随机值问题

**问题现象：**  
服务每次重启后，原有 token 全部失效，用户需要重新登录。

**根本原因：**  
`secrets.token_hex(32)` 在进程启动时生成随机值作为默认密钥，  
重启即换新密钥，导致旧 token 签名验证失败（401）。

**修复方案：**

```python
# api/v1/auth.py
JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY",
    "408-agent-secret-key-fixed-fallback"  # 开发环境固定值
)
```

> 生产环境应通过环境变量 `JWT_SECRET_KEY` 注入真正的随机密钥，  
> 并配合密钥轮转策略（rotate + grace period）实现零中断更新。

---

## 7. 面试问答参考

### Q1：为什么选 FastAPI 而不是 Flask/Django？

**答：** 三点核心理由：

1. **原生异步**：FastAPI 基于 Starlette + asyncio，`async def` 路由函数天然支持并发，配合 LangGraph 的 `astream()` 无需额外线程池，SSE 流式响应无阻塞。Flask 的同步模型需要 `gevent`/`eventlet` 打补丁才能实现类似效果。
2. **类型驱动**：Pydantic v2 模型自动做请求体校验、序列化和 OpenAPI 文档生成，减少大量样板代码。Django REST Framework 需要单独的 Serializer 层。
3. **轻量适合 AI 服务**：Django 自带 ORM、Admin、模板引擎，对于纯 API 服务是过重的。FastAPI 核心极简，按需集成 SQLAlchemy/Alembic。

---

### Q2：JWT 的 verify_token 失效了怎么排查？

**答：** 按以下顺序逐步排查：

1. **检查 secret key 是否一致**：最常见原因，尤其多进程部署时各进程密钥不同。打印 `JWT_SECRET_KEY[:8]` 确认两端一致。
2. **检查过期时间**：`jwt.decode` 返回 payload，打印 `payload["exp"]` 与 `datetime.utcnow()` 比较，确认是否真的过期。
3. **检查 algorithm 匹配**：encode 用 `HS256`，decode 也必须指定 `algorithms=["HS256"]`，不能留空。
4. **检查 token 格式**：Bearer Token 前端传值时去掉 `"Bearer "` 前缀再传给 `jwt.decode`，确认无多余空格。
5. **检查时钟漂移**：服务器时间不同步可能导致刚签发的 token 已"过期"，用 `leeway=timedelta(seconds=10)` 容忍小幅漂移。

---

### Q3：SSE 和 WebSocket 有什么区别，你为什么选 SSE？

**答：**

| 维度 | SSE | WebSocket |
|------|-----|-----------|
| 方向 | 服务端 → 客户端（单向） | 双向全双工 |
| 协议 | HTTP/1.1（text/event-stream） | WS 协议升级 |
| 断线重连 | 浏览器原生自动重连 | 需手动实现 |
| 负载均衡 | 普通 HTTP，天然兼容 | Sticky Session 或 WS-aware LB |
| 适合场景 | 推送通知、流式文本输出 | 实时双向交互（游戏、协作） |

**选 SSE 的理由**：AI 对话是典型的"用户发一条消息 → 服务端持续推送 token"的单向流场景，SSE 完全满足需求，且实现比 WebSocket 简单（无需握手状态管理），`EventSourceResponse` 十行代码搞定，维护成本低。

---

### Q4：get_agent 依赖里的 _agent_cache 线程安全吗？

**答：** **单进程 uvicorn 下是安全的**，理由如下：

FastAPI 路由默认运行在 asyncio 事件循环中，Python GIL + asyncio 单线程模型保证同一时刻只有一个协程在执行 Python 字节码。`_agent_cache[user_id] = agent` 是原子操作，不会出现 race condition。

**不安全的场景**：
- `uvicorn --workers 4`：多进程，每个进程有独立的 `_agent_cache`，同一用户可能命中不同进程的不同 Agent 实例，导致记忆不共享。
- 在路由中使用 `loop.run_in_executor` 将同步代码放入线程池，线程可能并发访问 dict。

**生产环境方案**：将 Agent 的关键状态（L2/L4 记忆）序列化存入 Redis，`get_agent` 每次从 Redis 恢复状态，实现无状态横向扩展。

---

### Q5：数据库用 SQLite，生产环境怎么迁移到 PostgreSQL？

**答：** 迁移只需三步，代码改动极小：

**Step 1：修改 DATABASE_URL**
```python
# dao/database.py
# SQLite（开发）
DATABASE_URL = "sqlite:///./408agent.db"

# PostgreSQL（生产）
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/408agent"
)
```

**Step 2：安装驱动并移除 SQLite 专属参数**
```python
# SQLite 需要 check_same_thread=False，PostgreSQL 不需要
# 开发
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# 生产
engine = create_engine(DATABASE_URL)  # 移除 connect_args
```

**Step 3：引入 Alembic 做迁移管理**
```bash
alembic init alembic
alembic revision --autogenerate -m "init"
alembic upgrade head
```

> SQLAlchemy ORM 层的模型定义（`dao/models.py`）完全不需要修改，  
> 这正是选择 ORM 而非裸 SQL 的核心价值：数据库无关性。

---

## 8. 三周总体成果汇总

```
╔══════════════════════════════════════════════════════════════════════════════╗
║              408考研学习Agent — 三周完整架构全景图                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │  Week 3 : FastAPI 服务层  (port 8000)                               │    ║
║  │                                                                     │    ║
║  │   /auth  ──── JWT Bearer Token ──── bcrypt 密码哈希                 │    ║
║  │   /chat  ──── SSE EventSource  ──── 5种事件类型                     │    ║
║  │   /plan  ──── SQLAlchemy CRUD  ──── study_plans / study_tasks       │    ║
║  │                                                                     │    ║
║  │   SQLite DB (5张表)   Docker Compose (api+gradio+redis)             │    ║
║  └─────────────────────────┬───────────────────────────────────────────┘    ║
║                            │  Depends(get_agent)                            ║
║  ┌─────────────────────────▼───────────────────────────────────────────┐    ║
║  │  Week 2 : LangGraph 编排层                                          │    ║
║  │                                                                     │    ║
║  │   AgentState (TypedDict + add_messages Reducer)                     │    ║
║  │                                                                     │    ║
║  │   START                                                             │    ║
║  │     │                                                               │    ║
║  │   [intent_router] ── 语义分类 + 关键词映射                          │    ║
║  │     │                                                               │    ║
║  │     ├─ study  ──► [rag_node] ──► [tool_executor]                   │    ║
║  │     ├─ plan   ──► [tool_executor]                                  │    ║
║  │     ├─ review ──► [rag_node] ──► [response_generator]              │    ║
║  │     └─ unknown──► [response_generator]                             │    ║
║  │                        │                                           │    ║
║  │                   [memory_update] ──► END                          │    ║
║  │                                                                     │    ║
║  │   astream(stream_mode="values") → token/pipeline events            │    ║
║  └─────────────────────────┬───────────────────────────────────────────┘    ║
║                            │  rag_node / tool_executor                      ║
║  ┌─────────────────────────▼───────────────────────────────────────────┐    ║
║  │  Week 1 : RAG + 记忆层                                              │    ║
║  │                                                                     │    ║
║  │   ┌──────────────────────┐    ┌─────────────────────────────────┐  │    ║
║  │   │  混合检索引擎        │    │  L1–L4 四层记忆系统             │  │    ║
║  │   │                      │    │                                 │  │    ║
║  │   │  ChromaDB 向量检索   │    │  L1: 事件流（session日志）      │  │    ║
║  │   │  + BM25 关键词检索   │    │  L2: 任务状态（学习计划）       │  │    ║
║  │   │  → RRF 融合排序      │    │  L3: 对话摘要（跨会话压缩）     │  │    ║
║  │   │  → Reranker 精排     │    │  L4: 用户画像（知识图谱）       │  │    ║
║  │   └──────────────────────┘    └─────────────────────────────────┘  │    ║
║  │                                                                     │    ║
║  │   ZhipuAI GLM-4 API   embedding-3 向量模型   408知识库             │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 9. 快速启动指南

```bash
# 方式1：直接启动 FastAPI 后端
.venv\Scripts\python.exe -m uvicorn server:app --reload --port 8000

# 方式2：启动 Gradio 前端
.venv\Scripts\python.exe app.py

# 方式3：Docker Compose 一键启动全服务
docker-compose up --build

# API 交互式文档（Swagger UI）
http://localhost:8000/docs

# API 备用文档（ReDoc）
http://localhost:8000/redoc

# 健康检查
curl http://localhost:8000/health

# 注册用户（示例）
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"test\",\"password\":\"123456\",\"email\":\"test@408.ai\"}"

# 流式对话（示例，需替换 <token>）
curl -N http://localhost:8000/chat/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"解释一下操作系统的页面置换算法\"}"
```

---

## 10. 第四周计划（Vue 3 前端 + RAG 可视化）

| 模块 | 计划内容 | 技术选型 |
|------|----------|----------|
| **Vue 3 前端** | 替换 Gradio，构建自定义聊天界面 | Vue 3 + Vite + TypeScript |
| **SSE 对话组件** | 接入 `/chat/stream`，实现打字机效果 | EventSource API + Pinia |
| **RAG 可视化** | 展示检索到的知识块来源与相关度分数 | ECharts / D3.js |
| **学习计划看板** | 可视化任务完成进度，甘特图展示 | vue-ganttastic |
| **记忆面板** | L2/L4 记忆内容实时展示 | Vuetify / Element Plus |
| **用户认证页** | 登录/注册表单，token 本地持久化 | localStorage + axios 拦截器 |
| **部署优化** | Nginx 反向代理，前后端统一端口 | Nginx + docker-compose v2 |

> **预期产出**：完整的 Web 应用，可作为面试 Demo 直接展示，  
> 包含 RAG 检索过程可视化、流式对话动画、学习计划管理三大核心功能。

---

*408学习Agent Week 3 升级报告 | 面向 Agent 开发工程师面试 | 持续更新中*
