"""Allocation engine for NEW students.

allocate() is pure: given NEW students (with optional ranked preferences), the option blocks,
all offerings (with current enrollment from EXISTING students) and the RuleSet, it returns a
proposed placement per student/block plus a per-offering seat report. Nothing is written to the
database here - the /api/allocation/commit endpoint does that after the timetabler reviews.

Algorithm (per student, in priority order):
  * Blocks that contain one of the student's preferences are processed first (best rank first).
  * Depth-first search over blocks, trying offerings in preference order, pruning when
    HL/SL counts overflow, a subject is duplicated, or required groups/categories can no longer
    be covered by the remaining blocks. The first complete programme that passes
    validate_programme() is accepted.
  * Pass 1 only uses offerings with remaining seats; a block whose offerings are ALL full is
    filled with a waitlist placement (UNALLOCATED_SLOT). Pass 2 (fallback) allows waitlist
    placements in any block if no seat-only programme exists.
"""
from __future__ import annotations

from collections import Counter

from ..rules import WARNING, RuleSet
from .types import BlockInfo, OfferingInfo, StudentInfo, grade_matches
from .validation import validate_programme

NO_PREF = 1000.0


def _pref_score(o: OfferingInfo, prefs: list[tuple[int, str, str | None]]) -> float:
    best = NO_PREF
    for rank, code, level in prefs:
        if code == o.subject_code:
            best = min(best, float(rank) if level in (None, "", o.level) else rank + 0.5)
    return best


def _search(student, block_order, cands, rules: RuleSet, remaining, node_limit):
    n = len(block_order)
    total = rules.subject_count or n
    skips_allowed = n - total
    if skips_allowed < 0:
        return None
    hl_t = rules.hl_count if rules.hl_count is not None else total
    sl_t = rules.sl_count if rules.sl_count is not None else total

    # suffix availability used for pruning
    suffix_groups = [set() for _ in range(n + 1)]
    suffix_cat = [[0] * len(rules.categories) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        suffix_groups[i] = suffix_groups[i + 1] | {o.group for o, _ in cands[i]}
        for k, cat in enumerate(rules.categories):
            suffix_cat[i][k] = suffix_cat[i + 1][k] + (1 if any(cat.matches(o.group, o.subject_code) for o, _ in cands[i]) else 0)

    chosen: list[tuple[BlockInfo, OfferingInfo | None, bool]] = []
    nodes = [0]

    def ok_future(i, hl, sl, groups, cat_counts, skipped):
        if hl > hl_t or sl > sl_t or skipped > skips_allowed:
            return False
        if any(g not in groups and g not in suffix_groups[i] for g in rules.required_groups):
            return False
        return all(cat_counts[k] + suffix_cat[i][k] >= cat.min_count for k, cat in enumerate(rules.categories))

    def dfs(i, hl, sl, groups, cat_counts, subjects, skipped):
        nodes[0] += 1
        if nodes[0] > node_limit:
            raise TimeoutError
        if i == n:
            picked = [o for _, o, _ in chosen if o is not None]
            issues = validate_programme(picked, rules, student.prior_subjects)
            return all(x.severity == WARNING for x in issues)
        need_hl, need_sl = hl_t - hl, sl_t - sl
        ordered = sorted(cands[i], key=lambda c: (
            c[1], _pref_score(c[0], student.preferences),
            0 if (c[0].level == "HL") == (need_hl >= need_sl) else 1,
            -remaining.get(c[0].id, 0), c[0].id,
        ))
        options = ordered + ([(None, False)] if skipped < skips_allowed else [])
        for o, wl in options:
            if o is None:
                if ok_future(i + 1, hl, sl, groups, cat_counts, skipped + 1):
                    chosen.append((block_order[i], None, False))
                    if dfs(i + 1, hl, sl, groups, cat_counts, subjects, skipped + 1):
                        return True
                    chosen.pop()
                continue
            if rules.no_duplicates and o.subject_code in subjects:
                continue
            nhl, nsl = hl + (o.level == "HL"), sl + (o.level == "SL")
            ngroups = groups | {o.group}
            ncat = [c + (1 if cat.matches(o.group, o.subject_code) else 0) for c, cat in zip(cat_counts, rules.categories)]
            if not ok_future(i + 1, nhl, nsl, ngroups, ncat, skipped):
                continue
            chosen.append((block_order[i], o, wl))
            if dfs(i + 1, nhl, nsl, ngroups, ncat, subjects | {o.subject_code}, skipped):
                return True
            chosen.pop()
        return False

    try:
        found = dfs(0, 0, 0, frozenset(), [0] * len(rules.categories), frozenset(), 0)
    except TimeoutError:
        return None
    return list(chosen) if found else None


def allocate(
    students: list[StudentInfo],
    blocks: list[BlockInfo],
    offerings: list[OfferingInfo],
    rules: RuleSet,
    node_limit: int = 200_000,
) -> dict:
    remaining = {o.id: o.capacity - o.enrollment for o in offerings}
    new_alloc = Counter()
    waitlist = Counter()
    block_by_id = {b.id: b for b in blocks}
    student_results = []

    for st in sorted(students, key=lambda s: (s.priority, s.student_id)):
        eligible = [
            o for o in offerings
            if o.is_active and o.subject_active and o.block_id in block_by_id
            and (st.programme_id is None or o.programme_id is None or o.programme_id == st.programme_id)
            and grade_matches(o.block_grade, st.grade)
            and (rules.allowed_groups is None or o.group in rules.allowed_groups)
        ]  # prerequisites are validated at the search leaf (they may be satisfied by another chosen subject)
        by_block: dict[int, list[OfferingInfo]] = {}
        for o in eligible:
            by_block.setdefault(o.block_id, []).append(o)
        st_blocks = [b for b in sorted(blocks, key=lambda b: (b.sort_order, b.name)) if b.id in by_block]

        def block_rank(b: BlockInfo):
            return min((_pref_score(o, st.preferences) for o in by_block[b.id]), default=NO_PREF)

        block_order = sorted(st_blocks, key=lambda b: (block_rank(b), b.sort_order, b.name))

        def cands_for(pass_no):
            out = []
            for b in block_order:
                free = [(o, False) for o in by_block[b.id] if remaining[o.id] > 0]
                full = [(o, True) for o in by_block[b.id] if remaining[o.id] <= 0]
                out.append(free if (pass_no == 1 and free) else free + full)
            return out

        solution = _search(st, block_order, cands_for(1), rules, remaining, node_limit)
        if solution is None:
            solution = _search(st, block_order, cands_for(2), rules, remaining, node_limit)

        known_codes = {o.subject_code for o in eligible}
        student_warnings = [f"Preference #{r} '{code}{' ' + lvl if lvl else ''}' is not offered to this student"
                            for r, code, lvl in st.preferences if code not in known_codes]

        if solution is None:
            student_results.append({
                "student_db_id": st.id, "student_id": st.student_id, "name": st.name,
                "status": "UNALLOCATED", "slots": [], "hl": 0, "sl": 0,
                "warnings": student_warnings + ["No combination of offerings satisfies the rules - allocate manually"],
            })
            continue

        slots = []
        for b, o, wl in sorted(solution, key=lambda x: (x[0].sort_order, x[0].name)):
            if o is None:
                slots.append({"block_id": b.id, "block": b.name, "offering_id": None, "status": "EMPTY",
                              "flag": None, "reasons": ["Block intentionally left empty (subject count < blocks)"]})
                continue
            score = _pref_score(o, st.preferences)
            reasons = []
            if score == NO_PREF:
                reasons.append("Assigned from remaining seats (no preference for this block)")
            elif score == int(score):
                reasons.append(f"Preference #{int(score)} satisfied")
            else:
                reasons.append(f"Preference #{int(score)} subject satisfied at {o.level} (level adjusted for HL/SL balance)")
            for alt in by_block[b.id]:
                alt_score = _pref_score(alt, st.preferences)
                if alt.id != o.id and alt_score < score:
                    why = "full" if remaining[alt.id] <= 0 else "not compatible with HL/SL, group or subject rules"
                    reasons.append(f"Preference #{int(alt_score)} {alt.label} not assigned: {why}")
            if wl:
                waitlist[o.id] += 1
                reasons.insert(0, f"No seat available in Block {b.name} - waitlisted for {o.label}")
            else:
                remaining[o.id] -= 1
                new_alloc[o.id] += 1
            slots.append({
                "block_id": b.id, "block": b.name, "offering_id": o.id, "subject_code": o.subject_code,
                "subject": o.subject_name, "level": o.level, "group": o.group,
                "status": "WAITLISTED" if wl else "ALLOCATED",
                "flag": "UNALLOCATED_SLOT" if wl else None, "reasons": reasons,
            })
        picked = [s for s in slots if s["offering_id"]]
        student_results.append({
            "student_db_id": st.id, "student_id": st.student_id, "name": st.name,
            "status": "PARTIAL" if any(s["status"] == "WAITLISTED" for s in slots) else "ALLOCATED",
            "slots": slots,
            "hl": sum(1 for s in picked if s["level"] == "HL"),
            "sl": sum(1 for s in picked if s["level"] == "SL"),
            "warnings": student_warnings,
        })

    offering_report = [{
        "offering_id": o.id, "block": o.block_name, "subject_code": o.subject_code, "subject": o.subject_name,
        "level": o.level, "capacity": o.capacity, "existing_enrollment": o.enrollment,
        "new_allocated": new_alloc[o.id], "seats_left": remaining[o.id], "waitlisted": waitlist[o.id],
    } for o in sorted(offerings, key=lambda o: (o.block_name, o.subject_name, o.level))]

    return {
        "students": student_results,
        "offerings": offering_report,
        "summary": {
            "students": len(student_results),
            "allocated": sum(1 for s in student_results if s["status"] == "ALLOCATED"),
            "partial": sum(1 for s in student_results if s["status"] == "PARTIAL"),
            "unallocated": sum(1 for s in student_results if s["status"] == "UNALLOCATED"),
            "seats_used": sum(new_alloc.values()),
            "waitlisted_slots": sum(waitlist.values()),
        },
    }
