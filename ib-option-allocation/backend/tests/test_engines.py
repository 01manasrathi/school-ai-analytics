"""Unit tests for the pure feasibility and allocation engines (no database)."""
import copy
import json
from collections import Counter
from types import SimpleNamespace

import pytest

from app.engines import allocate, check_feasibility
from app.engines.types import BlockInfo, OfferingInfo, StudentInfo
from app.rules import DEFAULT_RULES, build_ruleset

BLOCKS = [BlockInfo(i + 1, n, sort_order=i + 1, period=f"L{i + 1}") for i, n in enumerate("ABCDEFG")]
BID = {b.name: b.id for b in BLOCKS}


def rules_with(**changes):
    rows = []
    for r in DEFAULT_RULES:
        row = SimpleNamespace(rule_type=r["rule_type"], condition_json=json.dumps(r["condition"]), value=r["value"],
                              priority=r["priority"], is_active=True)
        if r["rule_type"] in changes:
            ch = changes[r["rule_type"]]
            if ch is None:
                row.is_active = False
            else:
                row.value = ch
        rows.append(row)
    return build_ruleset(rows)


RULES = rules_with()


def off(id_, code, name, group, level, block, cap=18, enr=10, min_e=8, **kw):
    return OfferingInfo(id=id_, subject_id=hash(code) % 10_000, subject_code=code, subject_name=name, group=group,
                        level=level, block_id=BID[block], block_name=block, capacity=cap, enrollment=enr,
                        min_enrollment=min_e, block_period=f"L{BID[block]}", **kw)


def world():
    return {o.id: o for o in [
        off(1, "ENG", "English A", 1, "HL", "A"), off(2, "ENG", "English A", 1, "SL", "A"),
        off(3, "FRE", "French B", 2, "HL", "B"), off(4, "FRE", "French B", 2, "SL", "B"),
        off(5, "ECON", "Economics", 3, "HL", "C"), off(6, "ECON", "Economics", 3, "SL", "C"),
        off(7, "PSYCH", "Psychology", 3, "HL", "C"), off(8, "PSYCH", "Psychology", 3, "SL", "C"),
        off(9, "BIO", "Biology", 4, "HL", "D"), off(10, "BIO", "Biology", 4, "SL", "D"),
        off(11, "CHEM", "Chemistry", 4, "HL", "D", enr=18), off(12, "CHEM", "Chemistry", 4, "SL", "D"),
        off(13, "MAA", "Maths AA", 5, "HL", "E"), off(14, "MAA", "Maths AA", 5, "SL", "E"),
        off(15, "GLOB", "Global Politics", 3, "HL", "E"), off(16, "GLOB", "Global Politics", 3, "SL", "E"),
        off(17, "VA", "Visual Arts", 6, "HL", "F"), off(18, "VA", "Visual Arts", 6, "SL", "F"),
        off(19, "CS", "Computer Science", 4, "SL", "F"),
        off(20, "FILM", "Film", 6, "HL", "G"), off(21, "FILM", "Film", 6, "SL", "G"),
        off(22, "GEOG", "Geography", 3, "SL", "G"), off(23, "GEOG", "Geography", 3, "HL", "E"),
    ]}


STUDENT = StudentInfo(id=1, student_id="S1", name="Test", grade=11, programme_id=None)
CURRENT_IDS = [1, 4, 7, 9, 13, 18, 22]  # ENG HL, FRE SL, PSYCH HL, BIO HL, MAA HL, VA SL, GEOG SL


def check(cur_id, req_id, w=None, rules=RULES, student=STUDENT, comp=None):
    w = w or world()
    swaps = [(w[cur_id], w[req_id])] + ([(w[comp[0]], w[comp[1]])] if comp else [])
    return check_feasibility(student, [w[i] for i in CURRENT_IDS], swaps, rules, list(w.values()))


# ---------------------------------------------------------------- feasibility

def test_same_block_swap_is_feasible():
    r = check(7, 5)  # Psychology HL -> Economics HL (Block C)
    assert r["status"] == "FEASIBLE"
    assert r["impact"]["blockChange"] == {"from": "C", "to": "C", "changed": False}
    assert r["impact"]["hlSlAfter"] == {"hl": 4, "sl": 3}
    assert r["impact"]["targetSeatsAfter"] == 7


def test_cross_block_conflict_detected():
    r = check(22, 19)  # Geography SL (G) -> Computer Science SL (F) while student has Visual Arts SL in F
    assert r["status"] == "NOT_FEASIBLE"
    assert "Block conflict: student already has Visual Arts SL in Block F" in r["reasons"]
    assert r["override_allowed"] is False


def test_cross_block_with_compensating_change_is_feasible():
    r = check(18, 21, comp=(22, 19))  # VA SL(F)->Film SL(G) + Geography SL(G)->CS SL(F)
    assert r["status"] == "FEASIBLE", r["reasons"]


def test_full_class_returns_waitlist():
    r = check(9, 11)  # Biology HL -> Chemistry HL (18/18)
    assert r["status"] == "FEASIBLE_WAITLIST"
    assert any("full (18/18)" in x for x in r["reasons"])
    assert r["impact"]["targetSeatsAfter"] == 0


def test_over_capacity_returns_not_feasible_but_overridable():
    w = world()
    w[11].enrollment = 19
    r = check(9, 11, w)
    assert r["status"] == "NOT_FEASIBLE"
    assert r["override_allowed"] is True


def test_hl_sl_violation_needs_override():
    r = check(7, 8)  # Psychology HL -> Psychology SL
    assert r["status"] == "NEEDS_OVERRIDE"
    assert any("HL/SL ratio would become 3 HL / 4 SL" in x for x in r["reasons"])


def test_hl_sl_rule_is_configurable():
    r = check(7, 8, rules=rules_with(HL_COUNT=None, SL_COUNT=None))
    assert r["status"] == "FEASIBLE"


def test_group_violation_needs_override():
    r = check(13, 15)  # Maths HL -> Global Politics HL (Group 3) in Block E
    assert r["status"] == "NEEDS_OVERRIDE"
    assert any("Group 5" in x for x in r["reasons"])
    assert any("Mathematics requirement" in x for x in r["reasons"])


def test_duplicate_subject_not_feasible():
    r = check(13, 23)  # Maths HL -> Geography HL while already taking Geography SL
    assert r["status"] == "NOT_FEASIBLE"
    assert any("Duplicate subject: Geography" in x for x in r["reasons"])
    assert r["override_allowed"] is False


def test_min_enrollment_warning():
    w = world()
    w[7].enrollment = 8
    r = check(7, 5, w)
    assert r["status"] == "FEASIBLE"
    assert any("below minimum enrollment (7/8)" in x for x in r["warnings"])


def test_prerequisites():
    w = world()
    w[5].prerequisites = ["IGCSE_ECON"]
    assert check(7, 5, w)["status"] == "NEEDS_OVERRIDE"
    st = copy.copy(STUDENT)
    st.prior_subjects = ["IGCSE_ECON"]
    assert check(7, 5, w, student=st)["status"] == "FEASIBLE"


def test_inactive_target_not_feasible():
    w = world()
    w[5].is_active = False
    r = check(7, 5, w)
    assert r["status"] == "NOT_FEASIBLE" and r["override_allowed"] is False


# ---------------------------------------------------------------- allocation

def _assert_valid(slots, rules=RULES):
    alloc = [s for s in slots if s["offering_id"]]
    assert len(alloc) == 7
    assert len({s["block"] for s in alloc}) == 7
    assert sum(s["level"] == "HL" for s in alloc) == 4 and sum(s["level"] == "SL" for s in alloc) == 3
    assert {1, 2, 3, 4, 5} <= {s["group"] for s in alloc}
    assert len({s["subject_code"] for s in alloc}) == 7


def test_allocation_new_student_respects_rules_and_preferences():
    st = StudentInfo(id=9, student_id="N1", name="New", grade=11, programme_id=None,
                     preferences=[(1, "ECON", "HL"), (2, "CHEM", "HL"), (3, "FILM", "HL")])
    r = allocate([st], BLOCKS, list(world().values()), RULES)
    s = r["students"][0]
    assert s["status"] == "ALLOCATED"
    _assert_valid(s["slots"])
    by_block = {x["block"]: x for x in s["slots"]}
    assert by_block["C"]["subject_code"] == "ECON" and by_block["C"]["level"] == "HL"
    assert by_block["D"]["subject_code"] != "CHEM" or by_block["D"]["level"] != "HL"  # Chemistry HL is full
    assert any("Chemistry HL not assigned: full" in x for x in by_block["D"]["reasons"])
    assert by_block["E"]["subject_code"] == "MAA"  # Maths is compulsory even though GLOB has seats


def test_allocation_never_exceeds_capacity():
    w = world()
    for o in w.values():
        o.capacity, o.enrollment = 4, 0
    students = [StudentInfo(id=i, student_id=f"N{i:02}", name=f"N{i}", grade=11, programme_id=None) for i in range(20)]
    r = allocate(students, BLOCKS, list(w.values()), RULES)
    used = Counter(x["offering_id"] for s in r["students"] for x in s["slots"] if x["status"] == "ALLOCATED")
    assert all(used[o.id] <= o.capacity for o in w.values())
    for s in r["students"]:
        if s["status"] == "ALLOCATED":
            _assert_valid(s["slots"])
    assert all(row["seats_left"] >= 0 for row in r["offerings"])


def test_allocation_no_seats_in_block_waitlists_slot():
    w = world()
    for oid in (13, 14, 15, 16, 23):  # every Block E offering full
        w[oid].enrollment = w[oid].capacity
    st = StudentInfo(id=9, student_id="N1", name="New", grade=11, programme_id=None, preferences=[(1, "MAA", "HL")])
    r = allocate([st], BLOCKS, list(w.values()), RULES)
    s = r["students"][0]
    assert s["status"] == "PARTIAL"
    e = next(x for x in s["slots"] if x["block"] == "E")
    assert e["status"] == "WAITLISTED" and e["flag"] == "UNALLOCATED_SLOT" and e["subject_code"] == "MAA"
    assert all(x["status"] == "ALLOCATED" for x in s["slots"] if x["block"] != "E")
    assert r["summary"]["waitlisted_slots"] == 1
    row = next(o for o in r["offerings"] if o["offering_id"] == 13)
    assert row["new_allocated"] == 0 and row["waitlisted"] == 1


def test_allocation_uses_configured_hl_sl_counts():
    rules = rules_with(HL_COUNT="3", SL_COUNT="4")
    st = StudentInfo(id=9, student_id="N1", name="New", grade=11, programme_id=None)
    s = allocate([st], BLOCKS, list(world().values()), rules)["students"][0]
    assert (s["hl"], s["sl"]) == (3, 4)


def test_allocation_impossible_rules_reports_unallocated():
    w = {k: v for k, v in world().items() if v.group != 5}  # no Maths offered at all
    st = StudentInfo(id=9, student_id="N1", name="New", grade=11, programme_id=None)
    s = allocate([st], BLOCKS, list(w.values()), RULES)["students"][0]
    assert s["status"] == "UNALLOCATED"


@pytest.mark.parametrize("rank_order", [True, False])
def test_allocation_priority_order(rank_order):
    w = world()
    w[5].enrollment = 17  # one seat left in Economics HL
    a = StudentInfo(id=1, student_id="A", name="A", grade=11, programme_id=None, priority=1 if rank_order else 2,
                    preferences=[(1, "ECON", "HL")])
    b = StudentInfo(id=2, student_id="B", name="B", grade=11, programme_id=None, priority=2 if rank_order else 1,
                    preferences=[(1, "ECON", "HL")])
    r = allocate([a, b], BLOCKS, list(w.values()), RULES)
    got = {s["student_id"]: next(x for x in s["slots"] if x["block"] == "C") for s in r["students"]}
    winner = "A" if rank_order else "B"
    assert got[winner]["subject_code"] == "ECON" and got[winner]["level"] == "HL"
