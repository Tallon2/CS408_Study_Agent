"""
models.py — SQLAlchemy ORM 模型定义

表设计：
- User：用户表（JWT 认证）
- ChatSession：会话表（替代 session 目录）
- ChatMessage：消息表（替代 journal.jsonl，保留 append-only 语义）
- StudyPlan：学习计划表
- StudyTask：计划任务表
- TaskState：L2 任务状态（替代 task_state.json）
- UserProfile：L4 用户画像（替代 profile.json）
- LearningRecord：L3 知识沉淀（替代 patterns/pitfalls JSONL）
- KnowledgeBase：知识库
- KnowledgeDoc：知识库文档
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from dao.database import Base


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True, default=_uuid)
    username      = Column(String(50), unique=True, nullable=False, index=True)
    email         = Column(String(120), unique=True, nullable=True)
    hashed_password = Column(String(256), nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # 关联
    sessions         = relationship("ChatSession",   back_populates="user", cascade="all, delete-orphan")
    plans            = relationship("StudyPlan",     back_populates="user", cascade="all, delete-orphan")
    task_states      = relationship("TaskState",     back_populates="user", cascade="all, delete-orphan")
    profile          = relationship("UserProfile",   back_populates="user", uselist=False, cascade="all, delete-orphan")
    learning_records = relationship("LearningRecord", back_populates="user", cascade="all, delete-orphan")
    knowledge_bases  = relationship("KnowledgeBase", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id         = Column(String(36), primary_key=True, default=_uuid)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at   = Column(DateTime, nullable=True)
    summary    = Column(Text, nullable=True)   # L1 会话摘要（hooks 生成）

    # 关联
    user       = relationship("User", back_populates="sessions")
    messages   = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id         = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role       = Column(String(20), nullable=False)   # "user" | "assistant" | "tool"
    content    = Column(Text, nullable=False)
    tool_name  = Column(String(50), nullable=True)    # 如果 role=="tool"
    intent     = Column(String(20), nullable=True)    # 路由到的意图
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    session    = relationship("ChatSession", back_populates="messages")


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id          = Column(String(36), primary_key=True, default=_uuid)
    user_id     = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title       = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    is_active   = Column(Boolean, default=True)

    # 关联
    user        = relationship("User", back_populates="plans")
    tasks       = relationship("StudyTask", back_populates="plan", cascade="all, delete-orphan")


class StudyTask(Base):
    __tablename__ = "study_tasks"

    id          = Column(String(36), primary_key=True, default=_uuid)
    plan_id     = Column(String(36), ForeignKey("study_plans.id"), nullable=False, index=True)
    title       = Column(String(200), nullable=False)
    subject     = Column(String(50), nullable=True)   # 数据结构/操作系统/计网/计组
    is_done     = Column(Boolean, default=False)
    due_date    = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    done_at     = Column(DateTime, nullable=True)

    # 关联
    plan        = relationship("StudyPlan", back_populates="tasks")


class TaskState(Base):
    """L2 任务状态（替代 task_state.json）"""
    __tablename__ = "task_states"

    id            = Column(String(36), primary_key=True, default=_uuid)
    user_id       = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    current_topic = Column(String(100), nullable=True)       # 当前学习主题
    weak_points   = Column(JSON, nullable=True)              # 薄弱点列表
    corrections   = Column(JSON, nullable=True)              # 纠正记录
    study_count   = Column(Integer, default=0)               # 累计学习次数
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # 关联
    user          = relationship("User", back_populates="task_states")


class UserProfile(Base):
    """L4 用户画像（替代 profile.json）"""
    __tablename__ = "user_profiles"

    id                 = Column(String(36), primary_key=True, default=_uuid)
    user_id            = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    knowledge_graph    = Column(JSON, nullable=True)         # 知识图谱（各知识点掌握状态）
    learning_style     = Column(String(50), nullable=True)   # 学习风格偏好
    preferred_subjects = Column(JSON, nullable=True)         # 偏好科目列表
    total_sessions     = Column(Integer, default=0)          # 总会话数
    last_active_at     = Column(DateTime, nullable=True)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at         = Column(DateTime, default=datetime.utcnow)

    # 关联
    user               = relationship("User", back_populates="profile")


class LearningRecord(Base):
    """L3 知识沉淀（替代 patterns/pitfalls JSONL）"""
    __tablename__ = "learning_records"

    id              = Column(String(36), primary_key=True, default=_uuid)
    user_id         = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    record_type     = Column(String(20), nullable=False)     # "pattern" | "pitfall" | "insight"
    subject         = Column(String(50), nullable=True)      # 所属科目
    content         = Column(Text, nullable=False)           # 记录内容（LLM 提炼的学习模式/踩坑记录）
    source_sessions = Column(JSON, nullable=True)            # 来源会话ID列表
    created_at      = Column(DateTime, default=datetime.utcnow)

    # 关联
    user            = relationship("User", back_populates="learning_records")


class KnowledgeBase(Base):
    """知识库"""
    __tablename__ = "knowledge_bases"

    id          = Column(String(36), primary_key=True, default=_uuid)
    user_id     = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name        = Column(String(100), nullable=False)        # 知识库名称
    description = Column(Text, nullable=True)
    doc_count   = Column(Integer, default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    user        = relationship("User", back_populates="knowledge_bases")
    docs        = relationship("KnowledgeDoc", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDoc(Base):
    """知识库文档"""
    __tablename__ = "knowledge_docs"

    id          = Column(String(36), primary_key=True, default=_uuid)
    kb_id       = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    filename    = Column(String(255), nullable=False)        # 原始文件名
    file_type   = Column(String(20), nullable=False)         # "pdf" | "txt" | "md"
    chunk_count = Column(Integer, default=0)                 # 分块数量
    file_size   = Column(Integer, nullable=True)             # 文件大小（bytes）
    status      = Column(String(20), default="indexed")      # "pending" | "indexing" | "indexed" | "failed"
    created_at  = Column(DateTime, default=datetime.utcnow)

    # 关联
    knowledge_base = relationship("KnowledgeBase", back_populates="docs")
