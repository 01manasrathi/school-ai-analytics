# School AI — Management Platform + Student Analytics Dashboard

Two complementary, fully local Python applications in one repository. No database, no Docker,
no Node.js, and **no API keys required** to run anything.

| | App | Stack | Entry point |
|---|---|---|---|
| 1 | **School AI** — attendance, marks, report cards and an agentic AI assistant | FastAPI + Streamlit + CSV + local Llama 3.1 via Ollama | `backend/app/main.py`, `frontend/app.py` |
| 2 | **Student Analytics & Report Generator** — a single-screen class analytics dashboard | Streamlit + Plotly + pandas + reportlab | `student_analytics/dashboard/Home.py` |

📊 **[Student Analytics documentation →](student_analytics/README.md)**
🔑 **[Optional API setup (Canvas LMS, Google Forms) →](student_analytics/API_SETUP.md)**
📘 **[School AI architecture & walkthrough →](PROJECT.md)**

---

## Quick start

```powershell
pip install -r requirements.txt

# App 2 — the analytics dashboard (data is committed, runs immediately)
.\start_analytics_dashboard.ps1        # http://localhost:8502

# App 1 — the management system (two terminals)
python seed_data.py                    # one-time sample data + demo logins
.\start_backend.ps1                    # http://127.0.0.1:8000/docs
.\start_frontend.ps1                   # http://localhost:8501
```

Demo logins for App 1: `admin/admin123`, `teacher1/teacher123`, `student1/student123`.

---

## The Student Analytics dashboard

Built by merging two reference projects — an
[automated report-card generator](https://github.com/akramlodi/Automated-Student-Report-Generator-with-Data-Visualization)
and a [Canvas API grade tracker](https://github.com/jlouisbru/grade-tracking-Canvas-API) —
into one Plotly dashboard over a realistic 1,800-student dataset (grades 8–10, 4 campuses,
48 sections, 8 subjects, 4 exams, ~108,000 rows).

**Nine pages**, all sharing a grade → campus → section filter:

- **Home — Class Command Center**: everything for one standard on a single screen — KPIs,
  auto-written findings, toppers vs. students needing support, subject diagnostics, attendance,
  section league table, risk radar, and a live exam-weightage playground
- **Toppers & Improvement**, **Subject Analysis**, **Student Deep Dive**,
  **Attendance & Drivers**, **Report Cards** (batch PDF), **Data Explorer**,
  **Integrations**, **School Overview**

Highlights:

- **Weighted grading** with configurable per-exam weightages, recomputable live in the UI
- **Composite risk score** blending low marks, attendance, negative trend and missed
  assignments — so a student who is *falling* is distinguished from one who is merely *behind*
- **PDF report cards** with subject-vs-class comparison charts, generated singly or in batches
- **Realistic data**: each student has a hidden latent profile (ability, diligence, momentum,
  per-subject aptitude), so correlations and trends carry genuine signal rather than noise

### Verifying

```powershell
python -m student_analytics.smoke_test        # analytics + all 30 charts + PDF generation
python -m student_analytics.dashboard_test    # renders all 9 pages headlessly
```

### Deploying to Streamlit Community Cloud

Main file path `student_analytics/dashboard/Home.py`; dependencies come from the root
`requirements.txt`; the committed `.parquet` dataset (~1.4 MB) means no build-time data
generation. See [the deployment notes](student_analytics/README.md#deploying-to-streamlit-community-cloud).

---

## Repository layout

```
backend/            FastAPI app: auth, CRUD routers, analytics, PDF reports, AI agent
frontend/           Streamlit UI for the management system (port 8501)
data/               CSV "tables" for the management system (gitignored, run seed_data.py)
student_analytics/  the analytics dashboard — see its own README
  core/             grading, analytics, insights, charts, PDF generation
  integrations/     Canvas LMS + Google Forms/Sheets connectors (optional)
  dashboard/        Streamlit pages (port 8502)
  data/             dataset (.parquet committed; .csv/.xlsx generated)
```

## Notes

- Generated CSVs, Excel workbooks and PDFs are gitignored build outputs; only the small
  Parquet dataset is committed so clones and cloud deploys work out of the box.
- The Canvas LMS and Google Forms connectors are entirely optional. Every feature works on
  the generated dataset alone.
