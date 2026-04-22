"""
database.py — SQLAlchemy 数据库连接配置

使用 SQLite（开发环境，无需 Docker）。
后续切换 PostgreSQL 只需修改 DATABASE_URL 环境变量。
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 默认使用 SQLite（开发环境）
# 生产环境设置环境变量：DATABASE_URL=postgresql+asyncpg://user:pass@host/db
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./storage/studycoach.db"
)

# SQLite 需要 check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # 设为 True 可看到 SQL 日志
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def create_tables():
    """创建所有表（如果不存在）。
    
    导入全部 ORM 模型确保 Base.metadata 中包含完整的表定义，
    避免遗漏 TaskState / UserProfile 等后期新增模型。
    """
    from dao.models import (  # noqa: F401 — 仅需触发注册，无需使用变量
        User,
        ChatSession,
        ChatMessage,
        StudyPlan,
        StudyTask,
        TaskState,
        UserProfile,
        LearningRecord,
        KnowledgeBase,
        KnowledgeDoc,
    )
    Base.metadata.create_all(bind=engine)
