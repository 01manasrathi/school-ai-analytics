"""School-wide view: all grades and campuses side by side, unfiltered."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from student_analytics import config as C                # noqa: E402
from student_analytics.core import analytics, charts     # noqa: E402
from student_analytics.dashboard import shared           # noqa: E402

shared.page_setup("School Overview")
ds = shared.require_dataset()
df = ds.summary

shared.hero(f"{C.SCHOOL_NAME} — School Overview",
            f"All {len(df):,} students across grades {min(ds.grades)}–{max(ds.grades)} and "
            f"{len(ds.campuses)} campuses. Use the other pages to drill into one class.")

shared.kpi_row(df)
st.markdown("")

st.subheader("Grade and campus comparison")
a, b = st.columns(2)
a.plotly_chart(charts.grade_comparison_bar(df), width="stretch")
camp = (df.groupby("campus").agg(students=("student_id", "count"),
                                avg=("overall_pct", "mean"),
                                att=("attendance_pct", "mean"),
                                at_risk=("risk_level", lambda s: int(s.isin(["High", "Critical"]).sum())))
        .round(2).reset_index())
fig = px.bar(camp.sort_values("avg"), x="avg", y="campus", orientation="h", color="avg",
             color_continuous_scale="Tealgrn", text=camp.sort_values("avg")["avg"].round(1),
             template=C.PLOTLY_TEMPLATE, labels={"avg": "Average score (%)", "campus": ""},
             hover_data=["students", "att", "at_risk"])
fig.update_traces(textposition="outside")
fig.update_layout(height=360, coloraxis_showscale=False, margin=dict(l=10, r=10, t=40, b=10),
                  title="Campus comparison")
b.plotly_chart(fig, width="stretch")

st.markdown("##### Grade × subject averages")
piv = ds.master.pivot_table(index="grade_label", columns="subject_name",
                            values="final_subject_score", aggfunc="mean").round(1)
fig = px.imshow(piv, text_auto=".1f", aspect="auto", color_continuous_scale="RdYlGn",
                template=C.PLOTLY_TEMPLATE, labels=dict(color="Avg %"))
fig.update_xaxes(side="top", tickangle=-25)
fig.update_layout(height=380, xaxis_title=None, yaxis_title=None,
                  margin=dict(l=10, r=10, t=70, b=10))
st.plotly_chart(fig, width="stretch")

st.markdown("---")
st.subheader("School-wide distributions")
c1, c2 = st.columns([2, 1])
c1.plotly_chart(charts.score_distribution(df, "Score distribution — whole school"),
                width="stretch")
c2.plotly_chart(charts.grade_donut(df, "Letter grades school-wide"), width="stretch")

d1, d2 = st.columns(2)
d1.plotly_chart(charts.band_sunburst(df), width="stretch")
d2.plotly_chart(charts.treemap_sections(df), width="stretch")

st.markdown("---")
st.subheader("School-wide leaderboards")
t1, t2, t3 = st.tabs(["🏆 Top 25 in the school", "🎯 Highest risk", "🏅 Best sections"])
with t1:
    shared.styled_table(analytics.toppers(df, 25).assign(
        grade=lambda x: x["student_id"].map(df.set_index("student_id")["grade_label"])),
        height=560)
with t2:
    shared.styled_table(analytics.needs_improvement(df, 25), height=560)
with t3:
    sec = (df.groupby(["grade_label", "campus", "section"])
           .agg(students=("student_id", "count"), avg_pct=("overall_pct", "mean"),
                attendance=("attendance_pct", "mean"),
                toppers=("performance_band", lambda s: int((s == "Topper").sum())),
                at_risk=("risk_level", lambda s: int(s.isin(["High", "Critical"]).sum())))
           .round(2).reset_index().sort_values("avg_pct", ascending=False))
    shared.styled_table(sec, height=560)
    shared.df_download(sec, "all_sections.csv", "⬇ Download all sections", key="dl_sec")

st.markdown("---")
st.subheader("Attendance and drivers, school-wide")
e1, e2 = st.columns([3, 2])
e1.plotly_chart(charts.attendance_trend(
    analytics.attendance_timeseries(ds.attendance, None, "grade_label", df), "grade_label",
    "Monthly attendance by grade"), width="stretch")
e2.plotly_chart(charts.drivers_bar(analytics.performance_drivers(df)), width="stretch")

f1, f2 = st.columns(2)
f1.plotly_chart(charts.attendance_vs_score_scatter(df.sample(min(2500, len(df)), random_state=1)),
                width="stretch")
f2.plotly_chart(charts.gender_split(df), width="stretch")

st.markdown("---")
st.subheader("Teachers")
subj_scores = (ds.master.groupby(["class_id", "subject_name"])["final_subject_score"]
               .mean().reset_index())
tmap = ds.subjects[["class_id", "subject_name", "teacher_id"]].merge(
    subj_scores, on=["class_id", "subject_name"], how="left")
tperf = (tmap.groupby("teacher_id").agg(classes=("class_id", "nunique"),
                                       avg_student_score=("final_subject_score", "mean"))
         .round(2).reset_index()
         .merge(ds.teachers[["teacher_id", "name", "subject_specialization", "campus",
                             "years_experience", "qualification"]], on="teacher_id")
         .sort_values("avg_student_score", ascending=False))
shared.styled_table(tperf.head(40), height=440)
st.caption("Average score of the students each teacher's sections achieve in their subject. "
           "Useful for spotting where to share practice — not a performance rating on its own.")
