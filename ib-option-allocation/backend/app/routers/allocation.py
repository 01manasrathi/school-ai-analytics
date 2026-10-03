from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from .. import models as M
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..engines import allocate, validate_programme
from ..engines.types import BlockInfo, offering_info, student_info
from ..rules import load_ruleset
from ..services import all_offering_infos, get_offering, get_student

router = APIRouter(prefix="/api/allocation", tags=["allocation"])


class RunIn(BaseModel):
    student_ids: list[int] | None = Field(None, description="Limit to these student DB ids (default: all unallocated NEW students)")


def unallocated_new_students(db: Session, ids: list[int] | None = None) -> list[M.Student]:
    q = select(M.Student.id).where(M.Student.status == M.StudentStatus.NEW)
    if ids:
        q = q.where(M.Student.id.in_(ids))
    students = [get_student(db, i) for i in db.scalars(q).all()]
    return [s for s in students if not any(c.status in (M.ChoiceStatus.APPROVED, M.ChoiceStatus.WAITLISTED) for c in s.choices)]


@router.post("/run")
def run(body: RunIn | None = None, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)):
    """Dry run: propose placements for NEW students. Nothing is saved."""
    students = unallocated_new_students(db, body.student_ids if body else None)
    by_prog: dict[int, list[M.Student]] = defaultdict(list)
    for s in students:
        by_prog[s.programme_id].append(s)
    result = {"students": [], "offerings": [], "summary": Counter()}
    for prog_id, group in by_prog.items():
        blocks = [BlockInfo(b.id, b.name, b.label, b.sort_order, b.period, b.max_choices_per_student)
                  for b in db.scalars(select(M.OptionBlock).where(M.OptionBlock.programme_id == prog_id)).all()]
        r = allocate([student_info(s) for s in group], blocks, all_offering_infos(db, prog_id), load_ruleset(db, prog_id))
        result["students"] += r["students"]
        result["offerings"] += r["offerings"]
        result["summary"].update(r["summary"])
    result["summary"] = dict(result["summary"])
    return result


class Placement(BaseModel):
    student_id: int
    offering_id: int
    status: str = "approved"  # approved | waitlisted


class CommitIn(BaseModel):
    placements: list[Placement]
    override_reason: str | None = None


@router.post("/commit")
def commit(body: CommitIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    """Write reviewed placements as StudentChoice rows (source NEW_ALLOCATION) and update enrollment atomically."""
    override = (body.override_reason or "").strip()
    errors: list[dict] = []
    by_student: dict[int, list[Placement]] = defaultdict(list)
    for p in body.placements:
        if p.status not in (M.ChoiceStatus.APPROVED, M.ChoiceStatus.WAITLISTED):
            raise HTTPException(422, f"Invalid placement status '{p.status}'")
        by_student[p.student_id].append(p)

    offerings = {oid: get_offering(db, oid, lock=True) for oid in {p.offering_id for p in body.placements}}
    seats_needed = Counter(p.offering_id for p in body.placements if p.status == M.ChoiceStatus.APPROVED)
    for oid, n in seats_needed.items():
        o = offerings[oid]
        if o.current_enrollment + n > o.capacity and not override:
            errors.append({"student_id": None, "message": f"{o.subject.name} {o.level} (Block {o.block.name}) would exceed capacity: "
                                                          f"{o.current_enrollment}+{n} > {o.capacity}"})

    students = {sid: get_student(db, sid) for sid in by_student}
    for sid, places in by_student.items():
        s = students[sid]
        if any(c.status in (M.ChoiceStatus.APPROVED, M.ChoiceStatus.WAITLISTED) for c in s.choices):
            errors.append({"student_id": s.student_id, "message": "Student already has choices recorded"})
            continue
        rules = load_ruleset(db, s.programme_id)
        per_block: dict[int, M.SubjectOffering] = {}
        for p in sorted(places, key=lambda p: p.status != M.ChoiceStatus.APPROVED):
            o = offerings[p.offering_id]
            if o.block.programme_id != s.programme_id:
                errors.append({"student_id": s.student_id, "message": f"{o.subject.name} is not in the student's programme"})
            per_block.setdefault(o.block_id, o)
        for issue in validate_programme([offering_info(o) for o in per_block.values()], rules, student_info(s).prior_subjects):
            if issue.severity == "WARNING":
                continue
            if not override or not issue.overridable:
                errors.append({"student_id": s.student_id, "message": issue.message, "severity": issue.severity})

    if errors:
        db.rollback()
        raise HTTPException(422, {"message": "Allocation not committed", "errors": errors})

    now = datetime.now(timezone.utc)
    for sid, places in by_student.items():
        s = students[sid]
        for p in places:
            o = offerings[p.offering_id]
            is_appr = p.status == M.ChoiceStatus.APPROVED
            s.choices.append(M.StudentChoice(
                student_id=s.id, offering_id=o.id, status=p.status, source=M.ChoiceSource.NEW_ALLOCATION,
                approved_by=user.username if is_appr else None, approved_at=now if is_appr else None,
            ))
            if is_appr:
                o.current_enrollment += 1
        audit.log(db, user.username, "NEW_ALLOCATION_COMMIT", "Student", s.student_id, None,
                  {"placements": [p.model_dump() for p in places], "override_reason": override or None})
    db.commit()
    return {"committed_students": len(by_student), "placements": len(body.placements)}
