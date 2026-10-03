"""Programme-level validation: checks a full set of choices against the RuleSet."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..rules import NEEDS_OVERRIDE, NOT_FEASIBLE, WARNING, RuleSet
from .types import OfferingInfo


@dataclass
class Issue:
    code: str
    severity: str  # NOT_FEASIBLE | NEEDS_OVERRIDE | WARNING
    message: str
    overridable: bool = True


def summarize(choices: list[OfferingInfo]) -> dict:
    groups = Counter(o.group for o in choices)
    return {
        "hl": sum(1 for o in choices if o.level == "HL"),
        "sl": sum(1 for o in choices if o.level == "SL"),
        "total": len(choices),
        "group_coverage": {str(g): groups.get(g, 0) for g in range(1, 7)},
    }


def validate_programme(choices: list[OfferingInfo], rules: RuleSet, prior_subjects: list[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    s = summarize(choices)

    if rules.subject_count is not None and s["total"] != rules.subject_count:
        issues.append(Issue("SUBJECT_COUNT", rules.subject_count_severity,
                            f"Student would have {s['total']} subjects (required {rules.subject_count})"))

    hl_bad = rules.hl_count is not None and s["hl"] != rules.hl_count
    sl_bad = rules.sl_count is not None and s["sl"] != rules.sl_count
    if hl_bad or sl_bad:
        issues.append(Issue("HL_SL_RATIO", rules.level_severity,
                            f"HL/SL ratio would become {s['hl']} HL / {s['sl']} SL "
                            f"(required {rules.hl_count} HL / {rules.sl_count} SL)"))

    if rules.one_per_block:
        per_block = Counter((o.block_id, o.block_name) for o in choices)
        for (bid, bname), n in per_block.items():
            limit = next((o.block_max_choices for o in choices if o.block_id == bid), 1)
            if n > limit:
                names = ", ".join(o.label for o in choices if o.block_id == bid)
                issues.append(Issue("BLOCK_CONFLICT", NOT_FEASIBLE,
                                    f"Block conflict: {n} subjects in Block {bname} ({names})", overridable=False))

    if rules.no_duplicates:
        dup = [code for code, n in Counter(o.subject_code for o in choices).items() if n > 1]
        for code in dup:
            name = next(o.subject_name for o in choices if o.subject_code == code)
            issues.append(Issue("DUPLICATE_SUBJECT", NOT_FEASIBLE, f"Duplicate subject: {name}", overridable=False))

    missing = [g for g in rules.required_groups if s["group_coverage"].get(str(g), 0) == 0]
    if missing:
        issues.append(Issue("GROUP_COVERAGE", rules.required_groups_severity,
                            "Group coverage broken: no subject from Group " + ", ".join(map(str, missing))))

    if rules.allowed_groups is not None:
        bad = [o for o in choices if o.group not in rules.allowed_groups]
        for o in bad:
            issues.append(Issue("GROUP_NOT_ALLOWED", rules.allowed_groups_severity,
                                f"{o.subject_name} (Group {o.group}) is not in an allowed group"))

    for cat in rules.categories:
        n = sum(1 for o in choices if cat.matches(o.group, o.subject_code))
        if n < cat.min_count:
            issues.append(Issue("REQUIRED_CATEGORY", cat.severity, f"{cat.name} requirement not met ({n}/{cat.min_count})"))

    if rules.prerequisites_enforced:
        have = set(prior_subjects or []) | {o.subject_code for o in choices}
        for o in choices:
            unmet = [p for p in o.prerequisites if p not in have]
            if unmet:
                issues.append(Issue("PREREQUISITE", rules.prerequisites_severity,
                                    f"{o.subject_name} prerequisite not met: {', '.join(unmet)}"))

    if rules.timetable_check:
        by_period: dict[str, list[OfferingInfo]] = {}
        for o in choices:
            if o.block_period:
                by_period.setdefault(o.block_period, []).append(o)
        for period, os_ in by_period.items():
            if len({o.block_id for o in os_}) > 1:
                issues.append(Issue("TIMETABLE_CLASH", NOT_FEASIBLE,
                                    f"Timetable clash in period {period}: " + ", ".join(o.label for o in os_),
                                    overridable=False))
    return issues


def worst(issues: list[Issue]) -> str | None:
    order = {WARNING: 0, NEEDS_OVERRIDE: 1, NOT_FEASIBLE: 2}
    blocking = [i for i in issues if i.severity != WARNING]
    return max(blocking, key=lambda i: order[i.severity]).severity if blocking else None
