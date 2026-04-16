import json
import os
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

PROFILE_PATH = "storage/user_profile/profile.json"

def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "stable_preferences": {},
        "knowledge_graph": {},
        "update_count": 0,
        "source_sessions": []
    }

def update_profile_from_digest(digest: dict, session_id: str):
    """每次会话结束都更新知识图谱，每3次触发一次LLM偏好提炼"""
    profile = load_profile()
    profile["update_count"] += 1
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

    save_profile(profile)

def _extract_preferences(profile: dict) -> dict:
    """用 LLM 从累积数据中提炼稳定偏好"""
    import re
    client = ZhipuAI(api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
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

def save_profile(profile: dict):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
