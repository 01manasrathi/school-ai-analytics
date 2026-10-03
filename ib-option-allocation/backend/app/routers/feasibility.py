from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..services import get_student, run_feasibility

router = APIRouter(prefix="/api/feasibility", tags=["feasibility"], dependencies=[Depends(get_current_user)])


class FeasibilityIn(BaseModel):
    student_id: str  # school student_id ("S1001") or DB id
    current_offering_id: int
    requested_offering_id: int
    compensating_current_offering_id: int | None = None
    compensating_requested_offering_id: int | None = None


@router.post("/check")
def check(body: FeasibilityIn, db: Session = Depends(get_db)):
    """Live what-if check. Read-only: never changes data."""
    s = get_student(db, body.student_id)
    return run_feasibility(db, s, body.current_offering_id, body.requested_offering_id,
                           body.compensating_current_offering_id, body.compensating_requested_offering_id)
