"""会话和消息相关 CRUD 操作"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from dao.models import ChatSession, ChatMessage


def create_session(db: Session, user_id: str, summary: str | None = None) -> ChatSession:
    """创建新的聊天会话"""
    session = ChatSession(user_id=user_id, summary=summary)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_user_sessions(db: Session, user_id: str, limit: int = 20) -> list[ChatSession]:
    """获取用户的聊天会话列表，按开始时间倒序排列"""
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.started_at.desc())
        .limit(limit)
        .all()
    )


def get_session(db: Session, session_id: str) -> ChatSession | None:
    """根据会话 ID 获取会话"""
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def end_session(db: Session, session_id: str, summary: str | None = None) -> ChatSession | None:
    """结束会话：设置 ended_at，可选更新摘要"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is None:
        return None
    session.ended_at = datetime.utcnow()
    if summary is not None:
        session.summary = summary
    db.commit()
    db.refresh(session)
    return session


def add_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    tool_name: str | None = None,
    intent: str | None = None,
) -> ChatMessage:
    """向会话中添加一条消息"""
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_name=tool_name,
        intent=intent,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_session_messages(db: Session, session_id: str) -> list[ChatMessage]:
    """获取指定会话的所有消息，按创建时间正序排列"""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
