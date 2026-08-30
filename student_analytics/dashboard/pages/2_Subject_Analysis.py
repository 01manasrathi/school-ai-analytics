"""Subject-level analysis: difficulty, spread, exam progression, teacher view."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from student_analytics import config as C                    # noqa: E402
from student_analytics.core import analytics, charts         # noqa: E402
from student_analytics.dashboard import shared               # noqa: E402

shared.page_setup("Subject Analysis")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "sa")
df, label = f["df"], f["label"]

shared.hero(f"{label} — Subject Analysis",
            "Which subjects carry the class, which drag it down, and how each section and "
            "teacher compares.")

if df.empty:
    st.warning("No students match the filters.")
    st.stop()

ids = df["student_id"]
scoped = ds.master[ds.master["student_id"].isin(ids)]
subs = analytics.subject_summary(ds.master, ids)

c = st.columns(5)
best, worst = subs.iloc[0], subs.iloc[-1]
shared.kpi(c[0], "Subjects", len(subs), "assessed this year")
shared.kpi(c[1], "Strongest", best["subject_name"], f"{best['avg_score']:.1f}% average", "#00A86B")
shared.kpi(c[2], "Weakest", worst["subject_name"], f"{worst['avg_score']:.1f}% average", "#E03131")
shared.kpi(c[3], "Widest spread", subs.nlargest(1, "std_score").iloc[0]["subject_name"],
           f"σ {subs['std_score'].max():.1f} pts", "#E8590C")
shared.kpi(c[4], "Total failures", int(subs["fail_count"].sum()),
           f"below {C.PASS_MARK_PCT:.0f}% pass mark", "#E03131")
st.markdown("")

t1, t2, t3, t4 = st.tabs(["📊 Overview", "🔥 Heatmaps", "📈 Exam progression", "🔍 One subject"])

with t1:
    a, b = st.columns(2)
    a.plotly_chart(charts.subject_average_bar(subs, df["overall_pct"].mean()),
                   width="stretch")
    b.plotly_chart(charts.subject_difficulty_quadrant(subs), width="stretch")
    st.plotly_chart(charts.subject_box(ds.master, ids), width="stretch")
    shared.styled_table(subs, height=360)
    shared.df_download(subs, "subject_summary.csv", "⬇ Download subject summary", key="dl_subs")

with t2:
    st.plotly_chart(charts.section_subject_heatmap(ds.master, ids), width="stretch")
    st.caption("Read down a column to find a subject that is weak everywhere (a curriculum or "
               "syllabus problem); read across a row to find a section that is weak in one "
               "subject only (usually a teaching or timetable problem).")
    a, b = st.columns(2)
    a.plotly_chart(charts.subject_correlation_heatmap(
        analytics.subject_correlation_matrix(ds.master, ids)), width="stretch")
    with b:
        st.markdown("##### Grade × subject averages (whole school)")
        piv = (ds.master.pivot_table(index="grade_label", columns="subject_name",
                                     values="final_subject_score", aggfunc="mean").round(1))
        st.dataframe(piv.style.background_gradient(cmap="RdYlGn", axis=None)
                     .format("{:.1f}"), width="stretch", height=280)
        st.caption("Highlights whether a weakness is specific to this class or systemic.")

with t3:
    prog = analytics.exam_progression(ds.master, ids)
    st.plotly_chart(charts.exam_progression_lines(prog), width="stretch")
    wide = prog.pivot_table(index="subject_name", columns="exam_type", values="pct")
    wide = wide[[e for e in C.EXAM_TYPES if e in wide.columns]]
    wide["Change (UT1 → Final)"] = (wide[C.EXAM_TYPES[-1]] - wide[C.EXAM_TYPES[0]]).round(2)
    st.dataframe(wide.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.1f}"),
                 width="stretch")
    st.caption("A subject that dips at the Mid Term and recovers by the Final Exam is usually a "
               "hard-paper artefact; one that declines monotonically is a genuine learning gap.")

with t4:
    subject = st.selectbox("Subject", subs["subject_name"].tolist(), key="sa_subject")
    sdf = scoped[scoped["subject_name"] == subject]
    row = subs[subs["subject_name"] == subject].iloc[0]

    m = st.columns(6)
    shared.kpi(m[0], "Average", f"{row['avg_score']:.1f}%")
    shared.kpi(m[1], "Median", f"{row['median_score']:.1f}%")
    shared.kpi(m[2], "Spread", f"σ {row['std_score']:.1f}")
    shared.kpi(m[3], "Pass rate", f"{row['pass_rate']:.0f}%",
               color="#00A86B" if row["pass_rate"] >= 90 else "#E03131")
    shared.kpi(m[4], "Failing", int(row["fail_count"]), color="#E03131")
    shared.kpi(m[5], "Trend", f"{row['avg_trend']:+.1f} pts",
               color="#00A86B" if row["avg_trend"] >= 0 else "#E03131")
    st.markdown("")

    a, b = st.columns(2)
    with a:
        st.markdown(f"##### Top 15 in {subject}")
        top = sdf.nlargest(15, "final_subject_score")[
            ["student_id", "name", "section", "final_subject_score", "letter_grade",
             "weighted_exam_pct", "submission_rate", "rank_in_grade_subject"]]
        shared.styled_table(top, height=560)
    with b:
        st.markdown(f"##### Bottom 15 in {subject}")
        bot = sdf.nsmallest(15, "final_subject_score")[
            ["student_id", "name", "section", "final_subject_score", "letter_grade",
             "weighted_exam_pct", "submission_rate", "trend_delta"]]
        shared.styled_table(bot, height=560)

    st.markdown("##### Section performance in this subject")
    by_sec = (sdf.groupby(["campus", "section"])
              .agg(students=("student_id", "count"),
                   avg=("final_subject_score", "mean"),
                   median=("final_subject_score", "median"),
                   failing=("passed", lambda s: int((~s).sum())),
                   trend=("trend_delta", "mean"))
              .round(2).reset_index().sort_values("avg", ascending=False))
    teach = ds.subjects[(ds.subjects["subject_name"] == subject)][
        ["class_id", "teacher_id"]].merge(ds.teachers, on="teacher_id", how="left")
    sec_teacher = (sdf[["class_id", "campus", "section"]].drop_duplicates()
                   .merge(teach[["class_id", "name", "years_experience", "qualification"]],
                          on="class_id", how="left")
                   .rename(columns={"name": "teacher"}))
    by_sec = by_sec.merge(sec_teacher[["campus", "section", "teacher", "years_experience"]],
                          on=["campus", "section"], how="left")
    shared.styled_table(by_sec, height=420)
    st.caption("Same subject, same syllabus — differences here point at teaching practice, "
               "timetable slots or section composition.")

    st.markdown("##### Exam-by-exam distribution")
    long = sdf.melt(value_vars=[e for e in C.EXAM_TYPES if e in sdf.columns],
                    var_name="exam_type", value_name="pct")
    fig = px.violin(long, x="exam_type", y="pct", box=True, points=False, color="exam_type",
                    category_orders={"exam_type": C.EXAM_TYPES},
                    labels={"exam_type": "", "pct": "Score (%)"},
                    template=C.PLOTLY_TEMPLATE, color_discrete_sequence=C.COLOR_SEQUENCE)
    fig.add_hline(y=C.PASS_MARK_PCT, line_dash="dot", line_color="#E03131")
    fig.update_layout(showlegend=False, height=400, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")
