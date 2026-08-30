"""Deep dive on the two ends of the class: who is winning, who needs help."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from student_analytics import config as C                      # noqa: E402
from student_analytics.core import analytics, charts           # noqa: E402
from student_analytics.dashboard import shared                 # noqa: E402

shared.page_setup("Toppers & Improvement")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "ti")
df, label = f["df"], f["label"]

shared.hero(f"{label} — Toppers, Movers & Students Needing Support",
            "Ranked leaderboards, honour roll, momentum analysis and a ready-to-print "
            "intervention plan.")

if df.empty:
    st.warning("No students match the filters.")
    st.stop()

shared.kpi_row(df)
st.markdown("")

tab_top, tab_low, tab_move, tab_plan = st.tabs(
    ["🏆 Toppers & honour roll", "🎯 Needs improvement", "📈 Movers", "🧭 Intervention plan"])

# ------------------------------------------------------------------- toppers
with tab_top:
    n = st.slider("How many top students", 5, 50, 15, key="ti_top_n")
    tops = analytics.toppers(df, n)
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(charts.leaderboard_bar(tops, title=f"Top {n} — {label}"),
                    width="stretch")
    c2.plotly_chart(charts.grade_donut(df), width="stretch")
    shared.styled_table(tops, height=min(600, 38 * len(tops) + 40))
    shared.df_download(tops, "toppers.csv", "⬇ Download toppers", key="dl_top")

    st.markdown("#### Subject champions")
    st.caption("The single best student in each subject for this cohort.")
    shared.styled_table(analytics.subject_toppers(ds.master, df["student_id"]), height=340)

    st.markdown("#### Honour roll")
    st.caption("Strong (≥80%) **and** consistent (spread ≤10 pts) **and** present (≥90%) "
               "**and** no failed subject — sustained excellence, not a single good exam.")
    hr = analytics.honour_roll(df)
    st.metric("Students on the honour roll", f"{len(hr):,}",
              f"{len(hr) / len(df) * 100:.1f}% of the cohort")
    shared.styled_table(hr, height=420)

# ----------------------------------------------------------- needs improvement
with tab_low:
    st.caption(f"Ranked by a composite risk score: score {C.RISK_WEIGHTS['low_score']:.0%}, "
               f"attendance {C.RISK_WEIGHTS['low_attendance']:.0%}, "
               f"trend {C.RISK_WEIGHTS['negative_trend']:.0%}, "
               f"assignment submission {C.RISK_WEIGHTS['low_submission']:.0%}.")
    n2 = st.slider("How many students to review", 5, 60, 20, key="ti_low_n")
    weak = analytics.needs_improvement(df, n2)
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(charts.leaderboard_bar(weak, title=f"Lowest {n2} by risk", ascending=True,
                                          colorscale="Reds_r"), width="stretch")
    c2.plotly_chart(charts.risk_scatter(df), width="stretch")
    shared.styled_table(weak, height=min(620, 38 * len(weak) + 40))
    shared.df_download(weak, "needs_improvement.csv", "⬇ Download list", key="dl_low")

    st.markdown("#### Failing subjects across the cohort")
    fails = (ds.master[(ds.master["student_id"].isin(df["student_id"])) & (~ds.master["passed"])]
             .groupby("subject_name").size().sort_values(ascending=False)
             .rename("students_failing").reset_index())
    if fails.empty:
        st.success("No student is below the pass mark in this cohort.")
    else:
        shared.styled_table(fails, height=320)

    st.markdown("#### Attendance red flags")
    low_att = df[df["attendance_pct"] < C.ATTENDANCE_RISK_THRESHOLD].sort_values("attendance_pct")
    st.metric(f"Below {C.ATTENDANCE_RISK_THRESHOLD:.0f}% attendance", f"{len(low_att):,}")
    shared.styled_table(low_att[["student_id", "name", "section", "attendance_pct", "absent_days",
                                 "overall_pct", "risk_level"]], height=380)

# --------------------------------------------------------------------- movers
with tab_move:
    st.caption("Change in score from Unit Test 1 to the Final Exam, averaged across subjects. "
               "This separates students who are *currently* low from students who are *falling*.")
    n3 = st.slider("How many movers each way", 5, 40, 12, key="ti_mov_n")
    up, down = analytics.biggest_movers(df, n3)
    st.plotly_chart(charts.movers_tornado(up, down), width="stretch")
    c1, c2 = st.columns(2)
    c1.markdown("##### 📈 Most improved")
    shared.styled_table(up, height=min(520, 38 * len(up) + 40))
    c2.markdown("##### 📉 Steepest decline")
    shared.styled_table(down, height=min(520, 38 * len(down) + 40))

    st.markdown("#### Improving vs. declining, by section")
    d = df.assign(momentum=lambda x: x["trend_delta"].apply(
        lambda v: "Improving (>+3)" if v > 3 else ("Declining (<-3)" if v < -3 else "Stable")))
    pivot = (d.groupby(["section", "momentum"]).size().unstack(fill_value=0)
             .reset_index())
    shared.styled_table(pivot, height=320)

# ---------------------------------------------------------------------- plan
with tab_plan:
    st.caption("An actionable worksheet: who to help, which subjects to target, and the specific "
               "next step implied by their data.")
    n4 = st.slider("Plan size", 5, 60, 25, key="ti_plan_n")
    plan = analytics.intervention_plan(df, ds.master, n4)
    if plan.empty:
        st.success("No students currently require intervention in this cohort.")
    else:
        st.dataframe(plan, width="stretch", hide_index=True, height=620,
                     column_config={
                         "overall_pct": st.column_config.ProgressColumn(
                             "Overall %", format="%.1f%%", min_value=0, max_value=100),
                         "risk_score": st.column_config.ProgressColumn(
                             "Risk", format="%.0f", min_value=0, max_value=100),
                         "recommended_actions": st.column_config.TextColumn("Recommended actions",
                                                                           width="large"),
                         "why_flagged": st.column_config.TextColumn("Why flagged", width="large"),
                     })
        shared.df_download(plan, "intervention_plan.csv", "⬇ Download the plan", key="dl_plan2")
