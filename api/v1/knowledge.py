"""
knowledge.py — 知识库管理路由

GET    /api/v1/knowledge/                          获取用户所有知识库
POST   /api/v1/knowledge/                          创建知识库 {name, description}
GET    /api/v1/knowledge/{kb_id}                   获取单个知识库详情（含文档列表）
DELETE /api/v1/knowledge/{kb_id}                   删除知识库（级联删除文档）
GET    /api/v1/knowledge/{kb_id}/docs              获取知识库文档列表
POST   /api/v1/knowledge/{kb_id}/docs/upload       上传文档（multipart/form-data, PDF/TXT）
DELETE /api/v1/knowledge/{kb_id}/docs/{doc_id}     删除文档
"""

from __future__ import annotations
import os
import shutil
import traceback
from datetime import datetime

from typing import List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dao.models import User, KnowledgeBase, KnowledgeDoc
from api.deps import get_db, get_current_user

# ── 常量 ──────────────────────────────────────────────────────────────────────
STORAGE_DIR = os.path.join(_ROOT, "storage", "knowledge")
ALLOWED_EXTENSIONS = {"pdf", "txt"}


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class CreateKBRequest(BaseModel):
    name: str
    description: Optional[str] = None


class KBDocResponse(BaseModel):
    id: str
    kb_id: str
    filename: str
    file_type: str
    chunk_count: int
    file_size: Optional[int]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class KBResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    doc_count: int
    created_at: datetime
    updated_at: datetime
    docs: List[KBDocResponse] = []

    class Config:
        from_attributes = True


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/knowledge", tags=["知识库"])


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _get_kb_or_404(kb_id: str, user: User, db: Session) -> KnowledgeBase:
    """获取知识库，校验归属，不存在或无权限时抛 HTTP 异常"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if kb.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return kb


def _kb_storage_dir(kb_id: str) -> str:
    """返回知识库文件存储目录路径"""
    return os.path.join(STORAGE_DIR, kb_id)


def _file_extension(filename: str) -> str:
    """提取文件扩展名（小写，不含点）"""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _try_index_file(file_path: str, file_type: str, kb_id: str) -> int:
    """
    尝试调用 RAG indexer 为文件建立索引。

    Returns:
        int — 成功写入的 chunk 数量（失败返回 0）
    """
    try:
        if file_type == "pdf":
            from memory.rag.indexer import index_pdf
            index_pdf(
                pdf_path=file_path,
                subject=f"kb_{kb_id}",
                collection_name=f"kb_{kb_id}",
                use_hierarchical=True,
            )
        elif file_type == "txt":
            from memory.rag.indexer import chunk_text, _get_collection
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            chunks = chunk_text(text, chunk_size=800, overlap=100)
            if chunks:
                import hashlib
                collection = _get_collection(f"kb_{kb_id}")
                ids = [
                    hashlib.md5(f"{os.path.basename(file_path)}_{i}".encode()).hexdigest()
                    for i in range(len(chunks))
                ]
                metadatas = [
                    {"source": os.path.basename(file_path), "chunk_index": i}
                    for i in range(len(chunks))
                ]
                collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            return len(chunks)
        else:
            return 0

        # PDF 的 index_pdf 不返回 chunk 数，尝试查 collection 获取数量
        if file_type == "pdf":
            from memory.rag.indexer import _get_collection
            collection = _get_collection(f"kb_{kb_id}")
            return collection.count()

    except Exception:
        traceback.print_exc()
        return 0

    return 0


# ── 路由：知识库 CRUD ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[KBResponse])
def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有知识库"""
    kbs = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == current_user.id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )
    return kbs


@router.post("/", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    req: CreateKBRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为当前用户创建新知识库"""
    kb = KnowledgeBase(
        user_id=current_user.id,
        name=req.name,
        description=req.description,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)

    # 创建文件存储目录
    os.makedirs(_kb_storage_dir(kb.id), exist_ok=True)
    return kb


@router.get("/{kb_id}", response_model=KBResponse)
def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个知识库详情（含文档列表），校验归属"""
    kb = _get_kb_or_404(kb_id, current_user, db)
    return kb


@router.delete("/{kb_id}", status_code=status.HTTP_200_OK)
def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除指定知识库（级联删除文档记录和存储文件），校验归属"""
    kb = _get_kb_or_404(kb_id, current_user, db)
    kb_name = kb.name

    # 删除文件存储目录
    storage_dir = _kb_storage_dir(kb_id)
    if os.path.isdir(storage_dir):
        shutil.rmtree(storage_dir, ignore_errors=True)

    # 尝试删除 ChromaDB collection
    try:
        from memory.rag.indexer import get_chroma_client
        client = get_chroma_client()
        client.delete_collection(f"kb_{kb_id}")
    except Exception:
        pass  # collection 可能不存在，静默忽略

    # 级联删除数据库记录（KnowledgeDoc 通过 cascade 自动删除）
    db.delete(kb)
    db.commit()
    return {"message": f"知识库 '{kb_name}' 已删除"}


# ── 路由：文档管理 ─────────────────────────────────────────────────────────────

@router.get("/{kb_id}/docs", response_model=List[KBDocResponse])
def list_docs(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取知识库的文档列表"""
    _get_kb_or_404(kb_id, current_user, db)
    docs = (
        db.query(KnowledgeDoc)
        .filter(KnowledgeDoc.kb_id == kb_id)
        .order_by(KnowledgeDoc.created_at.desc())
        .all()
    )
    return docs


@router.post(
    "/{kb_id}/docs/upload",
    response_model=KBDocResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_doc(
    kb_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传文档到知识库（支持 PDF / TXT）。

    流程：
    1. 校验文件类型
    2. 保存文件到 storage/knowledge/{kb_id}/
    3. 创建 KnowledgeDoc 记录
    4. 尝试调用 RAG indexer 建立索引（失败不阻塞上传）
    5. 更新 KnowledgeBase.doc_count
    """
    kb = _get_kb_or_404(kb_id, current_user, db)

    # 校验文件类型
    ext = _file_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '{ext}'，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 保存文件
    save_dir = _kb_storage_dir(kb_id)
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, file.filename)
    content = await file.read()
    file_size = len(content)
    with open(file_path, "wb") as f:
        f.write(content)

    # 创建文档记录
    doc = KnowledgeDoc(
        kb_id=kb_id,
        filename=file.filename,
        file_type=ext,
        file_size=file_size,
        chunk_count=0,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 尝试建立索引
    chunk_count = _try_index_file(file_path, ext, kb_id)
    if chunk_count > 0:
        doc.status = "indexed"
        doc.chunk_count = chunk_count
    else:
        # chunk_count == 0 可能是索引失败，也可能是空文件
        doc.status = "failed" if file_size > 0 else "indexed"

    db.commit()
    db.refresh(doc)

    # 更新知识库文档计数
    kb.doc_count = (
        db.query(KnowledgeDoc)
        .filter(KnowledgeDoc.kb_id == kb_id)
        .count()
    )
    db.commit()
    db.refresh(doc)

    return doc


@router.delete("/{kb_id}/docs/{doc_id}", status_code=status.HTTP_200_OK)
def delete_doc(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除知识库中的指定文档"""
    kb = _get_kb_or_404(kb_id, current_user, db)

    doc = db.query(KnowledgeDoc).filter(
        KnowledgeDoc.id == doc_id,
        KnowledgeDoc.kb_id == kb_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    filename = doc.filename

    # 删除存储文件
    file_path = os.path.join(_kb_storage_dir(kb_id), filename)
    if os.path.isfile(file_path):
        os.remove(file_path)

    # 删除数据库记录
    db.delete(doc)
    db.commit()

    # 更新知识库文档计数
    kb.doc_count = (
        db.query(KnowledgeDoc)
        .filter(KnowledgeDoc.kb_id == kb_id)
        .count()
    )
    db.commit()

    return {"message": f"文档 '{filename}' 已删除"}
