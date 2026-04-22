"""用户画像和学习记录相关 CRUD 操作（TaskState 已迁移至 dao/crud/task_state.py）"""
from datetime import datetime
from sqlalchemy.orm import Session
from dao.models import UserProfile, LearningRecord


# ── UserProfile ───────────────────────────────────────────────────────────────

def get_or_create_profile(db: Session, user_id: str) -> UserProfile:
    """获取用户画像，不存在则创建"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_profile(db: Session, user_id: str, **kwargs) -> UserProfile:
    """更新用户画像

    支持的关键字参数:
        knowledge_graph (dict): 知识图谱
        learning_style (str): 学习风格偏好
        preferred_subjects (list): 偏好科目列表
        total_sessions (int): 总会话数
        last_active_at (datetime): 最后活跃时间
    """
    profile = get_or_create_profile(db, user_id)
    allowed_fields = {
        "knowledge_graph", "learning_style", "preferred_subjects",
        "total_sessions", "last_active_at",
    }
    for key, value in kwargs.items():
        if key in allowed_fields:
            setattr(profile, key, value)
    profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return profile


# ── LearningRecord ────────────────────────────────────────────────────────────

def add_learning_record(
    db: Session,
    user_id: str,
    record_type: str,
    content: str,
    subject: str | None = None,
    source_sessions: list | None = None,
) -> LearningRecord:
    """新增学习记录（pattern / pitfall / insight）"""
    record = LearningRecord(
        user_id=user_id,
        record_type=record_type,
        content=content,
        subject=subject,
        source_sessions=source_sessions,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_learning_records(
    db: Session, user_id: str, record_type: str | None = None
) -> list[LearningRecord]:
    """获取学习记录，可按类型筛选，按创建时间倒序"""
    query = db.query(LearningRecord).filter(LearningRecord.user_id == user_id)
    if record_type is not None:
        query = query.filter(LearningRecord.record_type == record_type)
    return query.order_by(LearningRecord.created_at.desc()).all()
