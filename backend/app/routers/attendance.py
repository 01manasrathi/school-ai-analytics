from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from .. import auth, data_store
from ..schemas import AttendanceMark, BulkAttendance

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _upsert_attendance(student_id: str, class_id: str, date: str, status: str,
                        marked_by: str, remarks: str = "") -> dict:
    df = data_store.read_table("attendance")
    mask = (df["student_id"] == student_id) & (df["date"] == date)
    if mask.any():
        idx = df[mask].index[0]
        df.loc[idx, ["status", "remarks", "marked_by"]] = [status, remarks, marked_by]
        data_store.write_table("attendance", df)
        return df.loc[idx].to_dict()
    new_id = data_store.next_id("attendance", "id")
    row = {
        "id": new_id, "student_id": student_id, "class_id": class_id, "date": date,
        "status": status, "marked_by": marked_by, "remarks": remarks,
    }
    data_store.append_row("attendance", row)
    return row


@router.post("/mark")
def mark_attendance(payload: AttendanceMark, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    return _upsert_attendance(payload.student_id, payload.class_id, payload.date,
                               payload.status, user["username"], payload.remarks)


@router.post("/bulk")
def mark_bulk(payload: BulkAttendance, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    results = []
    for rec in payload.records:
        results.append(_upsert_attendance(
            rec["student_id"], payload.class_id, payload.date,
            rec["status"], user["username"], rec.get("remarks", ""),
        ))
    return {"status": "ok", "count": len(results)}


@router.get("")
def list_attendance(
    student_id: str | None = None,
    class_id: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    user: dict = Depends(auth.get_current_user),
):
    df = data_store.read_table("attendance")
    if user["role"] == "student":
        df = df[df["student_id"] == user.get("linked_id", "")]
    if student_id:
        df = df[df["student_id"] == student_id]
    if class_id:
        df = df[df["class_id"] == class_id]
    if date:
        df = df[df["date"] == date]
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    return df.sort_values("date").to_dict(orient="records")


@router.get("/summary/{student_id}")
def attendance_summary(student_id: str, user: dict = Depends(auth.get_current_user)):
    df = data_store.read_table("attendance")
    df = df[df["student_id"] == student_id]
    if df.empty:
        return {"student_id": student_id, "total_days": 0, "present": 0, "absent": 0,
                "late": 0, "attendance_pct": 0.0}
    total = len(df)
    present = (df["status"] == "Present").sum()
    absent = (df["status"] == "Absent").sum()
    late = (df["status"] == "Late").sum()
    pct = round((present + late) / total * 100, 2) if total else 0.0
    return {
        "student_id": student_id, "total_days": int(total), "present": int(present),
        "absent": int(absent), "late": int(late), "attendance_pct": pct,
    }
