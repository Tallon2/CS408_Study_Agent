"""
auth.py — JWT 认证中间件

提供两种认证方式：
1. 依赖注入方式：get_current_user()（已在 deps.py 中实现，推荐用于路由级认证）
2. 中间件方式：JWTAuthMiddleware（用于全局路由保护，排除白名单路径）

使用方式：
    from api.middleware.auth import JWTAuthMiddleware
    app.add_middleware(JWTAuthMiddleware, exclude_paths=["/health", "/docs", ...])
"""
import logging
from typing import List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# 默认不需要认证的路径
DEFAULT_EXCLUDE_PATHS = [
    "/health",
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
]


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    全局 JWT 认证中间件。
    
    对所有请求检查 Authorization 头中的 Bearer Token，
    白名单路径直接放行。
    
    注意：当前项目主要使用 deps.py 的依赖注入模式进行认证，
    此中间件作为可选的全局保护层。
    """
    
    def __init__(self, app, exclude_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or DEFAULT_EXCLUDE_PATHS
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # 白名单路径直接放行
        if any(path.startswith(ep) for ep in self.exclude_paths):
            return await call_next(request)
        
        # OPTIONS 预检请求放行（CORS）
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # 检查 Authorization 头
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "未提供认证令牌"},
            )
        
        token = auth_header.split(" ", 1)[1]
        
        # 验证 token
        try:
            from api.v1.auth import _decode_token
            payload = _decode_token(token)
            # 将用户信息挂载到 request.state
            request.state.user_id = payload.get("sub")
        except Exception as e:
            logger.warning(f"JWT 验证失败: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "认证令牌无效或已过期"},
            )
        
        return await call_next(request)
