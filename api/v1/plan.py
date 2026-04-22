"""
plan.py — 学习计划路由

GET    /api/v1/plan/                           获取用户所有计划
POST   /api/v1/plan/                           创建新计划
GET    /api/v1/plan/{plan_id}                  获取单个计划（含任务列表）
DELETE /api/v1/plan/{plan_id}                  删除计划
POST   /api/v1/plan/{plan_id}/tasks            新增任务
PATCH  /api/v1/plan/{plan_id}/tasks/{task_id}/done  标记任务完成
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dao.models import User, StudyPlan, StudyTask
from api.deps import get_db, get_current_user

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class CreatePlanRequest(BaseModel):
    title: str
    description: Optional[str] = None


class CreateTaskRequest(BaseModel):
    title: str
    subject: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: str
    plan_id: str
    title: str
    subject: Optional[str]
    is_done: bool
    due_date: Optional[datetime]
    created_at: datetime
    done_at: Optional[datetime]

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    tasks: List[TaskResponse] = []

    class Config:
        from_attributes = True


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/plan", tags=["学习计划"])


@router.get("/", response_model=List[PlanResponse])
def list_plans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有学习计划"""
    plans = (
        db.query(StudyPlan)
        .filter(StudyPlan.user_id == current_user.id)
        .order_by(StudyPlan.created_at.desc())
        .all()
    )
    return plans


@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    req: CreatePlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为当前用户创建新学习计划"""
    plan = StudyPlan(
        user_id=current_user.id,
        title=req.title,
        description=req.description,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个学习计划（含任务列表），校验归属"""
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if plan.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该计划")
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_200_OK)
def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除指定计划（级联删除其所有任务），校验归属"""
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if plan.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除该计划")
    db.delete(plan)
    db.commit()
    return {"message": f"计划 '{plan.title}' 已删除"}


@router.post("/{plan_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def add_task(
    plan_id: str,
    req: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向指定计划新增任务，校验计划归属"""
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if plan.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该计划")

    task = StudyTask(
        plan_id=plan_id,
        title=req.title,
        subject=req.subject,
        due_date=req.due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{plan_id}/tasks/{task_id}/done", response_model=TaskResponse)
def mark_task_done(
    plan_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标记指定任务为已完成，校验计划归属"""
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if plan.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该计划")

    task = db.query(StudyTask).filter(
        StudyTask.id == task_id,
        StudyTask.plan_id == plan_id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task.is_done = True
    task.done_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task
