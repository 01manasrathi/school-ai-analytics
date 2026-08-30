"""Attendance patterns and the statistical drivers behind performance."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from student_analytics import config as C                # noqa: E402
from student_analytics.core import analytics, charts     # noqa: E402
from student_analytics.dashboard import shared           # noqa: E402

shared.page_setup("Attendance & Drivers")
ds = shared.require_dataset()
f = shared.sidebar_filters(ds, "ad")
df, label = f["df"], f["label"]

shared.hero(f"{label} — Attendance & Performance Drivers",
            "Monthly attendance patterns, the attendance–marks relationship, and which "
            "lifestyle factors actually correlate with results.")

if df.empty:
    st.warning("No students match the filters.")
    st.stop()

ids = df["student_id"]
att = ds.attendance[ds.attendance["student_id"].isin(ids)]

c = st.columns(6)
shared.kpi(c[0], "Average attendance", f"{df['attendance_pct'].mean():.1f}%")
shared.kpi(c[1], f"Below {C.ATTENDANCE_RISK_THRESHOLD:.0f}%",
           int((df["attendance_pct"] < C.ATTENDANCE_RISK_THRESHOLD).sum()), "students", "#E03131")
shared.kpi(c[2], "Perfect (≥98%)", int((df["attendance_pct"] >= 98).sum()), "students", "#00A86B")
shared.kpi(c[3], "Total days absent", f"{int(df['absent_days'].sum()):,}", "across the cohort")
shared.kpi(c[4], "Late arrivals", f"{int(df['late_days'].sum()):,}", "days")
shared.kpi(c[5], "Attendance momentum", f"{df['attendance_trend'].mean():+.1f} pts",
           "last 3 vs first 3 months",
           "#00A86B" if df["attendance_trend"].mean() >= 0 else "#E03131")
st.markdown("")

t1, t2, t3 = st.tabs(["📅 Attendance patterns", "🔗 Attendance ↔ marks", "🧪 Drivers of performance"])

with t1:
    split = st.selectbox("Split by", ["section", "campus", "performance_band", "risk_level",
                                     "gender", "has_tuition"], key="ad_split")
    st.plotly_chart(charts.attendance_trend(
        analytics.attendance_timeseries(ds.attendance, ids, split, df), split,
        f"Monthly attendance — {label}, split by {split.replace('_', ' ')}"),
        width="stretch")

    st.markdown("##### Month-by-month heatmap (sections × months)")
    a = att.merge(df[["student_id", "campus", "section"]], on="student_id", how="left")
    a["class_label"] = a["campus"].str.replace(" Campus", "", regex=False) + " / " + a["section"]
    piv = a.pivot_table(index="class_label", columns="month_label", values="attendance_pct",
                        aggfunc="mean").round(1)
    order = (att.sort_values("month_index")["month_label"].drop_duplicates().tolist())
    piv = piv[[m for m in order if m in piv.columns]]
    fig = px.imshow(piv, text_auto=".0f", aspect="auto", color_continuous_scale="RdYlGn",
                    template=C.PLOTLY_TEMPLATE, labels=dict(color="Attendance %"))
    fig.update_xaxes(side="top")
    fig.update_layout(height=max(360, 30 * len(piv) + 140), xaxis_title=None, yaxis_title=None,
                      margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("A dark band down one column is a school-wide event (exam week, festival, illness); "
               "a dark row is a section with a persistent attendance problem.")

    st.markdown("##### Chronic absentees")
    chronic = (att.groupby("student_id")
               .agg(months_below_75=("attendance_pct", lambda s: int((s < 75).sum())),
                    worst_month=("attendance_pct", "min"),
                    absent=("absent_days", "sum"))
               .reset_index()
               .merge(df[["student_id", "name", "section", "attendance_pct", "overall_pct",
                          "risk_level"]], on="student_id")
               .query("months_below_75 >= 2")
               .sort_values(["months_below_75", "attendance_pct"], ascending=[False, True]))
    st.metric("Students below 75% in 2+ months", f"{len(chronic):,}")
    shared.styled_table(chronic, height=420)
    shared.df_download(chronic, "chronic_absentees.csv", "⬇ Download list", key="dl_chronic")

with t2:
    a, b = st.columns([3, 2])
    a.plotly_chart(charts.attendance_vs_score_scatter(df), width="stretch")
    b.plotly_chart(charts.attendance_band_bar(analytics.attendance_vs_marks(df)),
                   width="stretch")
    corr = df[["attendance_pct", "overall_pct"]].corr().iloc[0, 1]
    band = analytics.attendance_vs_marks(df)
    if len(band) >= 2:
        lo, hi = band.iloc[0], band.iloc[-1]
        st.info(f"Correlation between attendance and overall score is **r = {corr:.2f}**. "
                f"Students in the **{lo['attendance_band']}%** attendance band average "
                f"**{lo['avg_pct']:.1f}%**, while those in **{hi['attendance_band']}%** average "
                f"**{hi['avg_pct']:.1f}%** — a gap of "
                f"**{hi['avg_pct'] - lo['avg_pct']:.1f} percentage points**.")
    shared.styled_table(band, height=320)

    st.markdown("##### Assignment submission vs. score")
    fig = px.density_heatmap(df, x="submission_rate", y="overall_pct", nbinsx=25, nbinsy=25,
                             color_continuous_scale="Blues", template=C.PLOTLY_TEMPLATE,
                             labels={"submission_rate": "Assignments submitted (%)",
                                     "overall_pct": "Overall score (%)"})
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")

with t3:
    drv = analytics.performance_drivers(df)
    a, b = st.columns([2, 3])
    a.plotly_chart(charts.drivers_bar(drv), width="stretch")
    with b:
        st.markdown("##### Correlation table")
        shared.styled_table(drv, height=420)
        st.caption("Correlation is not causation, but the ranking tells you which levers are "
                   "worth pulling first.")

    st.markdown("##### Explore any factor against results")
    factor = st.selectbox("Factor", [c for c in analytics.DRIVER_COLS if c in df.columns]
                          + ["parent_education", "has_tuition", "internet_access",
                             "transport_mode", "career_interest", "house"], key="ad_factor")
    if df[factor].dtype.kind in "if":
        fig = px.scatter(df, x=factor, y="overall_pct", color="performance_band",
                         color_discrete_map=C.BAND_COLORS, opacity=0.6,
                         hover_data=["name", "section"], template=C.PLOTLY_TEMPLATE,
                         labels={factor: factor.replace("_", " ").title(),
                                 "overall_pct": "Overall score (%)"})
        fig.update_layout(height=440, margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", y=1.02, x=1, xanchor="right", title=None))
        st.plotly_chart(fig, width="stretch")
        bins = np.linspace(df[factor].min(), df[factor].max(), 7)
        d = df.assign(bucket=np.round(np.digitize(df[factor], bins), 0))
        agg = (d.groupby("bucket").agg(range_from=(factor, "min"), range_to=(factor, "max"),
                                      students=("student_id", "count"),
                                      avg_score=("overall_pct", "mean")).round(2).reset_index())
        shared.styled_table(agg.drop(columns=["bucket"]), height=300)
    else:
        agg = (df.groupby(factor).agg(students=("student_id", "count"),
                                     avg_score=("overall_pct", "mean"),
                                     avg_attendance=("attendance_pct", "mean"),
                                     toppers=("performance_band",
                                              lambda s: int((s == "Topper").sum())))
               .round(2).reset_index().sort_values("avg_score", ascending=False))
        fig = px.bar(agg, x=factor, y="avg_score", color="avg_score",
                     color_continuous_scale="Tealgrn", text=agg["avg_score"].round(1),
                     template=C.PLOTLY_TEMPLATE,
                     labels={factor: factor.replace("_", " ").title(),
                             "avg_score": "Average score (%)"})
        fig.update_traces(textposition="outside")
        fig.update_layout(height=420, coloraxis_showscale=False,
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        shared.styled_table(agg, height=320)

    st.markdown("##### Multi-factor view")
    st.plotly_chart(charts.parallel_bands(df), width="stretch")
    st.caption("Drag along any axis to filter the cohort and see which combinations of "
               "attendance, submissions and study time land in the green band.")
