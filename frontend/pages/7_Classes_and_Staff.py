import pandas as pd
import streamlit as st
from utils import api_delete, api_get, api_post, require_role, sidebar_user_info

st.set_page_config(page_title="Classes & Staff - School AI", page_icon="🏫", layout="wide")
require_role("admin")
sidebar_user_info()

st.title("🏫 Classes, Subjects & Teachers")

tab_classes, tab_subjects, tab_teachers = st.tabs(["Classes", "Subjects", "Teachers"])

with tab_classes:
    classes = api_get("/classes") or []
    st.dataframe(pd.DataFrame(classes), use_container_width=True, hide_index=True)
    teachers = api_get("/teachers") or []
    teacher_map = {t["name"]: t["teacher_id"] for t in teachers}
    with st.form("class_form"):
        c1, c2, c3 = st.columns(3)
        class_name = c1.text_input("Class name (e.g. Grade 6)")
        section = c2.text_input("Section (e.g. A)")
        teacher_choice = c3.selectbox("Class teacher", ["(none)"] + list(teacher_map.keys()))
        if st.form_submit_button("Add Class"):
            payload = {
                "class_name": class_name, "section": section,
                "class_teacher_id": teacher_map.get(teacher_choice, ""),
            }
            if api_post("/classes", json=payload):
                st.success("Class added")
                st.rerun()

    if classes:
        del_id = st.selectbox("Delete class", [""] + [c["class_id"] for c in classes], key="del_class")
        if st.button("Delete Class") and del_id:
            if api_delete(f"/classes/{del_id}"):
                st.success("Deleted")
                st.rerun()

with tab_subjects:
    classes = api_get("/classes") or []
    class_map = {f"{c['class_name']} {c['section']}": c["class_id"] for c in classes}
    subjects = api_get("/subjects") or []
    st.dataframe(pd.DataFrame(subjects), use_container_width=True, hide_index=True)
    teachers = api_get("/teachers") or []
    teacher_map = {t["name"]: t["teacher_id"] for t in teachers}
    with st.form("subject_form"):
        c1, c2, c3 = st.columns(3)
        subject_name = c1.text_input("Subject name")
        class_choice = c2.selectbox("Class", list(class_map.keys()) if class_map else [])
        teacher_choice = c3.selectbox("Teacher", ["(none)"] + list(teacher_map.keys()))
        if st.form_submit_button("Add Subject"):
            payload = {
                "subject_name": subject_name, "class_id": class_map.get(class_choice, ""),
                "teacher_id": teacher_map.get(teacher_choice, ""),
            }
            if api_post("/subjects", json=payload):
                st.success("Subject added")
                st.rerun()

    if subjects:
        del_id = st.selectbox("Delete subject", [""] + [s["subject_id"] for s in subjects], key="del_subject")
        if st.button("Delete Subject") and del_id:
            if api_delete(f"/subjects/{del_id}"):
                st.success("Deleted")
                st.rerun()

with tab_teachers:
    teachers = api_get("/teachers") or []
    st.dataframe(pd.DataFrame(teachers), use_container_width=True, hide_index=True)
    with st.form("teacher_form"):
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("Name")
        email = c2.text_input("Email")
        phone = c3.text_input("Phone")
        spec = c4.text_input("Subject specialization")
        if st.form_submit_button("Add Teacher"):
            payload = {"name": name, "email": email, "phone": phone, "subject_specialization": spec}
            if api_post("/teachers", json=payload):
                st.success("Teacher added")
                st.rerun()

    if teachers:
        del_id = st.selectbox("Delete teacher", [""] + [t["teacher_id"] for t in teachers], key="del_teacher")
        if st.button("Delete Teacher") and del_id:
            if api_delete(f"/teachers/{del_id}"):
                st.success("Deleted")
                st.rerun()

    st.divider()
    st.subheader("👤 Create Login User")
    st.caption("Create a login account (admin/teacher/student) linked to a teacher or student ID.")
    students = api_get("/students") or []
    with st.form("user_form"):
        c1, c2, c3 = st.columns(3)
        new_username = c1.text_input("Username")
        new_password = c2.text_input("Password", type="password")
        new_role = c3.selectbox("Role", ["admin", "teacher", "student"])
        full_name = st.text_input("Full name")
        linked_id = ""
        if new_role == "teacher" and teachers:
            t_choice = st.selectbox("Linked teacher", [t["name"] for t in teachers])
            linked_id = next(t["teacher_id"] for t in teachers if t["name"] == t_choice)
        elif new_role == "student" and students:
            s_choice = st.selectbox("Linked student", [s["name"] for s in students])
            linked_id = next(s["student_id"] for s in students if s["name"] == s_choice)
        if st.form_submit_button("Create User"):
            result = api_post("/auth/users", params={
                "username": new_username, "password": new_password, "role": new_role,
                "full_name": full_name, "linked_id": linked_id,
            })
            if result:
                st.success(f"User '{new_username}' created")
