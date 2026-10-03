"""Plain data objects used by the engines (decoupled from SQLAlchemy so they can be unit tested)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class OfferingInfo:
    id: int
    subject_id: int
    subject_code: str
    subject_name: str
    group: int
    level: str
    block_id: int
    block_name: str
    capacity: int
    enrollment: int
    min_enrollment: int = 0
    is_active: bool = True
    subject_active: bool = True
    programme_id: int | None = None
    block_grade: str = ""
    block_period: str = ""
    block_max_choices: int = 1
    teacher: str = ""
    room: str = ""
    prerequisites: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.subject_name} {self.level}"


@dataclass
class BlockInfo:
    id: int
    name: str
    label: str = ""
    sort_order: int = 0
    period: str = ""
    max_choices: int = 1


@dataclass
class StudentInfo:
    id: int
    student_id: str
    name: str
    grade: int
    programme_id: int | None
    status: str = "EXISTING"
    priority: int = 100
    prior_subjects: list[str] = field(default_factory=list)
    # list of (rank, subject_code, level or None)
    preferences: list[tuple[int, str, str | None]] = field(default_factory=list)


def grade_matches(block_grade: str, grade: int) -> bool:
    """Block grade may be '', '11', '11-12' or '11,12'."""
    g = (block_grade or "").strip()
    if not g:
        return True
    for part in g.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= grade <= int(hi):
                return True
        elif part and int(part) == grade:
            return True
    return False


def offering_info(o) -> OfferingInfo:
    """Convert an ORM SubjectOffering (with subject & block loaded) to OfferingInfo."""
    try:
        prereq = json.loads(o.subject.prerequisites or "[]")
    except json.JSONDecodeError:
        prereq = [p.strip() for p in (o.subject.prerequisites or "").split(",") if p.strip()]
    return OfferingInfo(
        id=o.id, subject_id=o.subject_id, subject_code=o.subject.code, subject_name=o.subject.name,
        group=o.subject.ib_group, level=o.level, block_id=o.block_id, block_name=o.block.name,
        capacity=o.capacity, enrollment=o.current_enrollment, min_enrollment=o.min_enrollment,
        is_active=o.is_active, subject_active=o.subject.is_active, programme_id=o.block.programme_id,
        block_grade=o.block.grade or "", block_period=o.block.period or "",
        block_max_choices=o.block.max_choices_per_student or 1,
        teacher=o.teacher or "", room=o.room or "", prerequisites=prereq,
    )


def student_info(s) -> StudentInfo:
    return StudentInfo(
        id=s.id, student_id=s.student_id, name=s.name, grade=s.grade, programme_id=s.programme_id,
        status=s.status, priority=s.priority or 100,
        prior_subjects=[c.strip() for c in (s.prior_subjects or "").split(",") if c.strip()],
        preferences=[(p.rank, p.subject.code, p.level) for p in s.preferences],
    )
