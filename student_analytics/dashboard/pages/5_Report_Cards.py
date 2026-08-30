"""Batch PDF report-card generation — the automated report generator, at scale."""
import io
import pathlib
import sys
import zipfile

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from student_analytics import config as C                      # noqa: E402
from student_analytics.core import analytics, report_pdf       # noqa: E402
from student_analytics.dashboard import shared                 # noqa: E402

shared.page_setup("Report Cards")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "rc")
df, label = f["df"], f["label"]

shared.hero(f"{label} — Automated Report Cards",
            "Generate weighted-grade PDF report cards with comparison charts for one student, "
            "a whole section, or the entire class — plus a class-level summary report.")

if df.empty:
    st.warning("No students match the filters.")
    st.stop()

wt = " · ".join(f"{k} {v*100:.0f}%" for k, v in C.EXAM_WEIGHTS.items())
st.info(f"**Grading formula:** exams weighted {wt}; final subject score = "
        f"{C.EXAM_BLEND_WEIGHT*100:.0f}% exams + {C.ASSIGNMENT_WEIGHT*100:.0f}% assignment work. "
        f"Pass mark {C.PASS_MARK_PCT:.0f}%. Edit these in `student_analytics/config.py`.")

t_batch, t_class, t_files = st.tabs(["📄 Student report cards", "📊 Class summary report",
                                    "🗂 Generated files"])

# --------------------------------------------------------------------- batch
with t_batch:
    c1, c2 = st.columns([2, 3])
    with c1:
        who = st.radio("Generate for", ["Selected students", "Top N", "Needs improvement (N)",
                                       "Whole cohort in view"], key="rc_who")
        if who == "Selected students":
            picks = st.multiselect(
                "Students", df.sort_values("name")["student_id"].tolist(),
                default=df.nlargest(1, "overall_pct")["student_id"].tolist(),
                format_func=lambda s: f"{df.loc[df['student_id'] == s, 'name'].iloc[0]} ({s})",
                key="rc_picks")
            targets = picks
        elif who == "Top N":
            n = st.number_input("N", 1, 200, 10, key="rc_topn")
            targets = analytics.toppers(df, int(n))["student_id"].tolist()
        elif who == "Needs improvement (N)":
            n = st.number_input("N", 1, 200, 10, key="rc_lown")
            targets = analytics.needs_improvement(df, int(n))["student_id"].tolist()
        else:
            targets = df["student_id"].tolist()
            if len(targets) > 100:
                st.warning(f"{len(targets)} report cards — this will take a few minutes. "
                           "Narrow the filters (e.g. one section) for a quicker run.")
        narrative = st.checkbox("Include analysis & recommendations", value=True, key="rc_narr")
        go = st.button(f"Generate {len(targets)} report card(s)", type="primary",
                       width="stretch", disabled=not targets)
    with c2:
        st.markdown("##### What goes into each PDF")
        st.markdown("""
- Identity block, class, guardian contact and the headline result
- **Weighted grade table**: every exam, the assignment component, the final subject
  score, letter grade, class average and rank in that subject
- **Subject vs. class-average** grouped bar chart (the signature chart of the
  original report-generator project)
- **Exam-by-exam progression** lines for every subject
- **Attendance donut** and the student's **position in the grade** histogram
- Written analysis and numbered recommended next steps
- Signature block for class teacher, principal and parent
        """)

    if go and targets:
        bar = st.progress(0.0, text="Starting …")
        paths = []
        for i, sid in enumerate(targets, 1):
            name = df.loc[df["student_id"] == sid, "name"]
            paths.append(report_pdf.generate_report(ds, sid, include_narrative=narrative))
            bar.progress(i / len(targets),
                         text=f"{i}/{len(targets)} — {name.iloc[0] if len(name) else sid}")
        bar.empty()
        st.success(f"Generated {len(paths)} report card(s) in `{C.REPORTS_DIR}`")
        st.session_state["rc_paths"] = [str(p) for p in paths]

    paths = [pathlib.Path(p) for p in st.session_state.get("rc_paths", [])]
    paths = [p for p in paths if p.exists()]
    if paths:
        if len(paths) == 1:
            st.download_button(f"⬇ Download {paths[0].name}", paths[0].read_bytes(),
                               file_name=paths[0].name, mime="application/pdf")
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p in paths:
                    z.write(p, p.name)
            st.download_button(f"⬇ Download all {len(paths)} report cards (ZIP)", buf.getvalue(),
                               file_name=f"report_cards_{label.replace(' ', '_')}.zip",
                               mime="application/zip")
        with st.expander(f"{len(paths)} file(s) from this run"):
            for p in paths:
                st.caption(f"{p.name} — {p.stat().st_size/1024:.0f} KB")

# ---------------------------------------------------------------- class report
with t_class:
    st.markdown("A single PDF for the whole class: KPI strip, written key findings, subject "
                "summary, top 15, the 15 highest-risk students and the section league table.")
    if st.button("📊 Generate class summary report", type="primary"):
        with st.spinner("Building the class report …"):
            campus = None if "All" in f["campus"] else (f["campus"][0] if f["campus"] else None)
            section = None if "All" in f["section"] else (f["section"][0] if f["section"] else None)
            p = report_pdf.generate_class_report(ds, f["grade"], campus, section)
        st.session_state["rc_class"] = str(p)
    cp = st.session_state.get("rc_class")
    if cp and pathlib.Path(cp).exists():
        cp = pathlib.Path(cp)
        st.success(f"{cp.name} ({cp.stat().st_size/1024:.0f} KB)")
        st.download_button("⬇ Download class report", cp.read_bytes(), file_name=cp.name,
                           mime="application/pdf")

# ---------------------------------------------------------------------- files
with t_files:
    files = sorted(C.REPORTS_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    st.caption(f"Output folder: `{C.REPORTS_DIR}`")
    if not files:
        st.info("No report cards generated yet.")
    else:
        import pandas as pd
        st.metric("PDFs on disk", f"{len(files):,}",
                  f"{sum(p.stat().st_size for p in files)/1_048_576:.1f} MB total")
        table = pd.DataFrame([{
            "file": p.name,
            "size_kb": round(p.stat().st_size / 1024),
            "modified": pd.Timestamp(p.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
        } for p in files[:300]])
        st.dataframe(table, width="stretch", hide_index=True, height=440)
        pick = st.selectbox("Download one", [p.name for p in files[:300]], key="rc_pick")
        chosen = C.REPORTS_DIR / pick
        st.download_button(f"⬇ {pick}", chosen.read_bytes(), file_name=pick,
                           mime="application/pdf")
