from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, data_store
from ..schemas import StudentIn

router = APIRouter(prefix="/students", tags=["students"])


@router.get("")
def list_students(class_id: str | None = None, user: dict = Depends(auth.get_current_user)):
    df = data_store.read_table("students")
    if class_id:
        df = df[df["class_id"] == class_id]
    if user["role"] == "student":
        df = df[df["student_id"] == user.get("linked_id", "")]
    return df.to_dict(orient="records")


@router.get("/{student_id}")
def get_student(student_id: str, user: dict = Depends(auth.get_current_user)):
    row = data_store.get_row("students", "student_id", student_id)
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    return row


@router.post("")
def create_student(payload: StudentIn, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    sid = data_store.next_id("students", "student_id", prefix="ST")
    row = payload.model_dump()
    row["student_id"] = sid
    if not row.get("enrollment_date"):
        row["enrollment_date"] = dt.date.today().isoformat()
    data_store.append_row("students", row)
    return row


@router.put("/{student_id}")
def update_student(student_id: str, payload: StudentIn, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    ok = data_store.update_row("students", "student_id", student_id, payload.model_dump())
    if not ok:
        raise HTTPException(status_code=404, detail="Student not found")
    return data_store.get_row("students", "student_id", student_id)


@router.delete("/{student_id}")
def delete_student(student_id: str, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.delete_row("students", "student_id", student_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"status": "deleted"}
