"""Class Command Center — the single-screen view of one standard/class.

Run from the project root:
    python -m streamlit run student_analytics/dashboard/Home.py --server.port 8502
"""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from student_analytics import config as C                       # noqa: E402
from student_analytics.core import analytics, charts, grading, insights  # noqa: E402
from student_analytics.dashboard import shared                   # noqa: E402

shared.page_setup("Class Command Center")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "home")
df, label = f["df"], f["label"]

shared.hero(
    f"{label} — Class Command Center",
    f"{C.SCHOOL_NAME} · Academic Year {C.ACADEMIC_YEAR} · "
    f"weighted grading, ranking, risk detection and subject diagnostics on one screen",
)

if df.empty:
    st.warning("No students match the current filters. Widen them in the sidebar.")
    st.stop()

ids = df["student_id"]
k = shared.kpi_row(df)
st.markdown("")

# --------------------------------------------------------------- auto insights
with st.container():
    st.subheader("What the data says")
    shared.insight_cards(insights.cohort_insights(df, ds.master, label), columns=2)

st.markdown("---")

# ------------------------------------------------------- toppers vs strugglers
left, right = st.columns(2)
top_n = st.sidebar.slider("Leaderboard size", 5, 30, 10, key="home_topn")

with left:
    st.subheader("🏆 Class toppers")
    tops = analytics.toppers(df, top_n)
    st.plotly_chart(charts.leaderboard_bar(tops, title=f"Top {top_n} — {label}"),
                    width="stretch")
    shared.styled_table(tops, height=min(420, 38 * len(tops) + 40))

with right:
    st.subheader("🎯 Students who need to improve")
    weak = analytics.needs_improvement(df, top_n)
    st.plotly_chart(charts.leaderboard_bar(weak, title=f"Lowest {top_n} by composite risk",
                                          ascending=True, colorscale="Reds_r"),
                    width="stretch")
    shared.styled_table(weak.drop(columns=["risk_reasons"], errors="ignore"),
                        height=min(420, 38 * len(weak) + 40))

with st.expander("Why each of those students was flagged"):
    shared.styled_table(weak[["student_id", "name", "section", "overall_pct", "risk_level",
                              "risk_score", "risk_reasons"]], height=360)

st.markdown("---")

# -------------------------------------------------------------- distributions
st.subheader("How the class is distributed")
c1, c2 = st.columns([2, 1])
c1.plotly_chart(charts.score_distribution(df, f"Score distribution — {label}"),
                width="stretch")
c2.plotly_chart(charts.grade_donut(df), width="stretch")

c3, c4 = st.columns(2)
c3.plotly_chart(charts.performance_band_bar(df), width="stretch")
c4.plotly_chart(charts.top_bottom_dumbbell(df, 12), width="stretch")

st.markdown("---")

# -------------------------------------------------------------------- subjects
st.subheader("Subject diagnostics — where to intervene")
subs = analytics.subject_summary(ds.master, ids)
s1, s2 = st.columns([1, 1])
s1.plotly_chart(charts.subject_average_bar(subs, k["avg_pct"]), width="stretch")
s2.plotly_chart(charts.subject_difficulty_quadrant(subs), width="stretch")

st.plotly_chart(charts.section_subject_heatmap(ds.master, ids), width="stretch")

s3, s4 = st.columns([3, 2])
s3.plotly_chart(charts.exam_progression_lines(analytics.exam_progression(ds.master, ids)),
                width="stretch")
s4.plotly_chart(charts.subject_correlation_heatmap(
    analytics.subject_correlation_matrix(ds.master, ids)), width="stretch")

with st.expander("Subject summary table + per-subject topper"):
    shared.styled_table(subs, height=340)
    st.markdown("**Best student in each subject**")
    shared.styled_table(analytics.subject_toppers(ds.master, ids), height=340)

st.markdown("---")

# ------------------------------------------------------------------ attendance
st.subheader("Attendance, momentum and behaviour")
a1, a2 = st.columns([3, 2])
split = a1.selectbox("Split the attendance trend by", ["section", "campus", "performance_band"],
                     key="home_att_split")
a1.plotly_chart(charts.attendance_trend(
    analytics.attendance_timeseries(ds.attendance, ids, split, df), split,
    f"Monthly attendance — {label}"), width="stretch")
a2.plotly_chart(charts.attendance_band_bar(analytics.attendance_vs_marks(df)),
                width="stretch")

b1, b2 = st.columns(2)
b1.plotly_chart(charts.attendance_vs_score_scatter(df), width="stretch")
up, down = analytics.biggest_movers(df, 10)
b2.plotly_chart(charts.movers_tornado(up, down), width="stretch")

st.markdown("---")

# --------------------------------------------------------------- sections/risk
st.subheader("Section league table and risk radar")
sec = analytics.section_comparison(df)
st.plotly_chart(charts.section_comparison_bar(sec), width="stretch")
r1, r2 = st.columns([3, 2])
r1.plotly_chart(charts.risk_scatter(df), width="stretch")
r2.plotly_chart(charts.treemap_sections(df), width="stretch")
with st.expander("Section comparison table"):
    shared.styled_table(sec, height=360)

st.markdown("---")

# ------------------------------------------------------------- drivers + extra
st.subheader("What drives results in this class")
d1, d2 = st.columns([2, 3])
d1.plotly_chart(charts.drivers_bar(analytics.performance_drivers(df)), width="stretch")
d2.plotly_chart(charts.parallel_bands(df), width="stretch")

e1, e2 = st.columns(2)
e1.plotly_chart(charts.gender_split(df), width="stretch")
e2.plotly_chart(charts.grade_comparison_bar(ds.summary), width="stretch")

st.markdown("---")

# ---------------------------------------------------------- weightage playground
st.subheader("Weightage playground")
st.caption("Change how the four exams are weighted and watch every grade recompute — this is the "
           "'customizable weightages' idea from the report-generator project, made interactive.")
wcols = st.columns(len(C.EXAM_TYPES) + 1)
weights = {}
for i, exam in enumerate(C.EXAM_TYPES):
    weights[exam] = wcols[i].slider(exam, 0.0, 1.0, float(C.EXAM_WEIGHTS[exam]), 0.05,
                                    key=f"w_{i}")
assign_w = wcols[-1].slider("Assignments", 0.0, 0.5, float(C.ASSIGNMENT_WEIGHT), 0.05)

if abs(sum(weights.values()) - 1.0) > 0.001:
    st.caption(f"Exam weights sum to {sum(weights.values()):.2f} — they are renormalised automatically.")

scoped_master = ds.master[ds.master["student_id"].isin(ids)]
re_master = grading.recompute_master(scoped_master, weights, assign_w)
new_summary = (re_master.groupby("student_id")
               .agg(new_pct=("final_subject_score", "mean"))
               .round(2).reset_index())
cmp_df = (df[["student_id", "name", "section", "overall_pct", "rank_in_grade"]]
          .merge(new_summary, on="student_id"))
cmp_df["change"] = (cmp_df["new_pct"] - cmp_df["overall_pct"]).round(2)
cmp_df["new_rank"] = cmp_df["new_pct"].rank(ascending=False, method="min").astype(int)
cmp_df["old_rank_in_view"] = cmp_df["overall_pct"].rank(ascending=False, method="min").astype(int)
cmp_df["rank_change"] = cmp_df["old_rank_in_view"] - cmp_df["new_rank"]

w1, w2, w3 = st.columns(3)
w1.metric("Class average under new weights", f"{cmp_df['new_pct'].mean():.2f}%",
          f"{cmp_df['new_pct'].mean() - df['overall_pct'].mean():+.2f} pts")
w2.metric("Students whose rank moves", f"{int((cmp_df['rank_change'] != 0).sum()):,}")
w3.metric("New class topper", cmp_df.nsmallest(1, "new_rank").iloc[0]["name"])
shared.styled_table(
    cmp_df.sort_values("rank_change", key=abs, ascending=False)
    .head(25)[["student_id", "name", "section", "overall_pct", "new_pct", "change",
               "old_rank_in_view", "new_rank", "rank_change"]], height=360)

st.markdown("---")
dl1, dl2, dl3 = st.columns(3)
with dl1:
    shared.df_download(df, f"{label.replace(' ', '_')}_students.csv",
                       "⬇ Download this cohort (CSV)", key="dl_cohort")
with dl2:
    shared.df_download(scoped_master, f"{label.replace(' ', '_')}_student_subject.csv",
                       "⬇ Download student×subject rows", key="dl_master")
with dl3:
    shared.df_download(analytics.intervention_plan(df, ds.master, 30),
                       f"{label.replace(' ', '_')}_intervention_plan.csv",
                       "⬇ Download intervention plan", key="dl_plan")

st.caption(f"Dataset: {ds.meta['n_students']:,} students · {ds.meta['total_rows']:,} rows across "
           f"10 tables · {ds.meta['data_dir']}")
