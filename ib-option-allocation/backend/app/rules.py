"""Rule configuration.

Every IB rule lives in the `rules` table (editable from Settings). This module turns those rows
into a `RuleSet` object that the engines consume. Nothing about IB requirements is hardcoded in
the engines themselves - only the *meaning* of each rule_type is defined here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import models

# Severities a rule violation can produce (condition_json.severity)
NOT_FEASIBLE = "NOT_FEASIBLE"
NEEDS_OVERRIDE = "NEEDS_OVERRIDE"
WARNING = "WARNING"


@dataclass
class Category:
    """A 'must include at least N subjects of this kind' requirement (Mathematics, Science, ...)."""
    name: str
    groups: list[int] = field(default_factory=list)
    subject_codes: list[str] = field(default_factory=list)
    min_count: int = 1
    severity: str = NEEDS_OVERRIDE

    def matches(self, group: int, code: str) -> bool:
        return group in self.groups or code in self.subject_codes


@dataclass
class RuleSet:
    subject_count: int | None = None
    subject_count_severity: str = NEEDS_OVERRIDE
    hl_count: int | None = None
    sl_count: int | None = None
    level_severity: str = NEEDS_OVERRIDE
    one_per_block: bool = False
    required_groups: list[int] = field(default_factory=list)
    required_groups_severity: str = NEEDS_OVERRIDE
    allowed_groups: list[int] | None = None
    allowed_groups_severity: str = NEEDS_OVERRIDE
    no_duplicates: bool = False
    categories: list[Category] = field(default_factory=list)
    waitlist_when_full: bool = False
    over_capacity_severity: str = NOT_FEASIBLE
    min_enrollment_warning: bool = False
    prerequisites_enforced: bool = False
    prerequisites_severity: str = NEEDS_OVERRIDE
    timetable_check: bool = False


# rule_type -> human description. Used by Settings UI and docs.
RULE_TYPES = {
    "SUBJECT_COUNT": "Exact number of option subjects per student (value).",
    "HL_COUNT": "Exact number of Higher Level subjects (value).",
    "SL_COUNT": "Exact number of Standard Level subjects (value).",
    "ONE_PER_BLOCK": "A student may take at most block.max_choices_per_student subjects per option block.",
    "REQUIRED_GROUPS": "At least one subject from each group in condition.groups.",
    "ALLOWED_GROUPS": "Every subject must come from condition.groups (e.g. 6th/7th subject from Group 6 or a repeat of 1-5).",
    "NO_DUPLICATE_SUBJECTS": "The same subject cannot be chosen twice (e.g. at HL and SL).",
    "REQUIRED_CATEGORY": "At least `value` subjects matching condition.groups / condition.subject_codes (Maths, Science, Language A/B...).",
    "WAITLIST_WHEN_FULL": "A request for a full offering (enrollment == capacity) is waitlisted instead of rejected.",
    "OVER_CAPACITY": "Requests for an offering already over capacity get condition.severity (override allowed).",
    "MIN_ENROLLMENT_WARNING": "Warn when a student leaving an offering drops it below min_enrollment.",
    "PREREQUISITES": "Enforce Subject.prerequisites (codes that must be in prior_subjects or current choices).",
    "TIMETABLE_CLASH": "Detect period clashes for the student and teacher/room clashes for the offering.",
}


DEFAULT_RULES: list[dict] = [
    {"rule_type": "SUBJECT_COUNT", "value": "7", "priority": 10, "condition": {"severity": NEEDS_OVERRIDE},
     "description": "Each student selects exactly 7 option subjects."},
    {"rule_type": "HL_COUNT", "value": "4", "priority": 20, "condition": {"severity": NEEDS_OVERRIDE},
     "description": "4 subjects at Higher Level."},
    {"rule_type": "SL_COUNT", "value": "3", "priority": 21, "condition": {"severity": NEEDS_OVERRIDE},
     "description": "3 subjects at Standard Level."},
    {"rule_type": "ONE_PER_BLOCK", "value": "1", "priority": 30, "condition": {"severity": NOT_FEASIBLE},
     "description": "One subject per option block."},
    {"rule_type": "REQUIRED_GROUPS", "value": "1", "priority": 40,
     "condition": {"groups": [1, 2, 3, 4, 5], "severity": NEEDS_OVERRIDE},
     "description": "At least one subject from each of Groups 1-5."},
    {"rule_type": "ALLOWED_GROUPS", "value": "1", "priority": 41,
     "condition": {"groups": [1, 2, 3, 4, 5, 6], "severity": NEEDS_OVERRIDE},
     "description": "Sixth/seventh subject may come from Group 6 or repeat Groups 1-5."},
    {"rule_type": "NO_DUPLICATE_SUBJECTS", "value": "1", "priority": 42, "condition": {"severity": NOT_FEASIBLE},
     "description": "No duplicate subjects."},
    {"rule_type": "REQUIRED_CATEGORY", "value": "1", "priority": 50,
     "condition": {"name": "Mathematics", "groups": [5], "subject_codes": [], "severity": NEEDS_OVERRIDE},
     "description": "Mathematics is compulsory."},
    {"rule_type": "REQUIRED_CATEGORY", "value": "1", "priority": 51,
     "condition": {"name": "Science", "groups": [4], "subject_codes": [], "severity": NEEDS_OVERRIDE},
     "description": "A Science is compulsory."},
    {"rule_type": "REQUIRED_CATEGORY", "value": "1", "priority": 52,
     "condition": {"name": "Language A", "groups": [1], "subject_codes": [], "severity": NEEDS_OVERRIDE},
     "description": "Language A is required."},
    {"rule_type": "REQUIRED_CATEGORY", "value": "1", "priority": 53,
     "condition": {"name": "Language B", "groups": [2], "subject_codes": [], "severity": NEEDS_OVERRIDE},
     "description": "Language B / Ab Initio is required."},
    {"rule_type": "WAITLIST_WHEN_FULL", "value": "1", "priority": 60, "condition": {},
     "description": "Full offering (enrollment == capacity) -> FEASIBLE_WAITLIST."},
    {"rule_type": "OVER_CAPACITY", "value": "1", "priority": 61, "condition": {"severity": NOT_FEASIBLE},
     "description": "Over-capacity offering -> NOT_FEASIBLE unless override."},
    {"rule_type": "MIN_ENROLLMENT_WARNING", "value": "1", "priority": 70, "condition": {},
     "description": "Warn if a student leaving an offering drops it below min_enrollment."},
    {"rule_type": "PREREQUISITES", "value": "1", "priority": 80, "condition": {"severity": NEEDS_OVERRIDE},
     "description": "Subject prerequisites must be met."},
    {"rule_type": "TIMETABLE_CLASH", "value": "1", "priority": 90, "condition": {},
     "description": "Check teacher / room / period clashes when data is present."},
]


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def build_ruleset(rows: list) -> RuleSet:
    """Build a RuleSet from Rule-like objects (rule_type, condition_json, value, is_active, priority)."""
    rs = RuleSet()
    for r in sorted(rows, key=lambda r: r.priority):
        if not r.is_active:
            continue
        cond = json.loads(r.condition_json or "{}") if isinstance(r.condition_json, str) else (r.condition_json or {})
        sev = cond.get("severity", NEEDS_OVERRIDE)
        t = r.rule_type
        if t == "SUBJECT_COUNT":
            rs.subject_count, rs.subject_count_severity = _int(r.value), sev
        elif t == "HL_COUNT":
            rs.hl_count, rs.level_severity = _int(r.value), sev
        elif t == "SL_COUNT":
            rs.sl_count, rs.level_severity = _int(r.value), sev
        elif t == "ONE_PER_BLOCK":
            rs.one_per_block = True
        elif t == "REQUIRED_GROUPS":
            rs.required_groups, rs.required_groups_severity = [int(g) for g in cond.get("groups", [])], sev
        elif t == "ALLOWED_GROUPS":
            rs.allowed_groups, rs.allowed_groups_severity = [int(g) for g in cond.get("groups", [])], sev
        elif t == "NO_DUPLICATE_SUBJECTS":
            rs.no_duplicates = True
        elif t == "REQUIRED_CATEGORY":
            rs.categories.append(Category(
                name=cond.get("name", "Category"),
                groups=[int(g) for g in cond.get("groups", [])],
                subject_codes=list(cond.get("subject_codes", [])),
                min_count=_int(r.value, 1),
                severity=sev,
            ))
        elif t == "WAITLIST_WHEN_FULL":
            rs.waitlist_when_full = True
        elif t == "OVER_CAPACITY":
            rs.over_capacity_severity = sev if "severity" in cond else NOT_FEASIBLE
        elif t == "MIN_ENROLLMENT_WARNING":
            rs.min_enrollment_warning = True
        elif t == "PREREQUISITES":
            rs.prerequisites_enforced, rs.prerequisites_severity = True, sev
        elif t == "TIMETABLE_CLASH":
            rs.timetable_check = True
    return rs


def load_ruleset(db: Session, programme_id: int | None) -> RuleSet:
    """Global rules (programme_id NULL) plus programme-specific rules. Programme rules override globals of the same type."""
    rows = db.scalars(select(models.Rule).where(
        or_(models.Rule.programme_id.is_(None), models.Rule.programme_id == programme_id)
    )).all()
    specific_types = {r.rule_type for r in rows if r.programme_id is not None and r.rule_type != "REQUIRED_CATEGORY"}
    rows = [r for r in rows if r.programme_id is not None or r.rule_type not in specific_types]
    return build_ruleset(rows)
