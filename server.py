"""
server.py — FastAPI 后端主入口

启动方式：
    .venv\\Scripts\\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload

API 文档（启动后访问）：
    http://localhost:8000/docs    Swagger UI
    http://localhost:8000/redoc  ReDoc
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── 路由注册 ──────────────────────────────────────
from api.v1.auth import router as auth_router
from api.v1.chat import router as chat_router
from api.v1.plan import router as plan_router
from api.v1.knowledge import router as knowledge_router
from api.v1.profile import router as profile_router

# ── 应用创建 ──────────────────────────────────────
app = FastAPI(
    title="408 学习 Agent API",
    description="LangGraph 驱动的个人学习助手后端服务",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS 中间件 ────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 开发阶段放开，生产环境限制域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由挂载 ──────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(plan_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")

# ── 启动事件 ──────────────────────────────────────
@app.on_event("startup")
async def startup():
    """启动时初始化数据库表"""
    from dao.database import create_tables
    create_tables()
    print("✅ FastAPI 启动成功，数据库表已就绪")
    print("📖 API 文档：http://localhost:8000/docs")

# ── 健康检查 ──────────────────────────────────────
@app.get("/health", tags=["系统"])
def health_check():
    return {"status": "ok", "version": "2.0.0", "service": "408-study-agent"}

@app.get("/", tags=["系统"])
def root():
    return {
        "message": "408 学习 Agent API",
        "docs": "/docs",
        "version": "2.0.0"
    }
