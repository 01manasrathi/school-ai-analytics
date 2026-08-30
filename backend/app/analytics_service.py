"""Business logic for dashboards, trends and grade computation.

Kept separate from the FastAPI routers so both the /analytics endpoints
and the PDF report generator / AI agent tools can reuse the same logic.
"""
from __future__ import annotations

import pandas as pd

from . import config, data_store


def calculate_final_grade(weighted_pct: float) -> str:
    if weighted_pct >= 90:
        return "A+"
    if weighted_pct >= 75:
        return "A"
    if weighted_pct >= 60:
        return "B"
    if weighted_pct >= 40:
        return "C"
    return "D (Needs Improvement)"


def student_weighted_score(marks_df: pd.DataFrame, student_id: str, subject_id: str) -> float | None:
    """Weighted % score for one student in one subject using config.EXAM_WEIGHTS."""
    sub = marks_df[(marks_df["student_id"] == student_id) & (marks_df["subject_id"] == subject_id)]
    if sub.empty:
        return None
    total_weight = 0.0
    weighted_sum = 0.0
    for exam, weight in config.EXAM_WEIGHTS.items():
        row = sub[sub["exam_type"] == exam]
        if row.empty:
            continue
        pct = float(row.iloc[0]["marks_obtained"]) / float(row.iloc[0]["max_marks"]) * 100
        weighted_sum += pct * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


def attendance_pct_for_student(att_df: pd.DataFrame, student_id: str) -> float:
    df = att_df[att_df["student_id"] == student_id]
    if df.empty:
        return 0.0
    present = df["status"].isin(["Present", "Late"]).sum()
    return round(present / len(df) * 100, 2)


def dashboard_summary() -> dict:
    students = data_store.read_table("students")
    teachers = data_store.read_table("teachers")
    classes = data_store.read_table("classes")
    attendance = data_store.read_table("attendance")
    marks = data_store.read_table("marks")

    if not attendance.empty:
        attendance = attendance.copy()
        attendance["is_present"] = attendance["status"].isin(["Present", "Late"])
        overall_attendance_pct = round(attendance["is_present"].mean() * 100, 2)
    else:
        overall_attendance_pct = 0.0

    if not marks.empty:
        m = marks.copy()
        m["marks_obtained"] = pd.to_numeric(m["marks_obtained"], errors="coerce")
        m["max_marks"] = pd.to_numeric(m["max_marks"], errors="coerce")
        m["pct"] = m["marks_obtained"] / m["max_marks"] * 100
        avg_marks_pct = round(m["pct"].mean(), 2)
    else:
        avg_marks_pct = 0.0

    at_risk = at_risk_students()

    return {
        "total_students": len(students),
        "total_teachers": len(teachers),
        "total_classes": len(classes),
        "overall_attendance_pct": overall_attendance_pct,
        "avg_marks_pct": avg_marks_pct,
        "at_risk_count": len(at_risk),
        "at_risk_students": at_risk[:10],
    }


def at_risk_students(threshold: float = config.ATTENDANCE_RISK_THRESHOLD) -> list[dict]:
    students = data_store.read_table("students")
    attendance = data_store.read_table("attendance")
    marks = data_store.read_table("marks")

    results = []
    if not marks.empty:
        marks = marks.copy()
        marks["marks_obtained"] = pd.to_numeric(marks["marks_obtained"], errors="coerce")
        marks["max_marks"] = pd.to_numeric(marks["max_marks"], errors="coerce")
        marks["pct"] = marks["marks_obtained"] / marks["max_marks"] * 100

    for _, s in students.iterrows():
        sid = s["student_id"]
        att_pct = attendance_pct_for_student(attendance, sid) if not attendance.empty else 0.0
        avg_pct = None
        if not marks.empty:
            sm = marks[marks["student_id"] == sid]
            if not sm.empty:
                avg_pct = round(sm["pct"].mean(), 2)
        reasons = []
        if att_pct < threshold:
            reasons.append(f"Low attendance ({att_pct}%)")
        if avg_pct is not None and avg_pct < 40:
            reasons.append(f"Failing average ({avg_pct}%)")
        if reasons:
            results.append({
                "student_id": sid,
                "name": s["name"],
                "class_id": s["class_id"],
                "attendance_pct": att_pct,
                "avg_marks_pct": avg_pct,
                "reasons": reasons,
            })
    results.sort(key=lambda r: r["attendance_pct"])
    return results


def attendance_trend(class_id: str | None = None, days: int = 30) -> list[dict]:
    attendance = data_store.read_table("attendance")
    if attendance.empty:
        return []
    df = attendance.copy()
    if class_id:
        df = df[df["class_id"] == class_id]
    df["is_present"] = df["status"].isin(["Present", "Late"])
    grouped = df.groupby("date")["is_present"].mean().reset_index()
    grouped["attendance_pct"] = (grouped["is_present"] * 100).round(2)
    grouped = grouped.sort_values("date").tail(days)
    return grouped[["date", "attendance_pct"]].to_dict(orient="records")


def class_performance(class_id: str) -> dict:
    students = data_store.read_table("students")
    students = students[students["class_id"] == class_id]
    subjects = data_store.read_table("subjects")
    subjects = subjects[subjects["class_id"] == class_id]
    marks = data_store.read_table("marks")
    attendance = data_store.read_table("attendance")

    subject_avgs = []
    if not marks.empty and not subjects.empty:
        m = marks.copy()
        m["marks_obtained"] = pd.to_numeric(m["marks_obtained"], errors="coerce")
        m["max_marks"] = pd.to_numeric(m["max_marks"], errors="coerce")
        m["pct"] = m["marks_obtained"] / m["max_marks"] * 100
        for _, sub in subjects.iterrows():
            sm = m[m["subject_id"] == sub["subject_id"]]
            avg = round(sm["pct"].mean(), 2) if not sm.empty else None
            subject_avgs.append({"subject_id": sub["subject_id"], "subject_name": sub["subject_name"], "avg_pct": avg})

    student_rankings = []
    if not marks.empty:
        m = marks.copy()
        m["marks_obtained"] = pd.to_numeric(m["marks_obtained"], errors="coerce")
        m["max_marks"] = pd.to_numeric(m["max_marks"], errors="coerce")
        m["pct"] = m["marks_obtained"] / m["max_marks"] * 100
        for _, s in students.iterrows():
            sid = s["student_id"]
            sm = m[m["student_id"] == sid]
            avg = round(sm["pct"].mean(), 2) if not sm.empty else None
            att_pct = attendance_pct_for_student(attendance, sid) if not attendance.empty else 0.0
            student_rankings.append({
                "student_id": sid, "name": s["name"], "avg_marks_pct": avg, "attendance_pct": att_pct,
            })
        student_rankings.sort(key=lambda r: (r["avg_marks_pct"] is None, -(r["avg_marks_pct"] or 0)))

    return {
        "class_id": class_id,
        "student_count": len(students),
        "subject_averages": subject_avgs,
        "student_rankings": student_rankings,
    }
