"""Auto-generated narrative insights.

Rule-based (always works, no API key, deterministic) with an optional local-LLM
polish step via Ollama if it happens to be running.
"""
from __future__ import annotations

import pandas as pd

from .. import config as C
from . import analytics


def _fmt(v, suffix="%") -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.1f}{suffix}"


def cohort_insights(df: pd.DataFrame, master: pd.DataFrame, label: str) -> list[tuple[str, str]]:
    """Returns a list of (severity, message). severity in success/info/warning/error."""
    if df.empty:
        return [("warning", "No students match the current filters.")]

    k = analytics.cohort_kpis(df)
    subs = analytics.subject_summary(master, df["student_id"])
    out: list[tuple[str, str]] = []

    out.append(("info",
                f"**{label}** has **{k['students']} students** averaging **{_fmt(k['avg_pct'])}** "
                f"(median {_fmt(k['median_pct'])}, spread ±{_fmt(k['std_pct'], '')} pts) "
                f"with **{_fmt(k['attendance_pct'])}** attendance."))

    if not subs.empty:
        best, worst = subs.iloc[0], subs.iloc[-1]
        out.append(("success",
                    f"Strongest subject: **{best['subject_name']}** at {_fmt(best['avg_score'])} "
                    f"({best['pass_rate']:.0f}% pass rate)."))
        out.append(("warning",
                    f"Weakest subject: **{worst['subject_name']}** at {_fmt(worst['avg_score'])} "
                    f"— {int(worst['fail_count'])} student(s) below the {C.PASS_MARK_PCT:.0f}% pass mark. "
                    f"This is the highest-leverage place to intervene."))
        declining = subs[subs["avg_trend"] < -2].sort_values("avg_trend")
        if not declining.empty:
            names = ", ".join(f"{r.subject_name} ({r.avg_trend:+.1f})" for r in declining.itertuples())
            out.append(("warning", f"Subjects sliding from Unit Test 1 to Final Exam: {names}."))

    top = analytics.toppers(df, 3)
    if not top.empty:
        names = ", ".join(f"**{r.name}** ({r.overall_pct:.1f}%, {r.section})" for r in top.itertuples())
        out.append(("success", f"Top 3 of the cohort: {names}."))

    if k["at_risk"]:
        share = k["at_risk"] / k["students"] * 100
        out.append(("error",
                    f"**{k['at_risk']} students ({share:.1f}%)** are High/Critical risk — "
                    f"driven by low scores, attendance below {C.ATTENDANCE_RISK_THRESHOLD:.0f}%, "
                    f"missed assignments or a declining trend. See the Needs-Improvement table."))

    low_att = int((df["attendance_pct"] < C.ATTENDANCE_RISK_THRESHOLD).sum())
    if low_att:
        out.append(("warning", f"{low_att} student(s) are below the "
                               f"{C.ATTENDANCE_RISK_THRESHOLD:.0f}% attendance threshold."))

    out.append(("info", f"Momentum: **{k['improving']} improving** vs **{k['declining']} declining** "
                        f"(≥3 pt change between the first and last exam)."))

    drivers = analytics.performance_drivers(df)
    strong = drivers[drivers["strength"].isin(["Moderate", "Strong"])].head(3)
    if not strong.empty:
        bits = ", ".join(f"{r.factor.replace('_', ' ')} ({r.correlation:+.2f})" for r in strong.itertuples())
        out.append(("info", f"Strongest statistical drivers of performance here: {bits}."))

    sections = analytics.section_comparison(df)
    if len(sections) > 1:
        b, w = sections.iloc[0], sections.iloc[-1]
        out.append(("info",
                    f"Best section **{b['class_label']}** ({_fmt(b['avg_pct'])}) leads the weakest "
                    f"**{w['class_label']}** ({_fmt(w['avg_pct'])}) by "
                    f"{b['avg_pct'] - w['avg_pct']:.1f} pts — worth comparing teaching approaches."))
    return out


def student_insights(row: pd.Series, profile: pd.DataFrame) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    out.append(("info",
                f"**{row['name']}** ({row['student_id']}) — {row['class_name']}, {row['campus']} — "
                f"scored **{_fmt(row['overall_pct'])}** (grade **{row['letter_grade']}**, "
                f"GPA {row['gpa']:.1f}), ranked **{int(row['rank_in_section'])}/{int(row['section_size'])}** "
                f"in section and **{int(row['rank_in_grade'])}/{int(row['grade_size'])}** in "
                f"{row['grade_label']} ({row['percentile_in_grade']:.0f}th percentile)."))

    delta = row["vs_grade_avg"]
    out.append(("success" if delta >= 0 else "warning",
                f"That is **{delta:+.1f} pts** vs the {row['grade_label']} average "
                f"of {_fmt(row['grade_avg_pct'])}."))

    if not profile.empty:
        b, w = profile.iloc[0], profile.iloc[-1]
        out.append(("success", f"Strongest subject: **{b['subject_name']}** "
                               f"({_fmt(b['final_subject_score'])}, rank "
                               f"{int(b['rank_in_section_subject'])} in section)."))
        out.append(("warning", f"Needs most work: **{w['subject_name']}** "
                               f"({_fmt(w['final_subject_score'])}, "
                               f"{w['vs_section_avg']:+.1f} vs section average)."))
        failing = profile[profile["final_subject_score"] < C.PASS_MARK_PCT]
        if not failing.empty:
            out.append(("error", "Below pass mark in: **"
                                 + ", ".join(failing["subject_name"]) + "**."))

    if row["attendance_pct"] < C.ATTENDANCE_RISK_THRESHOLD:
        out.append(("error", f"Attendance is only **{_fmt(row['attendance_pct'])}** "
                             f"({int(row['absent_days'])} days absent) — a strong predictor of "
                             f"further decline."))
    elif row["attendance_pct"] >= 95:
        out.append(("success", f"Excellent attendance: {_fmt(row['attendance_pct'])}."))

    t = row["trend_delta"]
    if t > 4:
        out.append(("success", f"Clear upward momentum: **{t:+.1f} pts** from Unit Test 1 to the Final Exam."))
    elif t < -4:
        out.append(("error", f"Declining: **{t:+.1f} pts** from Unit Test 1 to the Final Exam."))

    if row["submission_rate"] < 75:
        out.append(("warning", f"Only **{_fmt(row['submission_rate'])}** of assignments submitted "
                               f"— this alone is capping the internal-assessment component."))
    if row["consistency_std"] > 15:
        out.append(("warning", f"Very uneven across subjects (±{row['consistency_std']:.1f} pts) — "
                               f"suggests subject-specific gaps rather than general ability."))
    out.append(("info", f"Risk level: **{row['risk_level']}** (score {row['risk_score']:.0f}/100). "
                        f"{row['risk_reasons']}"))
    return out


def recommendations(row: pd.Series, profile: pd.DataFrame) -> list[str]:
    recs = []
    if not profile.empty:
        weak = profile.tail(2)["subject_name"].tolist()
        recs.append(f"Targeted remedial support in {' and '.join(weak)} (twice-weekly, 30 min).")
    if row["attendance_pct"] < C.ATTENDANCE_RISK_THRESHOLD:
        recs.append("Schedule a parent meeting about attendance; set a weekly presence target of 90%.")
    if row["submission_rate"] < 75:
        recs.append("Daily homework diary check with the class teacher's sign-off.")
    if row["study_hours_per_day"] < 1.5:
        recs.append(f"Study time is {row['study_hours_per_day']}h/day — build a fixed 2h evening slot.")
    if row["screen_time_hours"] > 6:
        recs.append(f"Screen time is {row['screen_time_hours']}h/day; cap recreational use on school nights.")
    if row["sleep_hours"] < 7:
        recs.append(f"Only {row['sleep_hours']}h sleep — shift bedtime earlier to protect concentration.")
    if row["stress_level"] >= 4:
        recs.append("High self-reported stress: refer to the school counsellor.")
    if row["overall_pct"] >= 85:
        recs.append("Offer enrichment / olympiad material and a peer-mentoring role.")
    if row["trend_delta"] > 4:
        recs.append("Acknowledge the improvement publicly — momentum is the strongest asset here.")
    if not recs:
        recs.append("On track — maintain current routine and review after the next unit test.")
    return recs


def llm_summary(prompt_context: str) -> str | None:
    """Optional: polish the numbers into prose using the local Ollama model.

    Returns None when Ollama is not reachable — callers fall back to the
    rule-based text above.
    """
    try:
        import ollama
        client = ollama.Client(host=C.OLLAMA_HOST)
        resp = client.chat(model=C.OLLAMA_MODEL, messages=[
            {"role": "system", "content":
             "You are a school data analyst. Write a concise, factual 4-6 sentence summary for "
             "a principal. Use only the numbers provided. No preamble, no bullet points."},
            {"role": "user", "content": prompt_context},
        ])
        return resp["message"]["content"].strip()
    except Exception:
        return None
