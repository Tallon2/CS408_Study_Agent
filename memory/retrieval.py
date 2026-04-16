from memory.l2_task import load_task_state
from memory.l4_profile import load_profile


def build_memory_context(user_id: str, current_question: str = "") -> str:
    """
    SessionStart Hook：每次新对话启动时，自动构建记忆上下文注入给 LLM。
    阶段3实现 L2 任务状态 + L4 用户画像注入。
    阶段4实现向量语义检索（MemoryRetriever）。
    """
    parts = []

    # L2：任务连续性
    task = load_task_state()
    if task.get("next_action") or task.get("session_count", 0) > 0:
        blockers_str = ", ".join(task.get("blockers", [])) or "无"
        corrections = task.get("task_corrections", [])[-3:]
        corrections_str = "; ".join(corrections) if corrections else "无"
        parts.append(
            f"## 当前任务状态\n"
            f"- 上次建议从这里继续：{task.get('next_action', '无')}\n"
            f"- 累计学习 {task.get('session_count', 0)} 次\n"
            f"- 当前薄弱点：{blockers_str}\n"
            f"- 历史纠偏：{corrections_str}"
        )

    # L4：用户画像
    profile = load_profile()
    kg = profile.get("knowledge_graph", {})
    if kg:
        mastered = [k for k, v in kg.items() if v.get("status") == "mastered"]
        struggling = [k for k, v in kg.items() if v.get("status") == "struggling"]
        introduced = [k for k, v in kg.items() if v.get("status") == "introduced"]
        kg_lines = []
        if mastered:
            kg_lines.append(f"- 已掌握：{', '.join(mastered)}")
        if struggling:
            kg_lines.append(f"- 薄弱点：{', '.join(struggling)}")
        if introduced:
            kg_lines.append(f"- 已接触：{', '.join(introduced)}")
        if kg_lines:
            parts.append("## 用户知识状态\n" + "\n".join(kg_lines))

    prefs = profile.get("stable_preferences", {})
    if prefs:
        parts.append(
            f"## 用户偏好\n"
            f"- 讲解风格：{prefs.get('explanation_style', '未知')}\n"
            f"- 练习偏好：{prefs.get('practice_preference', '未知')}\n"
            f"- 学习节奏：{prefs.get('pace', '未知')}"
        )

    # L3：向量语义检索（阶段4实现）
    if current_question:
        try:
            retriever = MemoryRetriever()
            relevant = retriever.search_relevant(current_question, top_k=3)
            if relevant:
                history_text = "\n".join(f"- {r}" for r in relevant)
                parts.append(f"## 相关历史学习记录\n{history_text}")
        except Exception:
            pass

    if not parts:
        return ""

    return "# 📝 记忆系统注入\n\n" + "\n\n".join(parts)


class MemoryRetriever:
    def __init__(self):
        import chromadb
        self.client = chromadb.PersistentClient(path="storage/vector_db")
        self.collection = self.client.get_or_create_collection(
            name="session_digests",
            metadata={"hnsw:space": "cosine"}
        )

    def index_session(self, session_id: str, digest: dict):
        """会话结束时调用，将摘要写入向量索引"""
        doc_text = (
            f"学习主题: {', '.join(digest.get('topics_learned', []))}. "
            f"掌握: {', '.join(digest.get('mastered', []))}. "
            f"薄弱: {', '.join(digest.get('struggled', []))}. "
            f"总结: {digest.get('summary', '')}"
        )
        self.collection.upsert(
            ids=[session_id],
            documents=[doc_text],
            metadatas=[{
                "session_id": session_id,
                "topics": ",".join(digest.get("topics_learned", []))
            }]
        )

    def search_relevant(self, query: str, top_k: int = 3) -> list:
        """语义检索最相关的历史会话摘要"""
        if self.collection.count() == 0:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count())
        )
        return results.get("documents", [[]])[0]
