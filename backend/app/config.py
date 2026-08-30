"""Central configuration for the School AI backend.

Everything is file-based (CSV) as requested — no external database, no Docker.
"""
import os
from pathlib import Path

# Project root = school ai/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
CHARTS_DIR = REPORTS_DIR / "charts"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# CSV "tables"
STUDENTS_CSV = DATA_DIR / "students.csv"
TEACHERS_CSV = DATA_DIR / "teachers.csv"
CLASSES_CSV = DATA_DIR / "classes.csv"
SUBJECTS_CSV = DATA_DIR / "subjects.csv"
ATTENDANCE_CSV = DATA_DIR / "attendance.csv"
MARKS_CSV = DATA_DIR / "marks.csv"
USERS_CSV = DATA_DIR / "users.csv"

# Auth
JWT_SECRET = os.environ.get("SCHOOL_AI_JWT_SECRET", "dev-secret-change-me-school-ai-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 12  # 12 hours

# Ollama / LLM
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("SCHOOL_AI_MODEL", "llama3.1:8b")

# Grading weights (mirrors the referenced report-generator project)
EXAM_WEIGHTS = {"Test1": 0.3, "Test2": 0.3, "Final": 0.4}

ATTENDANCE_RISK_THRESHOLD = 75.0  # % below this is "at risk"
