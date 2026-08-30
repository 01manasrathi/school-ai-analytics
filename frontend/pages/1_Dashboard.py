import pandas as pd
import plotly.express as px
import streamlit as st
from utils import api_get, require_role, sidebar_user_info

st.set_page_config(page_title="Dashboard - School AI", page_icon="📊", layout="wide")
require_role("admin", "teacher")
sidebar_user_info()

st.title("📊 School Dashboard")

summary = api_get("/analytics/dashboard")
if summary:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Students", summary["total_students"])
    c2.metric("Teachers", summary["total_teachers"])
    c3.metric("Classes", summary["total_classes"])
    c4.metric("Attendance %", f"{summary['overall_attendance_pct']}%")
    c5.metric("Avg Marks %", f"{summary['avg_marks_pct']}%")

    st.divider()
    left, right = st.columns([1, 1])

    with left:
        st.subheader("📈 Attendance Trend (last 30 days)")
        trend = api_get("/analytics/attendance-trend", params={"days": 30})
        if trend:
            df = pd.DataFrame(trend)
            fig = px.line(df, x="date", y="attendance_pct", markers=True,
                           title="Overall Attendance % Over Time")
            fig.update_layout(yaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No attendance data yet.")

    with right:
        st.subheader("⚠️ At-Risk Students")
        st.caption(f"{summary['at_risk_count']} student(s) flagged (low attendance or failing marks)")
        at_risk = api_get("/analytics/at-risk")
        if at_risk:
            df = pd.DataFrame(at_risk)
            df["reasons"] = df["reasons"].apply(lambda r: ", ".join(r))
            st.dataframe(
                df[["student_id", "name", "class_id", "attendance_pct", "avg_marks_pct", "reasons"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.success("No at-risk students 🎉")

    st.divider()
    st.subheader("🏫 Class Performance Explorer")
    classes = api_get("/classes") or []
    if classes:
        class_map = {f"{c['class_name']} {c['section']} ({c['class_id']})": c["class_id"] for c in classes}
        choice = st.selectbox("Select a class", list(class_map.keys()))
        class_id = class_map[choice]
        perf = api_get(f"/analytics/class-performance/{class_id}")
        if perf:
            colA, colB = st.columns([1, 1])
            with colA:
                st.markdown("**Subject Averages**")
                sub_df = pd.DataFrame(perf["subject_averages"])
                if not sub_df.empty:
                    fig = px.bar(sub_df, x="subject_name", y="avg_pct", title="Average % by Subject")
                    fig.update_layout(yaxis_range=[0, 100])
                    st.plotly_chart(fig, use_container_width=True)
            with colB:
                st.markdown("**Student Rankings**")
                rank_df = pd.DataFrame(perf["student_rankings"])
                st.dataframe(rank_df, use_container_width=True, hide_index=True)
