"""Central configuration for the Student Analytics & Report Generator module.

Self-contained: reads/writes its own CSV dataset under `student_analytics/data/`.
It can optionally seed itself from the parent School AI `data/*.csv` files.
"""
from __future__ import annotations

import os
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent

DATA_DIR = MODULE_DIR / "data"
OUTPUT_DIR = MODULE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
EXPORTS_DIR = OUTPUT_DIR / "exports"
CACHE_DIR = MODULE_DIR / ".cache"

# The original School AI CSV store (used as an optional seed source)
SCHOOL_AI_DATA_DIR = PROJECT_ROOT / "data"

for _d in (DATA_DIR, OUTPUT_DIR, REPORTS_DIR, EXPORTS_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- CSV tables
STUDENTS_CSV = DATA_DIR / "students.csv"
CLASSES_CSV = DATA_DIR / "classes.csv"
SUBJECTS_CSV = DATA_DIR / "subjects.csv"
TEACHERS_CSV = DATA_DIR / "teachers.csv"
MARKS_CSV = DATA_DIR / "marks.csv"
ATTENDANCE_CSV = DATA_DIR / "attendance_monthly.csv"
ASSIGNMENTS_CSV = DATA_DIR / "assignments.csv"
SURVEY_CSV = DATA_DIR / "survey_responses.csv"

# Pre-computed analytics tables (built by generate_dataset.py)
MASTER_CSV = DATA_DIR / "master_student_subject.csv"   # 1 row per student x subject
SUMMARY_CSV = DATA_DIR / "student_summary.csv"         # 1 row per student
MASTER_XLSX = DATA_DIR / "master_student_analytics.xlsx"

# ------------------------------------------------------------- dataset shape
# Deliberately kept small so the whole repo stays lightweight and the app fits
# comfortably in a free-tier cloud container. Grades 8-10 only, 4 sections per
# grade per campus. Scale up locally with --students if you want more volume.
N_STUDENTS = int(os.environ.get("SA_N_STUDENTS", 1800))
GRADES = [8, 9, 10]
SECTIONS = ["A", "B", "C", "D"]
ACADEMIC_YEAR = "2025-26"

SUBJECT_CATALOG = [
    ("Mathematics", "Core"),
    ("Science", "Core"),
    ("English", "Language"),
    ("Social Studies", "Core"),
    ("Hindi", "Language"),
    ("Computer Science", "Elective"),
    ("Art & Craft", "Co-curricular"),
    ("Physical Education", "Co-curricular"),
]

EXAM_TYPES = ["Unit Test 1", "Mid Term", "Unit Test 2", "Final Exam"]

# Weighted grading (the "customizable weightages" idea from the report-generator project)
EXAM_WEIGHTS: dict[str, float] = {
    "Unit Test 1": 0.15,
    "Mid Term": 0.25,
    "Unit Test 2": 0.15,
    "Final Exam": 0.45,
}

# Overall subject score blend: exams + internal assignment work
ASSIGNMENT_WEIGHT = 0.20   # share of the final subject score from assignment/homework
EXAM_BLEND_WEIGHT = 0.80

# ------------------------------------------------------------------- grading
# (lower_bound_inclusive, letter, gpa, descriptor)
GRADE_BANDS = [
    (91, "A+", 10.0, "Outstanding"),
    (81, "A", 9.0, "Excellent"),
    (71, "B+", 8.0, "Very Good"),
    (61, "B", 7.0, "Good"),
    (51, "C+", 6.0, "Above Average"),
    (41, "C", 5.0, "Average"),
    (33, "D", 4.0, "Needs Improvement"),
    (0, "E", 0.0, "Critical - Intervention Needed"),
]

PASS_MARK_PCT = 33.0

# ------------------------------------------------------------------ analysis
ATTENDANCE_RISK_THRESHOLD = 75.0
TOPPER_PERCENTILE = 90        # >= this percentile in class => Topper
IMPROVEMENT_PERCENTILE = 25   # <= this percentile in class => Needs Improvement
TOP_N_DEFAULT = 10

# Composite risk weights (higher risk score = more concern)
RISK_WEIGHTS = {
    "low_score": 0.40,
    "low_attendance": 0.25,
    "negative_trend": 0.20,
    "low_submission": 0.15,
}

# ------------------------------------------------------------------ branding
SCHOOL_NAME = os.environ.get("SA_SCHOOL_NAME", "Springfield Public School")
PLOTLY_TEMPLATE = "plotly_white"
COLOR_SEQUENCE = [
    "#4C6FFF", "#00C2A8", "#FFB020", "#FF6B6B", "#845EF7",
    "#20C997", "#F76707", "#339AF0", "#E64980", "#82C91E",
]
BAND_COLORS = {
    "Topper": "#00A86B",
    "Above Average": "#4C6FFF",
    "Average": "#FFB020",
    "Needs Improvement": "#FF8C42",
    "At Risk": "#E03131",
}

# -------------------------------------------------------------- integrations
# Canvas LMS (https://canvas.instructure.com -> Account > Settings > New Access Token)
CANVAS_DOMAIN = os.environ.get("CANVAS_DOMAIN", "")          # e.g. https://canvas.instructure.com
CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
CANVAS_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")

# Google Forms / Sheets (Google Cloud Console -> service account JSON)
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_FORM_ID = os.environ.get("GOOGLE_FORM_ID", "")

# Optional local LLM for narrative insights (reuses the parent project's Ollama setup)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("SCHOOL_AI_MODEL", "llama3.1:8b")


def canvas_configured() -> bool:
    return bool(CANVAS_DOMAIN and CANVAS_API_TOKEN)


def google_configured() -> bool:
    return bool(GOOGLE_SERVICE_ACCOUNT_JSON and Path(GOOGLE_SERVICE_ACCOUNT_JSON).exists())
