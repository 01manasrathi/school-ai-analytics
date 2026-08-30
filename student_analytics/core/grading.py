"""Weighted grading engine.

This is the piece carried over from the *Automated Student Report Generator*
project: configurable per-exam weightages -> a single weighted percentage ->
a letter grade / GPA / descriptor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C


def letter_grade(pct: float | None) -> str:
    return grade_band(pct)[0]


def grade_band(pct: float | None) -> tuple[str, float, str]:
    """Return (letter, gpa_points, descriptor) for a percentage."""
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return "N/A", 0.0, "No data"
    for lower, letter, gpa, descriptor in C.GRADE_BANDS:
        if pct >= lower:
            return letter, gpa, descriptor
    return "E", 0.0, "Critical - Intervention Needed"


def weighted_pct(exam_pcts: dict[str, float], weights: dict[str, float] | None = None) -> float | None:
    """Weighted percentage from {exam_type: pct}, renormalised over present exams."""
    weights = weights or C.EXAM_WEIGHTS
    total_w = 0.0
    acc = 0.0
    for exam, w in weights.items():
        val = exam_pcts.get(exam)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        acc += float(val) * w
        total_w += w
    if total_w == 0:
        return None
    return round(acc / total_w, 2)


def recompute_master(master: pd.DataFrame, weights: dict[str, float],
                     assignment_weight: float = C.ASSIGNMENT_WEIGHT) -> pd.DataFrame:
    """Re-score the master table with user-supplied weightages (dashboard slider).

    Returns a copy with weighted_exam_pct / final_subject_score / letter_grade
    / gpa_points recomputed, plus ranks refreshed.
    """
    df = master.copy()
    exams = [e for e in weights if e in df.columns]
    w = np.array([weights[e] for e in exams], dtype=float)
    mat = df[exams].to_numpy(dtype=float)
    present = (~np.isnan(mat)).astype(float)
    denom = present.dot(w)
    denom[denom == 0] = np.nan
    df["weighted_exam_pct"] = np.round(np.nansum(np.nan_to_num(mat) * w, axis=1) / denom, 2)

    exam_blend = max(0.0, 1.0 - assignment_weight)
    df["final_subject_score"] = np.round(
        exam_blend * df["weighted_exam_pct"].fillna(0)
        + assignment_weight * df["assignment_component"].fillna(0), 2)

    bands = df["final_subject_score"].map(grade_band)
    df["letter_grade"] = [b[0] for b in bands]
    df["gpa_points"] = [b[1] for b in bands]
    df["grade_descriptor"] = [b[2] for b in bands]
    df["passed"] = df["final_subject_score"] >= C.PASS_MARK_PCT

    g_sub = df.groupby(["class_id", "subject_name"])["final_subject_score"]
    df["rank_in_section_subject"] = g_sub.rank(ascending=False, method="min").astype(int)
    df["section_subject_avg"] = g_sub.transform("mean").round(2)
    grade_sub = df.groupby(["grade", "subject_name"])["final_subject_score"]
    df["rank_in_grade_subject"] = grade_sub.rank(ascending=False, method="min").astype(int)
    df["percentile_in_grade_subject"] = (grade_sub.rank(pct=True) * 100).round(1)
    df["grade_subject_avg"] = grade_sub.transform("mean").round(2)
    df["vs_section_avg"] = (df["final_subject_score"] - df["section_subject_avg"]).round(2)
    df["vs_grade_avg"] = (df["final_subject_score"] - df["grade_subject_avg"]).round(2)
    return df


def grade_distribution(scores: pd.Series) -> pd.DataFrame:
    """Counts per letter grade, in canonical high->low order."""
    order = [b[1] for b in C.GRADE_BANDS]
    letters = scores.map(lambda v: grade_band(v)[0])
    counts = letters.value_counts().reindex(order).fillna(0).astype(int)
    out = counts.reset_index()
    out.columns = ["letter_grade", "students"]
    out["descriptor"] = out["letter_grade"].map({b[1]: b[3] for b in C.GRADE_BANDS})
    out["pct_of_class"] = (out["students"] / max(len(scores), 1) * 100).round(1)
    return out
