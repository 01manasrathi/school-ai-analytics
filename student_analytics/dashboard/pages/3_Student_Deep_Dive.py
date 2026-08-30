"""Everything about one student: report card on screen, charts, narrative, PDF."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from student_analytics import config as C                              # noqa: E402
from student_analytics.core import analytics, charts, insights, report_pdf  # noqa: E402
from student_analytics.dashboard import shared                          # noqa: E402

shared.page_setup("Student Deep Dive")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "sd")
df, label = f["df"], f["label"]

if df.empty:
    shared.hero("Student Deep Dive", "No students match the filters.")
    st.stop()

# ------------------------------------------------------------------ selection
st.sidebar.markdown("### Student")
mode = st.sidebar.radio("Pick by", ["Search", "Rank"], horizontal=True, key="sd_mode")
if mode == "Search":
    q = st.sidebar.text_input("Name or student ID", key="sd_q")
    pool = ds.find_students(q, 200) if q else df
    pool = pool[pool["student_id"].isin(df["student_id"])] if q else df
    if pool.empty:
        st.sidebar.warning("No match in the current cohort.")
        pool = df
    options = pool.sort_values("name")["student_id"].tolist()
else:
    rank_choice = st.sidebar.selectbox("Show", ["Class topper", "2nd rank", "3rd rank",
                                              "Median student", "Lowest scorer",
                                              "Highest risk", "Most improved"], key="sd_rank")
    ordered = df.sort_values("overall_pct", ascending=False)
    pick = {
        "Class topper": ordered.iloc[0],
        "2nd rank": ordered.iloc[min(1, len(ordered) - 1)],
        "3rd rank": ordered.iloc[min(2, len(ordered) - 1)],
        "Median student": ordered.iloc[len(ordered) // 2],
        "Lowest scorer": ordered.iloc[-1],
        "Highest risk": df.nlargest(1, "risk_score").iloc[0],
        "Most improved": df.nlargest(1, "trend_delta").iloc[0],
    }[rank_choice]
    options = [pick["student_id"]] + df["student_id"].tolist()

label_map = dict(zip(df["student_id"], df["name"] + "  (" + df["student_id"] + ")"))
sid = st.sidebar.selectbox("Student", options, key="sd_sid",
                           format_func=lambda s: label_map.get(s, s))

row = ds.student_row(sid)
profile = analytics.student_subject_profile(ds.master, sid)
cohort = ds.summary[ds.summary["grade"] == row["grade"]]

band_color = C.BAND_COLORS.get(row["performance_band"], "#4C6FFF")
shared.hero(f"{row['name']} — {row['class_name']}, {row['campus']}",
            f"{row['student_id']} · Roll {int(row['roll_no'])} · {row['house']} House · "
            f"{row['performance_band']} · Risk: {row['risk_level']}")

# ---------------------------------------------------------------------- KPIs
c = st.columns(7)
shared.kpi(c[0], "Overall score", f"{row['overall_pct']:.1f}%",
           f"{row['vs_grade_avg']:+.1f} vs grade avg",
           "#00A86B" if row["vs_grade_avg"] >= 0 else "#E03131")
shared.kpi(c[1], "Final grade", row["letter_grade"], row["grade_descriptor"], band_color)
shared.kpi(c[2], "GPA", f"{row['gpa']:.2f}", "out of 10")
shared.kpi(c[3], "Rank in class", f"{int(row['rank_in_section'])}/{int(row['section_size'])}",
           f"{int(row['rank_in_grade'])}/{int(row['grade_size'])} in the grade")
shared.kpi(c[4], "Percentile", f"{row['percentile_in_grade']:.0f}th", "within the grade")
shared.kpi(c[5], "Attendance", f"{row['attendance_pct']:.1f}%",
           f"{int(row['absent_days'])} days absent",
           "#00A86B" if row["attendance_pct"] >= 85 else "#E03131")
shared.kpi(c[6], "Momentum", f"{row['trend_delta']:+.1f} pts", "UT1 → Final Exam",
           "#00A86B" if row["trend_delta"] >= 0 else "#E03131")
st.markdown("")

st.subheader("Automated analysis")
shared.insight_cards(insights.student_insights(row, profile), columns=2)

st.markdown("#### Recommended next steps")
for i, rec in enumerate(insights.recommendations(row, profile), 1):
    st.markdown(f"**{i}.** {rec}")

st.markdown("---")

# -------------------------------------------------------------------- charts
st.subheader("Subject performance")
a, b = st.columns([3, 2])
a.plotly_chart(charts.student_vs_class_bar(profile, row["name"]), width="stretch")
b.plotly_chart(charts.student_radar(profile, row["name"]), width="stretch")

shared.styled_table(profile, height=360)

st.markdown("---")
st.subheader("Progression, attendance and position")
d1, d2 = st.columns([3, 2])
d1.plotly_chart(charts.student_exam_trend(ds.marks, sid), width="stretch")
d2.plotly_chart(charts.student_percentile_gauge(row), width="stretch")

e1, e2 = st.columns(2)
e1.plotly_chart(charts.student_attendance_bars(ds.attendance, sid), width="stretch")
e2.plotly_chart(charts.student_ranking_position(cohort, sid), width="stretch")

st.markdown("---")
st.subheader("Habits & context (from the survey data)")
h1, h2 = st.columns([2, 3])
h1.plotly_chart(charts.survey_profile(cohort, row), width="stretch")
with h2:
    facts = {
        "Study hours / day": f"{row['study_hours_per_day']} h",
        "Sleep": f"{row['sleep_hours']} h",
        "Screen time": f"{row['screen_time_hours']} h",
        "Extracurricular": f"{row['extracurricular_hours']} h / week",
        "Motivation (1-5)": int(row["motivation_level"]),
        "Stress (1-5)": int(row["stress_level"]),
        "Parent involvement (1-5)": int(row["parent_involvement"]),
        "Private tuition": row["has_tuition"],
        "Internet at home": row["internet_access"],
        "Transport": row["transport_mode"],
        "Parent education": row["parent_education"],
        "Career interest": row["career_interest"],
        "Assignments submitted": f"{row['submission_rate']:.0f}%",
        "Submitted on time": f"{row['punctuality_rate']:.0f}%",
        "Consistency across subjects": f"±{row['consistency_std']:.1f} pts",
        "Guardian": f"{row['parent_name']} · {row['parent_contact']}",
    }
    st.markdown("##### Profile")
    left, right = st.columns(2)
    items = list(facts.items())
    for i, (k, v) in enumerate(items):
        (left if i < len(items) / 2 else right).markdown(f"**{k}:** {v}")

st.markdown("---")

# ----------------------------------------------------------------------- PDF
st.subheader("Report card")
p1, p2 = st.columns([1, 3])
with p1:
    narrative = st.checkbox("Include analysis & recommendations", value=True, key="sd_narr")
    if st.button("📄 Generate PDF report card", type="primary", width="stretch"):
        with st.spinner("Rendering charts and building the PDF …"):
            path = report_pdf.generate_report(ds, sid, include_narrative=narrative)
        st.session_state["sd_pdf"] = str(path)
    if st.session_state.get("sd_pdf"):
        p = pathlib.Path(st.session_state["sd_pdf"])
        if p.exists():
            st.success(f"{p.name} ({p.stat().st_size/1024:.0f} KB)")
            st.download_button("⬇ Download report card", p.read_bytes(), file_name=p.name,
                               mime="application/pdf", width="stretch")
with p2:
    st.caption("The PDF contains the weighted grade table, a subject-vs-class-average comparison "
               "chart, exam progression lines, an attendance breakdown, the student's position in "
               "the grade, and the written analysis — the automated report generator, applied to "
               "one student.")
    if st.session_state.get("sd_pdf") and pathlib.Path(st.session_state["sd_pdf"]).exists():
        st.caption(f"Saved to `{st.session_state['sd_pdf']}`")

st.markdown("---")
st.subheader("Compare with another student")
other = st.selectbox("Compare against", [s for s in df["student_id"] if s != sid],
                     format_func=lambda s: label_map.get(s, s), key="sd_cmp")
if other:
    orow = ds.student_row(other)
    oprofile = analytics.student_subject_profile(ds.master, other)
    cmp_cols = ["overall_pct", "gpa", "letter_grade", "attendance_pct", "submission_rate",
                "trend_delta", "consistency_std", "rank_in_grade", "percentile_in_grade",
                "best_subject", "weakest_subject", "study_hours_per_day", "risk_level"]
    import pandas as pd

    def fmt(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)

    table = pd.DataFrame({
        "Metric": [c.replace("_", " ").title() for c in cmp_cols],
        row["name"]: [fmt(row[c]) for c in cmp_cols],
        orow["name"]: [fmt(orow[c]) for c in cmp_cols],
    })
    st.dataframe(table, width="stretch", hide_index=True)
    merged = (profile[["subject_name", "final_subject_score"]]
              .rename(columns={"final_subject_score": row["name"]})
              .merge(oprofile[["subject_name", "final_subject_score"]]
                     .rename(columns={"final_subject_score": orow["name"]}), on="subject_name"))
    import plotly.express as px
    fig = px.bar(merged, x="subject_name", y=[row["name"], orow["name"]], barmode="group",
                 template=C.PLOTLY_TEMPLATE, color_discrete_sequence=C.COLOR_SEQUENCE,
                 labels={"subject_name": "", "value": "Score (%)", "variable": ""})
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.02, x=1, xanchor="right"))
    st.plotly_chart(fig, width="stretch")
