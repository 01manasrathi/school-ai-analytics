from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from .. import models as M
from ..auth import get_current_user
from ..database import get_db
from ..services import get_student, student_grid

router = APIRouter(prefix="/api/students", tags=["students"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_students(status: str | None = Query(None, description="EXISTING | NEW | WITHDRAWN"),
                  q: str | None = None, db: Session = Depends(get_db)):
    query = select(M.Student).options(
        selectinload(M.Student.choices).joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.subject),
        selectinload(M.Student.choices).joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.block),
        selectinload(M.Student.preferences).joinedload(M.StudentPreference.subject),
        joinedload(M.Student.programme),
    ).order_by(M.Student.student_id)
    if status:
        query = query.where(M.Student.status == status.upper())
    if q:
        like = f"%{q}%"
        query = query.where(M.Student.name.ilike(like) | M.Student.student_id.ilike(like))
    cache: dict = {}
    return [student_grid(db, s, cache) for s in db.scalars(query).unique().all()]


@router.get("/{student_id}")
def get_one(student_id: str, db: Session = Depends(get_db)):
    return student_grid(db, get_student(db, student_id))


@router.get("/{student_id}/choices")
def choices(student_id: str, db: Session = Depends(get_db)):
    s = get_student(db, student_id)
    grid = student_grid(db, s)
    history = [{
        "choice_id": c.id, "offering_id": c.offering_id, "subject": c.offering.subject.name, "level": c.offering.level,
        "block": c.offering.block.name, "status": c.status, "source": c.source, "approved_by": c.approved_by,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None, "created_at": c.created_at.isoformat(),
    } for c in sorted(s.choices, key=lambda c: (c.offering.block.sort_order, c.id))]
    return {**grid, "history": history}
