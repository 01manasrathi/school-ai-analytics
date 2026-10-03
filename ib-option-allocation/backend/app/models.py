"""SQLAlchemy ORM models. Enum-like fields are stored as strings for SQLite/PostgreSQL portability."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudentStatus:
    EXISTING = "EXISTING"
    NEW = "NEW"
    WITHDRAWN = "WITHDRAWN"
    ALL = (EXISTING, NEW, WITHDRAWN)


class ChoiceStatus:
    REQUESTED = "requested"
    APPROVED = "approved"
    WAITLISTED = "waitlisted"
    REJECTED = "rejected"
    DROPPED = "dropped"  # kept for history after a change request / override moves the student


class ChoiceSource:
    EXISTING_ALLOCATION = "EXISTING_ALLOCATION"
    NEW_ALLOCATION = "NEW_ALLOCATION"
    CHANGE_REQUEST = "CHANGE_REQUEST"


class CRStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    WAITLISTED = "WAITLISTED"
    REJECTED = "REJECTED"
    OVERRIDDEN = "OVERRIDDEN"


class Role:
    ADMIN = "ADMIN"
    READONLY = "READONLY"


class Programme(Base):
    __tablename__ = "programmes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    grade_range: Mapped[str] = mapped_column(String(20), default="")


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    grade: Mapped[int] = mapped_column(Integer)
    programme_id: Mapped[int] = mapped_column(ForeignKey("programmes.id"))
    cohort_year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=StudentStatus.NEW, index=True)
    nationality: Mapped[str] = mapped_column(String(100), default="")
    language_profile: Mapped[str] = mapped_column(String(200), default="")
    prior_subjects: Mapped[str] = mapped_column(Text, default="")  # comma separated subject codes (for prerequisites)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = allocated first

    programme: Mapped[Programme] = relationship()
    choices: Mapped[list["StudentChoice"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    preferences: Mapped[list["StudentPreference"]] = relationship(
        back_populates="student", cascade="all, delete-orphan", order_by="StudentPreference.rank"
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    programme_id: Mapped[int] = mapped_column(ForeignKey("programmes.id"))
    ib_group: Mapped[int] = mapped_column(Integer)
    offered_levels: Mapped[str] = mapped_column(String(10), default="HL,SL")
    prerequisites: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of subject codes
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    programme: Mapped[Programme] = relationship()


class OptionBlock(Base):
    __tablename__ = "option_blocks"
    __table_args__ = (UniqueConstraint("programme_id", "grade", "name", name="uq_block"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(100), default="")
    programme_id: Mapped[int] = mapped_column(ForeignKey("programmes.id"))
    grade: Mapped[str] = mapped_column(String(20), default="")  # "11", "11-12" or "" (all grades)
    period: Mapped[str] = mapped_column(String(50), default="")
    max_choices_per_student: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    programme: Mapped[Programme] = relationship()


class SubjectOffering(Base):
    __tablename__ = "subject_offerings"
    __table_args__ = (UniqueConstraint("subject_id", "block_id", "level", name="uq_offering"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    block_id: Mapped[int] = mapped_column(ForeignKey("option_blocks.id"))
    level: Mapped[str] = mapped_column(String(2))
    teacher: Mapped[str] = mapped_column(String(100), default="")
    room: Mapped[str] = mapped_column(String(50), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=18)
    current_enrollment: Mapped[int] = mapped_column(Integer, default=0)
    min_enrollment: Mapped[int] = mapped_column(Integer, default=8)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    subject: Mapped[Subject] = relationship()
    block: Mapped[OptionBlock] = relationship()


class StudentChoice(Base):
    __tablename__ = "student_choices"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("subject_offerings.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=ChoiceStatus.APPROVED)
    source: Mapped[str] = mapped_column(String(30), default=ChoiceSource.EXISTING_ALLOCATION)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped[Student] = relationship(back_populates="choices")
    offering: Mapped[SubjectOffering] = relationship()


class StudentPreference(Base):
    __tablename__ = "student_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    level: Mapped[str | None] = mapped_column(String(2), nullable=True)

    student: Mapped[Student] = relationship(back_populates="preferences")
    subject: Mapped[Subject] = relationship()


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    current_offering_id: Mapped[int] = mapped_column(ForeignKey("subject_offerings.id"))
    requested_offering_id: Mapped[int] = mapped_column(ForeignKey("subject_offerings.id"))
    compensating_current_offering_id: Mapped[int | None] = mapped_column(ForeignKey("subject_offerings.id"), nullable=True)
    compensating_requested_offering_id: Mapped[int | None] = mapped_column(ForeignKey("subject_offerings.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default=CRStatus.PENDING, index=True)
    feasibility_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    feasibility_reasons_json: Mapped[str] = mapped_column(Text, default="{}")
    override_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    student: Mapped[Student] = relationship()
    current_offering: Mapped[SubjectOffering] = relationship(foreign_keys=[current_offering_id])
    requested_offering: Mapped[SubjectOffering] = relationship(foreign_keys=[requested_offering_id])
    compensating_current_offering: Mapped[SubjectOffering | None] = relationship(foreign_keys=[compensating_current_offering_id])
    compensating_requested_offering: Mapped[SubjectOffering | None] = relationship(foreign_keys=[compensating_requested_offering_id])


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    programme_id: Mapped[int | None] = mapped_column(ForeignKey("programmes.id"), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(50), index=True)
    condition_json: Mapped[str] = mapped_column(Text, default="{}")
    value: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")

    programme: Mapped[Programme | None] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default=Role.READONLY)
