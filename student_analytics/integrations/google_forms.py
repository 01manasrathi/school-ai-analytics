"""Google Forms / Google Sheets connector.

Two ways to pull survey or quiz data in, in increasing order of setup effort:

1. **Published CSV** (zero credentials) — in Google Sheets use
   *File > Share > Publish to web > Comma-separated values*, then paste the URL.
   `fetch_published_csv(url)` reads it straight into a DataFrame.
2. **Service account** (proper API access) — a Google Cloud service-account JSON
   with the Sheets API and/or Forms API enabled, and the sheet/form shared with
   the service-account email. See student_analytics/API_SETUP.md.

Both paths return the same normalised schema so `core/` never cares which was used.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import requests

from .. import config as C

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
FORMS_SCOPES = ["https://www.googleapis.com/auth/forms.responses.readonly"]

# Maps common Google Form question titles onto this project's column names.
COLUMN_ALIASES = {
    "student id": "student_id",
    "student name": "name",
    "name": "name",
    "email address": "email",
    "grade": "grade",
    "class": "class_name",
    "section": "section",
    "how many hours do you study per day?": "study_hours_per_day",
    "hours of study per day": "study_hours_per_day",
    "how many hours do you sleep?": "sleep_hours",
    "hours of sleep": "sleep_hours",
    "daily screen time (hours)": "screen_time_hours",
    "do you attend tuition?": "has_tuition",
    "do you have internet access at home?": "internet_access",
    "hours spent on extracurricular activities": "extracurricular_hours",
    "how motivated do you feel about school? (1-5)": "motivation_level",
    "how stressed do you feel? (1-5)": "stress_level",
    "how involved are your parents in your studies? (1-5)": "parent_involvement",
    "what career are you interested in?": "career_interest",
    "timestamp": "submitted_at",
}

NUMERIC_COLS = ["study_hours_per_day", "sleep_hours", "screen_time_hours",
                "extracurricular_hours", "motivation_level", "stress_level",
                "parent_involvement", "grade"]


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Google-Form question headers to project columns and coerce types."""
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    renames = {}
    for col in out.columns:
        key = col.lower().strip()
        if key in COLUMN_ALIASES:
            renames[col] = COLUMN_ALIASES[key]
        else:
            # fall back to a snake_case version of the question text
            renames[col] = re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:60]
    out = out.rename(columns=renames)
    for c in NUMERIC_COLS:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "source" not in out.columns:
        out["source"] = "Google Forms"
    return out


class GoogleFormsClient:
    def __init__(self, service_account_json: str | None = None,
                 sheet_id: str | None = None, form_id: str | None = None):
        self.sa_json = service_account_json or C.GOOGLE_SERVICE_ACCOUNT_JSON
        self.sheet_id = sheet_id or C.GOOGLE_SHEET_ID
        self.form_id = form_id or C.GOOGLE_FORM_ID
        self._creds = None

    # ------------------------------------------------------------- no-credential
    @staticmethod
    def fetch_published_csv(url: str) -> pd.DataFrame:
        """Read a 'Publish to web -> CSV' Google Sheets link. No credentials needed."""
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return normalise(pd.read_csv(io.StringIO(r.text)))

    @staticmethod
    def sheet_export_url(sheet_id: str, gid: str | int = 0) -> str:
        """Build a CSV export URL for a sheet that is shared as 'anyone with the link'."""
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

    # --------------------------------------------------------------- credentialed
    @property
    def available(self) -> bool:
        from pathlib import Path
        return bool(self.sa_json and Path(self.sa_json).exists())

    def _credentials(self, scopes):
        if self._creds is None:
            from google.oauth2 import service_account
            self._creds = service_account.Credentials.from_service_account_file(
                self.sa_json, scopes=scopes)
        return self._creds

    def test_connection(self) -> tuple[bool, str]:
        if not self.available:
            return False, ("Not configured — set GOOGLE_SERVICE_ACCOUNT_JSON to the path of your "
                           "service-account key file (or use the published-CSV option instead).")
        try:
            from googleapiclient.discovery import build
            svc = build("sheets", "v4", credentials=self._credentials(SHEETS_SCOPES),
                        cache_discovery=False)
            meta = svc.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
            title = meta.get("properties", {}).get("title", "?")
            tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
            return True, f"Connected to spreadsheet '{title}' (tabs: {', '.join(tabs)})."
        except ImportError:
            return False, ("google-api-python-client / google-auth are not installed. "
                           "Run: pip install google-api-python-client google-auth")
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def fetch_sheet(self, range_name: str = "Form Responses 1", sheet_id: str | None = None
                    ) -> pd.DataFrame:
        """Read a tab of a spreadsheet via the Sheets API."""
        from googleapiclient.discovery import build
        svc = build("sheets", "v4", credentials=self._credentials(SHEETS_SCOPES),
                    cache_discovery=False)
        res = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id or self.sheet_id, range=range_name).execute()
        values = res.get("values", [])
        if not values:
            return pd.DataFrame()
        header, *rows = values
        width = len(header)
        rows = [r + [None] * (width - len(r)) for r in rows]
        return normalise(pd.DataFrame(rows, columns=header))

    def fetch_form_responses(self, form_id: str | None = None) -> pd.DataFrame:
        """Read responses straight from the Google Forms API (question IDs -> answers)."""
        from googleapiclient.discovery import build
        creds = self._credentials(FORMS_SCOPES)
        svc = build("forms", "v1", credentials=creds, cache_discovery=False)
        fid = form_id or self.form_id
        form = svc.forms().get(formId=fid).execute()
        titles = {}
        for item in form.get("items", []):
            q = (item.get("questionItem") or {}).get("question") or {}
            if q.get("questionId"):
                titles[q["questionId"]] = item.get("title", q["questionId"])

        out, token = [], None
        while True:
            resp = svc.forms().responses().list(formId=fid, pageToken=token).execute()
            for r in resp.get("responses", []):
                row = {"response_id": r.get("responseId"),
                       "submitted_at": r.get("lastSubmittedTime")}
                for qid, ans in (r.get("answers") or {}).items():
                    vals = [a.get("value") for a in
                            (ans.get("textAnswers") or {}).get("answers", [])]
                    row[titles.get(qid, qid)] = ", ".join(v for v in vals if v)
                out.append(row)
            token = resp.get("nextPageToken")
            if not token:
                break
        return normalise(pd.DataFrame(out))

    # ------------------------------------------------------------------- merging
    @staticmethod
    def merge_into_summary(summary: pd.DataFrame, responses: pd.DataFrame) -> pd.DataFrame:
        """Overlay real survey answers onto the student summary, keyed on student_id."""
        if responses.empty or "student_id" not in responses.columns:
            return summary
        cols = [c for c in NUMERIC_COLS + ["has_tuition", "internet_access", "career_interest"]
                if c in responses.columns and c != "grade"]
        if not cols:
            return summary
        incoming = responses[["student_id"] + cols].drop_duplicates("student_id")
        out = summary.drop(columns=[c for c in cols if c in summary.columns], errors="ignore")
        return out.merge(incoming, on="student_id", how="left")
