import streamlit as st
from utils import API_BASE, auth_headers, api_get, api_post, require_login, sidebar_user_info
import requests

st.set_page_config(page_title="Reports - School AI", page_icon="📄", layout="wide")
require_login()
sidebar_user_info()

st.title("📄 Student Report Cards")
st.caption("Generates a PDF report card with weighted grades, class-average comparison charts "
           "and attendance breakdown (matplotlib + reportlab).")

role = st.session_state.get("role")

if role in ("admin", "teacher"):
    students = api_get("/students") or []
    student_map = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in students}
    if student_map:
        choice = st.selectbox("Select a student", list(student_map.keys()))
        sid = student_map[choice]
    else:
        sid = None
        st.info("No students found.")
else:
    me = api_get("/auth/me")
    sid = me.get("linked_id") if me else None

if sid:
    if st.button("Generate Report Card", type="primary"):
        with st.spinner("Generating PDF report..."):
            result = api_post(f"/reports/student/{sid}")
        if result:
            st.success("Report generated!")
            resp = requests.get(f"{API_BASE}/reports/student/{sid}/download", headers=auth_headers())
            if resp.status_code == 200:
                st.download_button(
                    "⬇️ Download PDF Report Card", data=resp.content,
                    file_name=f"report_{sid}.pdf", mime="application/pdf",
                )
