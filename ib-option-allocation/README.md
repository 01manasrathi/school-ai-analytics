# IB Option Allocation & Change Feasibility Tool

A local web app for an IB/IGCSE school timetabler:

1. Load returning (EXISTING) students' IB option choices.
2. Allocate options to NEW students from the remaining seats, following every rule.
3. Test whether a requested option change is feasible: **FEASIBLE / FEASIBLE_WAITLIST / NOT_FEASIBLE / NEEDS_OVERRIDE**, with reasons.
4. Admin override (reason required, audited).
5. CSV import and CSV reports.

Everything runs **on your own machine**: SQLite database file, no cloud services, no paid APIs.

| Part | Tech | Folder | URL |
|---|---|---|---|
| **Streamlit UI** (deployable) | Python · Streamlit | `streamlit_app.py` | http://localhost:8501 |
| Backend API | Python 3.11+ · FastAPI · SQLAlchemy · Alembic · SQLite (PostgreSQL-ready) | `backend/` | http://127.0.0.1:8000 (Swagger docs at `/docs`) |
| Frontend UI | Next.js 14 · TypeScript · Tailwind CSS | `frontend/` | http://localhost:3000 |

**Two front ends, one backend.** Both read the same database and call the same rule engines.
Use the Streamlit app if you want a single command and a one-click cloud deploy; use the Next.js app
for the richer browser UI. See **[DEPLOYMENT.md](DEPLOYMENT.md)** for deployment (Streamlit Cloud, Render, Vercel)
and the full dependency table.

### Quick start (Streamlit — no Node.js needed)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The schema and demo data are created on first start. Log in with `admin` / `admin123`.

> For a detailed explanation of how every part works (APIs, engines, rules, data model), read **[GUIDE.md](GUIDE.md)**.

---

## Do I need to install JavaScript?

You don't install "JavaScript" itself, but the **frontend needs Node.js** (which includes `npm`). The backend needs **Python**.

- Node.js 18.17+ (you have v22 ✔) → https://nodejs.org
- Python 3.11+ (you have 3.13 ✔) → https://python.org

If you only want the API (no UI), Python alone is enough: open http://127.0.0.1:8000/docs and use the interactive Swagger UI.

---

## Setup (first time)

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows (Git Bash):   source .venv/Scripts/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# macOS/Linux:          source .venv/bin/activate
pip install -r requirements.txt

python -m app.seed          # runs migrations + loads the dummy data (WIPES existing data)
```

### 2. Frontend

```bash
cd frontend
npm install
```

> **Corporate network / SSL error** (`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`)? Tell Node to trust the Windows certificate store for that command:
> PowerShell: `$env:NODE_OPTIONS="--use-system-ca"; npm install` · Git Bash: `NODE_OPTIONS=--use-system-ca npm install`
>
> **Why Next.js is pinned to 14.2.33:** the registry reachable from this machine publishes the native SWC compiler binary
> (`@next/swc-win32-x64-msvc`) only up to 14.2.33, and Next cannot start without a matching binary. 14.2.33 carries a
> published security advisory, which is acceptable for a tool bound to `localhost`, but **upgrade when your network allows it**:
> `npm install next@latest @next/swc-win32-x64-msvc@latest` (then delete `frontend/.next` and restart). If `npm install`
> ever reports `Attempted to load @next/swc-...` or `ETARGET`, the two versions are out of step — install both at the same version.

## Run (every time) — two terminals

```bash
# Terminal 1 – API
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000      # macOS/Linux: .venv/bin/python ...

# Terminal 2 – UI
cd frontend
npm run dev
```

Open http://localhost:3000 and log in:

| User | Password | Role |
|---|---|---|
| `admin` | `admin123` | Admin / Timetabler (full access) |
| `viewer` | `viewer123` | Read-only |

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

37 tests cover: same-block swap, cross-block conflict, compensating swap, full class → waitlist, over-capacity, HL/SL violation, group violation, duplicate subject, prerequisites, min-enrollment warning, new-student allocation (preferences, capacity, no seats → waitlist, configurable HL/SL, impossible rules, priority order), allocation commit, approve/waitlist/override flows, audit log, roles, CSV import and CSV reports.

---

## Seed data (what you get out of the box)

- Programmes IGCSE (7-10) and IBDP (11-12); 7 IBDP option blocks A-G; 27 subjects; 50 offerings (one per subject per level). Capacity 18 / min 8 (Maths 20 so that 75 students fit – editable in Settings).
- **60 EXISTING** Grade 11 students (S1001–S1060), programmatically allocated with 4 HL + 3 SL, one subject per block, full group coverage. Chemistry HL is deliberately full (18/18).
- **15 NEW** students (S2001–S2015), no choices; 10 of them have ranked preferences.
- **5 pending change requests**:

| Student | Request | Expected result |
|---|---|---|
| S1020 | Psychology HL → Economics HL (same block C) | FEASIBLE |
| S1021 | Visual Arts SL (F) → Film SL (G) + compensating Geography SL (G) → Music SL (F) | FEASIBLE (warning: Visual Arts SL drops below min) |
| S1022 | Biology HL → Chemistry HL (full) | FEASIBLE_WAITLIST |
| S1023 | Geography SL (G) → Computer Science SL (F) – cross-block | NOT_FEASIBLE (block conflict) |
| S1024 | History HL → History SL | NEEDS_OVERRIDE (3 HL / 4 SL) |

Re-run `python -m app.seed` at any time to reset to this state.

---

## CSV import

UI: **Import CSV** page → pick a type → choose file → **Validate (dry run)** → adjust column mapping → **Import**.
Import is all-or-nothing unless you tick *Skip invalid rows*. Templates: *Download template* button, or the ready-made examples in [`sample_csv/`](sample_csv).

Recommended import order (each depends on the previous): **blocks → subjects → offerings → students → existing choices → new-student preferences → change requests**.

| Type | File example | Required columns | Notes |
|---|---|---|---|
| `blocks` | `blocks.csv` | name, programme | grade e.g. `11-12`; blocks with the same `period` clash |
| `subjects` | `subjects.csv` | code, name, programme, ib_group | `hl`/`sl` = Y/N; `prerequisites` = codes separated by `;` |
| `offerings` | `offerings.csv` | subject_code, block, programme, level | capacity default 18, min 8 |
| `students` | `students.csv` | student_id, name, grade, programme, cohort_year | status EXISTING/NEW/WITHDRAWN; `prior_subjects` for prerequisites; `priority` (lower = allocated first) |
| `choices` | `existing_choices.csv` | student_id, subject_code, level | `block` optional; enrollment is recalculated after import |
| `preferences` | `new_student_preferences.csv` | student_id | `preference_1` … `preference_7` as `CODE:HL`, `CODE:SL` or `CODE` |
| `change_requests` | `change_requests.csv` | student_id, current_subject_code, current_level, requested_subject_code, requested_level | feasibility is computed on import |

Rows are upserted by natural key (student_id, subject code, block name…), so re-importing a file updates instead of duplicating.

Via API (curl):

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -X POST localhost:8000/api/import/csv -H "Authorization: Bearer $TOKEN" \
  -F type=students -F file=@sample_csv/students.csv -F dry_run=true
```

---

## Switching to PostgreSQL

```bash
pip install psycopg2-binary
export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/ib_options   # PowerShell: $env:DATABASE_URL="..."
python -m app.seed
```

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/ib_options.db` | Database connection |
| `SECRET_KEY` | `local-dev-secret-change-me` | Signs login tokens – change it if other people use the machine |
| `TOKEN_TTL_HOURS` | `12` | Login session length |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed browser origins for direct API calls |
| `BACKEND_URL` (frontend) | `http://127.0.0.1:8000` | Where Next.js proxies `/api/*` |

## Project layout

```
backend/
  app/
    main.py            FastAPI app + router registration
    models.py          SQLAlchemy tables (Programme, Student, Subject, OptionBlock, SubjectOffering,
                       StudentChoice, StudentPreference, ChangeRequest, Rule, AuditLog, User)
    rules.py           Rule table -> RuleSet (+ default IB rules)
    engines/           Pure logic: validation.py, feasibility.py, allocation.py
    services.py        DB helpers shared by routers (load data, apply swaps, recompute enrollment)
    routers/           One file per API area
    seed.py            Dummy data generator
  alembic/versions/    Migrations
  tests/               pytest suite
frontend/
  app/<page>/page.tsx  UI pages
  components/          Nav, auth, shared UI (badges, block grid, feasibility card)
  lib/api.ts           fetch wrapper
sample_csv/            CSV templates with example rows
GUIDE.md               Detailed explanation of everything
```
