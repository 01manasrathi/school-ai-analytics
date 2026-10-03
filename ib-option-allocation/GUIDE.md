# How it all works: a detailed guide

This document explains the whole system: how the pieces fit together, how each API is built, how the allocation and feasibility engines decide things, and how to change the rules. For setup and run commands, see [README.md](README.md).

---

## Contents

1. [Big picture](#1-big-picture)
2. [What happens when you click a button (request flow)](#2-what-happens-when-you-click-a-button)
3. [Backend structure: how a FastAPI endpoint is built](#3-backend-structure)
4. [Data model (database tables)](#4-data-model)
5. [Rules: the Rule table and RuleSet](#5-rules)
6. [Validation: checking a whole programme](#6-validation)
7. [Feasibility engine (change requests)](#7-feasibility-engine)
8. [Allocation engine (new students)](#8-allocation-engine)
9. [Approve, waitlist, override: how data changes](#9-approve-waitlist-override)
10. [Authentication and roles](#10-authentication-and-roles)
11. [API reference with examples](#11-api-reference)
12. [CSV import internals](#12-csv-import-internals)
13. [Reports and CSV export](#13-reports)
14. [Frontend (Next.js)](#14-frontend)
15. [Database migrations (Alembic)](#15-migrations)
16. [Tests](#16-tests)
17. [Common tasks / FAQ](#17-common-tasks--faq)

---

## 1. Big picture

```
 ┌────────────────────────┐   /api/*  (same origin)   ┌──────────────────────────────┐        ┌──────────────┐
 │  Browser               │ ───────────────────────▶  │  Next.js dev server :3000    │        │              │
 │  React pages (UI)      │                           │  rewrites /api/* ─────────────┼──────▶ │ FastAPI :8000│
 └────────────────────────┘ ◀───────────────────────  └──────────────────────────────┘  JSON  │  (Python)    │
                                                                                            │      │       │
                                                                                            │  SQLAlchemy  │
                                                                                            │      ▼       │
                                                                                            │ SQLite file  │
                                                                                            │ ib_options.db│
                                                                                            └──────────────┘
```

- **Frontend** (`frontend/`, Next.js 14 + TypeScript + Tailwind): only screens. It holds no business logic; every decision comes from the API.
- **Backend** (`backend/`, FastAPI): all business rules, the database, the engines, CSV parsing and report generation.
- **Database**: a single SQLite file `backend/ib_options.db`. Set `DATABASE_URL` to switch to PostgreSQL; the code doesn't change.
- **Local only**: nothing calls the internet. Login tokens are signed with a local secret. There are no paid or external services.

Why Python/FastAPI rather than Prisma? The original spec named Prisma (a Node.js ORM). You asked for a Python FastAPI backend, so its Python equivalents are used: **SQLAlchemy** (ORM, playing the part of Prisma Client) and **Alembic** (migrations, playing the part of Prisma Migrate).

---

## 2. What happens when you click a button

Example: on the *Change Requests* page you pick student S1020, current subject *Psychology HL*, and requested *Economics HL*.

1. React state changes, and a `useEffect` calls `api("/api/feasibility/check", { body: {...} })` (`frontend/lib/api.ts`).
2. `api()` adds the header `Authorization: Bearer <token>` (saved at login in `localStorage`) and sends `POST /api/feasibility/check` to **localhost:3000**.
3. `next.config.js` has a *rewrite* that forwards `/api/:path*` to `http://127.0.0.1:8000/api/:path*`. Because the browser only ever talks to port 3000, you don't need CORS.
4. FastAPI matches the route in `backend/app/routers/feasibility.py`:
   ```python
   @router.post("/check")
   def check(body: FeasibilityIn, db: Session = Depends(get_db)):
   ```
   - `body: FeasibilityIn` is a **Pydantic model**. FastAPI parses the JSON, validates the types and returns **422** automatically if a field is missing or has the wrong type.
   - `Depends(get_db)` opens a database session for this request and closes it afterwards.
   - The router was declared with `dependencies=[Depends(get_current_user)]`, so the token is verified first (**401** if it's missing or invalid).
5. The handler calls `services.run_feasibility(...)`. That function loads the student, their approved choices, the two offerings and the rules from the DB, converts them into plain Python objects (`OfferingInfo`, `StudentInfo`, `RuleSet`) and calls the **pure** `engines.check_feasibility(...)`.
6. The engine returns a dict: `{status, reasons, warnings, override_allowed, impact}`. FastAPI serialises it to JSON.
7. React stores it in state and `<FeasibilityResult>` renders the coloured badge, reasons and impact.

Every page follows the same pattern: **UI → `/api/...` → router → services (DB) → engine (pure logic) → JSON → UI**.

---

## 3. Backend structure

```
backend/app/
├── config.py        env vars (DATABASE_URL, SECRET_KEY, ...)
├── database.py      engine + SessionLocal + Base + get_db() dependency
├── models.py        ORM tables
├── rules.py         DEFAULT_RULES, RULE_TYPES, build_ruleset(), load_ruleset()
├── engines/         PURE logic (no DB imports) → easy to unit-test
│   ├── types.py         OfferingInfo, StudentInfo, BlockInfo dataclasses + converters from ORM
│   ├── validation.py    validate_programme(), summarize()
│   ├── feasibility.py   check_feasibility()
│   └── allocation.py    allocate()
├── services.py      glue between DB and engines (load, apply swaps, recompute enrollment, grids)
├── audit.py         audit.log(...) helper
├── auth.py          password hashing, token create/verify, get_current_user, require_admin
├── routers/         HTTP layer (one file per area)
│   ├── auth_routes.py   /api/auth/*
│   ├── meta.py          /api/programmes, /blocks, /subjects, /offerings, /dashboard, /audit-log
│   ├── students.py      /api/students...
│   ├── allocation.py    /api/allocation/run, /commit
│   ├── feasibility.py   /api/feasibility/check
│   ├── change_requests.py /api/change-request(s)...
│   ├── reports.py       /api/reports/*
│   ├── imports.py       /api/import/*
│   └── settings.py      /api/rules, PUT offerings/blocks/subjects, recompute
├── seed.py          dummy data
└── main.py          creates FastAPI app, adds CORS, includes all routers
```

### Anatomy of an endpoint

```python
router = APIRouter(prefix="/api", tags=["change-requests"])     # URL prefix + Swagger group

class OverrideIn(BaseModel):                                     # request body schema (Pydantic)
    reason: str

@router.post("/change-request/{cr_id}/override")                 # HTTP method + path; {cr_id} is a path param
def override(cr_id: int,                                         # path param, auto-converted to int
             body: OverrideIn,                                   # JSON body, validated
             db: Session = Depends(get_db),                      # DB session injected
             user: CurrentUser = Depends(require_admin)):        # 401/403 unless an ADMIN token is sent
    ...
    db.commit()                                                  # one commit = one transaction
    return cr_dict(cr)                                           # dict → JSON
```

Key ideas:
- **Dependency injection** (`Depends`) is how FastAPI shares things like the DB session and the current user.
- **Pydantic models** define and validate inputs. Outputs are plain dicts.
- **`HTTPException(status, detail)`** returns errors: 404 not found, 409 conflict (such as "cannot approve"), 422 validation.
- **Transactions**: SQLAlchemy starts a transaction on first use. Nothing is saved until `db.commit()`, and an exception before it means nothing is written. Overrides, approvals and allocation commits all change enrollment and write audit rows **in the same transaction**, so they either fully happen or don't happen at all.
- **Interactive docs**: FastAPI generates OpenAPI automatically. Open http://127.0.0.1:8000/docs, click **Authorize**, paste a token from `/api/auth/login`, and try any endpoint.

### Why "pure" engines?

`engines/*` never import SQLAlchemy. They receive dataclasses and return dicts. This means:
- unit tests build tiny fake worlds in memory (`tests/test_engines.py`) with no database;
- the same validation code is reused by feasibility, allocation, commit and the student grid, so the rules are applied the same way everywhere.

---

## 4. Data model

(`backend/app/models.py`. Enum-like fields are strings, which keeps SQLite and PostgreSQL identical.)

| Table | Important columns | Meaning |
|---|---|---|
| `programmes` | name, grade_range | IGCSE (7-10), IBDP (11-12) |
| `students` | student_id (school ID), name, grade, programme_id, cohort_year, **status** (EXISTING/NEW/WITHDRAWN), nationality, language_profile, prior_subjects, **priority** | `prior_subjects` = codes used for prerequisites; `priority` = allocation order (lower first) |
| `subjects` | code, name, programme_id, **ib_group** (1-6), offered_levels ("HL,SL"), prerequisites (JSON list of codes), is_active | |
| `option_blocks` | name (A-G), label, programme_id, grade ("11-12"/""), **period**, max_choices_per_student, sort_order, notes | The block structure is data. Add or rename blocks in Settings |
| `subject_offerings` | subject_id, block_id, level, teacher, room, **capacity, current_enrollment, min_enrollment**, is_active | One row per subject × block × level |
| `student_choices` | student_id, offering_id, **status** (requested/approved/waitlisted/rejected/dropped), **source** (EXISTING_ALLOCATION/NEW_ALLOCATION/CHANGE_REQUEST), approved_by, approved_at | A student's programme = their `approved` rows. `dropped` keeps history after a move |
| `student_preferences` | student_id, rank (1-7), subject_id, level (nullable) | NEW students' ranked wishes |
| `change_requests` | student_id, current_offering_id, requested_offering_id, compensating_current/requested_offering_id, reason, priority, **status** (PENDING/APPROVED/WAITLISTED/REJECTED/OVERRIDDEN), feasibility_status, feasibility_reasons_json, override_by, override_reason, created_at | Optional compensating swap (e.g. fix HL/SL or free a block) |
| `rules` | programme_id (NULL = global), rule_type, condition_json, value, priority, is_active, description | See §5 |
| `audit_logs` | user, action, entity, entity_id, old_value, new_value, timestamp | Every write |
| `users` | username, password_hash, role (ADMIN/READONLY) | Local accounts |

**`current_enrollment`** is stored on the offering for speed and is always changed in the same transaction as the choice rows. *Settings → Recompute enrollment* (`POST /api/admin/recompute-enrollment`) rebuilds it from the approved choices if you ever edit the DB by hand.

---

## 5. Rules

All IB rules live in the **`rules` table** and can be edited on the Settings page. `rules.py` turns the active rows into a `RuleSet` object that the engines read. The engines know what each `rule_type` *means*, but the numbers, groups and severities all come from the table.

| rule_type | value | condition_json | Effect |
|---|---|---|---|
| `SUBJECT_COUNT` | `7` | `{"severity":"NEEDS_OVERRIDE"}` | exactly N subjects |
| `HL_COUNT` | `4` | severity | exactly N HL |
| `SL_COUNT` | `3` | severity | exactly N SL |
| `ONE_PER_BLOCK` | `1` | | max `block.max_choices_per_student` per block (hard conflict) |
| `REQUIRED_GROUPS` | | `{"groups":[1,2,3,4,5]}` | at least one subject from each |
| `ALLOWED_GROUPS` | | `{"groups":[1,2,3,4,5,6]}` | 6th/7th from Group 6 or a repeat of 1-5 |
| `NO_DUPLICATE_SUBJECTS` | | | same subject twice is a hard conflict |
| `REQUIRED_CATEGORY` | min count | `{"name":"Mathematics","groups":[5],"subject_codes":[]}` | seeded 4×: Mathematics (G5), Science (G4), Language A (G1), Language B (G2) |
| `WAITLIST_WHEN_FULL` | | | full class → FEASIBLE_WAITLIST (if disabled, full class → NOT_FEASIBLE) |
| `OVER_CAPACITY` | | `{"severity":"NOT_FEASIBLE"}` | over-capacity class → this status (override allowed) |
| `MIN_ENROLLMENT_WARNING` | | | warn when the source class drops below min |
| `PREREQUISITES` | | severity | Subject.prerequisites must be in prior_subjects or the student's other choices |
| `TIMETABLE_CLASH` | | | student period clash (hard); teacher/room clash (warning) |

**Severity** (`condition_json.severity`) controls how a violation shows up:
- `NEEDS_OVERRIDE`: the change is allowed, but only by an admin with a reason.
- `NOT_FEASIBLE`: rejected (still overridable unless it is a *hard* conflict).

*Hard* (never overridable) conflicts: invalid request (not enrolled, inactive offering, wrong programme/grade), block conflict, duplicate subject, student period clash. A student cannot physically attend two classes at once, so no override can allow these.

**Programme scoping**: a rule with `programme_id = NULL` applies to all programmes. A programme-specific rule of the same type replaces the global one (except `REQUIRED_CATEGORY`, which adds up). So you can give IGCSE different rules later without code changes.

**Examples**
- *Make Language B optional*: Settings → untick the `REQUIRED_CATEGORY` "Language B" row → Save.
- *Allow 3 HL / 4 SL*: set `HL_COUNT` value 3 and `SL_COUNT` value 4.
- *Count ESS as Individuals & Societies too*: add `"ESS"` to `subject_codes` of a category rule.

---

## 6. Validation

`engines/validation.py → validate_programme(choices, rules, prior_subjects)` checks one student's full set of offerings and returns a list of `Issue(code, severity, message, overridable)`:

1. subject count · 2. HL/SL counts ("HL/SL ratio would become X HL / Y SL") · 3. block limit · 4. duplicates · 5. required groups ("Group coverage broken: no subject from Group 5") · 6. allowed groups · 7. categories ("Mathematics requirement not met (0/1)") · 8. prerequisites · 9. period clashes.

`summarize(choices)` returns `{hl, sl, total, group_coverage: {"1":n,…,"6":n}}`.

It is used by:
- the **student grid** (Existing Allocations page: ✓/✗ and the issue list),
- the **feasibility engine** (on the programme *after* the swap),
- the **allocation engine** (to accept a complete programme),
- **allocation commit** (to re-check manual edits).

---

## 7. Feasibility engine

`engines/feasibility.py → check_feasibility(student, current_choices, swaps, rules, all_offerings)`

`swaps` is a list of `(current_offering, requested_offering)`: the main swap plus an optional compensating swap. The engine never writes anything.

Status ranking (the worst one wins): `FEASIBLE < FEASIBLE_WAITLIST < NEEDS_OVERRIDE < NOT_FEASIBLE`.

| Step | Check | Result if it fails |
|---|---|---|
| 1 | Student not withdrawn; student is enrolled in *current*; requested ≠ current and not already taken; requested offering & subject active; same programme; block grade matches student grade | NOT_FEASIBLE (hard) |
| 2 | **Block logic.** Same block → safe. Different block → does the student have another subject (not being removed) in the target block? | NOT_FEASIBLE (hard) "Block conflict: student already has X in Block Y" |
| 3 | **Level logic.** HL/SL counts after the swap | rule severity (default NEEDS_OVERRIDE) "HL/SL ratio would become 3 HL / 4 SL" |
| 4 | **Capacity** of the target: `enrollment < capacity` OK · `== capacity` → FEASIBLE_WAITLIST · `> capacity` → NOT_FEASIBLE (override allowed) | |
| 5 | **Group coverage**, allowed groups, duplicates, Maths/Science/Language categories after the swap | rule severity |
| 6 | **Prerequisites** | rule severity |
| 7 | **Timetable**: student period clash (hard); teacher/room teaching another offering in the same period | warning |
| 8 | **Source impact**: source class falls below `min_enrollment` | warning |

Steps 3, 5 and 6 are done by running `validate_programme` on the *after* programme. Issues that already existed *before* the swap (for example, legacy data) are reported as warnings ("Pre-existing issue…") so the change isn't blamed for them.

Response:

```json
{
  "status": "NEEDS_OVERRIDE",
  "reasons": ["HL/SL ratio would become 3 HL / 4 SL (required 4 HL / 3 SL)"],
  "warnings": [],
  "override_allowed": true,
  "impact": {
    "targetSeatsAfter": 4,            // seats left in the requested class after the move
    "sourceSeatsAfter": 6,            // seats left in the class the student leaves
    "targetEnrollmentAfter": 14,
    "sourceEnrollmentAfter": 11,
    "blockChange": {"from": "C", "to": "C", "changed": false},
    "hlSlAfter": {"hl": 3, "sl": 4},
    "groupCoverageAfter": {"1":1,"2":1,"3":1,"4":1,"5":1,"6":2}
  }
}
```

**Compensating change example (seed S1021):** Visual Arts SL (Block F) → Film SL (Block G) alone is a block conflict, because Geography SL sits in G. Adding the compensating swap Geography SL (G) → Music SL (F) empties G and refills F, so the combined change is FEASIBLE.

---

## 8. Allocation engine

`engines/allocation.py → allocate(students, blocks, offerings, rules)` returns a proposal and does not save anything.

1. `remaining[offering] = capacity − current_enrollment` (EXISTING students have already been counted).
2. Students are processed in **priority order** (`Student.priority`, then student_id). Seats taken by one student reduce `remaining` for the next.
3. For each student:
   - **Eligible offerings**: active, same programme, block grade matches, group allowed.
   - **Preference score** per offering: exact subject+level at rank *r* → `r`; right subject, other level → `r + 0.5`; not preferred → 1000.
   - **Block order**: blocks containing a preferred subject come first (best rank first), so preferences claim HL/SL "budget" before unpreferred blocks.
   - **Depth-first search**: for each block (in that order), try candidates sorted by (waitlist last, preference score, the level still most needed, most seats left). The search is **pruned** when:
     - the HL count > HL_COUNT or the SL count > SL_COUNT,
     - the subject is already chosen (no duplicates),
     - a required group or category can no longer be covered by the remaining blocks (worked out with suffix sets).
     
     At the leaf (all blocks filled), `validate_programme` must report no blocking issue. The first valid programme found is accepted.
   - **Pass 1** uses only offerings with seats. If *every* offering in a block is full, that block's candidates become waitlist placements, flagged **`UNALLOCATED_SLOT`**.
   - **Pass 2** (fallback if pass 1 finds nothing): waitlist placements are allowed in any block, still after all seat options.
   - No valid combination at all → student `UNALLOCATED` with an explanation.
4. **Slot reasons**: "Preference #3 satisfied", "Preference #4 subject satisfied at SL (level adjusted for HL/SL balance)", "Preference #4 Chemistry HL not assigned: full", "No seat available in Block E – waitlisted for Maths AA HL".
5. Output:
   ```json
   { "students": [{ "student_id":"S2001","status":"ALLOCATED|PARTIAL|UNALLOCATED","hl":4,"sl":3,
                    "slots":[{"block":"A","offering_id":3,"subject":"English A: Language & Literature","level":"HL",
                              "status":"ALLOCATED","flag":null,"reasons":["Preference #1 satisfied"]}, ...],
                    "warnings":[] }],
     "offerings": [{"block":"A","subject":"...","level":"HL","capacity":18,"existing_enrollment":12,
                    "new_allocated":2,"seats_left":4,"waitlisted":0}],
     "summary": {"students":15,"allocated":15,"partial":0,"unallocated":0,"seats_used":105,"waitlisted_slots":0} }
   ```

**Run → review → commit**
- `POST /api/allocation/run`: dry run, returns the proposal above.
- The UI lets you change any slot with a dropdown (each option shows the seats left).
- `POST /api/allocation/commit` with `{placements:[{student_id, offering_id, status}], override_reason?}`. In **one transaction** it:
  1. locks the offerings (`SELECT … FOR UPDATE` on PostgreSQL);
  2. rejects the commit if any approved placement would exceed capacity;
  3. re-validates each student's programme with `validate_programme` (manual edits could break rules). Overridable issues are accepted only if `override_reason` is given; hard ones never are;
  4. rejects students who already have choices (so you can't commit twice);
  5. writes `StudentChoice` rows with `source = NEW_ALLOCATION`, increments `current_enrollment` and writes one audit row per student.
  
  If anything fails, it returns 422 with the list of errors and **nothing** is saved.

---

## 9. Approve, waitlist, override

`routers/change_requests.py` + `services.apply_swaps()`.

| Action | Endpoint | What happens |
|---|---|---|
| Create | `POST /api/change-request` | Runs feasibility, stores CR as PENDING with the full result JSON, audit `CHANGE_REQUEST_CREATE` |
| Recheck | `POST /api/change-request/{id}/recheck` | Recomputes feasibility (capacity or rules may have changed) |
| Approve | `POST /api/change-request/{id}/approve` | **Re-runs feasibility first.** FEASIBLE → `apply_swaps` → APPROVED. FEASIBLE_WAITLIST → adds a `waitlisted` StudentChoice for the target (student keeps the current class) → WAITLISTED. Otherwise → **409** with the reasons |
| Override | `POST /api/change-request/{id}/override` `{reason}` | Reason required (≥5 chars, else 422). Re-runs feasibility; hard conflicts → 409. Otherwise `apply_swaps` even if over capacity or rules are broken → OVERRIDDEN, `override_by/override_reason` saved, audit `ADMIN_OVERRIDE` with the reasons that were overridden |
| Reject | `POST /api/change-request/{id}/reject` | CR → REJECTED, any waitlist entry for the target → rejected |

`apply_swaps` (runs inside the caller's transaction):
1. locks the source and target offerings;
2. marks the old approved choice `dropped` (history is kept);
3. clears any waitlist entry the student had for the target;
4. `source.current_enrollment −= 1`, `target.current_enrollment += 1`;
5. inserts a new approved choice (`source = CHANGE_REQUEST`, approved_by, approved_at);
6. writes audit `ENROLLMENT_CHANGE` with the old and new enrollment numbers.

A WAITLISTED request can be approved again later. Approval re-checks capacity, so once a seat frees up it goes through.

---

## 10. Authentication and roles

`auth.py`, stdlib only.
- Passwords: PBKDF2-SHA256 with a random salt, stored as `iterations$salt$hash`.
- Login `POST /api/auth/login` returns a token `base64(json{u, r, exp}).HMAC-SHA256(SECRET_KEY)`. It expires after `TOKEN_TTL_HOURS`.
- `get_current_user` verifies the signature and expiry and looks up the user → 401 if invalid.
- `require_admin` → 403 unless the role is `ADMIN`.
- **Read-only** users can call every GET, the feasibility *check* and the allocation *run* (both read-only). Every write needs ADMIN.
- The frontend stores the token in `localStorage`. The `AuthProvider` redirects to `/login` when there is no token, and `<AdminOnly>` hides write buttons for read-only users. The server enforces the roles regardless of what the UI shows.

Add a user (Python shell in `backend/`):
```python
from app.database import SessionLocal; from app import models; from app.auth import hash_password
db = SessionLocal(); db.add(models.User(username="jane", password_hash=hash_password("secret"), role="ADMIN")); db.commit()
```

---

## 11. API reference

All endpoints are under `http://127.0.0.1:8000`. Send `Authorization: Bearer <token>` except for login and health. Live, clickable docs: **/docs**.

### Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/login` | `{"username","password"}` | `{token, username, role}` |
| GET | `/api/auth/me` | | `{username, role}` |

### Reference data & dashboard
| Method | Path | Notes |
|---|---|---|
| GET | `/api/programmes` · `/api/blocks` · `/api/subjects` · `/api/offerings` | offerings include `seats_left, full, over_capacity, below_min` |
| GET | `/api/dashboard` | totals, full classes, below-min classes, waitlist count, pending CRs, unallocated new students |
| GET | `/api/audit-log?limit=200` | newest first |

### Students
| Method | Path | Notes |
|---|---|---|
| GET | `/api/students?status=EXISTING\|NEW\|WITHDRAWN&q=text` | each student includes a **block grid**, hl, sl, group_coverage, issues, valid |
| GET | `/api/students/{id}` | `{id}` = school ID (`S1020`) or DB id |
| GET | `/api/students/{id}/choices` | grid + full choice history (incl. dropped/waitlisted) |

### Allocation
| Method | Path | Body |
|---|---|---|
| POST | `/api/allocation/run` | `{}` or `{"student_ids":[61,62]}` |
| POST | `/api/allocation/commit` | `{"placements":[{"student_id":61,"offering_id":3,"status":"approved"}], "override_reason":null}` |

### Feasibility & change requests
| Method | Path | Body |
|---|---|---|
| POST | `/api/feasibility/check` | `{"student_id":"S1020","current_offering_id":24,"requested_offering_id":20, "compensating_current_offering_id":null,"compensating_requested_offering_id":null}` |
| GET | `/api/change-requests?status=PENDING` | |
| POST | `/api/change-request` | same as check + `"reason"`, `"priority"` |
| POST | `/api/change-request/{id}/approve` | |
| POST | `/api/change-request/{id}/override` | `{"reason":"..."}` |
| POST | `/api/change-request/{id}/reject` | `{"reason":"..."}` |
| POST | `/api/change-request/{id}/recheck` | |

### Reports (add `?format=csv` to download)
`GET /api/reports/capacity` · `/waitlist` · `/unallocated` · `/allocation?status=NEW` · `/change-requests`

### Import
| Method | Path | Body |
|---|---|---|
| POST | `/api/import/csv` | multipart: `type`, `file`, optional `mapping` (JSON), `dry_run`, `skip_invalid` |
| GET | `/api/import/templates/{type}` | header-only CSV |
| GET | `/api/import/specs` | fields + required fields per type |

### Settings
| Method | Path | Notes |
|---|---|---|
| GET | `/api/rules` | `{rule_types, rules}` |
| POST / PUT / DELETE | `/api/rules` · `/api/rules/{id}` | body `{programme_id, rule_type, condition, value, priority, is_active, description}` |
| POST / PUT | `/api/offerings` · `/api/offerings/{id}` | capacity, min, teacher, room, block, active |
| POST / PUT / DELETE | `/api/blocks` · `/api/blocks/{id}` | delete only if the block has no offerings |
| PUT | `/api/subjects/{id}` | name, group, levels, prerequisites, active |
| POST | `/api/admin/recompute-enrollment` | rebuild `current_enrollment` from approved choices |

### Example session with curl

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
H="Authorization: Bearer $TOKEN"

curl -s -H "$H" localhost:8000/api/change-requests | python -m json.tool | head -40
curl -s -X POST -H "$H" localhost:8000/api/change-request/4/approve          # 409 → needs override
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
     -d '{"reason":"Approved by DP coordinator"}' localhost:8000/api/change-request/4/override
curl -s -H "$H" "localhost:8000/api/reports/capacity?format=csv" -o capacity.csv
```

HTTP status codes used: **200** OK · **401** not logged in · **403** read-only user · **404** not found · **409** business conflict (cannot approve, hard conflict, already resolved) · **422** invalid input / rule errors on commit.

---

## 12. CSV import internals

`routers/imports.py`
1. The file is decoded as UTF-8 (a BOM from Excel is handled) and read with `csv.DictReader`.
2. **Column mapping**: if no mapping is sent, `suggest_mapping` normalises headers (`"Student ID"` → `student_id`) and applies a few aliases. The UI shows the mapping, lets you change it and re-validates.
3. Missing required columns are reported immediately.
4. Each row runs inside a **SAVEPOINT** (`db.begin_nested()`). A bad row is rolled back alone and its error recorded with the row number (row 1 = header).
5. At the end:
   - `dry_run=true` → rollback everything and return the report.
   - Errors and `skip_invalid=false` → rollback everything (all-or-nothing).
   - Otherwise commit, and for `choices` also recompute enrollment. One `CSV_IMPORT` audit row is written.
6. Upsert keys: student `student_id`, subject `code`, block `(programme, grade, name)`, offering `(subject, block, level)`, choice `(student, offering)`. Preferences replace the student's existing list. Change requests are always created, with feasibility computed on import.

---

## 13. Reports

`routers/reports.py`. Each report builds a list of flat dicts. `respond()` returns JSON, or with `?format=csv` streams it through `csv.DictWriter` as a download. The frontend's *Export CSV* button fetches with the token and saves the file (`downloadCsv` in `lib/api.ts`).

- **capacity**: every offering with enrolled, seats_left, status OK/FULL/OVER_CAPACITY/BELOW_MIN
- **waitlist**: position per offering, student, source
- **unallocated**: NEW students with no approved choices or with waitlisted slots
- **allocation**: one row per student, one column per block, HL/SL, valid, issues
- **change-requests**: every request with status, feasibility reasons, warnings and override info

---

## 14. Frontend

```
frontend/
├── next.config.js          /api/* → FastAPI rewrite
├── lib/api.ts              api(), downloadCsv(), auth token storage, errorText()
├── components/
│   ├── AuthProvider.tsx    login gate + useAuth() (user, isAdmin)
│   ├── Nav.tsx             sidebar
│   └── ui.tsx              Badge, Stat, ErrorBox, AdminOnly, FeasibilityResult, BlockGrid
└── app/                    (App Router: folder = URL)
    ├── login/              /login
    ├── page.tsx            /            Dashboard
    ├── import/             /import      CSV upload → validate → mapping → import
    ├── allocations/        /allocations block grid & table, filters, HL/SL + group coverage
    ├── new-allocation/     /new-allocation run → review/edit → commit
    ├── change-requests/    /change-requests live feasibility + list + approve/reject
    ├── override/           /override    reason-required override + audit log
    ├── reports/            /reports     5 reports + CSV export
    └── settings/           /settings    rules, capacities/offerings, block structure
```

Every page is a client component (`"use client"`) that loads data with `api()` inside `useEffect`, keeps it in `useState`, and re-fetches after actions. There is no global state library; the server is the source of truth.

---

## 15. Migrations

- Schema = `app/models.py`. Migrations live in `backend/alembic/versions/`. `0001_initial` creates all tables.
- `python -m app.seed` runs `alembic upgrade head` automatically.
- After changing a model:
  ```bash
  cd backend
  .venv/Scripts/python -m alembic revision --autogenerate -m "add column X"
  .venv/Scripts/python -m alembic upgrade head
  ```
- `render_as_batch=True` is enabled so column changes work on SQLite too.

---

## 16. Tests

`backend/tests/` (run with `python -m pytest -q`)
- `test_engines.py`: pure engine tests with a small hand-built 7-block world. Covers same-block, cross-block, compensating, full, over capacity, HL/SL, configurable rules, group violation, duplicates, min-enrollment, prerequisites, inactive, allocation preferences, capacity never exceeded, no seats → waitlist, HL/SL config, impossible rules, priority order.
- `test_api.py`: end-to-end through HTTP on the seeded DB. Covers auth/roles, 60 valid existing students, seed CR statuses, run+commit (enrollment ≤ capacity and matches choices, double commit blocked), commit rule/capacity rejection, read-only feasibility, approve, waitlist, needs-override blocked, override flow + audit, override can't bypass a block conflict, override over capacity, CSV reports, CSV import dry-run/commit/mapping, a rule change affecting feasibility.
- `conftest.py` seeds an in-memory SQLite once per session and copies it for each test (SQLite backup API), so each test starts clean and the suite stays fast.

---

## 17. Common tasks / FAQ

**Reset everything to the demo data:** `python -m app.seed`.

**Load my school's real data:** import CSVs in this order: blocks → subjects → offerings → students → existing choices → preferences → change requests. Then *Settings → Recompute enrollment* (it runs automatically after a choices import). To start from an empty DB instead of the demo, delete `backend/ib_options.db` (it's only a file), run `python -m alembic upgrade head`, and create an admin user (see §10).

**Change a class capacity:** Settings → Capacities / offerings → edit → Save (audited). Then *Recheck* any open change requests.

**Add an 8th block:** Settings → Block structure → + Add block → Save, then create offerings in it (Settings API or offerings CSV). If students should take 8 subjects, set the `SUBJECT_COUNT` rule to 8. If `SUBJECT_COUNT` is smaller than the number of blocks, allocation will leave some blocks empty.

**Why was a student waitlisted in allocation?** Every offering in that block was full (pass 1), or no seat-only combination satisfied the rules (pass 2). Read the slot reasons.

**Why can't I override?** The request has a hard conflict (block conflict, duplicate, period clash or invalid input). Add a compensating change that frees the block, or pick another subject.

**Is my data sent anywhere?** No. The API binds to 127.0.0.1, the database is a local file, and there are no external calls.

**Where's the database file?** `backend/ib_options.db`. Back it up by copying the file (while the API is stopped).
