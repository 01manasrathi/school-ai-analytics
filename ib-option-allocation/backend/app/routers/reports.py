"""Reports. Every endpoint returns JSON by default or a CSV download with ?format=csv."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import models as M
from ..auth import get_current_user
from ..database import get_db
from ..services import approved, get_student, offering_dict, offering_query, student_grid
from .change_requests import cr_dict

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


def respond(rows: list[dict], fmt: str, name: str):
    if fmt != "csv":
        return rows
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/capacity")
def capacity(format: str = "json", db: Session = Depends(get_db)):
    rows = []
    for o in sorted((offering_dict(o) for o in db.scalars(offering_query()).unique().all()),
                    key=lambda d: (d["block"], d["subject"], d["level"])):
        rows.append({
            "block": o["block"], "subject_code": o["subject_code"], "subject": o["subject"], "group": o["group"],
            "level": o["level"], "teacher": o["teacher"], "room": o["room"], "capacity": o["capacity"],
            "enrolled": o["current_enrollment"], "seats_left": o["seats_left"], "min_enrollment": o["min_enrollment"],
            "status": "OVER_CAPACITY" if o["over_capacity"] else "FULL" if o["full"] else "BELOW_MIN" if o["below_min"] else "OK",
            "active": o["is_active"],
        })
    return respond(rows, format, "capacity_report")


@router.get("/waitlist")
def waitlist(format: str = "json", db: Session = Depends(get_db)):
    q = (select(M.StudentChoice).where(M.StudentChoice.status == M.ChoiceStatus.WAITLISTED)
         .options(joinedload(M.StudentChoice.student),
                  joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.subject),
                  joinedload(M.StudentChoice.offering).joinedload(M.SubjectOffering.block))
         .order_by(M.StudentChoice.offering_id, M.StudentChoice.created_at))
    rows, pos = [], {}
    for c in db.scalars(q).all():
        pos[c.offering_id] = pos.get(c.offering_id, 0) + 1
        rows.append({"position": pos[c.offering_id], "student_id": c.student.student_id, "student": c.student.name,
                     "block": c.offering.block.name, "subject": c.offering.subject.name, "level": c.offering.level,
                     "source": c.source, "capacity": c.offering.capacity, "enrolled": c.offering.current_enrollment,
                     "since": c.created_at.isoformat()})
    return respond(rows, format, "waitlist_report")


@router.get("/unallocated")
def unallocated(format: str = "json", db: Session = Depends(get_db)):
    rows = []
    for sid in db.scalars(select(M.Student.id).where(M.Student.status == M.StudentStatus.NEW)).all():
        s = get_student(db, sid)
        n = len(approved(s))
        wl = [c for c in s.choices if c.status == M.ChoiceStatus.WAITLISTED]
        if n == 0 or wl:
            rows.append({"student_id": s.student_id, "name": s.name, "grade": s.grade, "approved_choices": n,
                         "waitlisted": "; ".join(f"{c.offering.subject.name} {c.offering.level}" for c in wl),
                         "status": "NOT ALLOCATED" if n == 0 else "PARTIAL"})
    return respond(rows, format, "unallocated_students")


@router.get("/allocation")
def allocation(status: str | None = None, format: str = "json", db: Session = Depends(get_db)):
    q = select(M.Student.id).order_by(M.Student.student_id)
    if status:
        q = q.where(M.Student.status == status.upper())
    rows, cache = [], {}
    for sid in db.scalars(q).all():
        g = student_grid(db, get_student(db, sid), cache)
        row = {"student_id": g["student_id"], "name": g["name"], "status": g["status"], "grade": g["grade"]}
        for b in g["blocks"]:
            c = b["choice"]
            row[f"block_{b['block']}"] = f"{c['subject']} {c['level']}" if c else (
                f"WAITLIST: {b['waitlisted'][0]['subject']} {b['waitlisted'][0]['level']}" if b["waitlisted"] else "")
        row.update({"hl": g["hl"], "sl": g["sl"], "valid": g["valid"], "issues": "; ".join(i["message"] for i in g["issues"])})
        rows.append(row)
    return respond(rows, format, "allocation_report")


@router.get("/change-requests")
def change_requests(format: str = "json", db: Session = Depends(get_db)):
    crs = [cr_dict(cr) for cr in db.scalars(select(M.ChangeRequest).order_by(M.ChangeRequest.id)).all()]
    if format != "csv":
        return crs
    fmt_off = lambda o: f"{o['subject']} {o['level']} (Block {o['block']})" if o else ""  # noqa: E731
    rows = [{
        "id": c["id"], "student_id": c["student_id"], "student": c["student_name"],
        "current": fmt_off(c["current_offering"]), "requested": fmt_off(c["requested_offering"]),
        "compensating": (fmt_off(c["compensating_current_offering"]) + " -> " + fmt_off(c["compensating_requested_offering"]))
        if c["compensating_current_offering"] else "",
        "reason": c["reason"], "priority": c["priority"], "status": c["status"],
        "feasibility_status": c["feasibility_status"],
        "feasibility_reasons": "; ".join(c["feasibility"].get("reasons", [])),
        "warnings": "; ".join(c["feasibility"].get("warnings", [])),
        "override_by": c["override_by"] or "", "override_reason": c["override_reason"] or "",
        "created_at": c["created_at"],
    } for c in crs]
    return respond(rows, "csv", "change_requests_report")
