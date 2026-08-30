from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import auth, analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(user: dict = Depends(auth.require_roles("admin", "teacher"))):
    return analytics_service.dashboard_summary()


@router.get("/at-risk")
def at_risk(threshold: float = 75.0, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    return analytics_service.at_risk_students(threshold)


@router.get("/attendance-trend")
def trend(class_id: str | None = None, days: int = 30, user: dict = Depends(auth.get_current_user)):
    return analytics_service.attendance_trend(class_id, days)


@router.get("/class-performance/{class_id}")
def class_perf(class_id: str, user: dict = Depends(auth.get_current_user)):
    return analytics_service.class_performance(class_id)
