"""Lightweight CSV-backed data access layer.

All "tables" are plain CSV files under /data. This module centralizes
schema definitions + generic CRUD helpers built on pandas so every router
reads/writes data the same way (single source of truth, easy to swap for a
real DB later without touching the routers much).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pandas as pd

from . import config

_LOCK = threading.Lock()

SCHEMAS: dict[str, list[str]] = {
    "students": [
        "student_id", "name", "gender", "dob", "class_id", "roll_no",
        "parent_name", "parent_contact", "email", "address", "enrollment_date",
    ],
    "teachers": [
        "teacher_id", "name", "email", "phone", "subject_specialization",
    ],
    "classes": [
        "class_id", "class_name", "section", "class_teacher_id",
    ],
    "subjects": [
        "subject_id", "subject_name", "class_id", "teacher_id",
    ],
    "attendance": [
        "id", "student_id", "class_id", "date", "status", "marked_by", "remarks",
    ],
    "marks": [
        "id", "student_id", "subject_id", "exam_type", "marks_obtained",
        "max_marks", "date",
    ],
    "users": [
        "username", "password_hash", "role", "full_name", "linked_id", "created_at",
    ],
}

_PATHS: dict[str, Path] = {
    "students": config.STUDENTS_CSV,
    "teachers": config.TEACHERS_CSV,
    "classes": config.CLASSES_CSV,
    "subjects": config.SUBJECTS_CSV,
    "attendance": config.ATTENDANCE_CSV,
    "marks": config.MARKS_CSV,
    "users": config.USERS_CSV,
}


def ensure_all_tables() -> None:
    for name, path in _PATHS.items():
        if not path.exists():
            pd.DataFrame(columns=SCHEMAS[name]).to_csv(path, index=False)


def read_table(name: str) -> pd.DataFrame:
    path = _PATHS[name]
    if not path.exists():
        return pd.DataFrame(columns=SCHEMAS[name])
    with _LOCK:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df


def write_table(name: str, df: pd.DataFrame) -> None:
    path = _PATHS[name]
    with _LOCK:
        df.to_csv(path, index=False)


def next_id(name: str, id_col: str, prefix: str = "") -> str:
    df = read_table(name)
    if df.empty or id_col not in df.columns:
        return f"{prefix}1"
    nums = []
    for v in df[id_col]:
        v = str(v).replace(prefix, "")
        if v.isdigit():
            nums.append(int(v))
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}{nxt}"


def append_row(name: str, row: dict[str, Any]) -> dict[str, Any]:
    df = read_table(name)
    with _LOCK:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_csv(_PATHS[name], index=False)
    return row


def update_row(name: str, key_col: str, key_val: str, updates: dict[str, Any]) -> bool:
    df = read_table(name)
    mask = df[key_col].astype(str) == str(key_val)
    if not mask.any():
        return False
    for k, v in updates.items():
        if k in df.columns:
            df.loc[mask, k] = v
    write_table(name, df)
    return True


def delete_row(name: str, key_col: str, key_val: str) -> bool:
    df = read_table(name)
    mask = df[key_col].astype(str) == str(key_val)
    if not mask.any():
        return False
    df = df[~mask]
    write_table(name, df)
    return True


def get_row(name: str, key_col: str, key_val: str) -> dict[str, Any] | None:
    df = read_table(name)
    mask = df[key_col].astype(str) == str(key_val)
    if not mask.any():
        return None
    return df[mask].iloc[0].to_dict()
