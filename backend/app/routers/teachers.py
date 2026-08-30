from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, data_store
from ..schemas import TeacherIn

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("")
def list_teachers(user: dict = Depends(auth.get_current_user)):
    return data_store.read_table("teachers").to_dict(orient="records")


@router.get("/{teacher_id}")
def get_teacher(teacher_id: str, user: dict = Depends(auth.get_current_user)):
    row = data_store.get_row("teachers", "teacher_id", teacher_id)
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return row


@router.post("")
def create_teacher(payload: TeacherIn, user: dict = Depends(auth.require_roles("admin"))):
    tid = data_store.next_id("teachers", "teacher_id", prefix="T")
    row = payload.model_dump()
    row["teacher_id"] = tid
    data_store.append_row("teachers", row)
    return row


@router.put("/{teacher_id}")
def update_teacher(teacher_id: str, payload: TeacherIn, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.update_row("teachers", "teacher_id", teacher_id, payload.model_dump())
    if not ok:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return data_store.get_row("teachers", "teacher_id", teacher_id)


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: str, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.delete_row("teachers", "teacher_id", teacher_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"status": "deleted"}
