"""Settings: rules, block structure, subjects and offerings (capacities). All writes are audited."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from .. import models as M
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..rules import RULE_TYPES
from ..services import get_offering, offering_dict, recompute_enrollment

router = APIRouter(prefix="/api", tags=["settings"])


def rule_dict(r: M.Rule) -> dict:
    return {"id": r.id, "programme_id": r.programme_id, "programme": r.programme.name if r.programme else "ALL",
            "rule_type": r.rule_type, "condition": json.loads(r.condition_json or "{}"), "value": r.value,
            "priority": r.priority, "is_active": r.is_active, "description": r.description}


def _snapshot(obj, fields):
    return {f: getattr(obj, f) for f in fields}


@router.get("/rules", dependencies=[Depends(get_current_user)])
def list_rules(db: Session = Depends(get_db)):
    return {"rule_types": RULE_TYPES,
            "rules": [rule_dict(r) for r in db.scalars(select(M.Rule).order_by(M.Rule.priority, M.Rule.id)).all()]}


class RuleIn(BaseModel):
    programme_id: int | None = None
    rule_type: str
    condition: dict = {}
    value: str = ""
    priority: int = 100
    is_active: bool = True
    description: str = ""


def _apply_rule(r: M.Rule, body: RuleIn):
    if body.rule_type not in RULE_TYPES:
        raise HTTPException(422, f"Unknown rule_type {body.rule_type}")
    r.programme_id, r.rule_type, r.condition_json = body.programme_id, body.rule_type, json.dumps(body.condition)
    r.value, r.priority, r.is_active, r.description = body.value, body.priority, body.is_active, body.description


@router.post("/rules")
def create_rule(body: RuleIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    r = M.Rule()
    _apply_rule(r, body)
    db.add(r)
    db.flush()
    audit.log(db, user.username, "RULE_CREATE", "Rule", r.id, None, body.model_dump())
    db.commit()
    return rule_dict(r)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    r = db.get(M.Rule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    old = rule_dict(r)
    _apply_rule(r, body)
    audit.log(db, user.username, "RULE_UPDATE", "Rule", r.id, old, body.model_dump())
    db.commit()
    return rule_dict(r)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    r = db.get(M.Rule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    audit.log(db, user.username, "RULE_DELETE", "Rule", r.id, rule_dict(r), None)
    db.delete(r)
    db.commit()
    return {"deleted": rule_id}


class OfferingIn(BaseModel):
    subject_id: int | None = None
    block_id: int | None = None
    level: str | None = None
    teacher: str | None = None
    room: str | None = None
    capacity: int | None = None
    min_enrollment: int | None = None
    is_active: bool | None = None


OFF_FIELDS = ["subject_id", "block_id", "level", "teacher", "room", "capacity", "min_enrollment", "is_active"]


@router.put("/offerings/{offering_id}")
def update_offering(offering_id: int, body: OfferingIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    o = get_offering(db, offering_id)
    old = _snapshot(o, OFF_FIELDS)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(o, k, v)
    if o.capacity < 0 or o.min_enrollment < 0:
        raise HTTPException(422, "Capacity / min enrollment must be >= 0")
    audit.log(db, user.username, "OFFERING_UPDATE", "SubjectOffering", o.id, old, _snapshot(o, OFF_FIELDS))
    db.commit()
    return offering_dict(get_offering(db, offering_id))


@router.post("/offerings")
def create_offering(body: OfferingIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    if not (body.subject_id and body.block_id and body.level):
        raise HTTPException(422, "subject_id, block_id and level are required")
    o = M.SubjectOffering(**{k: v for k, v in body.model_dump(exclude_none=True).items()})
    db.add(o)
    db.flush()
    audit.log(db, user.username, "OFFERING_CREATE", "SubjectOffering", o.id, None, body.model_dump())
    db.commit()
    return offering_dict(get_offering(db, o.id))


class BlockIn(BaseModel):
    name: str
    label: str = ""
    programme_id: int
    grade: str = ""
    period: str = ""
    max_choices_per_student: int = 1
    sort_order: int = 0
    notes: str = ""


BLOCK_FIELDS = list(BlockIn.model_fields.keys())


@router.post("/blocks")
def create_block(body: BlockIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    b = M.OptionBlock(**body.model_dump())
    db.add(b)
    db.flush()
    audit.log(db, user.username, "BLOCK_CREATE", "OptionBlock", b.id, None, body.model_dump())
    db.commit()
    return {"id": b.id, **body.model_dump()}


@router.put("/blocks/{block_id}")
def update_block(block_id: int, body: BlockIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    b = db.get(M.OptionBlock, block_id)
    if not b:
        raise HTTPException(404, "Block not found")
    old = _snapshot(b, BLOCK_FIELDS)
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    audit.log(db, user.username, "BLOCK_UPDATE", "OptionBlock", b.id, old, body.model_dump())
    db.commit()
    return {"id": b.id, **body.model_dump()}


@router.delete("/blocks/{block_id}")
def delete_block(block_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    b = db.get(M.OptionBlock, block_id)
    if not b:
        raise HTTPException(404, "Block not found")
    if db.scalar(select(func.count()).select_from(M.SubjectOffering).where(M.SubjectOffering.block_id == block_id)):
        raise HTTPException(409, "Block still has offerings - move or delete them first")
    audit.log(db, user.username, "BLOCK_DELETE", "OptionBlock", b.id, _snapshot(b, BLOCK_FIELDS), None)
    db.delete(b)
    db.commit()
    return {"deleted": block_id}


class SubjectIn(BaseModel):
    name: str | None = None
    ib_group: int | None = None
    offered_levels: str | None = None
    prerequisites: list[str] | None = None
    is_active: bool | None = None


@router.put("/subjects/{subject_id}")
def update_subject(subject_id: int, body: SubjectIn, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    s = db.get(M.Subject, subject_id)
    if not s:
        raise HTTPException(404, "Subject not found")
    fields = ["name", "ib_group", "offered_levels", "prerequisites", "is_active"]
    old = _snapshot(s, fields)
    data = body.model_dump(exclude_none=True)
    if "prerequisites" in data:
        data["prerequisites"] = json.dumps(data["prerequisites"])
    for k, v in data.items():
        setattr(s, k, v)
    audit.log(db, user.username, "SUBJECT_UPDATE", "Subject", s.id, old, _snapshot(s, fields))
    db.commit()
    return {"id": s.id, **_snapshot(s, fields)}


@router.post("/admin/recompute-enrollment")
def recompute(db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    changed = recompute_enrollment(db)
    audit.log(db, user.username, "RECOMPUTE_ENROLLMENT", "SubjectOffering", "*", None, {"changed": changed})
    db.commit()
    return {"offerings_changed": changed}
