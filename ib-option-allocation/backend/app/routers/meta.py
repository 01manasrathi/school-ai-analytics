"""Read endpoints for reference data + dashboard + audit log."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import get_current_user
from ..database import get_db
from ..services import approved, get_student, offering_dict, offering_query

router = APIRouter(prefix="/api", tags=["reference"], dependencies=[Depends(get_current_user)])


@router.get("/programmes")
def programmes(db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name, "grade_range": p.grade_range} for p in db.scalars(select(M.Programme)).all()]


@router.get("/blocks")
def blocks(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.OptionBlock).order_by(M.OptionBlock.programme_id, M.OptionBlock.sort_order)).all()
    return [{"id": b.id, "name": b.name, "label": b.label, "programme_id": b.programme_id, "programme": b.programme.name,
             "grade": b.grade, "period": b.period, "max_choices_per_student": b.max_choices_per_student,
             "sort_order": b.sort_order, "notes": b.notes} for b in rows]


@router.get("/subjects")
def subjects(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.Subject).order_by(M.Subject.ib_group, M.Subject.name)).all()
    return [{"id": s.id, "code": s.code, "name": s.name, "programme_id": s.programme_id, "ib_group": s.ib_group,
             "offered_levels": s.offered_levels, "prerequisites": s.prerequisites, "is_active": s.is_active} for s in rows]


@router.get("/offerings")
def offerings(db: Session = Depends(get_db)):
    rows = db.scalars(offering_query()).unique().all()
    return sorted((offering_dict(o) for o in rows), key=lambda d: (d["block"], d["subject"], d["level"]))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    offs = [offering_dict(o) for o in db.scalars(offering_query()).unique().all() if o.is_active]
    count = lambda status: db.scalar(select(func.count()).select_from(M.Student).where(M.Student.status == status))  # noqa: E731
    new_students = db.scalars(select(M.Student).where(M.Student.status == M.StudentStatus.NEW)).all()
    unallocated = []
    for s in new_students:
        s = get_student(db, s.id)
        n = len(approved(s))
        if n == 0 or any(c.status == M.ChoiceStatus.WAITLISTED for c in s.choices):
            unallocated.append({"id": s.id, "student_id": s.student_id, "name": s.name, "approved_choices": n})
    waitlist = db.scalar(select(func.count()).select_from(M.StudentChoice).where(M.StudentChoice.status == M.ChoiceStatus.WAITLISTED))
    pending = db.scalar(select(func.count()).select_from(M.ChangeRequest).where(M.ChangeRequest.status == M.CRStatus.PENDING))
    return {
        "students": {"existing": count(M.StudentStatus.EXISTING), "new": count(M.StudentStatus.NEW),
                     "withdrawn": count(M.StudentStatus.WITHDRAWN)},
        "offerings": len(offs),
        "total_capacity": sum(o["capacity"] for o in offs),
        "total_enrolled": sum(o["current_enrollment"] for o in offs),
        "full_classes": [o for o in offs if o["full"]],
        "below_min_classes": [o for o in offs if o["below_min"]],
        "waitlist_count": waitlist,
        "pending_change_requests": pending,
        "unallocated_new_students": unallocated,
    }


@router.get("/audit-log")
def audit_log(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.scalars(select(M.AuditLog).order_by(M.AuditLog.timestamp.desc(), M.AuditLog.id.desc()).limit(limit)).all()
    return [{"id": a.id, "user": a.user, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "old_value": a.old_value, "new_value": a.new_value, "timestamp": a.timestamp.isoformat()} for a in rows]
