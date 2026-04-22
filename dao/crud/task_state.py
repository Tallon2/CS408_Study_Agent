"""
dao/crud/task_state.py — TaskState CRUD 操作（职责分离）

对应 ORM 模型：dao.models.TaskState
对应业务层：memory.l2_task
"""
from datetime import datetime
from sqlalchemy.orm import Session
from dao.models import TaskState


# ── 基础 CRUD ─────────────────────────────────────────────────────────────────

def get_or_create_task_state(db: Session, user_id: str) -> TaskState:
    """获取用户任务状态，不存在则创建"""
    state = db.query(TaskState).filter(TaskState.user_id == user_id).first()
    if state is None:
        state = TaskState(user_id=user_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def update_task_state(db: Session, user_id: str, **kwargs) -> TaskState:
    """更新任务状态（current_topic, weak_points, corrections, study_count）

    支持的关键字参数:
        current_topic (str): 当前学习主题
        weak_points (list/dict): 薄弱点列表
        corrections (list/dict): 纠正记录
        study_count (int): 累计学习次数
    """
    state = get_or_create_task_state(db, user_id)
    allowed_fields = {"current_topic", "weak_points", "corrections", "study_count"}
    for key, value in kwargs.items():
        if key in allowed_fields:
            setattr(state, key, value)
    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    return state


# ── 业务层兼容接口（dict 格式） ────────────────────────────────────────────────

def load_task_state_dict(db: Session, user_id: str) -> dict:
    """从 DB 加载 TaskState，转换为业务层兼容的 dict 格式。

    字段映射（ORM → dict）：
        weak_points  → blockers
        corrections  → task_corrections
        study_count  → session_count
        current_topic→ next_action（当前话题作为下一步行动提示）
    """
    state = get_or_create_task_state(db, user_id)
    return {
        "main_goal": "",
        "current_phase": "explore",
        "next_action": state.current_topic or "",
        "blockers": list(state.weak_points or []),
        "task_corrections": list(state.corrections or []),
        "subtasks": [],
        "session_count": state.study_count or 0,
    }


def save_task_state_dict(db: Session, user_id: str, task_state: dict) -> None:
    """将业务层 dict 格式的任务状态持久化到 DB。

    字段映射（dict → ORM）：
        next_action      → current_topic
        blockers         → weak_points
        task_corrections → corrections
        session_count    → study_count
    """
    update_task_state(
        db,
        user_id,
        current_topic=task_state.get("next_action", ""),
        weak_points=task_state.get("blockers", []),
        corrections=task_state.get("task_corrections", []),
        study_count=task_state.get("session_count", 0),
    )
