"""Student report-card PDF generation with matplotlib charts.

Adapted from the "Automated Student Report Generator with Data
Visualization" reference project: per-student PDF with class comparison
bar charts, weighted final grade, and attendance summary.
"""
from __future__ import annotations

import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import analytics_service, config, data_store


def generate_student_report(student_id: str) -> str:
    student = data_store.get_row("students", "student_id", student_id)
    if not student:
        raise ValueError(f"Student {student_id} not found")

    marks = data_store.read_table("marks")
    marks = marks.copy()
    marks["marks_obtained"] = pd.to_numeric(marks["marks_obtained"], errors="coerce")
    marks["max_marks"] = pd.to_numeric(marks["max_marks"], errors="coerce")

    subjects = data_store.read_table("subjects")
    class_subjects = subjects[subjects["class_id"] == student["class_id"]]

    attendance = data_store.read_table("attendance")
    att_summary = {
        "total_days": 0, "present": 0, "absent": 0, "late": 0, "attendance_pct": 0.0,
    }
    student_att = attendance[attendance["student_id"] == student_id]
    if not student_att.empty:
        total = len(student_att)
        present = (student_att["status"] == "Present").sum()
        absent = (student_att["status"] == "Absent").sum()
        late = (student_att["status"] == "Late").sum()
        att_summary = {
            "total_days": int(total), "present": int(present), "absent": int(absent),
            "late": int(late), "attendance_pct": round((present + late) / total * 100, 2),
        }

    # per-subject: student pct vs class average pct
    rows = []
    for _, sub in class_subjects.iterrows():
        sid = sub["subject_id"]
        weighted = analytics_service.student_weighted_score(marks, student_id, sid)
        class_marks = marks[marks["subject_id"] == sid]
        class_avg_pct = None
        if not class_marks.empty:
            class_avg_pct = round((class_marks["marks_obtained"] / class_marks["max_marks"] * 100).mean(), 2)
        rows.append({
            "subject_name": sub["subject_name"],
            "weighted_pct": weighted,
            "class_avg_pct": class_avg_pct,
            "grade": analytics_service.calculate_final_grade(weighted) if weighted is not None else "N/A",
        })

    overall_pcts = [r["weighted_pct"] for r in rows if r["weighted_pct"] is not None]
    overall_pct = round(sum(overall_pcts) / len(overall_pcts), 2) if overall_pcts else 0.0
    overall_grade = analytics_service.calculate_final_grade(overall_pct)

    # --- Chart: student vs class average per subject ---
    chart_path = config.CHARTS_DIR / f"{student_id}_marks_comparison.png"
    subj_names = [r["subject_name"] for r in rows]
    student_vals = [r["weighted_pct"] or 0 for r in rows]
    class_vals = [r["class_avg_pct"] or 0 for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    x = range(len(subj_names))
    width = 0.35
    ax.bar([i - width / 2 for i in x], student_vals, width, label=student["name"], color="#4C72B0")
    ax.bar([i + width / 2 for i in x], class_vals, width, label="Class Average", color="#DD8452", alpha=0.85)
    ax.set_xticks(list(x))
    ax.set_xticklabels(subj_names, rotation=20, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_title(f"Performance Comparison - {student['name']}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)

    # --- Attendance pie chart ---
    att_chart_path = config.CHARTS_DIR / f"{student_id}_attendance.png"
    fig2, ax2 = plt.subplots(figsize=(3.2, 3.2))
    labels = ["Present", "Late", "Absent"]
    values = [att_summary["present"], att_summary["late"], att_summary["absent"]]
    colors = ["#55A868", "#C44E52", "#8172B2"]
    if sum(values) > 0:
        ax2.pie(values, labels=labels, autopct="%1.0f%%", colors=colors)
    else:
        ax2.text(0.5, 0.5, "No data", ha="center")
    ax2.set_title("Attendance Breakdown")
    fig2.tight_layout()
    fig2.savefig(att_chart_path, dpi=150)
    plt.close(fig2)

    # --- Build PDF ---
    pdf_path = config.REPORTS_DIR / f"report_{student_id}.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width_pt, height_pt = A4
    y = height_pt - 25 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "Student Report Card")
    y -= 12 * mm

    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, y, f"Name: {student['name']}    Student ID: {student_id}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Class: {student['class_id']}    Roll No: {student.get('roll_no', '-')}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Generated on: {dt.date.today().isoformat()}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, f"Overall Score: {overall_pct}%   Overall Grade: {overall_grade}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Subject")
    c.drawString(80 * mm, y, "Score %")
    c.drawString(115 * mm, y, "Class Avg %")
    c.drawString(155 * mm, y, "Grade")
    y -= 5 * mm
    c.line(20 * mm, y, 190 * mm, y)
    y -= 6 * mm

    c.setFont("Helvetica", 10)
    for r in rows:
        c.drawString(20 * mm, y, str(r["subject_name"])[:30])
        c.drawString(80 * mm, y, f"{r['weighted_pct']}" if r["weighted_pct"] is not None else "N/A")
        c.drawString(115 * mm, y, f"{r['class_avg_pct']}" if r["class_avg_pct"] is not None else "N/A")
        c.drawString(155 * mm, y, str(r["grade"]))
        y -= 6 * mm
        if y < 40 * mm:
            c.showPage()
            y = height_pt - 25 * mm

    y -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, f"Attendance: {att_summary['attendance_pct']}% "
                              f"(Present {att_summary['present']}, Late {att_summary['late']}, "
                              f"Absent {att_summary['absent']}, Total {att_summary['total_days']})")
    y -= 10 * mm

    if y < 110 * mm:
        c.showPage()
        y = height_pt - 25 * mm

    c.drawImage(str(chart_path), 15 * mm, y - 80 * mm, width=115 * mm, height=70 * mm, preserveAspectRatio=True)
    c.drawImage(str(att_chart_path), 135 * mm, y - 80 * mm, width=55 * mm, height=70 * mm, preserveAspectRatio=True)

    c.showPage()
    c.save()
    return str(pdf_path)
