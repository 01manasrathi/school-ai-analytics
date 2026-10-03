"""Integration tests against the seeded database through the HTTP API."""
import io

from sqlalchemy import func, select

from app import models as M


def _crs(client, h):
    return {c["student_id"]: c for c in client.get("/api/change-requests", headers=h).json()}


def _offering(client, h, oid):
    return next(o for o in client.get("/api/offerings", headers=h).json() if o["id"] == oid)


def test_auth_required_and_readonly_role(client, admin, viewer):
    assert client.get("/api/students").status_code == 401
    assert client.get("/api/students", headers=viewer).status_code == 200
    assert client.post("/api/allocation/commit", headers=viewer, json={"placements": []}).status_code == 403


def test_seed_existing_students_are_valid(client, admin):
    students = client.get("/api/students?status=EXISTING", headers=admin).json()
    assert len(students) == 60
    for s in students:
        assert (s["hl"], s["sl"]) == (4, 3), s["student_id"]
        assert all(s["group_coverage"][g] >= 1 for g in "12345")
        assert all(b["choice"] for b in s["blocks"])
        assert s["valid"], s["issues"]
    new = client.get("/api/students?status=NEW", headers=admin).json()
    assert len(new) == 15 and not any(s["allocated"] for s in new)


def test_seed_change_request_statuses(client, admin):
    crs = _crs(client, admin)
    assert crs["S1020"]["feasibility_status"] == "FEASIBLE"
    assert crs["S1021"]["feasibility_status"] == "FEASIBLE"
    assert crs["S1022"]["feasibility_status"] == "FEASIBLE_WAITLIST"
    assert crs["S1023"]["feasibility_status"] == "NOT_FEASIBLE"
    assert crs["S1024"]["feasibility_status"] == "NEEDS_OVERRIDE"


def test_allocation_run_and_commit(client, admin, db_session):
    run = client.post("/api/allocation/run", headers=admin, json={}).json()
    assert run["summary"]["students"] == 15
    placements = [{"student_id": s["student_db_id"], "offering_id": x["offering_id"],
                   "status": "approved" if x["status"] == "ALLOCATED" else "waitlisted"}
                  for s in run["students"] for x in s["slots"] if x["offering_id"]]
    r = client.post("/api/allocation/commit", headers=admin, json={"placements": placements})
    assert r.status_code == 200, r.text
    for o in client.get("/api/offerings", headers=admin).json():
        assert o["current_enrollment"] <= o["capacity"], o
    new = client.get("/api/students?status=NEW", headers=admin).json()
    assert all(s["valid"] and (s["hl"], s["sl"]) == (4, 3) for s in new if run["summary"]["allocated"] == 15)
    with db_session() as db:  # stored enrollment matches actual approved choices
        for o in db.scalars(select(M.SubjectOffering)).all():
            n = db.scalar(select(func.count()).select_from(M.StudentChoice).where(
                M.StudentChoice.offering_id == o.id, M.StudentChoice.status == "approved"))
            assert n == o.current_enrollment
    # committing again is rejected
    assert client.post("/api/allocation/commit", headers=admin, json={"placements": placements}).status_code == 422
    assert client.post("/api/allocation/run", headers=admin, json={}).json()["summary"].get("students", 0) == 0


def test_commit_rejects_rule_violations(client, admin):
    run = client.post("/api/allocation/run", headers=admin, json={}).json()
    s = run["students"][0]
    placements = [{"student_id": s["student_db_id"], "offering_id": x["offering_id"]} for x in s["slots"][:6]]
    r = client.post("/api/allocation/commit", headers=admin, json={"placements": placements})
    assert r.status_code == 422
    assert "subjects" in str(r.json()["detail"]["errors"])


def test_commit_rejects_full_offering(client, admin):
    full = next(o for o in client.get("/api/offerings", headers=admin).json() if o["full"])
    run = client.post("/api/allocation/run", headers=admin, json={}).json()
    s = run["students"][0]
    placements = [{"student_id": s["student_db_id"], "offering_id": full["id"] if x["block"] == full["block"] else x["offering_id"]}
                  for x in s["slots"]]
    r = client.post("/api/allocation/commit", headers=admin, json={"placements": placements})
    assert r.status_code == 422 and "exceed capacity" in r.text


def test_feasibility_check_is_read_only(client, admin):
    cr = _crs(client, admin)["S1020"]
    before = _offering(client, admin, cr["requested_offering"]["id"])["current_enrollment"]
    r = client.post("/api/feasibility/check", headers=admin, json={
        "student_id": "S1020", "current_offering_id": cr["current_offering"]["id"],
        "requested_offering_id": cr["requested_offering"]["id"]}).json()
    assert r["status"] == "FEASIBLE"
    assert _offering(client, admin, cr["requested_offering"]["id"])["current_enrollment"] == before


def test_approve_feasible_change(client, admin):
    cr = _crs(client, admin)["S1020"]
    src, tgt = cr["current_offering"], cr["requested_offering"]
    r = client.post(f"/api/change-request/{cr['id']}/approve", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert _offering(client, admin, src["id"])["current_enrollment"] == src["current_enrollment"] - 1
    assert _offering(client, admin, tgt["id"])["current_enrollment"] == tgt["current_enrollment"] + 1
    grid = client.get("/api/students/S1020", headers=admin).json()
    assert grid["valid"] and any(b["choice"]["offering_id"] == tgt["id"] for b in grid["blocks"])


def test_approve_full_class_waitlists(client, admin):
    cr = _crs(client, admin)["S1022"]
    r = client.post(f"/api/change-request/{cr['id']}/approve", headers=admin)
    assert r.json()["status"] == "WAITLISTED"
    wl = client.get("/api/reports/waitlist", headers=admin).json()
    assert any(w["student_id"] == "S1022" and w["subject"] == "Chemistry" for w in wl)
    assert _offering(client, admin, cr["requested_offering"]["id"])["current_enrollment"] == 18


def test_approve_needs_override_is_blocked(client, admin):
    cr = _crs(client, admin)["S1024"]
    r = client.post(f"/api/change-request/{cr['id']}/approve", headers=admin)
    assert r.status_code == 409


def test_override_flow(client, admin):
    cr = _crs(client, admin)["S1024"]
    url = f"/api/change-request/{cr['id']}/override"
    assert client.post(url, headers=admin, json={"reason": ""}).status_code == 422
    src, tgt = cr["current_offering"], cr["requested_offering"]
    r = client.post(url, headers=admin, json={"reason": "Medical workload exemption approved by DP coordinator"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OVERRIDDEN" and body["override_by"] == "admin"
    assert _offering(client, admin, src["id"])["current_enrollment"] == src["current_enrollment"] - 1
    assert _offering(client, admin, tgt["id"])["current_enrollment"] == tgt["current_enrollment"] + 1
    log = client.get("/api/audit-log", headers=admin).json()
    entry = next(a for a in log if a["action"] == "ADMIN_OVERRIDE")
    assert "Medical workload exemption" in entry["new_value"]
    assert any(a["action"] == "ENROLLMENT_CHANGE" for a in log)
    assert client.post(url, headers=admin, json={"reason": "again please"}).status_code == 409


def test_override_cannot_bypass_block_conflict(client, admin):
    cr = _crs(client, admin)["S1023"]
    r = client.post(f"/api/change-request/{cr['id']}/override", headers=admin, json={"reason": "Please force it"})
    assert r.status_code == 409


def test_override_over_capacity(client, admin):
    cr = _crs(client, admin)["S1022"]  # Chemistry HL is full -> override places student anyway
    r = client.post(f"/api/change-request/{cr['id']}/override", headers=admin, json={"reason": "Medicine pathway priority"})
    assert r.status_code == 200
    assert _offering(client, admin, cr["requested_offering"]["id"])["current_enrollment"] == 19
    # a further request into the now over-capacity class is NOT_FEASIBLE
    other = next(s for s in client.get("/api/students?status=EXISTING", headers=admin).json()
                 if any(b["block"] == "D" and b["choice"]["subject_code"] == "BIO" and b["choice"]["level"] == "HL" for b in s["blocks"]))
    cur = next(b["choice"]["offering_id"] for b in other["blocks"] if b["block"] == "D")
    res = client.post("/api/feasibility/check", headers=admin, json={
        "student_id": other["student_id"], "current_offering_id": cur, "requested_offering_id": cr["requested_offering"]["id"]}).json()
    assert res["status"] == "NOT_FEASIBLE" and res["override_allowed"]


def test_create_change_request(client, admin):
    s = client.get("/api/students/S1030", headers=admin).json()
    c = next(b["choice"] for b in s["blocks"] if b["block"] == "C")
    target = next(o for o in client.get("/api/offerings", headers=admin).json()
                  if o["block"] == "C" and o["level"] == c["level"] and o["subject_code"] != c["subject_code"] and not o["full"])
    r = client.post("/api/change-request", headers=admin, json={
        "student_id": "S1030", "current_offering_id": c["offering_id"], "requested_offering_id": target["id"], "reason": "test"})
    assert r.status_code == 200 and r.json()["feasibility_status"] == "FEASIBLE"


def test_reports_csv(client, admin):
    for path in ("capacity", "waitlist", "unallocated", "allocation", "change-requests"):
        r = client.get(f"/api/reports/{path}?format=csv", headers=admin)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    cap = client.get("/api/reports/capacity?format=csv", headers=admin).text.splitlines()
    assert cap[0].startswith("block,subject_code,subject") and len(cap) == 51
    assert "Chemistry" in client.get("/api/reports/change-requests?format=csv", headers=admin).text


def test_csv_import_dry_run_and_commit(client, admin):
    csv_text = ("student_id,name,grade,programme,cohort_year,status\n"
                "S9001,Alice New,11,IBDP,2027,NEW\n"
                "S9002,Bad Grade,eleven,IBDP,2027,NEW\n")
    files = {"file": ("students.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    r = client.post("/api/import/csv", headers=admin, data={"type": "students", "dry_run": "true"}, files=files).json()
    assert r["total_rows"] == 2 and r["valid_rows"] == 1 and r["errors"][0]["row"] == 3 and not r["committed"]
    files = {"file": ("students.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    r = client.post("/api/import/csv", headers=admin, data={"type": "students", "skip_invalid": "true"}, files=files).json()
    assert r["committed"] and r["created"] == 1
    assert client.get("/api/students/S9001", headers=admin).status_code == 200
    assert client.get("/api/students/S9002", headers=admin).status_code == 404


def test_csv_import_with_column_mapping(client, admin):
    csv_text = "Pupil,Pref1,Pref2\nS2011,ECON:HL,MAA:SL\n"
    files = {"file": ("prefs.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    mapping = '{"Pupil": "student_id", "Pref1": "preference_1", "Pref2": "preference_2"}'
    r = client.post("/api/import/csv", headers=admin, data={"type": "preferences", "mapping": mapping}, files=files).json()
    assert r["committed"], r
    prefs = client.get("/api/students/S2011", headers=admin).json()["preferences"]
    assert [(p["subject_code"], p["level"]) for p in prefs] == [("ECON", "HL"), ("MAA", "SL")]


def test_settings_rule_change_affects_feasibility(client, admin):
    rules = client.get("/api/rules", headers=admin).json()["rules"]
    for rt in ("HL_COUNT", "SL_COUNT"):
        r = next(x for x in rules if x["rule_type"] == rt)
        body = {k: r[k] for k in ("programme_id", "rule_type", "condition", "value", "priority", "description")}
        assert client.put(f"/api/rules/{r['id']}", headers=admin, json={**body, "is_active": False}).status_code == 200
    cr = _crs(client, admin)["S1024"]
    r = client.post(f"/api/change-request/{cr['id']}/recheck", headers=admin).json()
    assert r["feasibility_status"] == "FEASIBLE"
