"""End-to-end smoke test: load data, run every analytics function, build every
chart, and render one student report card + one class report.

    python -m student_analytics.smoke_test
"""
from __future__ import annotations

import traceback

from . import config as C
from .core import analytics, charts, grading, insights, loader, report_pdf

FAILS: list[str] = []


def check(label, fn, *a, **kw):
    try:
        out = fn(*a, **kw)
        n = len(out) if hasattr(out, "__len__") else "-"
        print(f"  OK   {label:46s} ({n})")
        return out
    except Exception as e:
        FAILS.append(f"{label}: {type(e).__name__}: {e}")
        print(f"  FAIL {label:46s} {type(e).__name__}: {e}")
        traceback.print_exc(limit=3)
        return None


def main() -> int:
    print("Loading dataset ...")
    ds = loader.load_dataset()
    print(f"  {ds.meta}")

    grade = ds.grades[0]
    df = analytics.scope(ds.summary, grade)
    ids = df["student_id"]
    print(f"\nAnalytics (Grade {grade}, {len(df)} students):")
    kpis = check("cohort_kpis", analytics.cohort_kpis, df)
    print(f"       -> {kpis}")
    check("toppers", analytics.toppers, df)
    check("needs_improvement", analytics.needs_improvement, df)
    check("biggest_movers", analytics.biggest_movers, df)
    check("honour_roll", analytics.honour_roll, df)
    subs = check("subject_summary", analytics.subject_summary, ds.master, ids)
    check("subject_toppers", analytics.subject_toppers, ds.master, ids)
    prog = check("exam_progression", analytics.exam_progression, ds.master, ids)
    check("section_comparison", analytics.section_comparison, df)
    drv = check("performance_drivers", analytics.performance_drivers, df)
    ts = check("attendance_timeseries", analytics.attendance_timeseries, ds.attendance, ids,
               "section", df)
    ab = check("attendance_vs_marks", analytics.attendance_vs_marks, df)
    corr = check("subject_correlation_matrix", analytics.subject_correlation_matrix, ds.master, ids)
    check("intervention_plan", analytics.intervention_plan, df, ds.master, 5)
    check("gender_house_breakdown", analytics.gender_house_breakdown, df, "gender")
    check("grade_distribution", grading.grade_distribution, df["overall_pct"])
    check("recompute_master (custom weights)", grading.recompute_master,
          ds.master[ds.master["student_id"].isin(ids)],
          {"Unit Test 1": 0.1, "Mid Term": 0.2, "Unit Test 2": 0.1, "Final Exam": 0.6}, 0.15)

    sid = df.nlargest(1, "overall_pct").iloc[0]["student_id"]
    row = ds.student_row(sid)
    profile = check("student_subject_profile", analytics.student_subject_profile, ds.master, sid)
    print(f"\nInsights (top student {sid} = {row['name']}):")
    ci = check("cohort_insights", insights.cohort_insights, df, ds.master, f"Grade {grade}")
    si = check("student_insights", insights.student_insights, row, profile)
    check("recommendations", insights.recommendations, row, profile)
    for sev, msg in (ci or [])[:3]:
        print(f"       [{sev}] {msg[:150]}")
    for sev, msg in (si or [])[:3]:
        print(f"       [{sev}] {msg[:150]}")

    print("\nCharts:")
    up, down = analytics.biggest_movers(df)
    for label, fn, args in [
        ("score_distribution", charts.score_distribution, (df,)),
        ("grade_donut", charts.grade_donut, (df,)),
        ("band_sunburst", charts.band_sunburst, (df,)),
        ("performance_band_bar", charts.performance_band_bar, (df,)),
        ("subject_average_bar", charts.subject_average_bar, (subs, kpis["avg_pct"])),
        ("subject_box", charts.subject_box, (ds.master, ids)),
        ("exam_progression_lines", charts.exam_progression_lines, (prog,)),
        ("section_subject_heatmap", charts.section_subject_heatmap, (ds.master, ids)),
        ("subject_correlation_heatmap", charts.subject_correlation_heatmap, (corr,)),
        ("subject_difficulty_quadrant", charts.subject_difficulty_quadrant, (subs,)),
        ("leaderboard_bar", charts.leaderboard_bar, (analytics.toppers(df, 10),)),
        ("movers_tornado", charts.movers_tornado, (up, down)),
        ("attendance_trend", charts.attendance_trend, (ts, "section")),
        ("attendance_vs_score_scatter", charts.attendance_vs_score_scatter, (df,)),
        ("attendance_band_bar", charts.attendance_band_bar, (ab,)),
        ("drivers_bar", charts.drivers_bar, (drv,)),
        ("section_comparison_bar", charts.section_comparison_bar, (analytics.section_comparison(df),)),
        ("grade_comparison_bar", charts.grade_comparison_bar, (ds.summary,)),
        ("treemap_sections", charts.treemap_sections, (df,)),
        ("risk_scatter", charts.risk_scatter, (df,)),
        ("parallel_bands", charts.parallel_bands, (df,)),
        ("gender_split", charts.gender_split, (df,)),
        ("top_bottom_dumbbell", charts.top_bottom_dumbbell, (df,)),
        ("student_radar", charts.student_radar, (profile, row["name"])),
        ("student_vs_class_bar", charts.student_vs_class_bar, (profile, row["name"])),
        ("student_exam_trend", charts.student_exam_trend, (ds.marks, sid)),
        ("student_attendance_bars", charts.student_attendance_bars, (ds.attendance, sid)),
        ("student_percentile_gauge", charts.student_percentile_gauge, (row,)),
        ("student_ranking_position", charts.student_ranking_position, (df, sid)),
        ("survey_profile", charts.survey_profile, (df, row)),
    ]:
        check(label, fn, *args)

    print("\nPDF reports:")
    p = check("generate_report (student)", report_pdf.generate_report, ds, sid)
    if p:
        print(f"       -> {p}  ({p.stat().st_size/1024:.0f} KB)")
    p2 = check("generate_report (weakest student)", report_pdf.generate_report, ds,
               df.nsmallest(1, "overall_pct").iloc[0]["student_id"])
    if p2:
        print(f"       -> {p2}  ({p2.stat().st_size/1024:.0f} KB)")
    p3 = check("generate_class_report", report_pdf.generate_class_report, ds, grade)
    if p3:
        print(f"       -> {p3}  ({p3.stat().st_size/1024:.0f} KB)")

    print("\nIntegrations (expected to report 'not configured'):")
    from .integrations import CanvasClient, GoogleFormsClient
    print(f"  canvas: {CanvasClient().test_connection()}")
    print(f"  google: {GoogleFormsClient().test_connection()}")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print("  -", f)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
