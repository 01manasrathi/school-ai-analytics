"""CSV import with column mapping, per-row validation and dry-run preview."""
import csv
import io
import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from .. import models as M
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..services import get_student, recompute_enrollment, run_feasibility

router = APIRouter(prefix="/api/import", tags=["import"])

PREF_FIELDS = [f"preference_{i}" for i in range(1, 8)]

# type -> (fields, required fields)
SPECS: dict[str, tuple[list[str], list[str]]] = {
    "students": (["student_id", "name", "grade", "programme", "cohort_year", "status", "nationality",
                  "language_profile", "prior_subjects", "priority"],
                 ["student_id", "name", "grade", "programme", "cohort_year"]),
    "subjects": (["code", "name", "programme", "ib_group", "hl", "sl", "prerequisites", "is_active"],
                 ["code", "name", "programme", "ib_group"]),
    "blocks": (["name", "label", "programme", "grade", "period", "max_choices_per_student", "sort_order", "notes"],
               ["name", "programme"]),
    "offerings": (["subject_code", "block", "programme", "level", "teacher", "room", "capacity", "min_enrollment", "is_active"],
                  ["subject_code", "block", "programme", "level"]),
    "choices": (["student_id", "subject_code", "level", "block", "status"], ["student_id", "subject_code", "level"]),
    "change_requests": (["student_id", "current_subject_code", "current_level", "requested_subject_code",
                         "requested_level", "requested_block", "reason", "priority"],
                        ["student_id", "current_subject_code", "current_level", "requested_subject_code", "requested_level"]),
    "preferences": (["student_id"] + PREF_FIELDS, ["student_id"]),
}

ALIASES = {"student_number": "student_id", "id": "student_id", "full_name": "name", "group": "ib_group",
           "subject": "subject_code", "code": "code", "option_block": "block", "programme_name": "programme",
           "program": "programme", "max_capacity": "capacity", "min": "min_enrollment"}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")


def suggest_mapping(headers: list[str], fields: list[str]) -> dict[str, str]:
    """Map CSV header -> field name (best guess)."""
    out = {}
    for h in headers:
        n = _norm(h)
        if n in fields:
            out[h] = n
        elif ALIASES.get(n) in fields and ALIASES[n] not in out.values():
            out[h] = ALIASES[n]
    return out


def _bool(v, default=True) -> bool:
    if v in (None, ""):
        return default
    return str(v).strip().lower() in ("y", "yes", "true", "1")


def _int(v, field, default=None):
    if v in (None, ""):
        if default is None:
            raise ValueError(f"{field} is required")
        return default
    try:
        return int(float(v))
    except ValueError:
        raise ValueError(f"{field} must be a number (got '{v}')")


def _level(v, field="level") -> str:
    lv = (v or "").strip().upper()
    if lv not in ("HL", "SL"):
        raise ValueError(f"{field} must be HL or SL (got '{v}')")
    return lv


def _programme(db, name, create=False) -> M.Programme:
    p = db.scalar(select(M.Programme).where(M.Programme.name == name.strip()))
    if not p and create:
        p = M.Programme(name=name.strip(), grade_range="")
        db.add(p)
        db.flush()
    if not p:
        raise ValueError(f"Unknown programme '{name}'")
    return p


def _subject(db, code) -> M.Subject:
    s = db.scalar(select(M.Subject).where(M.Subject.code == (code or "").strip()))
    if not s:
        raise ValueError(f"Unknown subject code '{code}'")
    return s


def _student(db, sid) -> M.Student:
    s = db.scalar(select(M.Student).where(M.Student.student_id == (sid or "").strip()))
    if not s:
        raise ValueError(f"Unknown student_id '{sid}'")
    return s


def _find_offering(db, subject: M.Subject, level: str, block_name: str | None, programme_id: int) -> M.SubjectOffering:
    q = (select(M.SubjectOffering).join(M.SubjectOffering.block)
         .where(M.SubjectOffering.subject_id == subject.id, M.SubjectOffering.level == level,
                M.OptionBlock.programme_id == programme_id))
    if block_name:
        q = q.where(M.OptionBlock.name == block_name.strip())
    rows = db.scalars(q).all()
    if not rows:
        raise ValueError(f"No offering for {subject.code} {level}{' in block ' + block_name if block_name else ''}")
    if len(rows) > 1:
        raise ValueError(f"{subject.code} {level} is offered in several blocks - specify block")
    return rows[0]


def import_row(db: Session, kind: str, r: dict) -> str:
    if kind == "students":
        prog = _programme(db, r["programme"])
        status = (r.get("status") or "NEW").strip().upper()
        if status not in M.StudentStatus.ALL:
            raise ValueError(f"status must be one of {M.StudentStatus.ALL}")
        s = db.scalar(select(M.Student).where(M.Student.student_id == r["student_id"].strip()))
        created = s is None
        s = s or M.Student(student_id=r["student_id"].strip())
        s.name, s.grade, s.programme_id = r["name"].strip(), _int(r["grade"], "grade"), prog.id
        s.cohort_year, s.status = _int(r["cohort_year"], "cohort_year"), status
        s.nationality, s.language_profile = r.get("nationality") or "", r.get("language_profile") or ""
        s.prior_subjects = (r.get("prior_subjects") or "").replace(";", ",")
        s.priority = _int(r.get("priority"), "priority", 100)
        db.add(s)
        return "created" if created else "updated"

    if kind == "subjects":
        prog = _programme(db, r["programme"], create=True)
        g = _int(r["ib_group"], "ib_group")
        if not 1 <= g <= 6:
            raise ValueError("ib_group must be 1-6")
        levels = [lv for lv, flag in (("HL", r.get("hl")), ("SL", r.get("sl"))) if _bool(flag)]
        if not levels:
            raise ValueError("Subject must be offered at HL or SL")
        s = db.scalar(select(M.Subject).where(M.Subject.code == r["code"].strip()))
        created = s is None
        s = s or M.Subject(code=r["code"].strip())
        s.name, s.programme_id, s.ib_group, s.offered_levels = r["name"].strip(), prog.id, g, ",".join(levels)
        s.prerequisites = json.dumps([p.strip() for p in re.split(r"[;,]", r.get("prerequisites") or "") if p.strip()])
        s.is_active = _bool(r.get("is_active"))
        db.add(s)
        return "created" if created else "updated"

    if kind == "blocks":
        prog = _programme(db, r["programme"], create=True)
        grade = (r.get("grade") or "").strip()
        b = db.scalar(select(M.OptionBlock).where(M.OptionBlock.programme_id == prog.id, M.OptionBlock.grade == grade,
                                                  M.OptionBlock.name == r["name"].strip()))
        created = b is None
        b = b or M.OptionBlock(name=r["name"].strip(), programme_id=prog.id, grade=grade)
        b.label, b.period, b.notes = r.get("label") or "", r.get("period") or "", r.get("notes") or ""
        b.max_choices_per_student = _int(r.get("max_choices_per_student"), "max_choices_per_student", 1)
        b.sort_order = _int(r.get("sort_order"), "sort_order", 0)
        db.add(b)
        return "created" if created else "updated"

    if kind == "offerings":
        prog = _programme(db, r["programme"])
        subj = _subject(db, r["subject_code"])
        level = _level(r["level"])
        if level not in subj.offered_levels.split(","):
            raise ValueError(f"{subj.name} is not offered at {level}")
        block = db.scalar(select(M.OptionBlock).where(M.OptionBlock.programme_id == prog.id, M.OptionBlock.name == r["block"].strip()))
        if not block:
            raise ValueError(f"Unknown block '{r['block']}' for {prog.name}")
        o = db.scalar(select(M.SubjectOffering).where(M.SubjectOffering.subject_id == subj.id,
                                                      M.SubjectOffering.block_id == block.id, M.SubjectOffering.level == level))
        created = o is None
        o = o or M.SubjectOffering(subject_id=subj.id, block_id=block.id, level=level, current_enrollment=0)
        o.teacher, o.room = r.get("teacher") or "", r.get("room") or ""
        o.capacity = _int(r.get("capacity"), "capacity", 18)
        o.min_enrollment = _int(r.get("min_enrollment"), "min_enrollment", 8)
        o.is_active = _bool(r.get("is_active"))
        db.add(o)
        return "created" if created else "updated"

    if kind == "choices":
        st = _student(db, r["student_id"])
        off = _find_offering(db, _subject(db, r["subject_code"]), _level(r["level"]), r.get("block"), st.programme_id)
        status = (r.get("status") or "approved").strip().lower()
        if status not in ("approved", "waitlisted", "requested"):
            raise ValueError("status must be approved, waitlisted or requested")
        existing = db.scalar(select(M.StudentChoice).where(M.StudentChoice.student_id == st.id, M.StudentChoice.offering_id == off.id,
                                                           M.StudentChoice.status.in_(["approved", "waitlisted", "requested"])))
        if existing:
            existing.status = status
            return "updated"
        db.add(M.StudentChoice(student_id=st.id, offering_id=off.id, status=status,
                               source=M.ChoiceSource.EXISTING_ALLOCATION if st.status == M.StudentStatus.EXISTING else M.ChoiceSource.NEW_ALLOCATION,
                               approved_by="csv-import" if status == "approved" else None))
        return "created"

    if kind == "change_requests":
        st = _student(db, r["student_id"])
        cur = _find_offering(db, _subject(db, r["current_subject_code"]), _level(r["current_level"], "current_level"), None, st.programme_id)
        req = _find_offering(db, _subject(db, r["requested_subject_code"]), _level(r["requested_level"], "requested_level"),
                             r.get("requested_block"), st.programme_id)
        if not db.scalar(select(M.StudentChoice).where(M.StudentChoice.student_id == st.id, M.StudentChoice.offering_id == cur.id,
                                                       M.StudentChoice.status == M.ChoiceStatus.APPROVED)):
            raise ValueError(f"{st.student_id} is not enrolled in {r['current_subject_code']} {cur.level}")
        db.flush()
        result = run_feasibility(db, get_student(db, st.id), cur.id, req.id)
        db.add(M.ChangeRequest(student_id=st.id, current_offering_id=cur.id, requested_offering_id=req.id,
                               reason=r.get("reason") or "", priority=_int(r.get("priority"), "priority", 3),
                               feasibility_status=result["status"], feasibility_reasons_json=json.dumps(result)))
        return "created"

    if kind == "preferences":
        st = _student(db, r["student_id"])
        prefs = []
        for rank, f in enumerate(PREF_FIELDS, start=1):
            v = (r.get(f) or "").strip()
            if not v:
                continue
            code, _, lv = v.partition(":")
            subj = _subject(db, code)
            lv = _level(lv, f) if lv else None
            if lv and lv not in subj.offered_levels.split(","):
                raise ValueError(f"{f}: {subj.name} is not offered at {lv}")
            prefs.append(M.StudentPreference(student_id=st.id, rank=rank, subject_id=subj.id, level=lv))
        for p in list(st.preferences):
            db.delete(p)
        db.flush()
        db.add_all(prefs)
        return "updated"

    raise ValueError(f"Unknown import type {kind}")


@router.post("/csv")
async def import_csv(
    type: str = Form(..., description="students | subjects | blocks | offerings | choices | change_requests | preferences"),
    file: UploadFile = File(...),
    mapping: str | None = Form(None, description='JSON {"CSV header": "field"}'),
    dry_run: bool = Form(False),
    skip_invalid: bool = Form(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
):
    if type not in SPECS:
        raise HTTPException(422, f"Unknown import type '{type}'")
    fields, required = SPECS[type]
    text = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    col_map = json.loads(mapping) if mapping else suggest_mapping(headers, fields)
    missing = [f for f in required if f not in col_map.values()]
    result = {"type": type, "headers": headers, "expected_fields": fields, "required_fields": required,
              "mapping": col_map, "total_rows": 0, "valid_rows": 0, "created": 0, "updated": 0,
              "errors": [], "preview": [], "committed": False}
    if missing:
        result["errors"].append({"row": 0, "message": f"Required columns not mapped: {', '.join(missing)}"})
        return result

    for i, raw in enumerate(reader, start=2):  # row 1 is the header
        row = {field: (raw.get(h) or "").strip() for h, field in col_map.items() if field}
        result["total_rows"] += 1
        if len(result["preview"]) < 5:
            result["preview"].append(row)
        empty = [f for f in required if not row.get(f)]
        if empty:
            result["errors"].append({"row": i, "message": f"Missing value for {', '.join(empty)}"})
            continue
        sp = db.begin_nested()
        try:
            outcome = import_row(db, type, row)
            db.flush()
            sp.commit()
            result["valid_rows"] += 1
            result[outcome] += 1
        except Exception as e:  # noqa: BLE001 - report any row-level failure to the user
            sp.rollback()
            msg = str(e.detail) if isinstance(e, HTTPException) else str(e).split("\n")[0]
            result["errors"].append({"row": i, "message": msg})

    if dry_run or (result["errors"] and not skip_invalid):
        db.rollback()
        return result
    if type == "choices":
        recompute_enrollment(db)
    audit.log(db, user.username, "CSV_IMPORT", type, file.filename,
              None, {k: result[k] for k in ("total_rows", "valid_rows", "created", "updated")})
    db.commit()
    result["committed"] = True
    return result


@router.get("/templates/{kind}", dependencies=[Depends(get_current_user)])
def template(kind: str):
    if kind not in SPECS:
        raise HTTPException(404, "Unknown template")
    return StreamingResponse(iter([",".join(SPECS[kind][0]) + "\n"]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}_template.csv"'})


@router.get("/specs", dependencies=[Depends(get_current_user)])
def specs():
    return {k: {"fields": f, "required": r} for k, (f, r) in SPECS.items()}
