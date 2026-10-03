"""Feasibility engine for change requests.

check_feasibility() is pure: it receives the student, the student's current (approved) choices,
the swap(s) requested and the RuleSet, and returns a JSON-serialisable verdict.
"""
from __future__ import annotations

from ..rules import NEEDS_OVERRIDE, NOT_FEASIBLE, RuleSet
from .types import OfferingInfo, StudentInfo, grade_matches
from .validation import summarize, validate_programme

FEASIBLE = "FEASIBLE"
FEASIBLE_WAITLIST = "FEASIBLE_WAITLIST"
STATUS_RANK = {FEASIBLE: 0, FEASIBLE_WAITLIST: 1, NEEDS_OVERRIDE: 2, NOT_FEASIBLE: 3}

Swap = tuple[OfferingInfo, OfferingInfo]  # (current offering, requested offering)


def check_feasibility(
    student: StudentInfo,
    current_choices: list[OfferingInfo],
    swaps: list[Swap],
    rules: RuleSet,
    all_offerings: list[OfferingInfo] | None = None,
) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []
    state = {"status": FEASIBLE, "override_allowed": True}

    def flag(status: str, msg: str, hard: bool = False):
        reasons.append(msg)
        if STATUS_RANK[status] > STATUS_RANK[state["status"]]:
            state["status"] = status
        if hard:
            state["override_allowed"] = False

    current_ids = {o.id for o in current_choices}
    removed = {cur.id for cur, _ in swaps}

    # 1. Validity of the request
    if student.status == "WITHDRAWN":
        flag(NOT_FEASIBLE, "Student is withdrawn", hard=True)
    for cur, req in swaps:
        if cur.id not in current_ids:
            flag(NOT_FEASIBLE, f"Student is not currently enrolled in {cur.label}", hard=True)
        if req.id == cur.id:
            flag(NOT_FEASIBLE, "Requested offering is the same as the current offering", hard=True)
        elif req.id in current_ids and req.id not in removed:
            flag(NOT_FEASIBLE, f"Student is already enrolled in {req.label}", hard=True)
        if not req.is_active or not req.subject_active:
            flag(NOT_FEASIBLE, f"{req.label} is not active", hard=True)
        if student.programme_id is not None and req.programme_id is not None and req.programme_id != student.programme_id:
            flag(NOT_FEASIBLE, f"{req.label} is not offered in the student's programme", hard=True)
        if not grade_matches(req.block_grade, student.grade):
            flag(NOT_FEASIBLE, f"{req.label} is not offered for Grade {student.grade}", hard=True)

    after = [o for o in current_choices if o.id not in removed] + [req for _, req in swaps]

    # 2. Block logic
    block_changes = []
    block_conflict = False
    for cur, req in swaps:
        block_changes.append({"from": cur.block_name, "to": req.block_name, "changed": cur.block_id != req.block_id})
        if cur.block_id != req.block_id:
            occupants = [o for o in current_choices if o.block_id == req.block_id and o.id not in removed]
            for occ in occupants:
                block_conflict = True
                flag(NOT_FEASIBLE, f"Block conflict: student already has {occ.label} in Block {req.block_name}", hard=True)

    # 3, 5, 6 (+ period clashes): full programme validation after the swap
    before_keys = {(i.code, i.message) for i in validate_programme(current_choices, rules, student.prior_subjects)}
    for issue in validate_programme(after, rules, student.prior_subjects):
        if issue.code == "BLOCK_CONFLICT" and block_conflict:
            continue
        if (issue.code, issue.message) in before_keys:
            warnings.append(f"Pre-existing issue (not caused by this change): {issue.message}")
            continue
        flag(issue.severity, issue.message, hard=not issue.overridable)

    # 4. Capacity of the target offering(s)
    waitlisted = False
    for cur, req in swaps:
        if req.enrollment > req.capacity:
            flag(rules.over_capacity_severity, f"{req.label} is over capacity ({req.enrollment}/{req.capacity})")
        elif req.enrollment >= req.capacity:
            if rules.waitlist_when_full:
                waitlisted = True
                flag(FEASIBLE_WAITLIST, f"{req.label} is full ({req.enrollment}/{req.capacity}) - student can be waitlisted")
            else:
                flag(NOT_FEASIBLE, f"{req.label} is full ({req.enrollment}/{req.capacity})")

    # 7. Teacher / room clashes (data-level, warning only)
    if rules.timetable_check and all_offerings:
        for _, req in swaps:
            if not req.block_period:
                continue
            for o in all_offerings:
                if o.id == req.id or not o.is_active or o.block_period != req.block_period or o.block_id == req.block_id:
                    continue
                if req.teacher and o.teacher == req.teacher:
                    warnings.append(f"Teacher clash: {req.teacher} also teaches {o.label} in period {req.block_period}")
                if req.room and o.room == req.room:
                    warnings.append(f"Room clash: {req.room} is also used by {o.label} in period {req.block_period}")

    # 8. Source class impact
    for cur, _ in swaps:
        if rules.min_enrollment_warning and cur.enrollment - 1 < cur.min_enrollment:
            warnings.append(f"{cur.label} would drop below minimum enrollment ({cur.enrollment - 1}/{cur.min_enrollment})")

    if state["status"] == FEASIBLE:
        reasons.append("All checks passed")

    summary = summarize(after)
    primary_cur, primary_req = swaps[0]
    return {
        "status": state["status"],
        "reasons": reasons,
        "warnings": warnings,
        "override_allowed": state["override_allowed"] and state["status"] != FEASIBLE,
        "impact": {
            "targetSeatsAfter": primary_req.capacity - primary_req.enrollment - (0 if waitlisted else 1),
            "sourceSeatsAfter": primary_cur.capacity - primary_cur.enrollment + 1,
            "targetEnrollmentAfter": primary_req.enrollment + (0 if waitlisted else 1),
            "sourceEnrollmentAfter": primary_cur.enrollment - (0 if waitlisted else 1),
            "blockChange": block_changes[0] if len(block_changes) == 1 else block_changes,
            "hlSlAfter": {"hl": summary["hl"], "sl": summary["sl"]},
            "groupCoverageAfter": summary["group_coverage"],
        },
    }
