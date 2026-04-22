"""
cors.py — CORS 中间件配置

将 CORS 配置从 server.py 中抽出，支持按环境切换。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# 开发环境：放开所有来源
DEV_ORIGINS = ["*"]

# 生产环境：限制来源
PROD_ORIGINS = [
    "http://localhost:5173",     # Vite dev server
    "http://localhost:3000",     # 前端构建产物
    "http://127.0.0.1:5173",
]


def setup_cors(app: FastAPI, debug: bool = True) -> None:
    """
    为 FastAPI 应用配置 CORS 中间件。
    
    Args:
        app: FastAPI 应用实例
        debug: True 使用开发配置（放开所有来源），False 使用生产配置
    """
    origins = DEV_ORIGINS if debug else PROD_ORIGINS
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
