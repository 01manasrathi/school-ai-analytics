import pandas as pd
import streamlit as st
from utils import api_get, api_post, require_login, sidebar_user_info

st.set_page_config(page_title="Marks - School AI", page_icon="📝", layout="wide")
require_login()
sidebar_user_info()

st.title("📝 Marks & Grades")
role = st.session_state.get("role")

if role in ("admin", "teacher"):
    tab_entry, tab_view = st.tabs(["Enter Marks", "View Marks"])

    with tab_entry:
        classes = api_get("/classes") or []
        class_map = {f"{c['class_name']} {c['section']}": c["class_id"] for c in classes}
        if class_map:
            class_choice = st.selectbox("Class", list(class_map.keys()))
            class_id = class_map[class_choice]
            subjects = api_get("/subjects", params={"class_id": class_id}) or []
            subject_map = {s["subject_name"]: s["subject_id"] for s in subjects}
            if subject_map:
                subject_choice = st.selectbox("Subject", list(subject_map.keys()))
                subject_id = subject_map[subject_choice]
                exam_type = st.selectbox("Exam", ["Test1", "Test2", "Final"])
                max_marks = st.number_input("Max marks", value=50.0 if exam_type != "Final" else 100.0)

                students = api_get("/students", params={"class_id": class_id}) or []
                if students:
                    st.markdown(f"Enter marks for **{len(students)}** students:")
                    marks_input = {}
                    cols = st.columns(3)
                    for i, s in enumerate(students):
                        with cols[i % 3]:
                            marks_input[s["student_id"]] = st.number_input(
                                f"{s['name']}", min_value=0.0, max_value=float(max_marks),
                                value=0.0, key=f"mark_{s['student_id']}_{subject_id}_{exam_type}",
                            )
                    if st.button("Submit Marks", type="primary"):
                        payload = [
                            {
                                "student_id": sid, "subject_id": subject_id, "exam_type": exam_type,
                                "marks_obtained": val, "max_marks": max_marks,
                            }
                            for sid, val in marks_input.items()
                        ]
                        result = api_post("/marks/bulk", json=payload)
                        if result:
                            st.success(f"Saved marks for {result['count']} students")
            else:
                st.info("No subjects found for this class.")
        else:
            st.info("No classes found.")

    with tab_view:
        students = api_get("/students") or []
        student_map = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in students}
        if student_map:
            choice = st.selectbox("Student", list(student_map.keys()), key="marks_view_student")
            sid = student_map[choice]
            marks = api_get("/marks", params={"student_id": sid})
            if marks:
                st.dataframe(pd.DataFrame(marks), use_container_width=True, hide_index=True)
            else:
                st.info("No marks recorded yet.")
else:
    me = api_get("/auth/me")
    sid = me.get("linked_id") if me else None
    if sid:
        marks = api_get("/marks", params={"student_id": sid})
        if marks:
            st.dataframe(pd.DataFrame(marks), use_container_width=True, hide_index=True)
        else:
            st.info("No marks recorded yet.")
    else:
        st.warning("No student profile linked to this account.")
