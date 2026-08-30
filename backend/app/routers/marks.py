from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, data_store
from ..schemas import MarkIn

router = APIRouter(prefix="/marks", tags=["marks"])


@router.get("")
def list_marks(
    student_id: str | None = None,
    subject_id: str | None = None,
    exam_type: str | None = None,
    user: dict = Depends(auth.get_current_user),
):
    df = data_store.read_table("marks")
    if user["role"] == "student":
        df = df[df["student_id"] == user.get("linked_id", "")]
    if student_id:
        df = df[df["student_id"] == student_id]
    if subject_id:
        df = df[df["subject_id"] == subject_id]
    if exam_type:
        df = df[df["exam_type"] == exam_type]
    return df.to_dict(orient="records")


@router.post("")
def add_mark(payload: MarkIn, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    df = data_store.read_table("marks")
    mask = (
        (df["student_id"] == payload.student_id)
        & (df["subject_id"] == payload.subject_id)
        & (df["exam_type"] == payload.exam_type)
    )
    row = payload.model_dump()
    if not row.get("date"):
        row["date"] = dt.date.today().isoformat()
    if mask.any():
        idx = df[mask].index[0]
        for k, v in row.items():
            df.loc[idx, k] = v
        data_store.write_table("marks", df)
        return df.loc[idx].to_dict()
    row["id"] = data_store.next_id("marks", "id")
    data_store.append_row("marks", row)
    return row


@router.post("/bulk")
def add_marks_bulk(payload: list[MarkIn], user: dict = Depends(auth.require_roles("admin", "teacher"))):
    count = 0
    for m in payload:
        add_mark(m, user)
        count += 1
    return {"status": "ok", "count": count}


@router.delete("/{mark_id}")
def delete_mark(mark_id: str, user: dict = Depends(auth.require_roles("admin", "teacher"))):
    ok = data_store.delete_row("marks", "id", mark_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mark not found")
    return {"status": "deleted"}
