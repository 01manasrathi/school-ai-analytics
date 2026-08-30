"""Shared helpers for the Streamlit frontend: API client + auth session state."""
from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.environ.get("SCHOOL_AI_API_BASE", "http://127.0.0.1:8000")


def auth_headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


_headers = auth_headers  # internal alias used within this module


def api_get(path: str, params: dict | None = None):
    r = requests.get(f"{API_BASE}{path}", headers=_headers(), params=params, timeout=60)
    return _handle(r)


def api_post(path: str, json: dict | None = None, params: dict | None = None):
    r = requests.post(f"{API_BASE}{path}", headers=_headers(), json=json, params=params, timeout=180)
    return _handle(r)


def api_put(path: str, json: dict | None = None):
    r = requests.put(f"{API_BASE}{path}", headers=_headers(), json=json, timeout=60)
    return _handle(r)


def api_delete(path: str):
    r = requests.delete(f"{API_BASE}{path}", headers=_headers(), timeout=60)
    return _handle(r)


def _handle(r: requests.Response):
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"API error ({r.status_code}): {detail}")
        return None
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return r.content


def login(username: str, password: str) -> bool:
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            data={"username": username, "password": password},
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach backend API. Make sure it's running at " + API_BASE)
        return False
    if r.status_code != 200:
        st.error("Invalid username or password")
        return False
    data = r.json()
    st.session_state["token"] = data["access_token"]
    st.session_state["role"] = data["role"]
    st.session_state["username"] = data["username"]
    st.session_state["full_name"] = data["full_name"]
    return True


def logout():
    for key in ("token", "role", "username", "full_name"):
        st.session_state.pop(key, None)


def require_login():
    if "token" not in st.session_state:
        st.warning("Please log in from the Home page first.")
        st.stop()


def require_role(*roles: str):
    require_login()
    if st.session_state.get("role") not in roles:
        st.error("You do not have permission to view this page.")
        st.stop()


def sidebar_user_info():
    with st.sidebar:
        if "token" in st.session_state:
            st.markdown(f"**{st.session_state.get('full_name')}**")
            st.caption(f"Role: {st.session_state.get('role')}")
            if st.button("Log out"):
                logout()
                st.rerun()
        else:
            st.info("Not logged in")
