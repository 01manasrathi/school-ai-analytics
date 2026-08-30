import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st
from utils import api_get, api_post, require_login, sidebar_user_info

st.set_page_config(page_title="Attendance - School AI", page_icon="🗓️", layout="wide")
require_login()
sidebar_user_info()

st.title("🗓️ Attendance")
role = st.session_state.get("role")
linked_id = st.session_state.get("linked_id")

if role in ("admin", "teacher"):
    tab_mark, tab_view, tab_trend = st.tabs(["Mark Attendance", "View by Student", "Class Trend"])

    with tab_mark:
        classes = api_get("/classes") or []
        class_map = {f"{c['class_name']} {c['section']} ({c['class_id']})": c["class_id"] for c in classes}
        if class_map:
            choice = st.selectbox("Class", list(class_map.keys()))
            class_id = class_map[choice]
            date = st.date_input("Date", value=dt.date.today())
            students = api_get("/students", params={"class_id": class_id}) or []
            if students:
                st.markdown(f"**{len(students)} students** in this class")
                statuses = {}
                cols = st.columns(3)
                for i, s in enumerate(students):
                    with cols[i % 3]:
                        statuses[s["student_id"]] = st.selectbox(
                            f"{s['name']} (Roll {s.get('roll_no', '-')})",
                            ["Present", "Absent", "Late"],
                            key=f"att_{s['student_id']}_{date}",
                        )
                if st.button("Submit Attendance", type="primary"):
                    records = [{"student_id": sid, "status": status} for sid, status in statuses.items()]
                    result = api_post("/attendance/bulk", json={
                        "class_id": class_id, "date": str(date), "records": records,
                    })
                    if result:
                        st.success(f"Marked attendance for {result['count']} students on {date}")
            else:
                st.info("No students found in this class.")
        else:
            st.info("No classes found. Add classes first.")

    with tab_view:
        students = api_get("/students") or []
        student_map = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in students}
        if student_map:
            choice = st.selectbox("Student", list(student_map.keys()))
            sid = student_map[choice]
            summary = api_get(f"/attendance/summary/{sid}")
            if summary:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Attendance %", f"{summary['attendance_pct']}%")
                c2.metric("Present", summary["present"])
                c3.metric("Late", summary["late"])
                c4.metric("Absent", summary["absent"])
            history = api_get("/attendance", params={"student_id": sid})
            if history:
                st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)

    with tab_trend:
        classes = api_get("/classes") or []
        class_map = {"All classes": ""} | {f"{c['class_name']} {c['section']}": c["class_id"] for c in classes}
        choice = st.selectbox("Scope", list(class_map.keys()), key="trend_scope")
        days = st.slider("Days", 7, 90, 30)
        trend = api_get("/analytics/attendance-trend", params={"class_id": class_map[choice] or None, "days": days})
        if trend:
            df = pd.DataFrame(trend)
            fig = px.line(df, x="date", y="attendance_pct", markers=True)
            fig.update_layout(yaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No attendance data for this selection.")
else:
    # Student view: only their own attendance
    me = api_get("/auth/me")
    sid = me.get("linked_id") if me else None
    if sid:
        summary = api_get(f"/attendance/summary/{sid}")
        if summary:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Attendance %", f"{summary['attendance_pct']}%")
            c2.metric("Present", summary["present"])
            c3.metric("Late", summary["late"])
            c4.metric("Absent", summary["absent"])
        history = api_get("/attendance", params={"student_id": sid})
        if history:
            st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
    else:
        st.warning("No student profile linked to this account.")
