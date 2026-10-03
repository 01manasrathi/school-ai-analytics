# Deployment guide

## The one thing to know before you start

**Streamlit Community Cloud cannot host the JavaScript app.** It runs exactly one command —
`streamlit run <file>.py` — inside a Python-only container. There is no Node.js runtime, no
`npm install`, and no way to serve a Next.js server there. No configuration file changes that.

So the two front ends have different homes:

| What you deploy | Entry point | Host | Cost |
|---|---|---|---|
| **Streamlit UI** (Python) | `streamlit_app.py` | **Streamlit Community Cloud** | free |
| **Next.js UI + FastAPI** (JS) | `frontend/` + `backend/` | **Render** (both, one blueprint) or **Vercel + Render** | free tier |

Both front ends run the same engines and the same database, so you lose no functionality by
deploying the Streamlit one — it is the same product with a Python-rendered UI.

---

## A. Streamlit Community Cloud (the Python app)

**The file you give Streamlit is `streamlit_app.py`** (repository root).

1. Push this repository to GitHub (see section C).
2. Go to https://share.streamlit.io → **New app** → select the repo and branch.
3. **Main file path:** `streamlit_app.py`
4. Open **Advanced settings** and pick a **Python version** — do this here, not via `runtime.txt`.
   Community Cloud frequently ignores `runtime.txt` and silently uses its newest supported Python,
   which is how most "it worked locally" build failures happen. 3.11, 3.12 and 3.13 all work.
5. *(Optional)* paste secrets — see below.
6. **Deploy.** The build installs the root `requirements.txt`.

On first start the app creates its schema and loads the demo data (60 existing students, 15 new
students, 5 change requests). Log in with **admin / admin123** or **viewer / viewer123**.

### Make the data persist (recommended)

Streamlit Cloud containers are **ephemeral**: the SQLite file is deleted whenever the app sleeps,
restarts or redeploys, and the demo data is regenerated. For real school data, attach PostgreSQL
(Neon, Supabase and Render all have free tiers):

1. Uncomment `psycopg2-binary>=2.9.9` in `requirements.txt`.
2. App → **Settings → Secrets**:
   ```toml
   DATABASE_URL = "postgresql+psycopg2://user:password@host:5432/ib_options"
   SECRET_KEY   = "a-long-random-string"
   ```
No code change needed: `backend/app/config.py` reads `DATABASE_URL`, and `streamlit_app.py` copies
it out of `st.secrets` at startup.

---

## B. The JavaScript app (Next.js + FastAPI)

### Option 1 — Render, both services from one file (easiest)

`render.yaml` in the repository root is a Render Blueprint that deploys **both** services and wires
them together automatically.

1. Push to GitHub.
2. https://dashboard.render.com → **New → Blueprint** → pick the repo.
3. Render reads `render.yaml`, creates `ib-allocation-api` (FastAPI) and `ib-allocation-web`
   (Next.js), and sets `BACKEND_URL` on the web service to the API's internal URL.
4. Open the `ib-allocation-web` URL.

Free Render instances sleep after inactivity and have an ephemeral disk, so the SQLite database
resets. Add a free Render PostgreSQL instance and set `DATABASE_URL` on the API service to keep data.

### Option 2 — Vercel (Next.js) + Render/Railway/Fly (FastAPI)

1. Deploy the API first on any Python host: start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT` with root directory `backend`.
2. On Vercel: **New Project** → this repo → **Root Directory = `frontend`** (Next.js is detected
   automatically; `frontend/vercel.json` holds the settings).
3. Vercel → Project → **Settings → Environment Variables**:
   `BACKEND_URL = https://your-api-host.onrender.com`
   `next.config.js` rewrites `/api/*` to that URL, so no CORS setup is needed.
4. Redeploy.

### Option 3 — Hugging Face Spaces (Docker)

A Space with SDK *docker* can run Node and Python in one container. Build the frontend
(`npm ci && npm run build`), then start uvicorn and `next start` together. Only worth it if you want
a single free URL for both.

---

## C. Push to GitHub

The working tree is already a git repository with a first commit and a `.gitignore` that excludes
`node_modules/`, `.venv/`, `*.db` and `.streamlit/secrets.toml`. Add your own remote and push:

```bash
cd C:/Users/mrathi/Desktop/CBSE_SCHOOL_PROJECT
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

Create `<your-repo>` on github.com first (empty — no README, no .gitignore). If git asks for a
password, use a **Personal Access Token** (github.com → Settings → Developer settings → Tokens),
not your account password.

---

## D. Dependencies

Two files, both verified to resolve with `pip install --dry-run` and with the backend test suite
green (37 passed):

| File | Used by | Contents |
|---|---|---|
| **`requirements.txt`** (root) | Streamlit Cloud, and any Python host | UI + backend libraries |
| `backend/requirements.txt` | REST API and `pytest` | the same core, plus test tools |

| Package | Range | Why |
|---|---|---|
| `streamlit` | `>=1.65,<2` | the UI; 1.65+ for `st.dataframe(width="stretch")` |
| `pandas` | `>=2.2` | tables in `st.dataframe` / `st.data_editor` |
| `SQLAlchemy` | `>=2.0.30,<2.1` | ORM; capped at the tested 2.0.x line |
| `alembic` | `>=1.13,<2` | migrations in `backend/alembic` |
| `pydantic` | `>=2.9,<3` | request models reused by the Streamlit pages |
| `fastapi` | `>=0.142,<1` | router/service layer imported directly by `streamlit_app.py` |
| `starlette` | `>=0.46,<2` | see the version note below |
| `uvicorn` | `>=0.30,<1` | only to run the REST API |
| `python-multipart` | `>=0.0.9` | only for `POST /api/import/csv` |
| `psycopg2-binary` | `>=2.9.9` | optional, PostgreSQL only |

No Node.js, no paid service and no external API are needed for the Streamlit deployment. SQLite is
part of Python.

### Version note worth keeping (this one bites)

Modern Streamlit runs on **Starlette** (`>=0.46,<2`). FastAPI **0.115.x** caps Starlette at `<0.42`,
so that combination is literally uninstallable — pip ends with `ResolutionImpossible`, and forcing
the old Starlette in anyway crashes at import:

```
TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'
```

The fix is to stay on **FastAPI >= 0.142**, which only requires `starlette>=0.46`. Do not pin
FastAPI backwards while Streamlit is in the same environment.

### Verify on a clean machine

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -c "import streamlit, pandas, sqlalchemy, fastapi, starlette; print('deps ok')"
.venv/Scripts/python -m streamlit run streamlit_app.py
```
