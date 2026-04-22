import json
import os
from datetime import datetime

PROFILE_PATH = "storage/user_profile/profile.json"

_DEFAULT_PROFILE = {
    "stable_preferences": {},
    "knowledge_graph": {},
    "update_count": 0,
    "source_sessions": [],
}


def load_profile(user_id: str = "student_001") -> dict:
    """从 SQLite 加载用户画像；DB 不可用时降级到 JSON 文件。

    字段映射（ORM → dict）：
        knowledge_graph (JSON) → profile["knowledge_graph"]
        learning_style  (str)  → profile["stable_preferences"]（JSON 反序列化）
        total_sessions  (int)  → profile["update_count"]
    """
    try:
        from dao.database import SessionLocal
        from dao.crud.profile import get_or_create_profile
        db = SessionLocal()
        try:
            orm_profile = get_or_create_profile(db, user_id)
            # 反序列化 stable_preferences（存在 learning_style 字段中）
            stable_prefs: dict = {}
            if orm_profile.learning_style:
                try:
                    stable_prefs = json.loads(orm_profile.learning_style)
                except (json.JSONDecodeError, TypeError):
                    stable_prefs = {"explanation_style": orm_profile.learning_style}

            return {
                "stable_preferences": stable_prefs,
                "knowledge_graph": dict(orm_profile.knowledge_graph or {}),
                "update_count": orm_profile.total_sessions or 0,
                "source_sessions": list(orm_profile.preferred_subjects or []),
            }
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️  DB 读取 profile 失败，降级到 JSON: {e}")

    # fallback：JSON 文件
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(_DEFAULT_PROFILE)


def update_profile_from_digest(
    digest: dict,
    session_id: str,
    user_id: str = "student_001",
) -> None:
    """每次会话结束都更新知识图谱，每3次触发一次LLM偏好提炼"""
    profile = load_profile(user_id)
    profile["update_count"] += 1
    if session_id not in profile["source_sessions"]:
        profile["source_sessions"].append(session_id)

    kg = profile["knowledge_graph"]
    for topic in digest.get("mastered", []):
        kg[topic] = {"status": "mastered", "last_session": session_id}
    for topic in digest.get("struggled", []):
        existing = kg.get(topic, {"attempts": 0})
        existing["status"] = "struggling"
        existing["attempts"] = existing.get("attempts", 0) + 1
        existing["last_session"] = session_id
        kg[topic] = existing
    for topic in digest.get("topics_learned", []):
        if topic not in kg:
            kg[topic] = {"status": "introduced", "last_session": session_id}

    if profile["update_count"] % 3 == 0:
        try:
            profile["stable_preferences"] = _extract_preferences(profile)
        except Exception as e:
            print(f"⚠️  偏好提炼失败: {e}")

    save_profile(profile, user_id)


def _extract_preferences(profile: dict) -> dict:
    """用 LLM 从累积数据中提炼稳定偏好"""
    import re
    from core.llm_client import get_llm_client
    client = get_llm_client()
    resp = client.chat.completions.create(
        model=client.default_model,
        messages=[
            {"role": "system", "content": "分析用户的学习模式，只输出 JSON，不要任何多余文字"},
            {"role": "user", "content":
                f"知识图谱: {json.dumps(profile['knowledge_graph'], ensure_ascii=False)}\n"
                f"当前偏好: {json.dumps(profile.get('stable_preferences', {}), ensure_ascii=False)}\n"
                f'请推断学习风格偏好，输出 JSON: {{"explanation_style": "...", "practice_preference": "...", "pace": "..."}}'}
        ]
    )
    text = resp.choices[0].message.content.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def save_profile(profile: dict, user_id: str = "student_001") -> None:
    """将用户画像写入 SQLite；DB 不可用时降级到 JSON 文件。

    字段映射（dict → ORM）：
        profile["knowledge_graph"]    → knowledge_graph
        profile["stable_preferences"] → learning_style（序列化为 JSON 字符串）
        profile["update_count"]       → total_sessions
        profile["source_sessions"]    → preferred_subjects
    """
    try:
        from dao.database import SessionLocal
        from dao.crud.profile import update_profile
        db = SessionLocal()
        try:
            update_profile(
                db,
                user_id,
                knowledge_graph=profile.get("knowledge_graph", {}),
                learning_style=json.dumps(
                    profile.get("stable_preferences", {}), ensure_ascii=False
                ),
                preferred_subjects=profile.get("source_sessions", []),
                total_sessions=profile.get("update_count", 0),
                last_active_at=datetime.utcnow(),
            )
            return
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️  DB 写入 profile 失败，降级到 JSON: {e}")

    # fallback：JSON 文件
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
