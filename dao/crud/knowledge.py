"""知识库相关 CRUD 操作"""
from sqlalchemy.orm import Session
from dao.models import KnowledgeBase, KnowledgeDoc


def get_user_kbs(db: Session, user_id: str) -> list[KnowledgeBase]:
    """获取用户的所有知识库，按更新时间倒序"""
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == user_id)
        .order_by(KnowledgeBase.updated_at.desc())
        .all()
    )


def create_kb(db: Session, user_id: str, name: str, description: str | None = None) -> KnowledgeBase:
    """创建新知识库"""
    kb = KnowledgeBase(user_id=user_id, name=name, description=description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def get_kb(db: Session, kb_id: str) -> KnowledgeBase | None:
    """根据 ID 获取知识库"""
    return db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()


def delete_kb(db: Session, kb_id: str) -> None:
    """删除知识库（级联删除其下所有文档）"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if kb is not None:
        db.delete(kb)
        db.commit()


def add_doc(
    db: Session,
    kb_id: str,
    filename: str,
    file_type: str,
    chunk_count: int = 0,
    file_size: int | None = None,
    status: str = "indexed",
) -> KnowledgeDoc:
    """向知识库添加文档记录"""
    doc = KnowledgeDoc(
        kb_id=kb_id,
        filename=filename,
        file_type=file_type,
        chunk_count=chunk_count,
        file_size=file_size,
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    # 同步更新知识库的文档数量
    update_kb_doc_count(db, kb_id)
    return doc


def get_kb_docs(db: Session, kb_id: str) -> list[KnowledgeDoc]:
    """获取知识库下的所有文档，按创建时间倒序"""
    return (
        db.query(KnowledgeDoc)
        .filter(KnowledgeDoc.kb_id == kb_id)
        .order_by(KnowledgeDoc.created_at.desc())
        .all()
    )


def get_doc(db: Session, doc_id: str) -> KnowledgeDoc | None:
    """根据 ID 获取单个文档"""
    return db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()


def delete_doc(db: Session, doc_id: str) -> None:
    """删除文档并更新知识库文档计数"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if doc is not None:
        kb_id = doc.kb_id
        db.delete(doc)
        db.commit()
        update_kb_doc_count(db, kb_id)


def update_doc_status(db: Session, doc_id: str, status: str, chunk_count: int | None = None) -> None:
    """更新文档状态，可选更新分块数量"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if doc is not None:
        doc.status = status
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        db.commit()
        db.refresh(doc)


def update_kb_doc_count(db: Session, kb_id: str) -> None:
    """重新计算并更新知识库的文档数量"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if kb is not None:
        count = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kb_id).count()
        kb.doc_count = count
        db.commit()
        db.refresh(kb)
