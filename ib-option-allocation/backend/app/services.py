"""Database-facing helpers shared by the routers (loading data for engines, applying changes)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from . import audit, models
from .engines import check_feasibility, summarize, validate_programme
from .engines.types import grade_matches, offering_info, student_info
from .rules import load_ruleset

M = models


def offering_query():
    return select(M.SubjectOffering).options(joinedload(M.SubjectOffering.subject), joinedload(M.SubjectOffering.block))


def get_offering(db: Session, offering_id: int, lock: bool = False) -> M.SubjectOffering:
    q = offering_query().where(M.SubjectOffering.id == offering_id)
    if lock:
        q = q.with_for_update()
    o = db.scalar(q)
    if not o:
        raise HTTPException(404, f"Offering {offering_id} not found")
    return o


def get_student(db: Session, student_id: int | str) -> M.Student:
    q = select(M.Student).options(
        selectinload(M.Student.choices).joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.subject),
        selectinload(M.Student.choices).joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.block),
        selectinload(M.Student.preferences).joinedload(M.StudentPreference.subject),
        joinedload(M.Student.programme),
    )
    sid = str(student_id)
    s = db.scalar(q.where(M.Student.student_id == sid))  # school student_id (e.g. "S1001") first, then DB id
    if not s and sid.isdigit():
        s = db.scalar(q.where(M.Student.id == int(sid)))
    if not s:
        raise HTTPException(404, f"Student {student_id} not found")
    return s


def offering_dict(o: M.SubjectOffering) -> dict:
    return {
        "id": o.id, "subject_id": o.subject_id, "subject_code": o.subject.code, "subject": o.subject.name,
        "group": o.subject.ib_group, "level": o.level, "block_id": o.block_id, "block": o.block.name,
        "block_label": o.block.label, "teacher": o.teacher, "room": o.room, "capacity": o.capacity,
        "current_enrollment": o.current_enrollment, "min_enrollment": o.min_enrollment,
        "seats_left": o.capacity - o.current_enrollment, "is_active": o.is_active,
        "full": o.current_enrollment >= o.capacity, "over_capacity": o.current_enrollment > o.capacity,
        "below_min": o.current_enrollment < o.min_enrollment,
    }


def approved(student: M.Student) -> list[M.StudentChoice]:
    return [c for c in student.choices if c.status == M.ChoiceStatus.APPROVED]


def blocks_for(db: Session, programme_id: int, grade: int, _cache: dict | None = None) -> list[M.OptionBlock]:
    rows = db.scalars(select(M.OptionBlock).where(M.OptionBlock.programme_id == programme_id)
                      .order_by(M.OptionBlock.sort_order, M.OptionBlock.name)).all()
    return [b for b in rows if grade_matches(b.grade, grade)]


def student_grid(db: Session, s: M.Student, rules_cache: dict | None = None) -> dict:
    rules_cache = rules_cache if rules_cache is not None else {}
    if s.programme_id not in rules_cache:
        rules_cache[s.programme_id] = load_ruleset(db, s.programme_id)
    rules = rules_cache[s.programme_id]
    key = ("blocks", s.programme_id, s.grade)
    if key not in rules_cache:
        rules_cache[key] = blocks_for(db, s.programme_id, s.grade)
    blocks = rules_cache[key]

    appr = approved(s)
    infos = [offering_info(c.offering) for c in appr]
    summary = summarize(infos)
    issues = validate_programme(infos, rules, student_info(s).prior_subjects) if appr else []
    grid = []
    for b in blocks:
        in_block = [c for c in s.choices if c.offering.block_id == b.id and c.status in (M.ChoiceStatus.APPROVED, M.ChoiceStatus.WAITLISTED)]
        main = next((c for c in in_block if c.status == M.ChoiceStatus.APPROVED), None)
        grid.append({
            "block_id": b.id, "block": b.name, "label": b.label,
            "choice": _choice_dict(main) if main else None,
            "waitlisted": [_choice_dict(c) for c in in_block if c.status == M.ChoiceStatus.WAITLISTED],
        })
    return {
        "id": s.id, "student_id": s.student_id, "name": s.name, "grade": s.grade,
        "programme": s.programme.name if s.programme else None, "programme_id": s.programme_id,
        "cohort_year": s.cohort_year, "status": s.status, "nationality": s.nationality,
        "language_profile": s.language_profile, "priority": s.priority,
        "preferences": [{"rank": p.rank, "subject_code": p.subject.code, "subject": p.subject.name, "level": p.level}
                        for p in s.preferences],
        "blocks": grid, **summary,
        "allocated": bool(appr),
        "issues": [{"code": i.code, "severity": i.severity, "message": i.message} for i in issues],
        "valid": bool(appr) and not [i for i in issues if i.severity != "WARNING"],
    }


def _choice_dict(c: M.StudentChoice) -> dict:
    o = c.offering
    return {
        "choice_id": c.id, "offering_id": o.id, "subject_code": o.subject.code, "subject": o.subject.name,
        "level": o.level, "group": o.subject.ib_group, "block": o.block.name, "status": c.status,
        "source": c.source, "approved_by": c.approved_by,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None,
    }


def all_offering_infos(db: Session, programme_id: int | None = None):
    q = offering_query()
    if programme_id is not None:
        q = q.join(M.SubjectOffering.block).where(M.OptionBlock.programme_id == programme_id)
    return [offering_info(o) for o in db.scalars(q).unique().all()]


def run_feasibility(db: Session, s: M.Student, current_id: int, requested_id: int,
                    comp_current_id: int | None = None, comp_requested_id: int | None = None) -> dict:
    swaps = [(offering_info(get_offering(db, current_id)), offering_info(get_offering(db, requested_id)))]
    if comp_current_id and comp_requested_id:
        swaps.append((offering_info(get_offering(db, comp_current_id)), offering_info(get_offering(db, comp_requested_id))))
    current = [offering_info(c.offering) for c in approved(s)]
    rules = load_ruleset(db, s.programme_id)
    return check_feasibility(student_info(s), current, swaps, rules, all_offering_infos(db, s.programme_id))


def cr_swaps(cr: M.ChangeRequest) -> list[tuple[int, int]]:
    swaps = [(cr.current_offering_id, cr.requested_offering_id)]
    if cr.compensating_current_offering_id and cr.compensating_requested_offering_id:
        swaps.append((cr.compensating_current_offering_id, cr.compensating_requested_offering_id))
    return swaps


def apply_swaps(db: Session, s: M.Student, swaps: list[tuple[int, int]], user: str, note: str) -> list[dict]:
    """Move the student from each current offering to the requested one (inside the caller's transaction)."""
    now = datetime.now(timezone.utc)
    changes = []
    for cur_id, req_id in swaps:
        cur = get_offering(db, cur_id, lock=True)
        req = get_offering(db, req_id, lock=True)
        choice = next((c for c in approved(s) if c.offering_id == cur_id), None)
        if not choice:
            raise HTTPException(409, f"Student is not enrolled in offering {cur_id}")
        choice.status = M.ChoiceStatus.DROPPED
        for c in s.choices:
            if c.offering_id == req_id and c.status == M.ChoiceStatus.WAITLISTED:
                c.status = M.ChoiceStatus.DROPPED
        old = {"source": [cur.id, cur.current_enrollment], "target": [req.id, req.current_enrollment]}
        cur.current_enrollment -= 1
        req.current_enrollment += 1
        s.choices.append(M.StudentChoice(
            student_id=s.id, offering_id=req.id, status=M.ChoiceStatus.APPROVED,
            source=M.ChoiceSource.CHANGE_REQUEST, approved_by=user, approved_at=now,
        ))
        new = {"source": [cur.id, cur.current_enrollment], "target": [req.id, req.current_enrollment]}
        audit.log(db, user, "ENROLLMENT_CHANGE", "SubjectOffering", f"{cur.id}->{req.id}", old, {**new, "note": note})
        changes.append({"from": offering_dict(cur), "to": offering_dict(req)})
    return changes


def add_waitlist(db: Session, s: M.Student, offering_id: int, user: str) -> None:
    if any(c.offering_id == offering_id and c.status == M.ChoiceStatus.WAITLISTED for c in s.choices):
        return
    s.choices.append(M.StudentChoice(student_id=s.id, offering_id=offering_id, status=M.ChoiceStatus.WAITLISTED,
                                     source=M.ChoiceSource.CHANGE_REQUEST))
    audit.log(db, user, "WAITLIST_ADD", "StudentChoice", s.student_id, None, {"offering_id": offering_id})


def recompute_enrollment(db: Session) -> int:
    counts = dict(db.execute(
        select(M.StudentChoice.offering_id, func.count())
        .join(M.Student, M.Student.id == M.StudentChoice.student_id)
        .where(M.StudentChoice.status == M.ChoiceStatus.APPROVED, M.Student.status != M.StudentStatus.WITHDRAWN)
        .group_by(M.StudentChoice.offering_id)
    ).all())
    changed = 0
    for o in db.scalars(select(M.SubjectOffering)).all():
        n = counts.get(o.id, 0)
        if o.current_enrollment != n:
            o.current_enrollment, changed = n, changed + 1
    return changed
