"""
indexer.py — 文档切片与 ChromaDB 向量入库模块

职责：
1. 提供统一的 ChromaDB 客户端（持久化）
2. 文本滑动窗口切片
3. PDF 教材入库（textbooks collection）
4. Markdown 笔记入库（key_points collection）
5. JSONL 真题入库（exam_questions collection）

依赖：
    pip install chromadb pymupdf
"""

import os
import re
import json
import hashlib

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings

# 引入同目录下的 PDF 解析模块
from memory.rag.pdf_parser import parse_pdf

# ============================================================
# ChromaDB 持久化路径与集合名称常量
# ============================================================
CHROMA_PATH = "storage/chroma_db"

COLLECTION_TEXTBOOKS = "textbooks"        # 教材内容
COLLECTION_EXAM = "exam_questions"        # 历年真题
COLLECTION_KEYPOINTS = "key_points"       # Markdown 章节笔记（高频考点）


# ============================================================
# 智谱 embedding-3 向量化函数（供 ChromaDB 使用）
# ============================================================
class ZhipuEmbeddingFunction(EmbeddingFunction):
    """
    使用智谱 AI embedding-3 模型将文本转换为向量。
    ChromaDB 支持自定义 EmbeddingFunction，
    入库和检索都会自动调用此函数，确保向量空间一致。
    """
    def __init__(self):
        from core.llm_client import get_llm_client
        self._client = get_llm_client()

    def __call__(self, input: Documents) -> Embeddings:
        """
        批量将文本列表转换为向量列表。
        ChromaDB 会在 upsert 和 query 时自动调用。
        """
        embeddings = []
        # 智谱 API 支持批量，每次最多处理若干条
        # 为稳定性，逐条调用（数量不大时可接受）
        for text in input:
            # 截断超长文本（embedding-3 最大 512 token）
            text = text[:1500] if len(text) > 1500 else text
            resp = self._client.embeddings.create(
                model="embedding-3",
                input=text
            )
            embeddings.append(resp.data[0].embedding)
        return embeddings


# ============================================================
# ChromaDB 客户端与集合（单例，绑定智谱 Embedding）
# ============================================================
_chroma_client = None
_embedding_fn = None


def _get_embedding_fn() -> ZhipuEmbeddingFunction:
    """获取 Embedding 函数单例"""
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = ZhipuEmbeddingFunction()
    return _embedding_fn


def get_chroma_client() -> chromadb.PersistentClient:
    """
    获取 ChromaDB 持久化客户端（懒加载单例）。

    数据保存在 storage/chroma_db 目录下，
    程序重启后数据不丢失。

    Returns:
        chromadb.PersistentClient 实例
    """
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        print(f"[ChromaDB] 初始化持久化客户端，路径：{CHROMA_PATH}")
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def _get_collection(name: str):
    """
    获取或创建绑定了智谱 Embedding 的 ChromaDB 集合。
    所有集合统一使用 ZhipuEmbeddingFunction，确保入库和检索向量空间一致。
    """
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        embedding_function=_get_embedding_fn()
    )


# ============================================================
# 文本切片：滑动窗口算法
# ============================================================
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    对长文本进行滑动窗口切片，使相邻片段有重叠，避免上下文断裂。

    Args:
        text       : 待切片的原始文本
        chunk_size : 每个片段的最大字符数（默认 800）
        overlap    : 相邻片段的重叠字符数（默认 100）

    Returns:
        list[str]，每个元素为一个文本片段

    示例：
        文本长度 2000，chunk_size=800，overlap=100
        → 片段1: [0, 800]，片段2: [700, 1500]，片段3: [1400, 2000]
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:  # 跳过空片段
            chunks.append(chunk)
        # 步进 = chunk_size - overlap，保证重叠
        step = chunk_size - overlap
        if step <= 0:
            step = chunk_size  # 防止无限循环
        start += step

    return chunks


# ============================================================
# 三级滑动窗口分块（Hierarchical Chunking）
# ============================================================
def chunk_text_hierarchical(text: str) -> dict[str, list[str]]:
    """
    三级滑动窗口分块。

    三级设计：
    - L1（父块）：2000字符，200重叠 — 用于最终返回给 LLM，保证上下文完整
    - L2（子块）：600字符，80重叠  — 用于向量检索，粒度适中
    - L3（句子块）：150字符，20重叠 — 用于精确匹配，细粒度

    每个子块/句子块的列表中仅保存文本本身，
    调用方可通过索引位置反推其所属父块（parent_index）。

    Args:
        text: 待切片的原始文本

    Returns:
        dict，键为 "l1" / "l2" / "l3"，值为对应级别的文本片段列表。
        示例：{"l1": ["..."], "l2": ["...", "..."], "l3": ["...", ...]}
    """
    if not text or not text.strip():
        return {"l1": [], "l2": [], "l3": []}

    # L1 父块：2000字符，200重叠
    l1_chunks = chunk_text(text, chunk_size=2000, overlap=200)
    # L2 子块：600字符，80重叠
    l2_chunks = chunk_text(text, chunk_size=600, overlap=80)
    # L3 句子块：150字符，20重叠
    l3_chunks = chunk_text(text, chunk_size=150, overlap=20)

    return {"l1": l1_chunks, "l2": l2_chunks, "l3": l3_chunks}


def chunk_text_with_parent(
    text: str,
    child_size: int = 600,
    child_overlap: int = 80,
    parent_size: int = 2000,
    parent_overlap: int = 200
) -> list[dict]:
    """
    带父块索引的分块函数（Auto-merging 核心）。

    先按 parent_size 切出父块列表，再按 child_size 切出子块列表，
    然后将每个子块映射到其文本内容覆盖范围最大的父块，
    记录 parent_index 供检索后 Auto-merging 使用。

    Args:
        text          : 待切片的原始文本
        child_size    : 子块字符数（默认 600）
        child_overlap : 子块重叠字符数（默认 80）
        parent_size   : 父块字符数（默认 2000）
        parent_overlap: 父块重叠字符数（默认 200）

    Returns:
        list[dict]，每个元素包含：
        {
            "text"         : str,   # 子块文本（用于向量检索）
            "parent_text"  : str,   # 父块文本（命中时返回给 LLM）
            "parent_index" : int,   # 父块在父块列表中的索引
            "child_index"  : int,   # 子块在全局子块列表中的索引
            "level"        : "child"
        }
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # ---- 生成父块（含起始偏移量，用于子块归属判断）----
    parent_step = max(parent_size - parent_overlap, 1)
    parent_chunks: list[dict] = []
    pos = 0
    text_len = len(text)
    while pos < text_len:
        end = min(pos + parent_size, text_len)
        chunk_str = text[pos:end].strip()
        if chunk_str:
            parent_chunks.append({
                "text": chunk_str,
                "start": pos,
                "end": end
            })
        pos += parent_step

    if not parent_chunks:
        return []

    # ---- 生成子块（含起始偏移量，用于父块归属）----
    child_step = max(child_size - child_overlap, 1)
    result: list[dict] = []
    pos = 0
    child_global_idx = 0

    while pos < text_len:
        end = min(pos + child_size, text_len)
        child_str = text[pos:end].strip()

        if child_str:
            # 子块中心点，用于定位最近父块
            child_center = (pos + end) // 2

            # 找到覆盖子块中心的父块（取最后一个满足 start <= center 的父块）
            best_parent_idx = 0
            for pi, p in enumerate(parent_chunks):
                if p["start"] <= child_center:
                    best_parent_idx = pi
                else:
                    break

            parent_info = parent_chunks[best_parent_idx]

            result.append({
                "text": child_str,
                "parent_text": parent_info["text"],
                "parent_index": best_parent_idx,
                "child_index": child_global_idx,
                "level": "child"
            })
            child_global_idx += 1

        pos += child_step

    return result


# ============================================================
# 工具函数：生成安全的文档 ID
# ============================================================
def _make_safe_id(raw_id: str) -> str:
    """
    将任意字符串转换为 ChromaDB 兼容的文档 ID。
    ChromaDB 要求 ID 不超过 512 字节，且不含特殊字符。
    超长时用 MD5 截断处理。
    """
    # 替换常见特殊字符
    safe = re.sub(r'[^\w\-_.]', '_', raw_id)
    # 超过 200 字符时，用哈希保证唯一性
    if len(safe) > 200:
        hash_suffix = hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:8]
        safe = safe[:190] + "_" + hash_suffix
    return safe


# ============================================================
# PDF 教材入库
# ============================================================
def index_pdf(
    pdf_path: str,
    subject: str,
    collection_name: str = COLLECTION_TEXTBOOKS,
    use_hierarchical: bool = True
) -> None:
    """
    将一本 PDF 教材解析、切片后批量写入 ChromaDB。

    流程：
        1. 调用 parse_pdf() 逐页提取文本
        2. 对每页文本调用分块函数切片
           - use_hierarchical=True（默认）：使用 chunk_text_with_parent()
             生成带父块索引的子块，metadata 中记录分层信息
           - use_hierarchical=False：沿用原 chunk_text() 单级分块
        3. 每个片段生成唯一 ID 并附上 metadata
        4. 批量 upsert 到 ChromaDB collection

    Args:
        pdf_path          : PDF 文件路径
        subject           : 科目名称，如 "数据结构"、"操作系统"
        collection_name   : 目标 collection，默认 "textbooks"
        use_hierarchical  : 是否启用三级分块（默认 True）

    Metadata 字段（use_hierarchical=True）：
        - subject      : 科目
        - source       : PDF 文件名
        - page         : 来源页码
        - chunk_index  : 子块在本页中的切片序号（从0开始）
        - parent_index : 父块索引（Auto-merging 用）
        - child_index  : 子块在全局子块列表中的索引
        - parent_text  : 父块文本前500字符（避免 ChromaDB metadata 超限）
        - chunk_level  : "child"（标记分块级别）

    Metadata 字段（use_hierarchical=False，兼容旧格式）：
        - subject     : 科目
        - source      : PDF 文件名
        - page        : 来源页码
        - chunk_index : 该页内的切片序号（从0开始）
    """
    collection = _get_collection(collection_name)

    print(f"\n[入库] 开始处理教材：{pdf_path}")
    mode_tag = "三级分层分块" if use_hierarchical else "单级分块"
    print(f"  科目：{subject}，目标集合：{collection_name}，分块模式：{mode_tag}")

    # 第1步：解析 PDF
    pages = parse_pdf(pdf_path)
    source_name = os.path.basename(pdf_path)

    # 统计变量
    total_chunks = 0
    batch_ids = []
    batch_docs = []
    batch_metas = []
    BATCH_SIZE = 100  # 每批最多 100 条，避免内存溢出

    # 第2步：逐页切片
    for page_data in pages:
        page_num = page_data["page"]
        page_text = page_data["text"]

        if use_hierarchical:
            # ---- 三级分层分块：使用 chunk_text_with_parent ----
            child_chunks = chunk_text_with_parent(page_text)

            for chunk_idx, item in enumerate(child_chunks):
                # 生成唯一 ID：文件名_页码_切片序号
                raw_id = f"{source_name}_{page_num}_{chunk_idx}"
                doc_id = _make_safe_id(raw_id)

                # parent_text 截断至500字符，防止 ChromaDB metadata 超限
                parent_text_short = item["parent_text"][:500] if item["parent_text"] else ""

                batch_ids.append(doc_id)
                batch_docs.append(item["text"])
                batch_metas.append({
                    "subject": subject,
                    "source": source_name,
                    "page": page_num,
                    "chunk_index": chunk_idx,
                    "parent_index": item["parent_index"],
                    "child_index": item["child_index"],
                    "parent_text": parent_text_short,
                    "chunk_level": "child"
                })
                total_chunks += 1

                # 达到批量大小时写入
                if len(batch_ids) >= BATCH_SIZE:
                    collection.upsert(
                        ids=batch_ids,
                        documents=batch_docs,
                        metadatas=batch_metas
                    )
                    print(f"  [入库] 已写入 {total_chunks} 个片段...")
                    batch_ids, batch_docs, batch_metas = [], [], []

        else:
            # ---- 兼容模式：原单级 chunk_text 分块 ----
            chunks = chunk_text(page_text)

            for chunk_idx, chunk in enumerate(chunks):
                # 生成唯一 ID：文件名_页码_切片序号
                raw_id = f"{source_name}_{page_num}_{chunk_idx}"
                doc_id = _make_safe_id(raw_id)

                batch_ids.append(doc_id)
                batch_docs.append(chunk)
                batch_metas.append({
                    "subject": subject,
                    "source": source_name,
                    "page": page_num,
                    "chunk_index": chunk_idx
                })
                total_chunks += 1

                # 达到批量大小时写入
                if len(batch_ids) >= BATCH_SIZE:
                    collection.upsert(
                        ids=batch_ids,
                        documents=batch_docs,
                        metadatas=batch_metas
                    )
                    print(f"  [入库] 已写入 {total_chunks} 个片段...")
                    batch_ids, batch_docs, batch_metas = [], [], []

    # 写入剩余片段
    if batch_ids:
        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas
        )

    print(f"  [入库] ✅ 完成！共写入 {total_chunks} 个片段 → 集合 [{collection_name}]")


# ============================================================
# Markdown 笔记入库
# ============================================================
def index_markdown(
    md_path: str,
    subject: str,
    collection_name: str = COLLECTION_KEYPOINTS
) -> None:
    """
    将 Markdown 笔记按 ## 二级标题切割后写入 ChromaDB。

    每个二级标题（##）下的内容作为一个独立片段，
    保留标题本身以便检索时提供上下文。

    Args:
        md_path         : Markdown 文件路径
        subject         : 科目名称
        collection_name : 目标 collection，默认 "key_points"

    Metadata 字段：
        - subject : 科目
        - source  : 文件名
        - section : 该片段对应的标题内容
    """
    if not os.path.exists(md_path):
        print(f"  [警告] Markdown 文件不存在：{md_path}")
        return

    source_name = os.path.basename(md_path)
    print(f"\n[入库] 处理笔记：{source_name}（科目：{subject}）")

    # 读取文件内容
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 ## 标题切割（保留标题行）
    # 使用正则匹配：## 开头的行作为分隔点
    sections = re.split(r'\n(?=##\s)', content)

    collection = _get_collection(collection_name)

    batch_ids = []
    batch_docs = []
    batch_metas = []
    total_sections = 0

    for section_idx, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # 提取该 section 的标题（第一行）
        lines = section.split("\n", 1)
        section_title = lines[0].strip()  # 例如 "## 1.1 操作系统的概念"

        # 如果内容太长，进一步切片处理
        sub_chunks = chunk_text(section, chunk_size=800, overlap=100)

        for sub_idx, chunk in enumerate(sub_chunks):
            # ID：文件名_章节序号_子切片序号
            raw_id = f"{source_name}_{section_idx}_{sub_idx}"
            doc_id = _make_safe_id(raw_id)

            batch_ids.append(doc_id)
            batch_docs.append(chunk)
            batch_metas.append({
                "subject": subject,
                "source": source_name,
                "section": section_title
            })
            total_sections += 1

    # 一次性写入（笔记文件一般不大）
    if batch_ids:
        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas
        )

    print(f"  [入库] ✅ 完成！写入 {total_sections} 个片段 → 集合 [{collection_name}]")


# ============================================================
# JSONL 真题入库
# ============================================================
def index_exam_jsonl(
    jsonl_path: str,
    collection_name: str = COLLECTION_EXAM
) -> None:
    """
    读取 JSONL 格式的历年真题并写入 ChromaDB。

    JSONL 格式：每行一个 JSON 对象，字段如下：
        {
            "year": 2023,
            "number": 15,
            "subject": "数据结构",
            "chapter": "第三章 栈和队列",
            "topic": "栈的基本操作",
            "type": "单选题",
            "difficulty": "medium",
            "question": "题目内容...",
            "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
            "answer": "A",
            "explanation": "解析内容..."
        }

    写入文档格式：
        [{year}年第{number}题-{subject}-{chapter}]
        题目：{question}
        选项：A. xxx  B. xxx  C. xxx  D. xxx
        答案：{answer}
        解析：{explanation}

    Args:
        jsonl_path      : JSONL 文件路径
        collection_name : 目标 collection，默认 "exam_questions"

    Metadata 字段：
        - year       : 年份
        - subject    : 科目
        - chapter    : 章节
        - topic      : 考点
        - type       : 题型
        - difficulty : 难度
    """
    if not os.path.exists(jsonl_path):
        print(f"  [错误] 真题文件不存在：{jsonl_path}")
        return

    collection = _get_collection(collection_name)

    print(f"\n[入库] 处理真题文件：{jsonl_path}")

    batch_ids = []
    batch_docs = []
    batch_metas = []
    total = 0
    skipped = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [警告] 第 {line_num} 行 JSON 解析失败，跳过：{e}")
                skipped += 1
                continue

            # 提取字段（带默认值防止 KeyError）
            year = item.get("year", "未知")
            number = item.get("number", line_num)
            subject = item.get("subject", "未知科目")
            chapter = item.get("chapter", "未知章节")
            topic = item.get("topic", "")
            q_type = item.get("type", "未知题型")
            difficulty = item.get("difficulty", "medium")
            question = item.get("question", "")
            options = item.get("options", {})
            answer = item.get("answer", "")
            explanation = item.get("explanation", "")

            # 格式化选项字符串（如 "A. xxx  B. xxx  C. xxx  D. xxx"）
            if isinstance(options, dict):
                options_str = "  ".join(
                    f"{k}. {v}" for k, v in sorted(options.items())
                )
            elif isinstance(options, list):
                # 兼容 list 格式：["A. xxx", "B. xxx", ...]
                options_str = "  ".join(options)
            else:
                options_str = str(options)

            # 拼接文档文本
            doc_text = (
                f"[{year}年第{number}题-{subject}-{chapter}]\n"
                f"题目：{question}\n"
                f"选项：{options_str}\n"
                f"答案：{answer}\n"
                f"解析：{explanation}"
            )

            # 生成唯一 ID：年份_题号_行号（行号保证全局唯一，防止同年重复题号）
            raw_id = f"exam_{year}_{number}_{line_num}"
            doc_id = _make_safe_id(raw_id)

            batch_ids.append(doc_id)
            batch_docs.append(doc_text)
            batch_metas.append({
                "year": str(year),        # ChromaDB metadata 值要求为字符串或数字
                "subject": subject,
                "chapter": chapter,
                "topic": topic,
                "type": q_type,
                "difficulty": difficulty
            })
            total += 1

            # 每 100 条写入一次
            if len(batch_ids) >= 100:
                collection.upsert(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_metas
                )
                print(f"  [入库] 已写入 {total} 道题...")
                batch_ids, batch_docs, batch_metas = [], [], []

    # 写入剩余
    if batch_ids:
        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas
        )

    print(f"  [入库] ✅ 完成！写入 {total} 道题（跳过 {skipped} 条）→ 集合 [{collection_name}]")


# ============================================================
# Auto-merging：子块命中后替换为父块，供 LLM 使用
# ============================================================
def auto_merge_context(retrieved_items: list[dict]) -> list[dict]:
    """
    Auto-merging：将命中的子块替换为其父块文本，用于最终提供给 LLM 的上下文。

    检索阶段通常返回粒度较细的子块（600字符），直接传给 LLM 时上下文可能不完整。
    本函数将命中子块替换为其对应的父块文本（2000字符），并按 parent_index 去重，
    确保同一父块只出现一次，避免 LLM 收到重复上下文。

    Args:
        retrieved_items: 检索返回的列表，每个元素为 dict，
                         通常包含以下字段（ChromaDB query 返回格式）：
                         {
                             "id"       : str,   # 文档 ID
                             "document" : str,   # 检索到的子块文本
                             "metadata" : dict,  # 入库时附加的 metadata
                             "distance" : float  # 向量距离（可选）
                         }
                         metadata 中若包含 "parent_text" 和 "parent_index"，
                         则触发 Auto-merging；否则原样返回（兼容旧格式数据）。

    Returns:
        list[dict]，合并后的上下文列表，每个元素格式：
        {
            "id"           : str,   # 原文档 ID
            "document"     : str,   # 合并后文本（父块 or 原子块）
            "metadata"     : dict,  # 原始 metadata
            "distance"     : float, # 原始向量距离（若有）
            "merged"       : bool   # True 表示已被父块替换
        }

    示例：
        3 个子块命中，分属 2 个父块 → 返回 2 条（去重后），
        每条 document 为对应父块的完整文本。
    """
    if not retrieved_items:
        return []

    # 用于按 parent_index 去重，key = (source, page, parent_index) 或 fallback 到 id
    seen_parents: dict[str, dict] = {}
    no_parent_items: list[dict] = []

    for item in retrieved_items:
        metadata = item.get("metadata") or {}
        parent_text = metadata.get("parent_text", "")
        parent_index = metadata.get("parent_index", None)

        # ---- 判断是否为分层分块的子块 ----
        if parent_text and parent_index is not None:
            # 构造去重键：同一文件同一页同一父块只保留一次
            source = metadata.get("source", "")
            page = metadata.get("page", "")
            dedup_key = f"{source}__page{page}__parent{parent_index}"

            if dedup_key not in seen_parents:
                # 用父块文本替换子块文本，标记已合并
                merged_item = dict(item)           # 浅拷贝，保留原字段
                merged_item["document"] = parent_text
                merged_item["merged"] = True
                seen_parents[dedup_key] = merged_item
            # 同一父块已存在则跳过（去重）

        else:
            # ---- 旧格式数据（无 parent_text），原样返回 ----
            fallback_item = dict(item)
            fallback_item["merged"] = False
            no_parent_items.append(fallback_item)

    # 合并结果：分层命中（已去重）+ 旧格式原样
    result = list(seen_parents.values()) + no_parent_items
    return result
