import pandas as pd
import streamlit as st
from utils import api_delete, api_get, api_post, api_put, require_login, sidebar_user_info

st.set_page_config(page_title="Students - School AI", page_icon="🧑‍🎓", layout="wide")
require_login()
sidebar_user_info()

st.title("🧑‍🎓 Students")
role = st.session_state.get("role")

classes = api_get("/classes") or []
class_map = {c["class_id"]: f"{c['class_name']} {c['section']}" for c in classes}

students = api_get("/students") or []
df = pd.DataFrame(students)
if not df.empty:
    df["class_name"] = df["class_id"].map(class_map)

st.subheader("Directory")
search = st.text_input("Search by name")
show_df = df.copy()
if not show_df.empty and search:
    show_df = show_df[show_df["name"].str.contains(search, case=False, na=False)]
st.dataframe(show_df, use_container_width=True, hide_index=True)

if role in ("admin", "teacher"):
    st.divider()
    st.subheader("➕ Add / ✏️ Update Student")
    with st.form("student_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            existing_ids = [""] + (df["student_id"].tolist() if not df.empty else [])
            edit_id = st.selectbox("Edit existing (optional)", existing_ids)
            name = st.text_input("Full name")
            gender = st.selectbox("Gender", ["M", "F", "Other"])
        with col2:
            class_choice = st.selectbox("Class", list(class_map.keys()) if class_map else [],
                                         format_func=lambda cid: class_map.get(cid, cid))
            roll_no = st.text_input("Roll No")
            dob = st.date_input("Date of birth")
        with col3:
            parent_name = st.text_input("Parent name")
            parent_contact = st.text_input("Parent contact")
            email = st.text_input("Email")

        submitted = st.form_submit_button("Save Student")
        if submitted:
            payload = {
                "name": name, "gender": gender, "dob": str(dob), "class_id": class_choice,
                "roll_no": roll_no, "parent_name": parent_name, "parent_contact": parent_contact,
                "email": email, "address": "", "enrollment_date": "",
            }
            if edit_id:
                result = api_put(f"/students/{edit_id}", json=payload)
            else:
                result = api_post("/students", json=payload)
            if result:
                st.success(f"Saved student {result.get('name')}")
                st.rerun()

if role == "admin":
    st.divider()
    st.subheader("🗑️ Delete Student")
    del_id = st.selectbox("Student to delete", [""] + (df["student_id"].tolist() if not df.empty else []))
    if st.button("Delete", type="primary") and del_id:
        if api_delete(f"/students/{del_id}"):
            st.success("Deleted")
            st.rerun()
