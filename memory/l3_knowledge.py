import json
import os
import re
from core.llm_client import get_llm_client

KB_DIR = "storage/knowledge_base"

ALCHEMIST_PROMPT = """你是知识提炼专家。
根据下方多次学习记录，提炼出可复用的"学习模式/踩坑记录"。

每条知识用以下 JSON 格式输出：
{
  "entries": [
    {
      "type": "pattern 或 pitfall",
      "title": "标题",
      "description": "详细描述",
      "tags": ["相关知识点标签"]
    }
  ]
}

学习记录：
{digests}"""


def maybe_extract_knowledge(session_count: int):
    """每 5 次会话触发一次知识提炼"""
    if session_count % 5 != 0 or session_count == 0:
        return

    sessions_dir = "storage/sessions"
    recent_digests = []
    if os.path.exists(sessions_dir):
        dirs = sorted(os.listdir(sessions_dir))[-5:]
        for d in dirs:
            digest_path = os.path.join(sessions_dir, d, "digest.json")
            if os.path.exists(digest_path):
                with open(digest_path, "r", encoding="utf-8") as f:
                    recent_digests.append(json.load(f))

    if len(recent_digests) < 3:
        return

    print(f"🔬 触发知识提炼（第 {session_count} 次会话）...")

    client = get_llm_client()
    resp = client.chat.completions.create(
        model=client.default_model,
        messages=[
            {"role": "system", "content": "只输出 JSON，不要任何多余文字"},
            {"role": "user", "content": ALCHEMIST_PROMPT.replace(
                "{digests}", json.dumps(recent_digests, ensure_ascii=False))}
        ]
    )

    raw = resp.choices[0].message.content.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if match:
        raw = match.group(1).strip()

    try:
        result = json.loads(raw)
    except Exception as e:
        print(f"⚠️  知识提炼解析失败: {e}")
        return

    saved_count = 0
    for entry in result.get("entries", []):
        entry_type = entry.get("type", "pattern")
        if entry_type not in ("pattern", "pitfall"):
            entry_type = "pattern"
        dir_path = os.path.join(KB_DIR, f"{entry_type}s")
        os.makedirs(dir_path, exist_ok=True)

        safe_title = re.sub(r'[^\w\u4e00-\u9fff\-]', '-', entry.get("title", "unknown"))[:50]
        filename = safe_title.lower() + ".md"
        filepath = os.path.join(dir_path, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"type: {entry_type}\n")
            f.write(f'title: "{entry["title"]}"\n')
            f.write(f"tags: {json.dumps(entry.get('tags', []), ensure_ascii=False)}\n")
            f.write(f"---\n\n")
            f.write(f"# {entry['title']}\n\n")
            f.write(f"{entry['description']}\n")
        saved_count += 1

    _rebuild_memory_index()
    print(f"✅ 知识提炼完成，保存了 {saved_count} 条知识条目")


def _rebuild_memory_index():
    """重建 MEMORY.md 索引"""
    index_path = os.path.join(KB_DIR, "MEMORY.md")
    lines = ["# 学习知识库\n"]

    for category in ["patterns", "pitfalls"]:
        cat_dir = os.path.join(KB_DIR, category)
        if os.path.exists(cat_dir):
            md_files = [f for f in os.listdir(cat_dir) if f.endswith(".md")]
            if md_files:
                lines.append(f"\n## {category.title()}\n")
                for fname in sorted(md_files):
                    lines.append(f"- [{fname}]({category}/{fname})")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
