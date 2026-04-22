"""
deps.py — FastAPI 依赖注入

提供：
- get_db()：数据库 Session 依赖
- get_current_user()：JWT 认证依赖（从 Authorization: Bearer <token> 解析）
- get_agent()：LangGraphAgent 实例依赖（按用户 ID 缓存）
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from dao.database import SessionLocal
from dao.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    """数据库 Session 依赖（自动关闭）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    JWT 认证依赖。
    从 Authorization: Bearer <token> 头中解析用户信息。
    失败时抛出 401。
    """
    from api.v1.auth import verify_token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


# LangGraphAgent 缓存（按用户 ID）
_agent_cache: dict = {}

def get_agent(current_user: User = Depends(get_current_user)):
    """LangGraphAgent 实例依赖（按用户缓存，避免重复初始化）"""
    from agent.main_agent import LangGraphAgent
    uid = str(current_user.id)
    if uid not in _agent_cache:
        _agent_cache[uid] = LangGraphAgent(user_id=uid)
    return _agent_cache[uid]
