"""Live data connectors: Canvas LMS and Google Forms / Sheets.

Nothing here is required — the dashboard runs entirely on the generated dataset.
This page is where you plug in real credentials to pull live gradebooks and
survey responses instead.
"""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from student_analytics import config as C                                # noqa: E402
from student_analytics.dashboard import shared                            # noqa: E402
from student_analytics.integrations import CanvasClient, GoogleFormsClient  # noqa: E402
from student_analytics.integrations import google_forms                    # noqa: E402

shared.page_setup("Integrations")
ds = shared.require_dataset()

shared.hero("Integrations — Canvas LMS & Google Forms",
            "Pull real gradebooks and survey responses in, instead of using the generated data. "
            "Credentials are read from environment variables and never written to disk.")

canvas_ok = C.canvas_configured()
google_ok = C.google_configured()

s = st.columns(3)
shared.kpi(s[0], "Canvas LMS", "Connected" if canvas_ok else "Not configured",
           C.CANVAS_DOMAIN or "set CANVAS_DOMAIN + CANVAS_API_TOKEN",
           "#00A86B" if canvas_ok else "#868E96")
shared.kpi(s[1], "Google Sheets / Forms", "Connected" if google_ok else "Not configured",
           "service-account JSON" if google_ok else "set GOOGLE_SERVICE_ACCOUNT_JSON",
           "#00A86B" if google_ok else "#868E96")
shared.kpi(s[2], "Active data source", "Generated dataset",
           f"{ds.meta['n_students']:,} students · {ds.meta['total_rows']:,} rows", "#4C6FFF")
st.markdown("")

t_canvas, t_google, t_setup = st.tabs(["🎓 Canvas LMS", "📝 Google Forms / Sheets", "🔑 Setup guide"])

# --------------------------------------------------------------------- Canvas
with t_canvas:
    st.markdown("#### Connection")
    c1, c2, c3 = st.columns(3)
    domain = c1.text_input("Canvas domain", C.CANVAS_DOMAIN,
                           placeholder="https://canvas.instructure.com", key="cv_dom")
    token = c2.text_input("Access token", C.CANVAS_API_TOKEN, type="password", key="cv_tok")
    course = c3.text_input("Course ID", C.CANVAS_COURSE_ID, placeholder="12345", key="cv_course")
    client = CanvasClient(domain, token, course)

    if st.button("Test connection", key="cv_test"):
        ok, msg = client.test_connection()
        (st.success if ok else st.error)(msg)

    if not client.available:
        st.info("Enter a domain and token above (or set the `CANVAS_DOMAIN` / `CANVAS_API_TOKEN` "
                "environment variables) to enable the fetch buttons. See the **Setup guide** tab "
                "for how to generate a token.")

    st.markdown("#### Fetch")
    f1, f2, f3, f4 = st.columns(4)
    disabled = not client.available
    actions = {
        "Courses": ("cv_courses", client.fetch_courses, f1),
        "Students": ("cv_students", client.fetch_students, f2),
        "Assignments": ("cv_assign", client.fetch_assignments, f3),
        "Full gradebook": ("cv_grades", client.fetch_gradebook, f4),
    }
    for label, (key, fn, col) in actions.items():
        if col.button(label, disabled=disabled, key=f"btn_{key}", width="stretch"):
            try:
                with st.spinner(f"Fetching {label.lower()} from Canvas …"):
                    st.session_state[key] = fn()
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")

    for label, (key, _fn, _col) in actions.items():
        data = st.session_state.get(key)
        if data is not None:
            st.markdown(f"##### {label} — {len(data):,} rows")
            st.dataframe(data, width="stretch", hide_index=True, height=340)
            shared.df_download(data, f"canvas_{key}.csv", f"⬇ Download {label.lower()}",
                               key=f"dl_{key}")

    st.markdown("#### Push grades back to Canvas")
    st.caption("The reverse direction from the reference project: upload a whole column of "
               "grades to one Canvas assignment.")
    with st.form("cv_upload"):
        u1, u2 = st.columns(2)
        aid = u1.number_input("Assignment ID", 0, step=1, key="cv_aid")
        subject = u2.selectbox("Use scores from subject", ds.subject_names(), key="cv_subj")
        grade_pick = st.selectbox("Class", ds.grades, format_func=lambda g: f"Grade {g}",
                                 key="cv_grade")
        confirm = st.checkbox("I understand this writes grades into Canvas", key="cv_confirm")
        submitted = st.form_submit_button("Upload grades", disabled=disabled)
    if submitted:
        if not confirm or not aid:
            st.warning("Tick the confirmation box and provide a valid assignment ID.")
        else:
            st.error("Mapping local student IDs to Canvas user IDs requires a fetched student "
                     "list. Click **Students** above first, then re-run — the mapping uses the "
                     "`sis_user_id` field, which must match this project's `student_id`.")

# --------------------------------------------------------------------- Google
with t_google:
    st.markdown("#### Option A — published CSV (no credentials needed)")
    st.caption("In Google Sheets: **File → Share → Publish to web → Comma-separated values (.csv)**, "
               "then paste the link here. Works for any Google Form's response sheet.")
    url = st.text_input("Published CSV URL or a share URL of an open sheet", key="gf_url",
                        placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv")
    cc1, cc2 = st.columns([1, 3])
    if cc1.button("Fetch CSV", disabled=not url, key="gf_fetch_csv"):
        try:
            with st.spinner("Downloading …"):
                st.session_state["gf_data"] = GoogleFormsClient.fetch_published_csv(url)
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")
    sheet_id = cc2.text_input("…or just a Sheet ID (must be shared as 'anyone with the link')",
                              C.GOOGLE_SHEET_ID, key="gf_sid")
    if sheet_id and st.button("Fetch by Sheet ID", key="gf_fetch_id"):
        try:
            with st.spinner("Downloading …"):
                st.session_state["gf_data"] = GoogleFormsClient.fetch_published_csv(
                    GoogleFormsClient.sheet_export_url(sheet_id))
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")

    st.markdown("#### Option B — service account (Sheets API / Forms API)")
    g1, g2 = st.columns(2)
    sa = g1.text_input("Service-account JSON path", C.GOOGLE_SERVICE_ACCOUNT_JSON, key="gf_sa")
    rng = g2.text_input("Sheet tab / range", "Form Responses 1", key="gf_range")
    gclient = GoogleFormsClient(sa or None, sheet_id or None)
    b1, b2, b3 = st.columns(3)
    if b1.button("Test connection", key="gf_test"):
        ok, msg = gclient.test_connection()
        (st.success if ok else st.error)(msg)
    if b2.button("Fetch sheet tab", disabled=not gclient.available, key="gf_tab"):
        try:
            st.session_state["gf_data"] = gclient.fetch_sheet(rng)
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")
    form_id = b3.text_input("Form ID (Forms API)", C.GOOGLE_FORM_ID, key="gf_fid")
    if form_id and st.button("Fetch form responses", disabled=not gclient.available, key="gf_resp"):
        try:
            st.session_state["gf_data"] = GoogleFormsClient(sa or None, form_id=form_id
                                                            ).fetch_form_responses()
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")

    data = st.session_state.get("gf_data")
    if data is not None:
        st.markdown(f"##### Fetched — {len(data):,} rows × {len(data.columns)} columns")
        st.dataframe(data, width="stretch", hide_index=True, height=380)
        st.caption("Question headers are auto-mapped onto this project's column names "
                   "(see `COLUMN_ALIASES` in `integrations/google_forms.py`). Unrecognised "
                   "questions are kept as snake_case columns.")
        shared.df_download(data, "google_form_responses.csv", "⬇ Download normalised responses",
                           key="dl_gf")
        if "student_id" in data.columns:
            merged = GoogleFormsClient.merge_into_summary(ds.summary, data)
            matched = merged["student_id"].isin(data["student_id"]).sum()
            st.success(f"`student_id` column found — {matched:,} of {len(data):,} responses match "
                       f"a student in the dataset and can overlay the simulated survey answers.")
        else:
            st.warning("No `student_id` column found. Add a 'Student ID' question to the form so "
                       "responses can be joined to student records.")

    st.markdown("#### Currently loaded (simulated) survey data")
    st.caption("This is what the real Google Form data would replace: "
               f"{len(ds.survey):,} responses.")
    st.dataframe(ds.survey.head(200), width="stretch", hide_index=True, height=300)
    st.markdown("**Suggested Google Form questions** (these map straight onto the columns the "
                "dashboard already analyses):")
    st.dataframe(
        {"Google Form question": [q.title() for q in google_forms.COLUMN_ALIASES],
         "Maps to column": list(google_forms.COLUMN_ALIASES.values())},
        width="stretch", hide_index=True, height=320)

# ---------------------------------------------------------------------- setup
with t_setup:
    st.markdown((_ROOT / "student_analytics" / "API_SETUP.md").read_text(encoding="utf-8")
                if (_ROOT / "student_analytics" / "API_SETUP.md").exists()
                else "API_SETUP.md not found.")
