import json
import os

TASK_STATE_PATH = "storage/tasks/task_state.json"

_DEFAULT_TASK_STATE = {
    "main_goal": "",
    "current_phase": "explore",
    "next_action": "",
    "blockers": [],
    "task_corrections": [],
    "subtasks": [],
    "session_count": 0,
}


def load_task_state(user_id: str = "student_001") -> dict:
    """从 SQLite 加载任务状态；DB 不可用时降级到 JSON 文件。"""
    try:
        from dao.database import SessionLocal
        from dao.crud.task_state import load_task_state_dict
        db = SessionLocal()
        try:
            return load_task_state_dict(db, user_id)
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️  DB 读取 task_state 失败，降级到 JSON: {e}")

    # fallback：JSON 文件
    if os.path.exists(TASK_STATE_PATH):
        with open(TASK_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(_DEFAULT_TASK_STATE)


def update_task_state(
    digest: dict,
    task_state: dict,
    user_id: str = "student_001",
) -> dict:
    """根据会话摘要更新任务状态（确定性逻辑，不依赖 LLM）"""
    task_state["session_count"] += 1

    if digest.get("next_recommendation"):
        task_state["next_action"] = digest["next_recommendation"]

    if digest.get("struggled"):
        for item in digest["struggled"]:
            if item not in task_state["blockers"]:
                task_state["blockers"].append(item)

    if digest.get("mastered"):
        task_state["blockers"] = [
            b for b in task_state["blockers"] if b not in digest["mastered"]
        ]

    if digest.get("corrections"):
        task_state["task_corrections"].extend(digest["corrections"])

    save_task_state(task_state, user_id)
    return task_state


def save_task_state(task_state: dict, user_id: str = "student_001") -> None:
    """将任务状态写入 SQLite；DB 不可用时降级到 JSON 文件。"""
    try:
        from dao.database import SessionLocal
        from dao.crud.task_state import save_task_state_dict
        db = SessionLocal()
        try:
            save_task_state_dict(db, user_id, task_state)
            return
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️  DB 写入 task_state 失败，降级到 JSON: {e}")

    # fallback：JSON 文件
    os.makedirs(os.path.dirname(TASK_STATE_PATH), exist_ok=True)
    with open(TASK_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(task_state, f, ensure_ascii=False, indent=2)
