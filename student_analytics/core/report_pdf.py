"""Automated PDF report-card generator.

This is the direct descendant of the *Automated Student Report Generator with
Data Visualization* project: for each student it computes a weighted final
grade, renders comparison charts against the class average, and lays it all out
as a printable PDF.

Charts are rendered with matplotlib (Agg backend) so this works headless and
inside Streamlit alike.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402
from reportlab.lib import colors           # noqa: E402
from reportlab.lib.enums import TA_CENTER   # noqa: E402
from reportlab.lib.pagesizes import A4       # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm            # noqa: E402
from reportlab.platypus import (KeepTogether, Image, PageBreak, Paragraph,  # noqa: E402
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .. import config as C                  # noqa: E402
from . import analytics, insights           # noqa: E402

ACCENT = colors.HexColor("#4C6FFF")
DARK = colors.HexColor("#212529")
MUTED = colors.HexColor("#6C757D")
GOOD = colors.HexColor("#00A86B")
BAD = colors.HexColor("#E03131")
LIGHT = colors.HexColor("#F1F3F5")

plt.rcParams.update({
    "font.size": 8.5, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
})


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=18, textColor=DARK,
                                spaceAfter=2),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=9.5, textColor=MUTED,
                              alignment=TA_CENTER, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=ACCENT,
                             spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=13),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8, textColor=MUTED, leading=11),
        "bullet": ParagraphStyle("bu", parent=ss["Normal"], fontSize=9, leading=13,
                                 leftIndent=10, bulletIndent=2, spaceAfter=2),
    }


def _fig_to_image(fig, width_mm: float) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    w, h = fig.get_size_inches()
    return Image(buf, width=width_mm * mm, height=width_mm * mm * h / w)


# ------------------------------------------------------------------- charts
def _chart_subject_vs_class(profile: pd.DataFrame, name: str):
    d = profile.sort_values("final_subject_score")
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(6.4, 0.42 * len(d) + 1.0))
    ax.barh(y + 0.19, d["final_subject_score"], height=0.38, color="#4C6FFF", label=name)
    ax.barh(y - 0.19, d["section_subject_avg"], height=0.38, color="#FFB020",
            label="Class average")
    for i, (v, a) in enumerate(zip(d["final_subject_score"], d["section_subject_avg"])):
        ax.text(v + 1, i + 0.19, f"{v:.0f}", va="center", fontsize=7.5)
        ax.text(a + 1, i - 0.19, f"{a:.0f}", va="center", fontsize=7.5, color="#8a5a00")
    ax.set_yticks(y, d["subject_name"])
    ax.set_xlim(0, 108)
    ax.set_xlabel("Score (%)")
    ax.set_title("Subject-wise performance vs. class average")
    ax.axvline(C.PASS_MARK_PCT, ls=":", color="#E03131", lw=1)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.25)
    return fig


def _chart_exam_trend(marks: pd.DataFrame, student_id: str):
    m = marks[marks["student_id"] == student_id]
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    if m.empty:
        ax.axis("off")
        return fig
    piv = m.pivot_table(index="exam_type", columns="subject_name", values="pct")
    piv = piv.reindex([e for e in C.EXAM_TYPES if e in piv.index])
    for col in piv.columns:
        ax.plot(piv.index, piv[col], marker="o", ms=3.5, lw=1.4, label=col)
    ax.set_ylabel("Score (%)")
    ax.set_title("Exam-by-exam progression")
    ax.axhline(C.PASS_MARK_PCT, ls=":", color="#E03131", lw=1)
    ax.legend(frameon=False, fontsize=6.5, ncol=4, loc="lower center",
              bbox_to_anchor=(0.5, -0.42))
    ax.grid(alpha=0.25)
    ax.tick_params(axis="x", labelrotation=12)
    return fig


def _chart_attendance(attendance: pd.DataFrame, student_id: str):
    a = attendance[attendance["student_id"] == student_id].sort_values("month_index")
    fig, ax = plt.subplots(figsize=(3.1, 2.5))
    if a.empty:
        ax.axis("off")
        return fig
    totals = [a["present_days"].sum(), a["late_days"].sum(),
              a["leave_days"].sum(), a["absent_days"].sum()]
    labels = ["Present", "Late", "Leave", "Absent"]
    cols = ["#00A86B", "#FFB020", "#4C6FFF", "#E03131"]
    keep = [(t, l, c) for t, l, c in zip(totals, labels, cols) if t > 0]
    ax.pie([k[0] for k in keep], labels=[k[1] for k in keep], colors=[k[2] for k in keep],
           autopct="%1.0f%%", startangle=100, textprops={"fontsize": 7.5},
           wedgeprops={"width": 0.45, "edgecolor": "white"})
    ax.set_title("Attendance breakdown")
    return fig


def _chart_position(cohort: pd.DataFrame, row: pd.Series):
    fig, ax = plt.subplots(figsize=(3.1, 2.5))
    ax.hist(cohort["overall_pct"], bins=28, color="#CED4DA")
    ax.axvline(row["overall_pct"], color="#E03131", lw=2)
    ax.axvline(cohort["overall_pct"].mean(), color="#4C6FFF", ls="--", lw=1.4)
    ax.set_title("Position in the grade")
    ax.set_xlabel("Overall score (%)")
    ax.set_ylabel("Students")
    ax.grid(alpha=0.2)
    return fig


# --------------------------------------------------------------------- tables
def _kv_table(pairs, col_widths=(34 * mm, 56 * mm)):
    t = Table([[Paragraph(f"<b>{k}</b>", _styles()["small"]), str(v)] for k, v in pairs],
              colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#DEE2E6")),
    ]))
    return t


def _marks_table(profile: pd.DataFrame):
    exams = [e for e in C.EXAM_TYPES if e in profile.columns]
    header = ["Subject", *[e.replace("Unit Test", "UT").replace(" Exam", "") for e in exams],
              "Assign.", "Weighted", "Final", "Grade", "Class avg", "Rank"]
    rows = [header]
    records = profile.to_dict("records")
    for r in records:
        rows.append([
            r["subject_name"],
            *[("-" if pd.isna(r.get(e)) else f"{r[e]:.0f}") for e in exams],
            f"{r['avg_assignment_score']:.0f}",
            f"{r['weighted_exam_pct']:.1f}",
            f"{r['final_subject_score']:.1f}",
            r["letter_grade"],
            f"{r['section_subject_avg']:.1f}",
            f"{int(r['rank_in_section_subject'])}",
        ])
    t = Table(rows, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DEE2E6")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    final_col = len(header) - 4
    for i, r in enumerate(records, start=1):
        if r["final_subject_score"] < C.PASS_MARK_PCT:
            style.append(("TEXTCOLOR", (final_col, i), (final_col + 1, i), BAD))
            style.append(("FONTNAME", (final_col, i), (final_col + 1, i), "Helvetica-Bold"))
        elif r["final_subject_score"] >= 85:
            style.append(("TEXTCOLOR", (final_col, i), (final_col + 1, i), GOOD))
    t.setStyle(TableStyle(style))
    return t


# ------------------------------------------------------------------ main API
def generate_report(ds, student_id: str, out_dir: Path | None = None,
                    include_narrative: bool = True) -> Path:
    """Render one student's PDF report card. Returns the file path."""
    row = ds.student_row(student_id)
    if row is None:
        raise ValueError(f"Unknown student_id: {student_id}")
    profile = analytics.student_subject_profile(ds.master, student_id)
    cohort = ds.summary[ds.summary["grade"] == row["grade"]]
    S = _styles()
    out_dir = Path(out_dir or C.REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{student_id}_{row['name'].replace(' ', '_')}.pdf"

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Report Card - {row['name']}",
                            author=C.SCHOOL_NAME)
    story = []

    # ---- header
    story.append(Paragraph(C.SCHOOL_NAME, S["title"]))
    story.append(Paragraph(
        f"Annual Report Card &nbsp;|&nbsp; Academic Year {C.ACADEMIC_YEAR} &nbsp;|&nbsp; "
        f"Generated {date.today().isoformat()}", S["sub"]))
    story.append(Table([[""]], colWidths=[doc.width], rowHeights=[1.6],
                       style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT)])))
    story.append(Spacer(1, 7))

    # ---- identity + headline results, side by side
    left = _kv_table([
        ("Student", row["name"]),
        ("Student ID", row["student_id"]),
        ("Class", f"{row['class_name']}  ({row['campus']})"),
        ("Roll No.", int(row["roll_no"])),
        ("House", row["house"]),
        ("Parent / Guardian", row["parent_name"]),
        ("Contact", row["parent_contact"]),
    ])
    right = _kv_table([
        ("Overall score", f"{row['overall_pct']:.2f}%"),
        ("Final grade", f"{row['letter_grade']}  —  {row['grade_descriptor']}"),
        ("GPA", f"{row['gpa']:.2f} / 10"),
        ("Rank in class", f"{int(row['rank_in_section'])} of {int(row['section_size'])}"),
        ("Rank in grade", f"{int(row['rank_in_grade'])} of {int(row['grade_size'])}"),
        ("Percentile", f"{row['percentile_in_grade']:.0f}th"),
        ("Attendance", f"{row['attendance_pct']:.1f}%  ({int(row['present_days'])}"
                       f"/{int(row['school_days'])} days)"),
    ])
    story.append(Table([[left, right]], colWidths=[doc.width / 2, doc.width / 2],
                       style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0)])))
    story.append(Spacer(1, 6))

    # ---- weightage note (the "customizable weightages" feature)
    wt = ", ".join(f"{k} {v*100:.0f}%" for k, v in C.EXAM_WEIGHTS.items())
    story.append(Paragraph(
        f"<b>Grading formula:</b> exams are weighted as {wt}; the final subject score blends "
        f"exams ({C.EXAM_BLEND_WEIGHT*100:.0f}%) with internal assignment work "
        f"({C.ASSIGNMENT_WEIGHT*100:.0f}%). Pass mark {C.PASS_MARK_PCT:.0f}%.", S["small"]))

    # ---- marks table
    story.append(Paragraph("Subject-wise Results", S["h2"]))
    story.append(_marks_table(profile))

    # ---- charts
    story.append(Paragraph("Performance vs. Class", S["h2"]))
    story.append(_fig_to_image(_chart_subject_vs_class(profile, row["name"]), doc.width / mm))
    story.append(PageBreak())

    story.append(Paragraph("Progression &amp; Attendance", S["h2"]))
    story.append(_fig_to_image(_chart_exam_trend(ds.marks, student_id), doc.width / mm))
    half = doc.width / 2 / mm - 3
    story.append(Table(
        [[_fig_to_image(_chart_attendance(ds.attendance, student_id), half),
          _fig_to_image(_chart_position(cohort, row), half)]],
        colWidths=[doc.width / 2, doc.width / 2],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                         ("LEFTPADDING", (0, 0), (-1, -1), 0)])))

    # ---- narrative
    if include_narrative:
        story.append(Paragraph("Analysis", S["h2"]))
        for _sev, msg in insights.student_insights(row, profile):
            story.append(Paragraph("• " + _strip_md(msg), S["bullet"]))
        story.append(Paragraph("Recommended Next Steps", S["h2"]))
        for i, rec in enumerate(insights.recommendations(row, profile), 1):
            story.append(Paragraph(f"{i}. {_strip_md(rec)}", S["bullet"]))

    story.append(Spacer(1, 10))
    story.append(KeepTogether(Table(
        [["Class Teacher", "Principal", "Parent / Guardian"], ["", "", ""]],
        colWidths=[doc.width / 3] * 3, rowHeights=[12, 26],
        style=TableStyle([
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.HexColor("#ADB5BD")),
        ]))))
    story.append(Paragraph(
        "This report is generated automatically from the school's assessment, attendance and "
        "assignment records. Scores are weighted percentages, not raw totals.", S["small"]))

    doc.build(story)
    return path


def _strip_md(text: str) -> str:
    """Convert the markdown-ish insight strings into reportlab mini-HTML."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = safe.split("**")
    return "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(parts))


def generate_batch(ds, student_ids: list[str], out_dir: Path | None = None,
                   progress=None) -> list[Path]:
    """Generate many report cards. `progress` is an optional callable(i, n, path)."""
    paths = []
    n = len(student_ids)
    for i, sid in enumerate(student_ids, 1):
        p = generate_report(ds, sid, out_dir)
        paths.append(p)
        if progress:
            progress(i, n, p)
    return paths


def generate_class_report(ds, grade: int, campus=None, section=None,
                          out_dir: Path | None = None) -> Path:
    """A single class/grade-level PDF: KPIs, subject table, toppers, at-risk list."""
    df = analytics.scope(ds.summary, grade, campus, section)
    if df.empty:
        raise ValueError("No students match that scope")
    S = _styles()
    label = f"Grade {grade}"
    if campus and campus != "All":
        label += f" · {campus}"
    if section and section != "All":
        label += f" · Section {section}"

    out_dir = Path(out_dir or C.REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"class_report_{label.replace(' ', '_').replace('·', '-')}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Class Report - {label}", author=C.SCHOOL_NAME)
    story = [Paragraph(C.SCHOOL_NAME, S["title"]),
             Paragraph(f"Class Performance Report &nbsp;|&nbsp; {label} &nbsp;|&nbsp; "
                       f"{C.ACADEMIC_YEAR} &nbsp;|&nbsp; {date.today().isoformat()}", S["sub"])]

    k = analytics.cohort_kpis(df)
    kpi_rows = [["Students", "Average", "Median", "Attendance", "Pass rate",
                 "Toppers", "Needs work", "At risk"],
                [k["students"], f"{k['avg_pct']:.1f}%", f"{k['median_pct']:.1f}%",
                 f"{k['attendance_pct']:.1f}%", f"{k['pass_rate']:.0f}%",
                 k["toppers"], k["needs_improvement"], k["at_risk"]]]
    t = Table(kpi_rows, colWidths=[doc.width / 8] * 8)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DEE2E6")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 6)]

    story.append(Paragraph("Key Findings", S["h2"]))
    for _sev, msg in insights.cohort_insights(df, ds.master, label):
        story.append(Paragraph("• " + _strip_md(msg), S["bullet"]))

    subs = analytics.subject_summary(ds.master, df["student_id"])
    story.append(Paragraph("Subject Summary", S["h2"]))
    story.append(_simple_table(subs[["subject_name", "avg_score", "median_score", "std_score",
                                    "min_score", "max_score", "pass_rate", "fail_count",
                                    "avg_trend"]], doc.width))

    story.append(PageBreak())
    story.append(Paragraph("Top 15 Students", S["h2"]))
    story.append(_simple_table(analytics.toppers(df, 15)[
        ["rank_in_view", "student_id", "name", "section", "overall_pct", "letter_grade",
         "attendance_pct", "best_subject"]], doc.width))

    story.append(Paragraph("Students Needing Improvement (highest risk first)", S["h2"]))
    story.append(_simple_table(analytics.needs_improvement(df, 15)[
        ["student_id", "name", "section", "overall_pct", "attendance_pct", "submission_rate",
         "risk_score", "risk_level", "weakest_subject"]], doc.width))

    story.append(Paragraph("Section League Table", S["h2"]))
    story.append(_simple_table(analytics.section_comparison(df)[
        ["class_label", "students", "avg_pct", "median_pct", "avg_attendance", "toppers",
         "at_risk", "avg_trend"]], doc.width))

    doc.build(story)
    return path


def _simple_table(df: pd.DataFrame, width: float) -> Table:
    if df is None or df.empty:
        return Table([["No data"]])
    header = [c.replace("_", " ").title() for c in df.columns]
    body = [[f"{v:.1f}" if isinstance(v, float) else str(v) for v in r]
            for r in df.itertuples(index=False)]
    t = Table([header] + body, repeatRows=1, colWidths=[width / len(header)] * len(header))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343A40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DEE2E6")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t
