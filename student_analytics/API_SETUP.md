## Getting API credentials

Nothing on this page is required — the dashboard runs entirely on the locally generated
dataset. Set these up only when you want to pull **real** data in.

Set credentials as **environment variables** (PowerShell examples below), or paste them into
the fields on the Integrations page for a one-off session. Never commit them to git.

---

### 1. Canvas LMS API — gradebook, students, assignments

**Where to create an account:** <https://canvas.instructure.com/register> — choose
*"I'm a Teacher"* for a permanently free Canvas Free-for-Teacher account. If your
institution already runs Canvas, use its domain instead (e.g. `https://canvas.chapman.edu`).

**How to get the token:**
1. Log in to Canvas.
2. Go to **Account → Settings**.
3. Scroll to **Approved Integrations**.
4. Click **+ New Access Token**.
5. Purpose: `School AI analytics`. Leave the expiry blank for no expiry.
6. Click **Generate Token** and **copy it immediately** — Canvas will not show it again.

**Course ID:** open the course; the number in the URL is the ID —
`https://canvas.instructure.com/courses/`**`12345`**

```powershell
$env:CANVAS_DOMAIN    = "https://canvas.instructure.com"
$env:CANVAS_API_TOKEN = "1234~abcdefg..."
$env:CANVAS_COURSE_ID = "12345"
```

**API reference:** <https://canvas.instructure.com/doc/api/>
**Endpoints used:** `/courses`, `/courses/:id/users`, `/courses/:id/assignments`,
`/courses/:id/students/submissions`, `/courses/:id/enrollments`, and
`/assignments/:id/submissions/update_grades` for pushing grades back.

---

### 2. Google Forms / Google Sheets — survey & quiz responses

There are two paths. **Option A needs no credentials at all** and is the fastest.

#### Option A — publish the response sheet as CSV (recommended, zero setup)
1. Open the Google Form → **Responses** tab → the green Sheets icon to create a response
   spreadsheet.
2. In that spreadsheet: **File → Share → Publish to web**.
3. Under *Link*, pick the response sheet and choose **Comma-separated values (.csv)**.
4. Click **Publish** and copy the URL.
5. Paste it into the Integrations page → *Option A*.

#### Option B — service account with the Sheets / Forms API
1. Go to <https://console.cloud.google.com/> and sign in (free tier is enough).
2. **Create a project** (top-left project dropdown → New Project).
3. Enable the APIs — **APIs & Services → Library** — enable:
   - **Google Sheets API** → <https://console.cloud.google.com/apis/library/sheets.googleapis.com>
   - **Google Forms API** → <https://console.cloud.google.com/apis/library/forms.googleapis.com>
4. **APIs & Services → Credentials → Create Credentials → Service account.**
   Give it a name, skip the optional role steps, click **Done**.
5. Click the new service account → **Keys → Add key → Create new key → JSON**. A `.json`
   file downloads — that is your credential file.
6. Copy the service account's email (looks like
   `something@project-id.iam.gserviceaccount.com`) and **share the spreadsheet / form with
   that email** (Viewer is enough).
7. Note the IDs from the URLs:
   - Sheet: `https://docs.google.com/spreadsheets/d/`**`<SHEET_ID>`**`/edit`
   - Form: `https://docs.google.com/forms/d/`**`<FORM_ID>`**`/edit`

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_JSON = "C:\keys\school-ai-sa.json"
$env:GOOGLE_SHEET_ID             = "1AbC...xyz"
$env:GOOGLE_FORM_ID              = "1FAIpQL..."
pip install google-api-python-client google-auth
```

**Suggested Google Form questions** — name them exactly like this and they auto-map onto the
columns the dashboard already analyses (see `COLUMN_ALIASES` in
`integrations/google_forms.py`):

| Question title | Maps to |
|---|---|
| Student ID | `student_id` |
| Student Name | `name` |
| How many hours do you study per day? | `study_hours_per_day` |
| How many hours do you sleep? | `sleep_hours` |
| Daily screen time (hours) | `screen_time_hours` |
| Do you attend tuition? | `has_tuition` |
| Do you have internet access at home? | `internet_access` |
| Hours spent on extracurricular activities | `extracurricular_hours` |
| How motivated do you feel about school? (1-5) | `motivation_level` |
| How stressed do you feel? (1-5) | `stress_level` |
| How involved are your parents in your studies? (1-5) | `parent_involvement` |
| What career are you interested in? | `career_interest` |

Anything else is kept as an extra snake_case column, so adding your own questions is safe.

---

### 3. Optional — local LLM for narrative summaries

Already part of the parent School AI project; no key and no cost.

```powershell
ollama pull llama3.1:8b
$env:SCHOOL_AI_MODEL = "llama3.1:8b"   # optional override
```

If Ollama is not running, the dashboard silently falls back to its deterministic
rule-based insight text — no feature is lost.

---

### Not required

For completeness, these were considered and are **not** needed: no paid analytics API, no
cloud database, no OpenAI/Anthropic key, no Google Classroom scope. The generated dataset
plus the two optional connectors above cover every feature on the dashboard.
