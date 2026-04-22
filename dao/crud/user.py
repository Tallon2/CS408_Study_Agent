"""用户相关 CRUD 操作"""
from sqlalchemy.orm import Session
from dao.models import User


def get_user_by_username(db: Session, username: str) -> User | None:
    """根据用户名查询用户"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """根据用户 ID 查询用户"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, username: str, hashed_password: str, email: str | None = None) -> User:
    """创建新用户并持久化到数据库"""
    user = User(username=username, hashed_password=hashed_password, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
