"""School AI — Streamlit frontend entry point (login / landing page)."""
import streamlit as st
from utils import login, sidebar_user_info

st.set_page_config(page_title="School AI", page_icon="🏫", layout="wide")

sidebar_user_info()

st.title("🏫 School AI — Smart Attendance, Marks & Insights")
st.caption("Open-source, local-first school management platform with an agentic AI assistant "
           "(Streamlit + FastAPI + CSV storage + local LLM via Ollama).")

if "token" in st.session_state:
    st.success(f"Logged in as **{st.session_state['full_name']}** ({st.session_state['role']})")
    st.markdown(
        "Use the sidebar to navigate to **Dashboard**, **Students**, **Attendance**, "
        "**Marks**, **Reports**, **AI Assistant**, or **Classes & Subjects**."
    )
else:
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
        if submitted:
            if login(username, password):
                st.rerun()

    with st.expander("Demo credentials"):
        st.markdown(
            """
            | Role | Username | Password |
            |------|----------|----------|
            | Admin | `admin` | `admin123` |
            | Teacher | `teacher1` | `teacher123` |
            | Student | `student1` | `student123` |
            """
        )
        st.caption("These accounts are created by running `python seed_data.py` from the project root.")

st.divider()
st.markdown(
    """
    ### What's inside
    - **Student & Class Management** — CRUD for students, teachers, classes and subjects.
    - **Attendance Tracking** — daily marking, per-student history, attendance trend charts.
    - **Marks & Report Cards** — weighted grading, auto-generated PDF report cards with charts.
    - **Analytics Dashboard** — school-wide KPIs, at-risk student detection, class performance.
    - **AI Assistant** — an agentic workflow (local Llama 3.1 via Ollama) that can query live
      school data through tools and answer natural-language questions.

    All data is stored in plain **CSV files** under `data/` — no database, no Docker required.
    """
)
