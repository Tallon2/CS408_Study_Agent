import json
import os
import re
from datetime import datetime
from zhipuai import ZhipuAI
from config import API_KEY, MODEL

SCRIBE_PROMPT = """请根据以下学习对话记录，生成结构化摘要。严格按 JSON 格式输出，不要有任何多余文字：

{
  "summary": "一句话总结本次学习内容",
  "topics_learned": ["涉及的知识点列表"],
  "mastered": ["用户已理解的知识点"],
  "struggled": ["用户卡住或答错的知识点"],
  "corrections": ["本次发现的认知纠偏"],
  "next_recommendation": "建议下次从哪里开始"
}

对话记录：
{conversation}
"""

def _parse_json_safe(text: str) -> dict:
    """安全解析 JSON，处理 LLM 返回带 ```json ... ``` 的情况"""
    text = text.strip()
    # 去掉 markdown 代码块包裹
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)

def on_session_stop(session_manager) -> dict:
    conversation = session_manager.get_messages_text()
    if not conversation.strip():
        return {}

    client = ZhipuAI(api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个精确的学习记录分析师。只输出 JSON，不要多余文字。"},
            {"role": "user", "content": SCRIBE_PROMPT.replace("{conversation}", conversation)}
        ]
    )

    raw = response.choices[0].message.content
    try:
        digest = _parse_json_safe(raw)
    except Exception as e:
        print(f"⚠️  摘要解析失败: {e}\n原始内容: {raw[:200]}")
        return {}

    # 落盘：session_notes.md
    notes_path = os.path.join(session_manager.session_dir, "session_notes.md")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(f"## 会话摘要 {session_manager.session_id}\n\n")
        f.write(f"**总结**：{digest.get('summary', '')}\n\n")
        f.write(f"**涉及知识点**：{', '.join(digest.get('topics_learned', []))}\n\n")
        f.write(f"**已掌握**：{', '.join(digest.get('mastered', []))}\n\n")
        f.write(f"**薄弱点**：{', '.join(digest.get('struggled', []))}\n\n")
        f.write(f"**下次建议**：{digest.get('next_recommendation', '')}\n")

    # 落盘：digest.json
    digest_path = os.path.join(session_manager.session_dir, "digest.json")
    digest["session_id"] = session_manager.session_id
    with open(digest_path, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    # Step 2: 更新任务状态 (L2)
    try:
        from memory.l2_task import load_task_state, update_task_state
        task = load_task_state()
        update_task_state(digest, task)
    except Exception as e:
        print(f"⚠️  L2 任务状态更新失败: {e}")

    # Step 3: 更新用户画像 (L4)
    try:
        from memory.l4_profile import update_profile_from_digest
        update_profile_from_digest(digest, session_manager.session_id)
    except Exception as e:
        print(f"⚠️  L4 用户画像更新失败: {e}")

    # Step 4: 写入向量索引（阶段4实现后生效）
    try:
        from memory.retrieval import MemoryRetriever
        retriever = MemoryRetriever()
        retriever.index_session(session_manager.session_id, digest)
    except Exception:
        pass

    # Step 5: 触发知识提炼 (L3)（每5次会话）
    try:
        from memory.l3_knowledge import maybe_extract_knowledge
        from memory.l2_task import load_task_state
        current_task = load_task_state()
        maybe_extract_knowledge(current_task.get("session_count", 0))
    except Exception as e:
        print(f"⚠️  L3 知识提炼触发失败: {e}")

    session_manager.log_event("session_stop", {"digest": digest})
    return digest


def on_pre_compact(session_manager) -> dict:
    compact = {
        "session_id": session_manager.session_id,
        "topics_touched": session_manager.topics_touched,
        "user_struggles": session_manager.user_struggles,
        "event_count": session_manager.event_counter,
        "saved_at": datetime.now().isoformat()
    }
    compact_path = os.path.join(session_manager.session_dir, "compact_state.json")
    with open(compact_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, indent=2)
    return compact
