import json

from sqlalchemy.orm import Session

from . import models


def _dump(v) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, default=str)


def log(db: Session, user: str, action: str, entity: str, entity_id, old=None, new=None) -> None:
    """Add an audit entry to the current transaction (committed together with the change)."""
    db.add(models.AuditLog(user=user, action=action, entity=entity, entity_id=str(entity_id or ""),
                           old_value=_dump(old), new_value=_dump(new)))
