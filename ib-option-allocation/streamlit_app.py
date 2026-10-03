"""IB Option Allocation & Change Feasibility Tool — Streamlit UI.

This is a second, self-contained front end for the same backend. It imports the FastAPI
project's engines and services directly (no HTTP call, no API server needed), so a single
`streamlit run streamlit_app.py` is the whole application. All IB rules, feasibility and
allocation decisions still come from backend/app/engines and the rules table.

Run locally:      streamlit run streamlit_app.py
Streamlit Cloud:  main file = streamlit_app.py, dependencies = requirements.txt
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

# A writable database location. Streamlit Cloud gives every run a fresh container, so the
# default SQLite file is re-created and re-seeded on first start unless DATABASE_URL is set
# (use st.secrets / env var to point at PostgreSQL for persistent storage).
if not os.getenv("DATABASE_URL"):
    try:
        if "DATABASE_URL" in st.secrets:
            os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    except Exception:
        pass

from fastapi import HTTPException  # noqa: E402  (services raise HTTPException; we render it)
from sqlalchemy import func, inspect, select  # noqa: E402

from app import models as M  # noqa: E402
from app.auth import CurrentUser, verify_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.routers import allocation as allocation_api  # noqa: E402
from app.routers import change_requests as cr_api  # noqa: E402
from app.routers import imports as import_api  # noqa: E402
from app.routers import meta as meta_api  # noqa: E402
from app.routers import reports as reports_api  # noqa: E402
from app.routers import settings as settings_api  # noqa: E402
from app.seed import seed_data  # noqa: E402
from app.services import (  # noqa: E402
    get_student,
    offering_dict,
    offering_query,
    run_feasibility,
    student_grid,
)

st.set_page_config(page_title="IB Option Allocation Tool", page_icon="🎓", layout="wide")

STATUS_COLOR = {
    "FEASIBLE": "#059669", "APPROVED": "#059669", "ALLOCATED": "#059669", "OK": "#059669",
    "FEASIBLE_WAITLIST": "#d97706", "WAITLISTED": "#d97706", "PARTIAL": "#d97706", "FULL": "#d97706",
    "NEEDS_OVERRIDE": "#ea580c", "NOT_FEASIBLE": "#e11d48", "UNALLOCATED": "#e11d48", "OVER_CAPACITY": "#e11d48",
    "OVERRIDDEN": "#7c3aed", "PENDING": "#0284c7", "BELOW_MIN": "#0284c7", "REJECTED": "#64748b",
}


# --------------------------------------------------------------------------- infrastructure

@st.cache_resource
def bootstrap() -> dict:
    """Create the schema and load the demo data the first time the app starts."""
    created = False
    if not inspect(engine).has_table("students"):
        Base.metadata.create_all(engine)
        created = True
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(M.Student)) == 0:
            seed_data(db)
            created = True
    return {"seeded": created}


def session():
    return SessionLocal()


def user() -> CurrentUser | None:
    u = st.session_state.get("user")
    return CurrentUser(u["username"], u["role"]) if u else None


def is_admin() -> bool:
    u = user()
    return bool(u and u.is_admin)


def show_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            st.error(detail.get("message", str(detail)))
            for e in detail.get("errors", []) or []:
                st.caption(f"• {e.get('student_id') or ''} {e.get('message')}")
            feas = detail.get("feasibility")
            if feas:
                for r in feas.get("reasons", []):
                    st.caption(f"• {r}")
        else:
            st.error(str(detail))
    else:
        st.error(f"{type(exc).__name__}: {exc}")


def badge(status: str | None) -> str:
    if not status:
        return ""
    colour = STATUS_COLOR.get(status, "#64748b")
    return f":{'green' if colour == '#059669' else 'orange' if colour in ('#d97706', '#ea580c') else 'red' if colour == '#e11d48' else 'violet' if colour == '#7c3aed' else 'blue'}[**{status.replace('_', ' ')}**]"


def download_csv(rows: list[dict], filename: str, label: str = "Download CSV") -> None:
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    st.download_button(label, buf.getvalue(), file_name=filename, mime="text/csv")


# --------------------------------------------------------------------------- login

def login_view() -> None:
    st.title("🎓 IB Option Allocation & Change Feasibility Tool")
    st.caption("Local tool for IGCSE (Grades 7-10) and IBDP (Grades 11-12) option management.")
    with st.form("login"):
        col1, col2 = st.columns(2)
        username = col1.text_input("Username", value="admin")
        password = col2.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            with session() as db:
                row = db.scalar(select(M.User).where(M.User.username == username.strip()))
            if row and verify_password(password, row.password_hash):
                st.session_state["user"] = {"username": row.username, "role": row.role}
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.info("Demo accounts — **admin / admin123** (Admin & Timetabler) · **viewer / viewer123** (read-only)")


# --------------------------------------------------------------------------- pages

def page_dashboard() -> None:
    st.header("Dashboard")
    with session() as db:
        d = meta_api.dashboard(db)
    c = st.columns(4)
    c[0].metric("Existing students", d["students"]["existing"])
    c[1].metric("New students", d["students"]["new"])
    c[2].metric("Seats used", f"{d['total_enrolled']} / {d['total_capacity']}")
    c[3].metric("Active offerings", d["offerings"])
    c = st.columns(4)
    c[0].metric("Full classes", len(d["full_classes"]))
    c[1].metric("Waitlist entries", d["waitlist_count"])
    c[2].metric("Pending change requests", d["pending_change_requests"])
    c[3].metric("Unallocated new students", len(d["unallocated_new_students"]))

    left, right = st.columns(2)
    with left:
        st.subheader("Full / over-capacity classes")
        if d["full_classes"]:
            st.dataframe(pd.DataFrame([{"Block": o["block"], "Subject": o["subject"], "Level": o["level"],
                                        "Enrolled": f"{o['current_enrollment']}/{o['capacity']}"}
                                       for o in d["full_classes"]]), hide_index=True, width="stretch")
        else:
            st.caption("Nothing is full — every class still has seats.")
    with right:
        st.subheader("New students needing attention")
        if d["unallocated_new_students"]:
            st.dataframe(pd.DataFrame(d["unallocated_new_students"])[["student_id", "name", "approved_choices"]],
                         hide_index=True, width="stretch")
        else:
            st.caption("All new students are fully allocated.")

    st.subheader(f"Classes below minimum enrollment ({len(d['below_min_classes'])})")
    if d["below_min_classes"]:
        st.dataframe(pd.DataFrame([{"Block": o["block"], "Subject": o["subject"], "Level": o["level"],
                                    "Enrolled": o["current_enrollment"], "Minimum": o["min_enrollment"]}
                                   for o in d["below_min_classes"]]), hide_index=True, width="stretch")


def _student_rows(students: list[dict]) -> pd.DataFrame:
    rows = []
    for s in students:
        row = {"ID": s["student_id"], "Name": s["name"], "Status": s["status"]}
        for b in s["blocks"]:
            ch = b["choice"]
            row[f"Block {b['block']}"] = f"{ch['subject_code']} {ch['level']}" if ch else "—"
        row["HL/SL"] = f"{s['hl']}/{s['sl']}"
        row["Groups"] = " ".join(f"G{g}:{n}" for g, n in s["group_coverage"].items())
        row["Valid"] = "✅" if s["valid"] else ("❌" if s["allocated"] else "—")
        rows.append(row)
    return pd.DataFrame(rows)


def page_allocations() -> None:
    st.header("Existing Allocations")
    c = st.columns([1, 2, 2, 1])
    status = c[0].selectbox("Status", ["EXISTING", "NEW", "WITHDRAWN", "All"])
    query = c[1].text_input("Search name or ID")
    with session() as db:
        q = select(M.Student).order_by(M.Student.student_id)
        if status != "All":
            q = q.where(M.Student.status == status)
        ids = db.scalars(q).all()
        cache: dict = {}
        students = [student_grid(db, get_student(db, s.id), cache) for s in ids]
    if query:
        ql = query.lower()
        students = [s for s in students if ql in s["name"].lower() or ql in s["student_id"].lower()]
    subjects = sorted({b["choice"]["subject"] for s in students for b in s["blocks"] if b["choice"]})
    subject = c[2].selectbox("Takes subject", ["Any"] + subjects)
    if subject != "Any":
        students = [s for s in students if any(b["choice"] and b["choice"]["subject"] == subject for b in s["blocks"])]
    only_issues = c[3].checkbox("Only issues")
    if only_issues:
        students = [s for s in students if not s["valid"]]

    st.caption(f"{len(students)} students")
    st.dataframe(_student_rows(students), hide_index=True, width="stretch", height=430)
    download_csv([{k: v for k, v in r.items()} for r in _student_rows(students).to_dict("records")],
                 "allocation_table.csv")

    if students:
        pick = st.selectbox("Inspect a student's block grid",
                            [f"{s['student_id']} · {s['name']}" for s in students])
        s = next(x for x in students if f"{x['student_id']} · {x['name']}" == pick)
        cols = st.columns(len(s["blocks"]))
        for col, b in zip(cols, s["blocks"]):
            ch = b["choice"]
            with col:
                st.caption(f"Block {b['block']}")
                if ch:
                    st.markdown(f"**{ch['subject']}**")
                    st.caption(f"{ch['level']} · Group {ch['group']}")
                else:
                    st.markdown(":red[— empty —]")
                for w in b["waitlisted"]:
                    st.caption(f"⏳ waitlist: {w['subject']} {w['level']}")
        st.write(f"**{s['hl']} HL / {s['sl']} SL** · groups " +
                 " ".join(f"G{g}:{n}" for g, n in s["group_coverage"].items()))
        for issue in s["issues"]:
            st.warning(f"[{issue['severity']}] {issue['message']}")


def page_new_allocation() -> None:
    st.header("New Student Allocation")
    st.caption("Run a dry run, review or edit the proposal, then commit. Nothing is stored until you commit.")

    if st.button("▶ Run allocation (dry run)", type="primary"):
        with session() as db:
            try:
                st.session_state["proposal"] = allocation_api.run(allocation_api.RunIn(), db, user())
                st.session_state.pop("edits", None)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)

    proposal = st.session_state.get("proposal")
    if not proposal:
        return
    if not proposal["students"]:
        st.info("No unallocated NEW students — everyone already has choices.")
        return

    summary = proposal["summary"]
    cols = st.columns(len(summary))
    for col, (k, v) in zip(cols, summary.items()):
        col.metric(k.replace("_", " ").title(), v)

    rows = [{"Student": f"{s['student_id']} {s['name']}", "Status": s["status"], "HL": s["hl"], "SL": s["sl"],
             **{f"Block {x['block']}": (f"{x['subject_code']} {x['level']}" +
                                        (" ⏳" if x["status"] == "WAITLISTED" else "")) if x["offering_id"] else "—"
                for x in s["slots"]}}
            for s in proposal["students"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with session() as db:
        offerings = [offering_dict(o) for o in db.scalars(offering_query()).unique().all()]
    by_block = {}
    for o in offerings:
        by_block.setdefault(o["block_id"], []).append(o)

    edits: dict = st.session_state.setdefault("edits", {})
    with st.expander("Adjust a student's placement manually"):
        pick = st.selectbox("Student", [f"{s['student_id']} · {s['name']}" for s in proposal["students"]])
        s = next(x for x in proposal["students"] if f"{x['student_id']} · {x['name']}" == pick)
        for slot in s["slots"]:
            choices = [o for o in by_block.get(slot["block_id"], []) if o["is_active"]]
            labels = [f"{o['subject']} {o['level']} — {o['seats_left']} left" for o in choices]
            key = f"{s['student_db_id']}:{slot['block_id']}"
            current = edits.get(key, slot["offering_id"])
            index = next((i for i, o in enumerate(choices) if o["id"] == current), 0)
            sel = st.selectbox(f"Block {slot['block']}", labels, index=index, key=f"sel-{key}")
            edits[key] = choices[labels.index(sel)]["id"]
            st.caption(" · ".join(slot["reasons"]))

    st.subheader("Seats per offering after this proposal")
    st.dataframe(pd.DataFrame(proposal["offerings"]), hide_index=True, width="stretch", height=260)

    if not is_admin():
        st.info("Read-only role: committing requires the Admin / Timetabler account.")
        return
    reason = st.text_input("Override reason (only if manual edits break a rule or capacity)")
    if st.button("💾 Commit allocation", type="primary"):
        placements = []
        for s in proposal["students"]:
            for slot in s["slots"]:
                oid = edits.get(f"{s['student_db_id']}:{slot['block_id']}", slot["offering_id"])
                if not oid:
                    continue
                offering = next((o for o in offerings if o["id"] == oid), None)
                edited = f"{s['student_db_id']}:{slot['block_id']}" in edits
                status = ("approved" if (offering and offering["seats_left"] > 0) else "waitlisted") if edited else (
                    "approved" if slot["status"] == "ALLOCATED" else "waitlisted")
                placements.append(allocation_api.Placement(student_id=s["student_db_id"], offering_id=oid, status=status))
        with session() as db:
            try:
                result = allocation_api.commit(
                    allocation_api.CommitIn(placements=placements, override_reason=reason or None), db, user())
                st.success(f"Committed {result['committed_students']} students ({result['placements']} placements).")
                st.session_state.pop("proposal", None)
                st.session_state.pop("edits", None)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)


def _feasibility_card(result: dict) -> None:
    st.markdown(f"### Result: {badge(result['status'])}")
    if result["status"] != "FEASIBLE":
        st.caption("Admin override allowed with a reason." if result["override_allowed"]
                   else "Hard conflict — this can never be overridden.")
    for r in result["reasons"]:
        st.write(f"• {r}")
    for w in result["warnings"]:
        st.warning(f"⚠ {w}")
    imp = result["impact"]
    c = st.columns(5)
    c[0].metric("Target seats after", imp["targetSeatsAfter"])
    c[1].metric("Source seats after", imp["sourceSeatsAfter"])
    bc = imp["blockChange"] if isinstance(imp["blockChange"], list) else [imp["blockChange"]]
    c[2].metric("Block change", ", ".join(f"{b['from']}→{b['to']}" for b in bc))
    c[3].metric("HL / SL after", f"{imp['hlSlAfter']['hl']} HL / {imp['hlSlAfter']['sl']} SL")
    c[4].metric("Group coverage", " ".join(f"G{g}:{n}" for g, n in imp["groupCoverageAfter"].items()))


def page_change_requests() -> None:
    st.header("Change Requests")

    with session() as db:
        students = [student_grid(db, get_student(db, s.id)) for s in
                    db.scalars(select(M.Student).order_by(M.Student.student_id)).all()]
        offerings = [offering_dict(o) for o in db.scalars(offering_query()).unique().all()]
    students = [s for s in students if s["allocated"]]
    offerings.sort(key=lambda o: (o["block"], o["subject"], o["level"]))

    st.subheader("Test a change")
    c = st.columns(4)
    pick = c[0].selectbox("Student", ["—"] + [f"{s['student_id']} · {s['name']}" for s in students])
    if pick != "—":
        s = next(x for x in students if f"{x['student_id']} · {x['name']}" == pick)
        choices = [b["choice"] for b in s["blocks"] if b["choice"]]
        cur_label = c[1].selectbox("Current subject",
                                   [f"{ch['subject']} {ch['level']} (Block {ch['block']})" for ch in choices])
        cur = next(ch for ch in choices
                   if f"{ch['subject']} {ch['level']} (Block {ch['block']})" == cur_label)
        opts = [o for o in offerings if o["is_active"] and o["id"] != cur["offering_id"]]
        req_label = c[2].selectbox(
            "Requested subject / level",
            [f"[{o['block']}] {o['subject']} {o['level']} — {o['current_enrollment']}/{o['capacity']}"
             + (" FULL" if o["full"] else "") for o in opts])
        req = opts[[f"[{o['block']}] {o['subject']} {o['level']} — {o['current_enrollment']}/{o['capacity']}"
                    + (" FULL" if o["full"] else "") for o in opts].index(req_label)]
        priority = c[3].number_input("Priority (1 = highest)", 1, 5, 3)

        comp_cur_id = comp_req_id = None
        with st.expander("Optional compensating change (fix the HL/SL ratio or free the target block)"):
            others = [ch for ch in choices if ch["offering_id"] != cur["offering_id"]]
            cc = st.selectbox("Also move from", ["— none —"] +
                              [f"{ch['subject']} {ch['level']} (Block {ch['block']})" for ch in others])
            if cc != "— none —":
                comp_cur_id = next(ch["offering_id"] for ch in others
                                   if f"{ch['subject']} {ch['level']} (Block {ch['block']})" == cc)
                cr_opts = [o for o in offerings if o["is_active"] and o["id"] != comp_cur_id]
                cr_labels = [f"[{o['block']}] {o['subject']} {o['level']}" for o in cr_opts]
                comp_req_id = cr_opts[cr_labels.index(st.selectbox("…to", cr_labels))]["id"]

        reason = st.text_input("Reason", placeholder="Why is this change requested?")
        with session() as db:
            try:
                result = run_feasibility(db, get_student(db, s["student_id"]), cur["offering_id"], req["id"],
                                         comp_cur_id, comp_req_id)
                _feasibility_card(result)
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
                result = None
        if result and is_admin() and st.button("Submit change request"):
            with session() as db:
                try:
                    cr_api.create_cr(cr_api.CRIn(
                        student_id=s["student_id"], current_offering_id=cur["offering_id"],
                        requested_offering_id=req["id"], compensating_current_offering_id=comp_cur_id,
                        compensating_requested_offering_id=comp_req_id, reason=reason, priority=int(priority)), db, user())
                    st.success("Change request created.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    show_error(exc)

    st.divider()
    st.subheader("All change requests")
    with session() as db:
        crs = cr_api.list_crs(None, db)
    if not crs:
        st.caption("No change requests.")
        return
    fmt = lambda o: f"{o['subject']} {o['level']} ({o['block']})" if o else ""  # noqa: E731
    st.dataframe(pd.DataFrame([{
        "#": c["id"], "Student": f"{c['student_id']} {c['student_name']}",
        "From": fmt(c["current_offering"]), "To": fmt(c["requested_offering"]),
        "Compensating": (fmt(c["compensating_current_offering"]) + " → " + fmt(c["compensating_requested_offering"]))
        if c["compensating_current_offering"] else "",
        "Priority": c["priority"], "Feasibility": c["feasibility_status"], "Status": c["status"],
        "Reason": c["reason"]} for c in crs]), hide_index=True, width="stretch")

    open_crs = [c for c in crs if c["status"] in ("PENDING", "WAITLISTED")]
    if not open_crs:
        return
    pick = st.selectbox("Act on request", [f"#{c['id']} {c['student_id']} → {fmt(c['requested_offering'])}" for c in open_crs])
    cr = open_crs[[f"#{c['id']} {c['student_id']} → {fmt(c['requested_offering'])}" for c in open_crs].index(pick)]
    _feasibility_card(cr["feasibility"])
    if not is_admin():
        st.info("Read-only role: approving or rejecting requires the Admin / Timetabler account.")
        return
    c = st.columns(3)
    if c[0].button("✅ Approve", type="primary"):
        with session() as db:
            try:
                st.success(f"Request #{cr['id']} is now {cr_api.approve(cr['id'], db, user())['status']}.")
            except Exception as exc:  # noqa: BLE001
                show_error(exc)
    if c[1].button("🔄 Re-check"):
        with session() as db:
            cr_api.recheck(cr["id"], db, user())
        st.rerun()
    if c[2].button("✖ Reject"):
        with session() as db:
            try:
                cr_api.reject(cr["id"], cr_api.RejectIn(reason="Rejected by timetabler"), db, user())
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                show_error(exc)


def page_override() -> None:
    st.header("Admin Override")
    st.caption("Force a change the rules would block. A reason is mandatory and every override is audited.")
    with session() as db:
        crs = [c for c in cr_api.list_crs(None, db) if c["status"] in ("PENDING", "WAITLISTED")]
    if not crs:
        st.info("No open change requests.")
    else:
        fmt = lambda o: f"{o['subject']} {o['level']} (Block {o['block']}) {o['current_enrollment']}/{o['capacity']}"  # noqa: E731
        labels = [f"#{c['id']} {c['student_id']} → {c['requested_offering']['subject']} "
                  f"{c['requested_offering']['level']} [{c['feasibility_status']}]" for c in crs]
        cr = crs[labels.index(st.selectbox("Open requests", labels))]
        st.write(f"**{cr['student_id']} · {cr['student_name']}**")
        st.write(f"From: {fmt(cr['current_offering'])}")
        st.write(f"To: **{fmt(cr['requested_offering'])}**")
        if cr["reason"]:
            st.caption(f"Reason given: {cr['reason']}")
        _feasibility_card(cr["feasibility"])
        if is_admin():
            reason = st.text_area("Override reason (required, minimum 5 characters)")
            if st.button("🛡 Apply override", type="primary", disabled=len(reason.strip()) < 5):
                with session() as db:
                    try:
                        cr_api.override(cr["id"], cr_api.OverrideIn(reason=reason), db, user())
                        st.success(f"Change request #{cr['id']} overridden; enrollment updated and audited.")
                    except Exception as exc:  # noqa: BLE001
                        show_error(exc)
        else:
            st.info("Read-only role: overriding requires the Admin / Timetabler account.")

    st.subheader("Audit log (latest 50)")
    with session() as db:
        log = meta_api.audit_log(50, db)
    st.dataframe(pd.DataFrame([{"Time": a["timestamp"][:19].replace("T", " "), "User": a["user"], "Action": a["action"],
                                "Entity": f"{a['entity']} {a['entity_id']}", "Old": a["old_value"][:80],
                                "New": a["new_value"][:120]} for a in log]),
                 hide_index=True, width="stretch", height=320)


REPORTS = {
    "Capacity by subject / block": ("capacity", lambda db: reports_api.capacity("json", db)),
    "Waitlist": ("waitlist", lambda db: reports_api.waitlist("json", db)),
    "Unallocated students": ("unallocated", lambda db: reports_api.unallocated("json", db)),
    "Allocation per student": ("allocation", lambda db: reports_api.allocation(None, "json", db)),
}


def page_reports() -> None:
    st.header("Reports")
    name = st.radio("Report", list(REPORTS.keys()) + ["Change requests"], horizontal=True)
    with session() as db:
        if name == "Change requests":
            key, rows = "change_requests", [{
                "id": c["id"], "student": f"{c['student_id']} {c['student_name']}",
                "current": f"{c['current_offering']['subject']} {c['current_offering']['level']}",
                "requested": f"{c['requested_offering']['subject']} {c['requested_offering']['level']}",
                "feasibility": c["feasibility_status"], "status": c["status"],
                "reasons": "; ".join(c["feasibility"].get("reasons", [])),
                "override_reason": c["override_reason"] or ""} for c in cr_api.list_crs(None, db)]
        else:
            key, fn = REPORTS[name]
            rows = fn(db)
    st.caption(f"{len(rows)} rows")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=460)
        download_csv(rows, f"{key}_report.csv", "⬇ Export CSV")
    else:
        st.caption("No rows for this report.")


def page_import() -> None:
    st.header("Import CSV")
    st.caption("Recommended order: blocks → subjects → offerings → students → existing choices → preferences → change requests.")
    kind = st.selectbox("Data type", list(import_api.SPECS.keys()))
    fields, required = import_api.SPECS[kind]
    st.write("Columns: " + ", ".join(f"**{f}**" if f in required else f for f in fields) + "  (bold = required)")
    st.download_button("⬇ Download template", ",".join(fields) + "\n", file_name=f"{kind}_template.csv", mime="text/csv")

    upload = st.file_uploader("CSV file", type="csv")
    if not upload:
        return
    text = upload.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    suggested = import_api.suggest_mapping(headers, fields)
    st.subheader("Column mapping")
    mapping = {}
    cols = st.columns(min(3, max(1, len(headers))))
    for i, h in enumerate(headers):
        options = ["— ignore —"] + fields
        default = suggested.get(h, "— ignore —")
        chosen = cols[i % len(cols)].selectbox(h, options, index=options.index(default) if default in options else 0,
                                               key=f"map-{kind}-{h}")
        if chosen != "— ignore —":
            mapping[h] = chosen

    missing = [f for f in required if f not in mapping.values()]
    if missing:
        st.error("Required columns not mapped: " + ", ".join(missing))
        return
    skip_invalid = st.checkbox("Skip invalid rows")
    dry = st.button("1 · Validate (dry run)")
    commit = st.button("2 · Import", type="primary", disabled=not is_admin())
    if not (dry or commit):
        return

    result = {"total": 0, "valid": 0, "created": 0, "updated": 0, "errors": []}
    with session() as db:
        for i, raw in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            row = {field: (raw.get(h) or "").strip() for h, field in mapping.items()}
            result["total"] += 1
            empty = [f for f in required if not row.get(f)]
            if empty:
                result["errors"].append({"row": i, "message": f"Missing value for {', '.join(empty)}"})
                continue
            sp = db.begin_nested()
            try:
                outcome = import_api.import_row(db, kind, row)
                db.flush()
                sp.commit()
                result["valid"] += 1
                result[outcome] += 1
            except Exception as exc:  # noqa: BLE001
                sp.rollback()
                msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc).split("\n")[0]
                result["errors"].append({"row": i, "message": msg})
        if commit and is_admin() and (not result["errors"] or skip_invalid):
            if kind == "choices":
                from app.services import recompute_enrollment
                recompute_enrollment(db)
            db.commit()
            st.success(f"Imported: {result['created']} created, {result['updated']} updated.")
        else:
            db.rollback()

    c = st.columns(3)
    c[0].metric("Rows", result["total"])
    c[1].metric("Valid", result["valid"])
    c[2].metric("Errors", len(result["errors"]))
    if result["errors"]:
        st.dataframe(pd.DataFrame(result["errors"]), hide_index=True, width="stretch")
        if commit and not skip_invalid:
            st.warning("Nothing was imported. Fix the errors or tick “Skip invalid rows”.")


def page_settings() -> None:
    st.header("Settings")
    st.caption("Every IB rule, capacity and block lives in the database — nothing is hardcoded.")
    tab_rules, tab_offerings = st.tabs(["IB rules", "Capacities / offerings"])

    with tab_rules:
        with session() as db:
            payload = settings_api.list_rules(db)
        rules = payload["rules"]
        df = pd.DataFrame([{"id": r["id"], "active": r["is_active"], "rule_type": r["rule_type"], "value": r["value"],
                            "condition": json.dumps(r["condition"]), "priority": r["priority"],
                            "description": r["description"]} for r in rules])
        edited = st.data_editor(df, hide_index=True, width="stretch", disabled=not is_admin(),
                                column_config={"id": st.column_config.NumberColumn(disabled=True)}, key="rules-editor")
        with st.expander("What each rule type means"):
            for k, v in payload["rule_types"].items():
                st.write(f"**{k}** — {v}")
        if is_admin() and st.button("💾 Save rule changes"):
            changed = 0
            with session() as db:
                for before, after in zip(df.to_dict("records"), edited.to_dict("records")):
                    if before == after:
                        continue
                    original = next(r for r in rules if r["id"] == after["id"])
                    try:
                        settings_api.update_rule(int(after["id"]), settings_api.RuleIn(
                            programme_id=original["programme_id"], rule_type=after["rule_type"],
                            condition=json.loads(after["condition"] or "{}"), value=str(after["value"]),
                            priority=int(after["priority"]), is_active=bool(after["active"]),
                            description=after["description"] or ""), db, user())
                        changed += 1
                    except Exception as exc:  # noqa: BLE001
                        show_error(exc)
            st.success(f"Saved {changed} rule(s). Feasibility and allocation use them immediately.")

    with tab_offerings:
        with session() as db:
            offerings = sorted((offering_dict(o) for o in db.scalars(offering_query()).unique().all()),
                               key=lambda o: (o["block"], o["subject"], o["level"]))
        df = pd.DataFrame([{"id": o["id"], "block": o["block"], "subject": o["subject"], "level": o["level"],
                            "teacher": o["teacher"], "room": o["room"], "capacity": o["capacity"],
                            "min_enrollment": o["min_enrollment"], "enrolled": o["current_enrollment"],
                            "active": o["is_active"]} for o in offerings])
        edited = st.data_editor(
            df, hide_index=True, width="stretch", height=420, disabled=not is_admin(),
            column_config={k: st.column_config.Column(disabled=True) for k in ("id", "block", "subject", "level", "enrolled")},
            key="offerings-editor")
        if is_admin():
            c = st.columns(2)
            if c[0].button("💾 Save capacity changes"):
                changed = 0
                with session() as db:
                    for before, after in zip(df.to_dict("records"), edited.to_dict("records")):
                        if before == after:
                            continue
                        try:
                            settings_api.update_offering(int(after["id"]), settings_api.OfferingIn(
                                teacher=after["teacher"], room=after["room"], capacity=int(after["capacity"]),
                                min_enrollment=int(after["min_enrollment"]), is_active=bool(after["active"])), db, user())
                            changed += 1
                        except Exception as exc:  # noqa: BLE001
                            show_error(exc)
                st.success(f"Saved {changed} offering(s).")
            if c[1].button("🔄 Recompute enrollment from approved choices"):
                with session() as db:
                    st.success(f"{settings_api.recompute(db, user())['offerings_changed']} offering(s) corrected.")


def page_danger() -> None:
    st.header("Demo data")
    st.caption("Reload the 60 existing students, 15 new students and 5 change requests. This wipes current data.")
    if not is_admin():
        st.info("Read-only role.")
        return
    confirm = st.text_input("Type RESET to confirm")
    if st.button("♻ Reload demo data", disabled=confirm != "RESET"):
        with session() as db:
            summary = seed_data(db)
        st.cache_resource.clear()
        st.success(f"Demo data reloaded: {summary}")


PAGES = {
    "Dashboard": page_dashboard,
    "Existing Allocations": page_allocations,
    "New Student Allocation": page_new_allocation,
    "Change Requests": page_change_requests,
    "Admin Override": page_override,
    "Reports": page_reports,
    "Import CSV": page_import,
    "Settings": page_settings,
    "Demo data": page_danger,
}


def main() -> None:
    bootstrap()
    if not st.session_state.get("user"):
        login_view()
        return
    u = st.session_state["user"]
    with st.sidebar:
        st.markdown("### 🎓 IB Option Allocation")
        st.caption("& Change Feasibility Tool")
        choice = st.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")
        st.divider()
        st.caption(f"**{u['username']}** · {'Admin / Timetabler' if u['role'] == 'ADMIN' else 'Read-only'}")
        if st.button("Log out"):
            st.session_state.pop("user")
            st.rerun()
    PAGES[choice]()


main()
