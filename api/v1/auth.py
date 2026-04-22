"""
auth.py — 用户认证路由

POST /api/v1/auth/register  注册新用户
POST /api/v1/auth/login     登录，返回 JWT token
GET  /api/v1/auth/me        获取当前用户信息（需认证）
"""

from __future__ import annotations
import os

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from passlib.context import CryptContext

from dao.models import User
from api.deps import get_db, get_current_user

# ── JWT 配置 ──────────────────────────────────────────────────────────────────
# 固定的 fallback 密钥（开发环境），生产环境务必通过环境变量覆盖
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-408-study-agent-change-in-prod")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRE_DAYS = 7

# ── 密码哈希 ──────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    created_at: datetime


# ── JWT 工具函数 ───────────────────────────────────────────────────────────────

def create_token(user_id: str, username: str) -> str:
    """生成 JWT access token，有效期 7 天"""
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT token，返回 payload dict；无效则返回 None"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户，用户名唯一，返回 JWT token"""
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{req.username}' 已存在",
        )

    hashed_pw = pwd_context.hash(req.password)
    new_user = User(
        username=req.username,
        email=req.email,
        hashed_password=hashed_pw,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_token(str(new_user.id), new_user.username)
    return TokenResponse(
        access_token=token,
        user_id=str(new_user.id),
        username=new_user.username,
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录，验证密码，返回 JWT token"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(str(user.id), user.username)
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        username=user.username,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（需要 Bearer token）"""
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at,
    )
