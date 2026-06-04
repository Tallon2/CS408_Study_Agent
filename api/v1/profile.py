"""
profile.py — 用户学习画像路由

GET  /api/v1/profile/          获取完整学习画像
GET  /api/v1/profile/summary   获取画像摘要（轻量版，供侧边栏使用）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user
from dao.models import User, UserProfile, LearningRecord, TaskState, ChatSession
from dao.crud.profile import get_or_create_profile, get_learning_records

router = APIRouter(prefix="/profile", tags=["学习画像"])


# ── Pydantic Response Schemas ──────────────────────────────────────────────────

class SubjectKnowledge(BaseModel):
    mastered: list[str] = []
    struggling: list[str] = []
    introduced: list[str] = []


class PatternItem(BaseModel):
    content: str
    subject: Optional[str] = None


class ProfileUser(BaseModel):
    username: str
    created_at: Optional[str] = None
    total_sessions: int = 0
    last_active_at: Optional[str] = None


class ProfileStats(BaseModel):
    study_count: int = 0
    weak_points: int = 0
    corrections: int = 0


class ProfileResponse(BaseModel):
    user: ProfileUser
    knowledge_graph: dict[str, SubjectKnowledge] = {}
    learning_style: str = ""
    patterns: list[PatternItem] = []
    pitfalls: list[PatternItem] = []
    stats: ProfileStats


class ProfileSummary(BaseModel):
    username: str
    total_sessions: int
    weak_points: int
    learning_style: str


# ── 辅助：知识图谱格式转换 ─────────────────────────────────────────────────────

# 知识点 → 科目的映射（topic 关键词前缀匹配）
_SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "数据结构": ["排序", "树", "链表", "栈", "队列", "图", "堆", "哈希", "查找", "搜索",
                  "二叉", "平衡", "B+", "B树", "跳表", "散列"],
    "操作系统": ["进程", "线程", "调度", "内存", "虚拟", "死锁", "信号量", "文件系统",
                  "中断", "I/O", "管道", "磁盘", "页面", "段"],
    "计算机网络": ["TCP", "UDP", "IP", "HTTP", "DNS", "路由", "以太网", "协议", "拥塞",
                    "握手", "HTTPS", "网络层", "传输层", "应用层", "MAC", "ARP"],
    "计算机组成原理": ["补码", "浮点", "流水线", "Cache", "总线", "ALU", "CPU", "指令",
                       "寄存器", "存储", "中断", "DMA", "编码", "运算器"],
}

_SUBJECT_ORDER = ["数据结构", "操作系统", "计算机网络", "计算机组成原理"]


def _topic_to_subject(topic: str) -> str:
    """根据关键词将知识点映射到对应科目，无法匹配则归入「其他」"""
    for subject, keywords in _SUBJECT_KEYWORDS.items():
        for kw in keywords:
            if kw in topic:
                return subject
    return "其他"


def _build_knowledge_graph(
    raw_kg: dict | None,
) -> dict[str, SubjectKnowledge]:
    """
    将 DB 中的扁平知识图谱（{topic: {status, ...}}）
    转换为前端期望的按科目分组结构（{科目: {mastered[], struggling[], introduced[]}}）。
    """
    if not raw_kg:
        return {s: SubjectKnowledge() for s in _SUBJECT_ORDER}

    grouped: dict[str, SubjectKnowledge] = {}

    for topic, info in raw_kg.items():
        if not isinstance(info, dict):
            continue
        status = info.get("status", "introduced")
        subject = _topic_to_subject(topic)
        if subject not in grouped:
            grouped[subject] = SubjectKnowledge()
        if status == "mastered":
            grouped[subject].mastered.append(topic)
        elif status == "struggling":
            grouped[subject].struggling.append(topic)
        else:
            grouped[subject].introduced.append(topic)

    # 保证四个主科目始终存在（即使为空）
    for s in _SUBJECT_ORDER:
        if s not in grouped:
            grouped[s] = SubjectKnowledge()

    # 按固定顺序排列
    ordered: dict[str, SubjectKnowledge] = {}
    for s in _SUBJECT_ORDER:
        ordered[s] = grouped[s]
    for s in grouped:
        if s not in ordered:
            ordered[s] = grouped[s]

    return ordered


def _parse_learning_style(raw: str | None) -> str:
    """从 DB 的 learning_style 字段解析出可读字符串"""
    if not raw:
        return ""
    import json
    try:
        prefs: dict = json.loads(raw)
        style = prefs.get("explanation_style", "")
        pace = prefs.get("pace", "")
        parts = [p for p in [style, pace] if p]
        return " · ".join(parts) if parts else ""
    except (json.JSONDecodeError, TypeError):
        return raw  # 旧版直接存字符串


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的完整学习画像"""
    user_id = str(current_user.id)

    # ── 1. 用户画像 (UserProfile) ──
    orm_profile: UserProfile = get_or_create_profile(db, user_id)

    # ── 2. 学习记录 (LearningRecord) ──
    all_records = get_learning_records(db, user_id)
    patterns = [
        PatternItem(content=r.content, subject=r.subject)
        for r in all_records if r.record_type == "pattern"
    ]
    pitfalls = [
        PatternItem(content=r.content, subject=r.subject)
        for r in all_records if r.record_type == "pitfall"
    ]

    # ── 3. 任务状态 (TaskState) ──
    task_state = (
        db.query(TaskState)
        .filter(TaskState.user_id == user_id)
        .order_by(TaskState.updated_at.desc())
        .first()
    )
    study_count = task_state.study_count if task_state else 0
    weak_points_list: list = task_state.weak_points or [] if task_state else []
    corrections_list: list = task_state.corrections or [] if task_state else []

    # ── 4. 会话统计 ──
    total_sessions = orm_profile.total_sessions or 0

    # ── 5. 构建响应 ──
    profile_user = ProfileUser(
        username=current_user.username,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        total_sessions=total_sessions,
        last_active_at=(
            orm_profile.last_active_at.isoformat()
            if orm_profile.last_active_at else None
        ),
    )

    return ProfileResponse(
        user=profile_user,
        knowledge_graph=_build_knowledge_graph(orm_profile.knowledge_graph),
        learning_style=_parse_learning_style(orm_profile.learning_style),
        patterns=patterns,
        pitfalls=pitfalls,
        stats=ProfileStats(
            study_count=study_count,
            weak_points=len(weak_points_list),
            corrections=len(corrections_list),
        ),
    )


@router.get("/summary", response_model=ProfileSummary)
def get_profile_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取画像摘要（轻量版，供侧边栏等低成本场景使用）"""
    user_id = str(current_user.id)
    orm_profile: UserProfile = get_or_create_profile(db, user_id)

    task_state = (
        db.query(TaskState)
        .filter(TaskState.user_id == user_id)
        .order_by(TaskState.updated_at.desc())
        .first()
    )
    weak_points_list: list = task_state.weak_points or [] if task_state else []

    return ProfileSummary(
        username=current_user.username,
        total_sessions=orm_profile.total_sessions or 0,
        weak_points=len(weak_points_list),
        learning_style=_parse_learning_style(orm_profile.learning_style),
    )


@router.post("/refresh")
def refresh_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动触发画像刷新：从当前会话历史生成 digest，更新 L2/L4 数据。

    - 60 秒内重复请求直接返回缓存结果，避免重复调用 LLM
    - 无活跃会话时返回提示
    """
    import time
    from agent.graph.nodes.memory_update import run_batch_profile_update
    from api.deps import _agent_cache

    user_id = str(current_user.id)
    agent = _agent_cache.get(user_id)

    if agent is None:
        return {"message": "当前无活跃会话，无需刷新", "updated": False}

    # ── 去重时间窗：60 秒内不重复触发 ──
    now = time.time()
    last_refresh = getattr(agent, "_last_manual_refresh_ts", 0.0)
    if now - last_refresh < 60:
        remaining = int(60 - (now - last_refresh))
        return {
            "message": f"刷新冷却中，请 {remaining} 秒后再试",
            "updated": False,
        }

    # ── 同步执行（手动刷新允许等待结果） ──
    try:
        run_batch_profile_update(user_id, list(agent._messages))
        agent._last_manual_refresh_ts = now
        return {"message": "画像已刷新", "updated": True}
    except Exception as exc:
        return {"message": f"刷新失败: {exc}", "updated": False}
