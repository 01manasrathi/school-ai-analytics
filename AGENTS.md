# AGENTS.md — School AI

Project overview and detailed workflow: see `PROJECT.md`.

There are two apps in this repo:
1. **School AI** — FastAPI + Streamlit management system (`backend/`, `frontend/`, `data/`).
2. **Student Analytics & Report Generator** — standalone analytics dashboard
   (`student_analytics/`). See `student_analytics/README.md`.

## Setup
```powershell
pip install -r requirements.txt
ollama pull llama3.1:8b   # if not already pulled
python seed_data.py       # generates data/*.csv sample data + demo login users
```
The analytics dataset ships as committed `.parquet` files, so no generation step is needed.
Rebuild it (plus the CSV/Excel copies) only if you change the generator:
```powershell
python -m student_analytics.generate_dataset            # 1,800 students, grades 8-10
python -m student_analytics.generate_dataset --no-excel # much faster; skips the workbook
```

## Run
```powershell
.\start_backend.ps1               # FastAPI on http://127.0.0.1:8000 (docs at /docs)
.\start_frontend.ps1              # Streamlit on http://localhost:8501 (second terminal)
.\start_analytics_dashboard.ps1   # Analytics dashboard on http://localhost:8502
```

## Verify
```powershell
python -m student_analytics.smoke_test       # analytics + all Plotly charts + 3 PDFs
python -m student_analytics.dashboard_test   # renders all 9 dashboard pages headlessly
```
Run both after touching anything under `student_analytics/`.

## Demo logins (created by seed_data.py)
- admin / admin123
- teacher1 / teacher123
- student1 / student123

## Notes
- All data lives in `data/*.csv` and `student_analytics/data/*.csv` — no database, no Docker,
  no Node.js.
- The analytics module is self-contained: it reads its own dataset and does not need the
  FastAPI backend or a login. Only `student_analytics/data/*.parquet` is committed (~1.4 MB);
  the CSV and `.xlsx` copies are gitignored build outputs. `core/loader.py` prefers Parquet and
  falls back to CSV, and the dashboard self-generates if neither exists.
- Writing the Excel workbook dominates generation time; pass `--no-excel` when iterating.
- Streamlit Cloud entry point is `student_analytics/dashboard/Home.py`; it installs
  `student_analytics/dashboard/requirements.txt` (Cloud prefers a requirements file next to the
  entrypoint over the root one).
- Requirements use version floors (`>=`), not exact pins, on purpose. Streamlit Cloud defaults
  to Python 3.14 and ignores `runtime.txt`/`.python-version`, so older exact pins have no cp314
  wheel and trigger a source build that fails (`command 'cmake' failed` for pyarrow). Floors:
  `pyarrow>=22`, `pandas>=2.3.3`, `numpy>=2.3.2`. Verify any pin change against the newest
  resolvable versions, not just the locally installed ones.
- After regenerating, clear the Streamlit cache (⋮ menu → Clear cache → Rerun); the dataset is
  held in `@st.cache_resource`.
- No API keys are required for any feature. Canvas LMS / Google Forms connectors are optional
  and live in `student_analytics/integrations/` — credential steps are in
  `student_analytics/API_SETUP.md`.
- Streamlit 1.52 deprecates `use_container_width`; use `width="stretch"` in new dashboard code.
- AI assistant uses local Ollama model `llama3.1:8b` (configurable via `SCHOOL_AI_MODEL` env var).
- If backend routers change, restart uvicorn (or use `--reload`, already default in start_backend.ps1).
- The bcrypt/passlib version-detection warning on startup ("(trapped) error reading bcrypt
  version") is harmless and does not affect password hashing/verification.
