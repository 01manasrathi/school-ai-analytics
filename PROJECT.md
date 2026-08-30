# School AI — Smart Attendance, Marks & Insights Platform

A complete, **open-source, local-first** school management system with an **agentic AI
assistant**. Built end-to-end with **FastAPI** (backend), **Streamlit** (frontend), **CSV
files** as the data store (no database, no Docker), and a **local Llama 3.1 model via Ollama**
for AI features. No paid APIs or cloud dependencies are used anywhere.

It combines ideas from three reference projects into one working system:
- Attendance tracking & role-based dashboards (inspired by `attendance-report`)
- An AI assistant with agentic tool-calling over live data (inspired by `attend-ops`)
- Weighted-grade report cards with comparison charts (inspired by `Automated Student Report
  Generator with Data Visualization`)

---

## 1. Architecture

```
                ┌─────────────────────┐
                │   Streamlit UI      │   http://localhost:8501
                │  (frontend/*.py)    │   Login, Dashboard, Students,
                │                     │   Attendance, Marks, Reports, AI Chat
                └──────────┬──────────┘
                           │ REST (requests + JWT bearer token)
                           ▼
                ┌─────────────────────┐
                │   FastAPI backend    │  http://127.0.0.1:8000  (/docs for Swagger UI)
                │  (backend/app/*.py)  │
                │  - auth (JWT/bcrypt) │
                │  - CRUD routers      │
                │  - analytics_service │
                │  - report_service    │───► PDF report cards (reportlab + matplotlib)
                │  - agent/ (AI)        │───► Ollama (local LLM, tool-calling loop)
                └──────────┬──────────┘
                           │ pandas read/write
                           ▼
                ┌─────────────────────┐
                │   data/*.csv         │  students, teachers, classes, subjects,
                │  (plain CSV files)   │  attendance, marks, users
                └─────────────────────┘
```

**Why this stack:**
- **CSV instead of a database** — every "table" is a CSV file under `data/`, read/written with
  pandas via a small generic CRUD layer (`backend/app/data_store.py`). Simple, inspectable,
  zero setup, and easy to open in Excel directly.
- **No Node.js / Docker** — the frontend is Streamlit (pure Python), so there's no npm/Node
  toolchain to install. Everything runs with just Python + pip.
- **Local LLM (Ollama + Llama 3.1 8B)** — the AI assistant calls a **local** model, so there's
  no API key, no cost, and no data leaves the machine.

---

## 2. Data model (CSV "tables" in `data/`)

| File | Key columns |
|---|---|
| `students.csv` | student_id, name, gender, dob, class_id, roll_no, parent_name, parent_contact, email |
| `teachers.csv` | teacher_id, name, email, phone, subject_specialization |
| `classes.csv` | class_id, class_name, section, class_teacher_id |
| `subjects.csv` | subject_id, subject_name, class_id, teacher_id |
| `attendance.csv` | id, student_id, class_id, date, status (Present/Absent/Late), marked_by |
| `marks.csv` | id, student_id, subject_id, exam_type (Test1/Test2/Final), marks_obtained, max_marks |
| `users.csv` | username, password_hash (bcrypt), role (admin/teacher/student), linked_id |

`backend/app/data_store.py` centralizes schemas + generic `read_table` / `append_row` /
`update_row` / `delete_row` helpers so every router uses the same access pattern.

---

## 3. Backend (FastAPI) — `backend/app/`

| Module | Responsibility |
|---|---|
| `config.py` | Paths, JWT secret/expiry, Ollama host/model, grading weights |
| `data_store.py` | CSV read/write/CRUD helpers |
| `auth.py` | bcrypt password hashing, JWT issue/verify, `require_roles()` dependency |
| `schemas.py` | Pydantic request models |
| `analytics_service.py` | Weighted grade calculation, dashboard KPIs, at-risk detection, attendance trends, class performance |
| `report_service.py` | Builds a per-student PDF report card (reportlab) with matplotlib bar/pie charts |
| `agent/tools.py` | Python functions exposed to the LLM as "tools" (get_student_marks, get_at_risk_students, etc.) + their JSON schemas |
| `agent/agent.py` | The **agentic loop**: sends the conversation + tool schemas to Ollama, executes any tool calls the model requests, feeds results back, repeats until a final answer |
| `routers/*` | REST endpoints: `/auth`, `/students`, `/teachers`, `/classes`, `/subjects`, `/attendance`, `/marks`, `/analytics`, `/reports`, `/ai` |

Role-based access control: **admin** (full access), **teacher** (manage students/attendance/marks
for their classes), **student** (read-only, own data only) — enforced via `auth.require_roles(...)`
on each route.

Explore the live API docs at **http://127.0.0.1:8000/docs** once the backend is running.

### The agentic AI workflow (`/ai/chat`)

This is the most "agentic" piece of the system. Rather than a single prompt-response call:

1. The user's question + a system prompt + a set of **tool schemas** (JSON function
   definitions) are sent to `llama3.1:8b` running in Ollama, using Ollama's native
   tool-calling API.
2. The model decides which tool(s) it needs (e.g. `get_at_risk_students`,
   `get_student_marks`, `generate_student_report_card`) and returns structured tool calls
   instead of guessing an answer.
3. The backend executes those Python functions against the **live CSV data**, and feeds the
   results back to the model as `tool` messages.
4. The loop repeats (up to 6 iterations) until the model has enough information and produces
   a final natural-language answer — grounded in real data, not hallucinated.

This means the assistant can answer things like *"Which students are at risk?"* or *"Generate
a report card for ST0001"* by actually querying and acting on your data, not just chatting.

---

## 4. Frontend (Streamlit) — `frontend/`

Multi-page Streamlit app (`app.py` + `pages/`):

| Page | Purpose |
|---|---|
| `app.py` | Login screen, session/token management |
| `1_Dashboard.py` | KPIs, attendance trend chart, at-risk table, class performance explorer (admin/teacher) |
| `2_Students.py` | Student directory, add/edit/delete |
| `3_Attendance.py` | Mark daily attendance per class, per-student history, trend charts |
| `4_Marks.py` | Bulk marks entry per class/subject/exam, per-student marks view |
| `5_Reports.py` | Generate & download PDF report cards |
| `6_AI_Assistant.py` | Chat UI for the agentic AI assistant, shows the tool calls it made |
| `7_Classes_and_Staff.py` | Manage classes, subjects, teachers, and create login users (admin only) |

`frontend/utils.py` wraps all API calls (adds the JWT bearer token, error handling) and holds
login/session-state helpers.

---

## 5. Setup & running

### Prerequisites
- Python 3.10+ (already installed)
- [Ollama](https://ollama.com) installed and running, with a model pulled:
  ```powershell
  ollama pull llama3.1:8b
  ```
  (No Node.js, no Docker, no database needed.)

### Install dependencies
```powershell
cd "school ai"
pip install -r requirements.txt
```

### Seed sample data (one-time, or re-run to reset)
```powershell
python seed_data.py
```
This creates ~98 students across 5 classes, 90 days of attendance history, marks for 3 exams
per subject, and 3 login accounts:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Teacher | `teacher1` | `teacher123` |
| Student | `student1` | `student123` |

### Run the backend
```powershell
.\start_backend.ps1
# or: cd backend; python -m uvicorn app.main:app --reload --port 8000
```

### Run the frontend (in a second terminal)
```powershell
.\start_frontend.ps1
# or: cd frontend; python -m streamlit run app.py --server.port 8501
```

Then open **http://localhost:8501** and log in with any demo account above.

---

## 6. Demo walkthrough

1. **Log in as `admin`.**
2. **Dashboard** — see total students/teachers/classes, overall attendance %, average marks %,
   an attendance trend chart, and a live list of at-risk students.
3. **Students** — search the directory, add a new student, assign them to a class.
4. **Attendance** — pick a class and date, mark each student Present/Absent/Late in one click,
   then check the "View by Student" and "Class Trend" tabs.
5. **Marks** — pick a class/subject/exam and bulk-enter marks for the whole class.
6. **Reports** — pick a student, click "Generate Report Card" to get a PDF with a weighted
   grade, subject-by-subject comparison bar chart vs. class average, and an attendance pie
   chart, then download it.
7. **AI Assistant** — ask natural-language questions such as:
   - *"Which students are at risk due to low attendance?"*
   - *"What are Riya Sharma's marks?"*
   - *"Show me class C1's performance."*
   - *"Generate a report card for ST0001."*

   Expand "Tool calls made by the agent" under each answer to see exactly which data-query
   functions the model invoked — this is the agentic workflow in action.
8. Log out and log back in as `teacher1` or `student1` to see the role-scoped views.

---

## 7. Key design decisions / trade-offs

- **CSV over SQL**: trivial to inspect/edit in Excel, zero infra, but not built for
  high-concurrency writes — fine for a single-school, single-admin deployment. A
  `threading.Lock` guards writes to avoid corrupting files under concurrent requests.
- **JWT auth with bcrypt-hashed passwords** stored in `users.csv` — no OAuth provider needed,
  but still real hashing (not plaintext) and expiring tokens.
- **Local LLM only** — every AI feature (chat assistant) runs against `llama3.1:8b` (or any
  other tool-capable Ollama model, configurable via the `SCHOOL_AI_MODEL` env var) so there's
  no dependency on paid APIs.
- **Streamlit instead of a JS framework** — avoids any Node.js/npm requirement while still
  giving a full interactive multi-page dashboard experience.

## 8. Possible extensions

- Excel (`.xlsx`) export/import buttons per table (openpyxl is already a dependency).
- Timetable management module (per the `attendance-report` reference project).
- Parent-facing portal / notifications.
- Swap `data_store.py`'s CSV backend for SQLite without touching the routers (the CRUD
  interface is already abstracted).
