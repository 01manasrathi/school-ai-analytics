# Project notes for agents

IB Option Allocation & Change Feasibility Tool — FastAPI backend (`backend/`) + Next.js 14 frontend (`frontend/`).
All logic lives in the backend; the frontend only renders. See `GUIDE.md` for the full architecture.

## Commands (Windows, Git Bash)

```bash
# Streamlit UI (from repo root) — the deployable front end, imports backend/app directly
backend/.venv/Scripts/python -m streamlit run streamlit_app.py --server.port 8501

# Backend (from backend/)
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m app.seed                                  # migrate + reload dummy data (wipes DB)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000  # API on 127.0.0.1:8000, docs at /docs
.venv/Scripts/python -m pytest -q                                 # 37 tests, ~11s
.venv/Scripts/python -m alembic revision --autogenerate -m "msg"   # after editing models.py
.venv/Scripts/python -m alembic upgrade head

# Frontend (from frontend/)
npm run dev        # http://localhost:3000, proxies /api/* to 127.0.0.1:8000
npm run build
```

## Environment gotchas on this machine

- **Corporate TLS proxy**: `npm` fails with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` unless `NODE_OPTIONS=--use-system-ca` is set.
  Large installs also hit `ECONNRESET`; use `--maxsockets=1 --fetch-retries=8 --fetch-timeout=900000`. Never set
  `strict-ssl=false` or `NODE_TLS_REJECT_UNAUTHORIZED=0`.
- Avoid `npm --prefer-offline`: stale cached metadata causes bogus `ETARGET` errors.
- **`starlette` must stay pinned to 0.41.3.** `pip install streamlit` pulls starlette 1.x, which breaks
  FastAPI 0.115.6 at import time (`Router.__init__() got an unexpected keyword argument 'on_startup'`).
  Both root `requirements.txt` and `backend/requirements.txt` pin it.
- **Next.js is pinned to 14.2.33** because the reachable registry only publishes `@next/swc-win32-x64-msvc` up to that
  version, and Next will not start without a matching native binary. Keep `next` and `@next/swc-win32-x64-msvc`
  (in `optionalDependencies`) at the **same** version. 14.2.33 has a security advisory — upgrade both together when the
  network allows.
- Killing a dev server with the shell tool can leave an orphan `node.exe` holding port 3000
  (`netstat -ano | grep :3000`, then `taskkill //PID <pid> //F`).

## Conventions

- Rules are data, never hardcoded: add a `rule_type` to `app/rules.py` (`RULE_TYPES`, `build_ruleset`) and let the engines read
  the resulting `RuleSet`. Block structure comes from the `option_blocks` table.
- `app/engines/*` must stay pure (no SQLAlchemy imports) so tests can build in-memory worlds.
- Any write endpoint: `Depends(require_admin)`, mutate + `audit.log(...)` in one transaction, single `db.commit()`.
- Tests seed an in-memory SQLite once per session and copy it per test (`tests/conftest.py`); `PBKDF2_ITERATIONS=1000`
  keeps hashing fast there.
