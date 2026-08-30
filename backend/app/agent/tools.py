"""Tools exposed to the local LLM agent.

Each tool is a plain Python function operating on the CSV data store. The
agent (agent.py) exposes these to Ollama's tool-calling API so the model
can decide which ones to call, in a loop, to answer natural-language
questions about the school (agentic RAG-over-CSV workflow).
"""
from __future__ import annotations

import json

import pandas as pd

from .. import analytics_service, data_store, report_service


def get_dashboard_summary() -> dict:
    """Get school-wide summary stats: total students/teachers/classes, overall attendance %, average marks %, and count of at-risk students."""
    return analytics_service.dashboard_summary()


def get_at_risk_students(threshold: float = 75.0) -> list:
    """List students considered at-risk because of low attendance (below threshold %) or failing average marks (below 40%)."""
    return analytics_service.at_risk_students(float(threshold))


def get_student_info(student_id: str = "", name: str = "") -> dict:
    """Look up a student's profile by student_id or by (partial, case-insensitive) name. Returns basic info including class_id."""
    df = data_store.read_table("students")
    if student_id:
        row = data_store.get_row("students", "student_id", student_id)
        return row or {"error": f"No student with id {student_id}"}
    if name:
        matches = df[df["name"].str.contains(name, case=False, na=False)]
        if matches.empty:
            return {"error": f"No student matching name '{name}'"}
        return matches.to_dict(orient="records")
    return {"error": "Provide student_id or name"}


def get_student_attendance(student_id: str) -> dict:
    """Get a student's attendance summary: total days, present, absent, late counts and attendance percentage."""
    attendance = data_store.read_table("attendance")
    pct = analytics_service.attendance_pct_for_student(attendance, student_id)
    df = attendance[attendance["student_id"] == student_id]
    return {
        "student_id": student_id,
        "attendance_pct": pct,
        "total_days": int(len(df)),
        "present": int((df["status"] == "Present").sum()) if not df.empty else 0,
        "absent": int((df["status"] == "Absent").sum()) if not df.empty else 0,
        "late": int((df["status"] == "Late").sum()) if not df.empty else 0,
    }


def get_student_marks(student_id: str) -> list:
    """Get all marks/grades for a student across subjects and exams, including weighted subject percentages."""
    marks = data_store.read_table("marks")
    marks = marks.copy()
    marks["marks_obtained"] = pd.to_numeric(marks["marks_obtained"], errors="coerce")
    marks["max_marks"] = pd.to_numeric(marks["max_marks"], errors="coerce")
    subjects = data_store.read_table("subjects")
    student_marks = marks[marks["student_id"] == student_id]
    result = []
    for sid in student_marks["subject_id"].unique():
        sub_row = subjects[subjects["subject_id"] == sid]
        subj_name = sub_row.iloc[0]["subject_name"] if not sub_row.empty else sid
        weighted = analytics_service.student_weighted_score(marks, student_id, sid)
        exams = student_marks[student_marks["subject_id"] == sid][
            ["exam_type", "marks_obtained", "max_marks"]
        ].to_dict(orient="records")
        result.append({
            "subject": subj_name, "weighted_pct": weighted,
            "grade": analytics_service.calculate_final_grade(weighted) if weighted is not None else "N/A",
            "exams": exams,
        })
    return result


def get_class_performance(class_id: str) -> dict:
    """Get a class's performance summary: per-subject averages and a ranked list of students by average marks and attendance."""
    return analytics_service.class_performance(class_id)


def get_attendance_trend(class_id: str = "", days: int = 30) -> list:
    """Get the daily attendance percentage trend for the whole school or one class over the last N days."""
    return analytics_service.attendance_trend(class_id or None, int(days))


def list_classes() -> list:
    """List all classes/sections in the school with their IDs and class teacher."""
    return data_store.read_table("classes").to_dict(orient="records")


def list_students_in_class(class_id: str) -> list:
    """List all students (id, name, roll_no) belonging to a given class_id."""
    df = data_store.read_table("students")
    df = df[df["class_id"] == class_id]
    return df[["student_id", "name", "roll_no"]].to_dict(orient="records")


def generate_student_report_card(student_id: str) -> dict:
    """Generate a PDF report card for a student (grades, class comparison chart, attendance). Returns the file path."""
    path = report_service.generate_student_report(student_id)
    return {"status": "generated", "path": path}


# Registry used by the agent to build the Ollama tool schema + dispatch calls.
TOOL_FUNCTIONS = {
    "get_dashboard_summary": get_dashboard_summary,
    "get_at_risk_students": get_at_risk_students,
    "get_student_info": get_student_info,
    "get_student_attendance": get_student_attendance,
    "get_student_marks": get_student_marks,
    "get_class_performance": get_class_performance,
    "get_attendance_trend": get_attendance_trend,
    "list_classes": list_classes,
    "list_students_in_class": list_students_in_class,
    "generate_student_report_card": generate_student_report_card,
}


def _py_type_to_json_schema(value) -> dict:
    return {"type": "string"}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_summary",
            "description": get_dashboard_summary.__doc__,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_at_risk_students",
            "description": get_at_risk_students.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"threshold": {"type": "number", "description": "Attendance % threshold (default 75)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_info",
            "description": get_student_info.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "Exact student ID, e.g. ST0001"},
                    "name": {"type": "string", "description": "Full or partial student name"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_attendance",
            "description": get_student_attendance.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"student_id": {"type": "string", "description": "Student ID"}},
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_marks",
            "description": get_student_marks.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"student_id": {"type": "string", "description": "Student ID"}},
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_class_performance",
            "description": get_class_performance.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"class_id": {"type": "string", "description": "Class ID, e.g. C1"}},
                "required": ["class_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_trend",
            "description": get_attendance_trend.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "class_id": {"type": "string", "description": "Optional class ID to filter"},
                    "days": {"type": "integer", "description": "Number of recent days (default 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_classes",
            "description": list_classes.__doc__,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_students_in_class",
            "description": list_students_in_class.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"class_id": {"type": "string", "description": "Class ID, e.g. C1"}},
                "required": ["class_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_student_report_card",
            "description": generate_student_report_card.__doc__,
            "parameters": {
                "type": "object",
                "properties": {"student_id": {"type": "string", "description": "Student ID"}},
                "required": ["student_id"],
            },
        },
    },
]


def call_tool(name: str, arguments: dict) -> str:
    """Dispatch a tool call by name and return a JSON string result."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool '{name}'"})
    try:
        result = fn(**arguments)
        return json.dumps(result, default=str)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})
