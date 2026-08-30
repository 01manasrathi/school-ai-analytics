from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, data_store
from ..schemas import ClassIn, SubjectIn

router = APIRouter(tags=["classes"])


@router.get("/classes")
def list_classes(user: dict = Depends(auth.get_current_user)):
    return data_store.read_table("classes").to_dict(orient="records")


@router.post("/classes")
def create_class(payload: ClassIn, user: dict = Depends(auth.require_roles("admin"))):
    cid = data_store.next_id("classes", "class_id", prefix="C")
    row = payload.model_dump()
    row["class_id"] = cid
    data_store.append_row("classes", row)
    return row


@router.put("/classes/{class_id}")
def update_class(class_id: str, payload: ClassIn, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.update_row("classes", "class_id", class_id, payload.model_dump())
    if not ok:
        raise HTTPException(status_code=404, detail="Class not found")
    return data_store.get_row("classes", "class_id", class_id)


@router.delete("/classes/{class_id}")
def delete_class(class_id: str, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.delete_row("classes", "class_id", class_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"status": "deleted"}


@router.get("/subjects")
def list_subjects(class_id: str | None = None, user: dict = Depends(auth.get_current_user)):
    df = data_store.read_table("subjects")
    if class_id:
        df = df[df["class_id"] == class_id]
    return df.to_dict(orient="records")


@router.post("/subjects")
def create_subject(payload: SubjectIn, user: dict = Depends(auth.require_roles("admin"))):
    sid = data_store.next_id("subjects", "subject_id", prefix="S")
    row = payload.model_dump()
    row["subject_id"] = sid
    data_store.append_row("subjects", row)
    return row


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: str, user: dict = Depends(auth.require_roles("admin"))):
    ok = data_store.delete_row("subjects", "subject_id", subject_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"status": "deleted"}
