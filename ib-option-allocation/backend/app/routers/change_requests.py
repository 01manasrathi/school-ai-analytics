import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import audit
from .. import models as M
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..engines import FEASIBLE, FEASIBLE_WAITLIST
from ..services import add_waitlist, apply_swaps, cr_swaps, get_student, run_feasibility

router = APIRouter(prefix="/api", tags=["change-requests"])


def _off(o: M.SubjectOffering | None):
    if not o:
        return None
    return {"id": o.id, "subject": o.subject.name, "subject_code": o.subject.code, "level": o.level,
            "block": o.block.name, "capacity": o.capacity, "current_enrollment": o.current_enrollment}


def cr_dict(cr: M.ChangeRequest) -> dict:
    return {
        "id": cr.id, "student_db_id": cr.student_id, "student_id": cr.student.student_id, "student_name": cr.student.name,
        "current_offering": _off(cr.current_offering), "requested_offering": _off(cr.requested_offering),
        "compensating_current_offering": _off(cr.compensating_current_offering),
        "compensating_requested_offering": _off(cr.compensating_requested_offering),
        "reason": cr.reason, "priority": cr.priority, "status": cr.status,
        "feasibility_status": cr.feasibility_status, "feasibility": json.loads(cr.feasibility_reasons_json or "{}"),
        "override_by": cr.override_by, "override_reason": cr.override_reason,
        "resolved_by": cr.resolved_by, "resolved_at": cr.resolved_at.isoformat() if cr.resolved_at else None,
        "created_at": cr.created_at.isoformat() if cr.created_at else None,
    }


def _load(db: Session, cr_id: int) -> M.ChangeRequest:
    cr = db.get(M.ChangeRequest, cr_id)
    if not cr:
        raise HTTPException(404, "Change request not found")
    return cr


def _recheck(db: Session, cr: M.ChangeRequest) -> dict:
    s = get_student(db, cr.student_id)
    result = run_feasibility(db, s, cr.current_offering_id, cr.requested_offering_id,
                             cr.compensating_current_offering_id, cr.compensating_requested_offering_id)
    cr.feasibility_status = result["status"]
    cr.feasibility_reasons_json = json.dumps(result)
    return result


@router.get("/change-requests", dependencies=[Depends(get_current_user)])
def list_crs(status: str | None = None, db: Session = Depends(get_db)):
    q = select(M.ChangeRequest).options(joinedload(M.ChangeRequest.student)).order_by(M.ChangeRequest.priority, M.ChangeRequest.id)
    if status:
        q = q.where(M.ChangeRequest.status == status.upper())
    return [cr_dict(cr) for cr in db.scalars(q).all()]


class CRIn(BaseModel):
    student_id: str
    current_offering_id: int
    requested_offering_id: int
    compensating_current_offering_id: int | None = None
    compensating_requested_offering_id: int | None = None
    reason: str = ""
    priority: int = 3


@router.post("/change-request")
def create_cr(body: CRIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    s = get_student(db, body.student_id)
    result = run_feasibility(db, s, body.current_offering_id, body.requested_offering_id,
                             body.compensating_current_offering_id, body.compensating_requested_offering_id)
    cr = M.ChangeRequest(
        student_id=s.id, current_offering_id=body.current_offering_id, requested_offering_id=body.requested_offering_id,
        compensating_current_offering_id=body.compensating_current_offering_id,
        compensating_requested_offering_id=body.compensating_requested_offering_id,
        reason=body.reason, priority=body.priority, status=M.CRStatus.PENDING,
        feasibility_status=result["status"], feasibility_reasons_json=json.dumps(result),
    )
    db.add(cr)
    db.flush()
    audit.log(db, user.username, "CHANGE_REQUEST_CREATE", "ChangeRequest", cr.id, None, body.model_dump())
    db.commit()
    return cr_dict(cr)


@router.post("/change-request/{cr_id}/recheck")
def recheck(cr_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)):
    cr = _load(db, cr_id)
    _recheck(db, cr)
    db.commit()
    return cr_dict(cr)


@router.post("/change-request/{cr_id}/approve")
def approve(cr_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    cr = _load(db, cr_id)
    if cr.status not in (M.CRStatus.PENDING, M.CRStatus.WAITLISTED):
        raise HTTPException(409, f"Change request is already {cr.status}")
    result = _recheck(db, cr)
    s = get_student(db, cr.student_id)
    now = datetime.now(timezone.utc)
    if result["status"] == FEASIBLE:
        apply_swaps(db, s, cr_swaps(cr), user.username, f"Change request #{cr.id} approved")
        cr.status = M.CRStatus.APPROVED
    elif result["status"] == FEASIBLE_WAITLIST:
        add_waitlist(db, s, cr.requested_offering_id, user.username)
        cr.status = M.CRStatus.WAITLISTED
    else:
        db.commit()  # persist refreshed feasibility
        raise HTTPException(409, {"message": f"Cannot approve: {result['status']}. Use override if appropriate.", "feasibility": result})
    cr.resolved_by, cr.resolved_at = user.username, now
    audit.log(db, user.username, "CHANGE_REQUEST_APPROVE", "ChangeRequest", cr.id, None, {"status": cr.status, "feasibility": result})
    db.commit()
    return cr_dict(cr)


class OverrideIn(BaseModel):
    reason: str


@router.post("/change-request/{cr_id}/override")
def override(cr_id: int, body: OverrideIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    reason = (body.reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(422, "An override reason (at least 5 characters) is required")
    cr = _load(db, cr_id)
    if cr.status not in (M.CRStatus.PENDING, M.CRStatus.WAITLISTED):
        raise HTTPException(409, f"Change request is already {cr.status}")
    result = _recheck(db, cr)
    if not result["override_allowed"] and result["status"] != FEASIBLE:
        db.commit()
        raise HTTPException(409, {"message": "This request has blocking issues that cannot be overridden", "feasibility": result})
    s = get_student(db, cr.student_id)
    old = {"status": cr.status, "feasibility_status": result["status"]}
    try:
        changes = apply_swaps(db, s, cr_swaps(cr), user.username, f"OVERRIDE #{cr.id}: {reason}")
    except HTTPException:
        db.rollback()
        raise
    cr.status = M.CRStatus.OVERRIDDEN
    cr.override_by, cr.override_reason = user.username, reason
    cr.resolved_by, cr.resolved_at = user.username, datetime.now(timezone.utc)
    audit.log(db, user.username, "ADMIN_OVERRIDE", "ChangeRequest", cr.id, old,
              {"status": cr.status, "reason": reason, "reasons_overridden": result["reasons"], "changes": changes})
    db.commit()
    return cr_dict(cr)


class RejectIn(BaseModel):
    reason: str = ""


@router.post("/change-request/{cr_id}/reject")
def reject(cr_id: int, body: RejectIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    cr = _load(db, cr_id)
    if cr.status not in (M.CRStatus.PENDING, M.CRStatus.WAITLISTED):
        raise HTTPException(409, f"Change request is already {cr.status}")
    s = get_student(db, cr.student_id)
    for c in s.choices:
        if c.offering_id == cr.requested_offering_id and c.status == M.ChoiceStatus.WAITLISTED:
            c.status = M.ChoiceStatus.REJECTED
    old = cr.status
    cr.status = M.CRStatus.REJECTED
    cr.resolved_by, cr.resolved_at = user.username, datetime.now(timezone.utc)
    audit.log(db, user.username, "CHANGE_REQUEST_REJECT", "ChangeRequest", cr.id, {"status": old}, {"status": cr.status, "reason": body.reason})
    db.commit()
    return cr_dict(cr)
