"""Class / grade level analytics: rankings, toppers, at-risk detection,
subject strength-weakness, correlations, movers.

Every function takes DataFrames and returns DataFrames/dicts so the same code
serves the Streamlit dashboard, the PDF report generator and any CLI export.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C


# --------------------------------------------------------------- risk & bands
def add_risk_and_bands(summary: pd.DataFrame) -> pd.DataFrame:
    """Attach performance_band, risk_score, risk_level and risk_reasons."""
    df = summary.copy()

    # --- performance band from percentile within the student's own grade ---
    pct_rank = df["percentile_in_grade"].fillna(0)
    band = np.select(
        [pct_rank >= C.TOPPER_PERCENTILE,
         pct_rank >= 60,
         pct_rank > C.IMPROVEMENT_PERCENTILE],
        ["Topper", "Above Average", "Average"],
        default="Needs Improvement",
    )
    df["performance_band"] = band

    # --- composite risk score (0-100, higher = more concerning) ---
    score_risk = ((70 - df["overall_pct"].fillna(0)) / 45).clip(0, 1)
    att_risk = ((92 - df["attendance_pct"].fillna(0)) / 30).clip(0, 1)
    trend_risk = ((-df["trend_delta"].fillna(0)) / 12).clip(0, 1)
    submit_risk = ((95 - df["submission_rate"].fillna(0)) / 45).clip(0, 1)

    w = C.RISK_WEIGHTS
    df["risk_score"] = ((w["low_score"] * score_risk
                        + w["low_attendance"] * att_risk
                        + w["negative_trend"] * trend_risk
                        + w["low_submission"] * submit_risk) * 100).round(1)

    df["risk_level"] = pd.cut(df["risk_score"], bins=[-0.1, 15, 30, 50, 100],
                              labels=["Low", "Moderate", "High", "Critical"]).astype(str)
    df.loc[df["risk_level"].isin(["High", "Critical"]), "performance_band"] = np.where(
        df.loc[df["risk_level"].isin(["High", "Critical"]), "overall_pct"] < 50,
        "At Risk",
        df.loc[df["risk_level"].isin(["High", "Critical"]), "performance_band"])

    reasons = []
    for r in df.itertuples():
        rs = []
        if r.overall_pct is not None and r.overall_pct < C.PASS_MARK_PCT + 10:
            rs.append(f"Low overall score ({r.overall_pct:.1f}%)")
        if getattr(r, "subjects_failed", 0) and r.subjects_failed > 0:
            rs.append(f"{int(r.subjects_failed)} subject(s) below pass mark")
        if r.attendance_pct is not None and r.attendance_pct < C.ATTENDANCE_RISK_THRESHOLD:
            rs.append(f"Attendance {r.attendance_pct:.1f}% (below {C.ATTENDANCE_RISK_THRESHOLD:.0f}%)")
        if r.trend_delta is not None and r.trend_delta < -6:
            rs.append(f"Declining trend ({r.trend_delta:+.1f} pts)")
        if r.submission_rate is not None and r.submission_rate < 70:
            rs.append(f"Only {r.submission_rate:.0f}% assignments submitted")
        reasons.append("; ".join(rs) if rs else "No flags")
    df["risk_reasons"] = reasons
    return df


# ------------------------------------------------------------------- scoping
def scope(summary: pd.DataFrame, grade: int | None = None,
          campus: str | list[str] | None = None,
          section: str | list[str] | None = None) -> pd.DataFrame:
    """Filter a student-level frame by grade / campus / section."""
    df = summary
    if grade is not None:
        df = df[df["grade"] == grade]
    if campus:
        campuses = [campus] if isinstance(campus, str) else list(campus)
        if campuses and "All" not in campuses:
            df = df[df["campus"].isin(campuses)]
    if section:
        sections = [section] if isinstance(section, str) else list(section)
        if sections and "All" not in sections:
            df = df[df["section"].isin(sections)]
    return df.copy()


def rescope_ranks(df: pd.DataFrame, score_col: str = "overall_pct") -> pd.DataFrame:
    """Recompute rank/percentile *within the current selection* (the visible cohort)."""
    out = df.copy()
    out["rank_in_view"] = out[score_col].rank(ascending=False, method="min").astype(int)
    out["percentile_in_view"] = (out[score_col].rank(pct=True) * 100).round(1)
    out["view_avg"] = out[score_col].mean().round(2)
    out["vs_view_avg"] = (out[score_col] - out["view_avg"]).round(2)
    return out


# ------------------------------------------------------------------- KPIs
def cohort_kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {k: 0 for k in ("students", "avg_pct", "median_pct", "avg_gpa", "attendance_pct",
                               "pass_rate", "toppers", "needs_improvement", "at_risk",
                               "avg_submission", "top_score", "std_pct", "improving", "declining")}
    return {
        "students": int(len(df)),
        "avg_pct": round(float(df["overall_pct"].mean()), 2),
        "median_pct": round(float(df["overall_pct"].median()), 2),
        "std_pct": round(float(df["overall_pct"].std()), 2),
        "top_score": round(float(df["overall_pct"].max()), 2),
        "avg_gpa": round(float(df["gpa"].mean()), 2),
        "attendance_pct": round(float(df["attendance_pct"].mean()), 2),
        "pass_rate": round(float((df["subjects_failed"] == 0).mean() * 100), 1),
        "toppers": int((df["performance_band"] == "Topper").sum()),
        "needs_improvement": int((df["performance_band"] == "Needs Improvement").sum()),
        "at_risk": int(df["risk_level"].isin(["High", "Critical"]).sum()),
        "avg_submission": round(float(df["submission_rate"].mean()), 2),
        "improving": int((df["trend_delta"] > 3).sum()),
        "declining": int((df["trend_delta"] < -3).sum()),
    }


# --------------------------------------------------------- toppers / laggards
RANK_COLS = ["rank_in_view", "student_id", "name", "campus", "section", "roll_no",
             "overall_pct", "gpa", "letter_grade", "attendance_pct", "best_subject",
             "weakest_subject", "trend_delta", "performance_band", "risk_level"]


def toppers(df: pd.DataFrame, n: int = C.TOP_N_DEFAULT) -> pd.DataFrame:
    out = rescope_ranks(df).nsmallest(n, "rank_in_view")
    return out[[c for c in RANK_COLS if c in out.columns]].reset_index(drop=True)


def needs_improvement(df: pd.DataFrame, n: int = C.TOP_N_DEFAULT) -> pd.DataFrame:
    """Lowest performers, ordered by composite risk (worst first)."""
    out = rescope_ranks(df).sort_values(
        ["risk_score", "overall_pct"], ascending=[False, True]).head(n)
    cols = RANK_COLS + ["risk_score", "risk_reasons", "subjects_failed", "submission_rate"]
    return out[[c for c in cols if c in out.columns]].reset_index(drop=True)


def biggest_movers(df: pd.DataFrame, n: int = C.TOP_N_DEFAULT) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [c for c in ["student_id", "name", "section", "overall_pct", "trend_delta",
                        "attendance_pct", "attendance_trend", "performance_band"] if c in df.columns]
    up = df.nlargest(n, "trend_delta")[cols].reset_index(drop=True)
    down = df.nsmallest(n, "trend_delta")[cols].reset_index(drop=True)
    return up, down


def honour_roll(df: pd.DataFrame) -> pd.DataFrame:
    """Students who are strong *and* consistent *and* present."""
    mask = ((df["overall_pct"] >= 80) & (df["attendance_pct"] >= 90)
            & (df["consistency_std"] <= 10) & (df["subjects_failed"] == 0))
    cols = [c for c in ["student_id", "name", "section", "overall_pct", "gpa", "attendance_pct",
                        "consistency_std", "best_subject"] if c in df.columns]
    return df[mask].sort_values("overall_pct", ascending=False)[cols].reset_index(drop=True)


# ------------------------------------------------------------- subject views
def subject_summary(master: pd.DataFrame, student_ids: pd.Series | None = None) -> pd.DataFrame:
    """Per-subject aggregate stats for the cohort."""
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return pd.DataFrame()
    out = m.groupby(["subject_name", "subject_category"]).agg(
        students=("student_id", "nunique"),
        avg_score=("final_subject_score", "mean"),
        median_score=("final_subject_score", "median"),
        std_score=("final_subject_score", "std"),
        min_score=("final_subject_score", "min"),
        max_score=("final_subject_score", "max"),
        avg_trend=("trend_delta", "mean"),
        pass_rate=("passed", "mean"),
        avg_submission=("submission_rate", "mean"),
    ).reset_index()
    out["pass_rate"] = (out["pass_rate"] * 100).round(1)
    out["fail_count"] = m.groupby("subject_name")["passed"].apply(lambda s: int((~s).sum())).values
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(2)
    return out.sort_values("avg_score", ascending=False).reset_index(drop=True)


def subject_toppers(master: pd.DataFrame, student_ids: pd.Series | None = None) -> pd.DataFrame:
    """The single best student in each subject for the cohort."""
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return pd.DataFrame()
    idx = m.groupby("subject_name")["final_subject_score"].idxmax()
    cols = ["subject_name", "student_id", "name", "section", "final_subject_score",
            "letter_grade", "weighted_exam_pct", "submission_rate"]
    return (m.loc[idx, cols].sort_values("final_subject_score", ascending=False)
            .reset_index(drop=True))


def exam_progression(master: pd.DataFrame, student_ids: pd.Series | None = None) -> pd.DataFrame:
    """Long-format cohort average per exam per subject (for trend lines)."""
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return pd.DataFrame()
    present = [e for e in C.EXAM_TYPES if e in m.columns]
    long = m.melt(id_vars=["subject_name"], value_vars=present,
                  var_name="exam_type", value_name="pct")
    out = long.groupby(["subject_name", "exam_type"])["pct"].mean().round(2).reset_index()
    out["exam_order"] = out["exam_type"].map({e: i for i, e in enumerate(C.EXAM_TYPES)})
    return out.sort_values(["subject_name", "exam_order"])


def student_subject_profile(master: pd.DataFrame, student_id: str) -> pd.DataFrame:
    """One student's subjects vs. their section and grade averages."""
    m = master[master["student_id"] == student_id]
    cols = ["subject_name", "subject_category", *[e for e in C.EXAM_TYPES if e in m.columns],
            "weighted_exam_pct", "avg_assignment_score", "submission_rate",
            "final_subject_score", "letter_grade", "grade_descriptor", "section_subject_avg",
            "grade_subject_avg", "vs_section_avg", "rank_in_section_subject",
            "rank_in_grade_subject", "percentile_in_grade_subject", "trend_delta"]
    return m[[c for c in cols if c in m.columns]].sort_values(
        "final_subject_score", ascending=False).reset_index(drop=True)


# ------------------------------------------------------- comparisons & stats
def section_comparison(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.groupby(["campus", "section"]).agg(
        students=("student_id", "count"),
        avg_pct=("overall_pct", "mean"),
        median_pct=("overall_pct", "median"),
        avg_attendance=("attendance_pct", "mean"),
        avg_gpa=("gpa", "mean"),
        toppers=("performance_band", lambda s: int((s == "Topper").sum())),
        at_risk=("risk_level", lambda s: int(s.isin(["High", "Critical"]).sum())),
        avg_trend=("trend_delta", "mean"),
    ).reset_index()
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(2)
    out["class_label"] = out["campus"].str.replace(" Campus", "", regex=False) + " / " + out["section"]
    return out.sort_values("avg_pct", ascending=False).reset_index(drop=True)


DRIVER_COLS = ["study_hours_per_day", "sleep_hours", "screen_time_hours",
               "extracurricular_hours", "motivation_level", "stress_level",
               "parent_involvement", "attendance_pct", "submission_rate",
               "punctuality_rate", "consistency_std"]


def performance_drivers(df: pd.DataFrame, target: str = "overall_pct") -> pd.DataFrame:
    """Pearson correlation of each lifestyle/behaviour factor with performance."""
    cols = [c for c in DRIVER_COLS if c in df.columns]
    if df.empty or not cols:
        return pd.DataFrame()
    corr = df[cols + [target]].corr(numeric_only=True)[target].drop(target)
    out = corr.reset_index()
    out.columns = ["factor", "correlation"]
    out["correlation"] = out["correlation"].round(3)
    out["direction"] = np.where(out["correlation"] >= 0, "Positive", "Negative")
    out["strength"] = pd.cut(out["correlation"].abs(), bins=[-0.01, 0.1, 0.3, 0.5, 1.0],
                             labels=["Negligible", "Weak", "Moderate", "Strong"]).astype(str)
    return out.reindex(out["correlation"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def attendance_timeseries(attendance: pd.DataFrame, student_ids: pd.Series | None = None,
                          by: str | None = None,
                          dims: pd.DataFrame | None = None) -> pd.DataFrame:
    """Monthly cohort attendance, optionally split by a student-level dimension.

    `by` may name a column that lives on the student frame (e.g. "section",
    "campus", "performance_band"); pass that frame as `dims` and it is joined in.
    """
    a = attendance if student_ids is None else attendance[attendance["student_id"].isin(student_ids)]
    if a.empty:
        return pd.DataFrame()
    if by and by not in a.columns:
        if dims is None or by not in dims.columns:
            by = None
        else:
            a = a.merge(dims[["student_id", by]].drop_duplicates("student_id"),
                        on="student_id", how="left")
    keys = ["month", "month_label", "month_index"] + ([by] if by else [])
    out = a.groupby(keys).agg(attendance_pct=("attendance_pct", "mean"),
                             students=("student_id", "nunique")).reset_index()
    out["attendance_pct"] = out["attendance_pct"].round(2)
    return out.sort_values("month_index")


def attendance_vs_marks(df: pd.DataFrame) -> pd.DataFrame:
    """Bucketed attendance band -> average score (a very legible visual)."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["attendance_band"] = pd.cut(d["attendance_pct"],
                                  bins=[0, 60, 70, 75, 80, 85, 90, 95, 100],
                                  labels=["<60", "60-70", "70-75", "75-80", "80-85",
                                          "85-90", "90-95", "95-100"])
    out = d.groupby("attendance_band", observed=True).agg(
        students=("student_id", "count"),
        avg_pct=("overall_pct", "mean"),
        at_risk=("risk_level", lambda s: int(s.isin(["High", "Critical"]).sum())),
    ).reset_index()
    out["avg_pct"] = out["avg_pct"].round(2)
    return out


def subject_correlation_matrix(master: pd.DataFrame, student_ids: pd.Series | None = None) -> pd.DataFrame:
    """Do students strong in Maths also do well in Science? (subject x subject corr)"""
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return pd.DataFrame()
    wide = m.pivot_table(index="student_id", columns="subject_name", values="final_subject_score")
    return wide.corr().round(2)


def gender_house_breakdown(df: pd.DataFrame, dimension: str = "gender") -> pd.DataFrame:
    if df.empty or dimension not in df.columns:
        return pd.DataFrame()
    out = df.groupby(dimension).agg(
        students=("student_id", "count"),
        avg_pct=("overall_pct", "mean"),
        avg_attendance=("attendance_pct", "mean"),
        toppers=("performance_band", lambda s: int((s == "Topper").sum())),
    ).reset_index()
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(2)
    return out


def intervention_plan(df: pd.DataFrame, master: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Actionable list: who to help, in which subject, and what to do."""
    focus = needs_improvement(df, n)
    if focus.empty:
        return pd.DataFrame()
    rows = []
    for r in focus.itertuples():
        sub = master[(master["student_id"] == r.student_id)].nsmallest(2, "final_subject_score")
        weak = ", ".join(f"{s.subject_name} ({s.final_subject_score:.0f}%)" for s in sub.itertuples())
        actions = []
        if getattr(r, "attendance_pct", 100) < C.ATTENDANCE_RISK_THRESHOLD:
            actions.append("Parent meeting on attendance")
        if getattr(r, "submission_rate", 100) < 70:
            actions.append("Daily homework check-in")
        if getattr(r, "trend_delta", 0) < -6:
            actions.append("Re-test weak chapters")
        if getattr(r, "subjects_failed", 0) > 0:
            actions.append("Remedial class enrolment")
        if not actions:
            actions.append("Peer tutoring / mentor pairing")
        rows.append({
            "student_id": r.student_id, "name": r.name, "section": r.section,
            "overall_pct": r.overall_pct, "risk_level": r.risk_level,
            "risk_score": getattr(r, "risk_score", None),
            "focus_subjects": weak, "recommended_actions": " | ".join(actions),
            "why_flagged": getattr(r, "risk_reasons", ""),
        })
    return pd.DataFrame(rows)
