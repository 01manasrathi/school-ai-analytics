"""Pydantic request/response models."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str


class StudentIn(BaseModel):
    name: str
    gender: str = ""
    dob: str = ""
    class_id: str
    roll_no: str = ""
    parent_name: str = ""
    parent_contact: str = ""
    email: str = ""
    address: str = ""
    enrollment_date: str = ""


class TeacherIn(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    subject_specialization: str = ""


class ClassIn(BaseModel):
    class_name: str
    section: str = ""
    class_teacher_id: str = ""


class SubjectIn(BaseModel):
    subject_name: str
    class_id: str
    teacher_id: str = ""


class AttendanceMark(BaseModel):
    student_id: str
    class_id: str
    date: str
    status: str  # Present / Absent / Late
    remarks: str = ""


class BulkAttendance(BaseModel):
    class_id: str
    date: str
    records: list[dict]  # [{student_id, status, remarks}]


class MarkIn(BaseModel):
    student_id: str
    subject_id: str
    exam_type: str
    marks_obtained: float
    max_marks: float = 100
    date: str = ""


class ChatMessage(BaseModel):
    message: str
    history: Optional[list[dict]] = None
