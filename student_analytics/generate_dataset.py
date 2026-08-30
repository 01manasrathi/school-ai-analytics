"""Generate a large, realistic, analysis-friendly student dataset.

Run:
    python -m student_analytics.generate_dataset            # ~5,000 students
    python -m student_analytics.generate_dataset --students 1200

Design notes
------------
The data is *not* uniform noise. Every student gets a hidden latent profile
(academic ability, diligence, term-over-term momentum, per-subject aptitude)
and every observable column (marks, attendance, assignment submissions, survey
answers) is derived from that profile plus noise. That means the dashboard's
correlations, rankings, at-risk detection and trend analysis surface *real*
structure instead of random static.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config as C

RNG_SEED = 42

# Cap on rows written to the "Student x Subject" Excel sheet. openpyxl/xlsxwriter get
# slow on large sheets; the complete table is always in the CSV and Parquet copies.
EXCEL_SHEET_ROWS = 20_000

FIRST_NAMES_M = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan",
    "Rudra", "Aryan", "Kabir", "Atharv", "Advik", "Dhruv", "Kian", "Neel", "Ved", "Yash",
    "Rohan", "Karan", "Nikhil", "Siddharth", "Manav", "Parth", "Tanish", "Ayush", "Harsh",
    "Devansh", "Om", "Shaurya", "Veer", "Rian", "Samar", "Aayush", "Laksh", "Pranav", "Ansh",
]
FIRST_NAMES_F = [
    "Aadhya", "Ananya", "Diya", "Ira", "Myra", "Sara", "Aarohi", "Anika", "Navya", "Kiara",
    "Riya", "Saanvi", "Pari", "Avni", "Meera", "Nitya", "Ishita", "Tara", "Zara", "Kavya",
    "Prisha", "Trisha", "Shreya", "Aditi", "Bhavya", "Charvi", "Devika", "Esha", "Gauri",
    "Janvi", "Khushi", "Lavanya", "Mahika", "Nidhi", "Ojasvi", "Pihu", "Rhea", "Siya",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Mehta", "Nair", "Reddy", "Gupta", "Singh", "Patel", "Joshi",
    "Kulkarni", "Chopra", "Bose", "Das", "Kapoor", "Malhotra", "Rao", "Menon", "Bhat",
    "Desai", "Sinha", "Pillai", "Agarwal", "Trivedi", "Shetty", "Chauhan", "Kaur", "Ghosh",
]
CAMPUSES = ["North Campus", "South Campus", "East Campus", "West Campus"]
CAMPUS_CODES = {"North Campus": "NC", "South Campus": "SC", "East Campus": "EC", "West Campus": "WC"}
SECTIONS = C.SECTIONS
HOUSES = ["Emerald", "Ruby", "Sapphire", "Topaz"]
TRANSPORT = ["School Bus", "Private Vehicle", "Walk", "Bicycle", "Public Transport"]
PARENT_EDUCATION = ["High School", "Diploma", "Graduate", "Post Graduate", "Doctorate"]
QUALIFICATIONS = ["B.Ed", "M.Ed", "M.Sc, B.Ed", "M.A, B.Ed", "Ph.D"]
CAREER_INTERESTS = [
    "Engineering", "Medicine", "Civil Services", "Arts & Design", "Sports",
    "Business", "Research / Science", "Law", "Teaching", "Undecided",
]
MONTH_LABELS = [
    ("2025-06", "Jun 2025", 22), ("2025-07", "Jul 2025", 24), ("2025-08", "Aug 2025", 23),
    ("2025-09", "Sep 2025", 22), ("2025-10", "Oct 2025", 18), ("2025-11", "Nov 2025", 24),
    ("2025-12", "Dec 2025", 19), ("2026-01", "Jan 2026", 23), ("2026-02", "Feb 2026", 22),
    ("2026-03", "Mar 2026", 21),
]
EXAM_DATES = {
    "Unit Test 1": date(2025, 7, 25),
    "Mid Term": date(2025, 10, 10),
    "Unit Test 2": date(2025, 12, 12),
    "Final Exam": date(2026, 3, 16),
}
EXAM_TERM = {
    "Unit Test 1": "Term 1", "Mid Term": "Term 1",
    "Unit Test 2": "Term 2", "Final Exam": "Term 2",
}


# --------------------------------------------------------------------- helpers
def _letter_grade(pct: float) -> tuple[str, float, str]:
    for lower, letter, gpa, descriptor in C.GRADE_BANDS:
        if pct >= lower:
            return letter, gpa, descriptor
    return "E", 0.0, "Critical - Intervention Needed"


def _vector_grades(pcts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    letters = np.empty(len(pcts), dtype=object)
    gpas = np.zeros(len(pcts))
    descs = np.empty(len(pcts), dtype=object)
    # bands are ordered high -> low; assign from the lowest band upwards
    for lower, letter, gpa, desc in reversed(C.GRADE_BANDS):
        mask = pcts >= lower
        letters[mask] = letter
        gpas[mask] = gpa
        descs[mask] = desc
    return letters, gpas, descs


# ------------------------------------------------------------ reference tables
def build_reference_tables(rng: np.random.Generator, n_students: int):
    """Campuses x grades x sections -> classes, subjects, teachers."""
    classes, subjects, teachers = [], [], []
    t_seq = 0

    for campus in CAMPUSES:
        code = CAMPUS_CODES[campus]
        for grade in C.GRADES:
            for section in SECTIONS:
                class_id = f"{code}-G{grade:02d}-{section}"
                classes.append({
                    "class_id": class_id,
                    "campus": campus,
                    "grade": grade,
                    "section": section,
                    "class_name": f"Grade {grade} - {section}",
                    "grade_label": f"Grade {grade}",
                    "room_no": f"{code[0]}{grade}{section}",
                })

    # one teacher per campus x grade-band x subject
    for campus in CAMPUSES:
        code = CAMPUS_CODES[campus]
        for grade in C.GRADES:
            for subject_name, category in C.SUBJECT_CATALOG:
                t_seq += 1
                gender = "M" if rng.random() < 0.42 else "F"
                first = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
                last = rng.choice(LAST_NAMES)
                teacher_id = f"T{t_seq:04d}"
                teachers.append({
                    "teacher_id": teacher_id,
                    "name": f"{first} {last}",
                    "gender": gender,
                    "email": f"{first.lower()}.{last.lower()}{t_seq}@school.edu",
                    "phone": f"98{rng.integers(10000000, 99999999)}",
                    "subject_specialization": subject_name,
                    "campus": campus,
                    "grade_taught": grade,
                    "years_experience": int(rng.integers(1, 31)),
                    "qualification": rng.choice(QUALIFICATIONS),
                    # teacher effectiveness nudges their students' scores a little
                    "effectiveness": round(float(rng.normal(0, 3.0)), 2),
                })
                for section in SECTIONS:
                    class_id = f"{code}-G{grade:02d}-{section}"
                    subjects.append({
                        "subject_id": f"{class_id}-{subject_name[:3].upper()}",
                        "subject_name": subject_name,
                        "category": category,
                        "campus": campus,
                        "grade": grade,
                        "section": section,
                        "class_id": class_id,
                        "teacher_id": teacher_id,
                        "max_marks": 100,
                    })

    classes_df = pd.DataFrame(classes)
    subjects_df = pd.DataFrame(subjects)
    teachers_df = pd.DataFrame(teachers)

    # assign a class teacher per class
    ct = (subjects_df[subjects_df["subject_name"] == "Mathematics"]
          .set_index("class_id")["teacher_id"])
    classes_df["class_teacher_id"] = classes_df["class_id"].map(ct)

    per_class = max(1, n_students // len(classes_df))
    classes_df["target_size"] = per_class
    # distribute the remainder across the first few classes
    remainder = n_students - per_class * len(classes_df)
    if remainder > 0:
        classes_df.loc[classes_df.index[:remainder], "target_size"] += 1
    return classes_df, subjects_df, teachers_df


# ------------------------------------------------------------------- students
def build_students(rng: np.random.Generator, classes_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sid = 0
    for _, cls in classes_df.iterrows():
        for roll in range(1, int(cls["target_size"]) + 1):
            sid += 1
            gender = "M" if rng.random() < 0.51 else "F"
            first = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
            last = rng.choice(LAST_NAMES)
            grade = int(cls["grade"])
            birth_year = 2026 - (grade + 5)
            dob = date(birth_year, int(rng.integers(1, 13)), int(rng.integers(1, 29)))
            rows.append({
                "student_id": f"S{sid:05d}",
                "name": f"{first} {last}",
                "gender": gender,
                "dob": dob.isoformat(),
                "age": 2026 - birth_year,
                "campus": cls["campus"],
                "grade": grade,
                "grade_label": cls["grade_label"],
                "section": cls["section"],
                "class_id": cls["class_id"],
                "class_name": cls["class_name"],
                "roll_no": roll,
                "house": HOUSES[(roll - 1) % len(HOUSES)],
                "parent_name": f"{rng.choice(FIRST_NAMES_M)} {last}",
                "parent_contact": f"9{rng.integers(100000000, 999999999)}",
                "email": f"{first.lower()}.{last.lower()}{sid}@student.school.edu",
                "enrollment_date": (date(2025, 6, 1) - timedelta(days=int(rng.integers(0, 900)))).isoformat(),
            })
    df = pd.DataFrame(rows)
    n = len(df)

    # ---------------- latent profile (drives everything else) ----------------
    ability = rng.normal(66, 14, n).clip(15, 99)              # core academic ability
    diligence = (0.55 * (ability - 66) / 14 + rng.normal(0, 0.85, n)).clip(-3, 3)
    momentum = rng.normal(0, 4.2, n)                           # term-over-term change
    # a deliberate minority of dramatic improvers / decliners makes trends interesting
    flip = rng.random(n)
    momentum = np.where(flip < 0.07, momentum + rng.normal(9, 2.5, n), momentum)
    momentum = np.where(flip > 0.94, momentum - rng.normal(9, 2.5, n), momentum)

    df["_ability"] = ability.round(3)
    df["_diligence"] = diligence.round(3)
    df["_momentum"] = momentum.round(3)

    # socio-economic / lifestyle attributes correlated with the latent profile
    z = (ability - 66) / 14
    df["parent_education"] = pd.cut(
        z + rng.normal(0, 0.9, n), bins=[-99, -1.1, -0.35, 0.35, 1.1, 99], labels=PARENT_EDUCATION
    ).astype(str)
    df["transport_mode"] = rng.choice(TRANSPORT, n, p=[0.42, 0.22, 0.14, 0.10, 0.12])
    df["has_tuition"] = np.where(rng.random(n) < (0.35 + 0.18 * np.clip(z, -1, 1)), "Yes", "No")
    df["internet_access"] = np.where(rng.random(n) < (0.86 + 0.08 * np.clip(z, -1, 1)), "Yes", "No")
    df["is_scholarship"] = np.where((z > 1.2) & (rng.random(n) < 0.35), "Yes", "No")
    df["study_hours_per_day"] = (2.2 + 0.85 * diligence + rng.normal(0, 0.55, n)).clip(0.3, 8).round(1)
    df["sleep_hours"] = (7.6 + 0.25 * diligence + rng.normal(0, 0.9, n)).clip(4, 11).round(1)
    df["screen_time_hours"] = (4.4 - 0.75 * diligence + rng.normal(0, 1.0, n)).clip(0.2, 11).round(1)
    df["extracurricular_hours"] = (rng.gamma(2.0, 1.6, n)).clip(0, 14).round(1)
    df["motivation_level"] = np.clip(np.round(3.1 + 0.62 * diligence + rng.normal(0, 0.6, n)), 1, 5).astype(int)
    df["stress_level"] = np.clip(np.round(3.0 - 0.22 * diligence + rng.normal(0, 0.95, n)), 1, 5).astype(int)
    df["parent_involvement"] = np.clip(np.round(3.0 + 0.45 * z + rng.normal(0, 0.85, n)), 1, 5).astype(int)
    df["career_interest"] = rng.choice(CAREER_INTERESTS, n)
    return df


# ---------------------------------------------------------- marks & aptitudes
def build_marks(rng: np.random.Generator, students: pd.DataFrame, subjects: pd.DataFrame):
    """Long-format marks: student x subject x exam. Fully vectorised."""
    subj_by_class = subjects.groupby("class_id")
    frames = []
    # Relative difficulty of each paper. Kept balanced between the first and last
    # exam so that a student's Unit Test 1 -> Final Exam delta measures *their*
    # momentum rather than a systematic drift baked into the paper difficulty.
    exam_offsets = {
        "Unit Test 1": +1.0, "Mid Term": -3.0, "Unit Test 2": +1.5, "Final Exam": +1.0,
    }
    exam_progress = {"Unit Test 1": 0.0, "Mid Term": 0.34, "Unit Test 2": 0.67, "Final Exam": 1.0}
    subject_difficulty = {
        "Mathematics": -5.5, "Science": -3.0, "English": +2.0, "Social Studies": -0.5,
        "Hindi": +3.0, "Computer Science": +1.5, "Art & Craft": +7.5, "Physical Education": +9.0,
    }

    for class_id, group in subj_by_class:
        cls_students = students[students["class_id"] == class_id]
        if cls_students.empty:
            continue
        n = len(cls_students)
        ability = cls_students["_ability"].to_numpy()
        momentum = cls_students["_momentum"].to_numpy()
        for _, subj in group.iterrows():
            sname = subj["subject_name"]
            # per-student aptitude for this specific subject
            aptitude = rng.normal(0, 6.5, n)
            base = ability + subject_difficulty.get(sname, 0.0) + aptitude
            for exam in C.EXAM_TYPES:
                pct = (base
                       + exam_offsets[exam]
                       + momentum * exam_progress[exam]
                       + rng.normal(0, 5.0, n))
                pct = np.clip(pct, 4, 100)
                frames.append(pd.DataFrame({
                    "student_id": cls_students["student_id"].to_numpy(),
                    "class_id": class_id,
                    "subject_id": subj["subject_id"],
                    "subject_name": sname,
                    "subject_category": subj["category"],
                    "exam_type": exam,
                    "term": EXAM_TERM[exam],
                    "max_marks": 100,
                    "marks_obtained": np.round(pct, 1),
                    "exam_date": EXAM_DATES[exam].isoformat(),
                }))
    marks = pd.concat(frames, ignore_index=True)
    marks.insert(0, "mark_id", np.arange(1, len(marks) + 1))
    marks["pct"] = (marks["marks_obtained"] / marks["max_marks"] * 100).round(2)
    return marks


# ----------------------------------------------------------------- attendance
def build_attendance(rng: np.random.Generator, students: pd.DataFrame) -> pd.DataFrame:
    frames = []
    n = len(students)
    diligence = students["_diligence"].to_numpy()
    base_rate = np.clip(0.905 + 0.032 * diligence + rng.normal(0, 0.035, n), 0.45, 1.0)
    for i, (month, label, school_days) in enumerate(MONTH_LABELS):
        seasonal = -0.02 if month in ("2025-12", "2026-01") else 0.0   # winter illness dip
        rate = np.clip(base_rate + seasonal + rng.normal(0, 0.045, n), 0.3, 1.0)
        present = rng.binomial(school_days, rate)
        remaining = school_days - present
        late = rng.binomial(np.maximum(present, 0), np.clip(0.06 - 0.012 * diligence, 0.005, 0.3))
        leave = rng.binomial(np.maximum(remaining, 0), 0.35)
        absent = remaining - leave
        frames.append(pd.DataFrame({
            "student_id": students["student_id"].to_numpy(),
            "class_id": students["class_id"].to_numpy(),
            "month": month,
            "month_label": label,
            "month_index": i + 1,
            "school_days": school_days,
            "present_days": present,
            "late_days": late,
            "leave_days": leave,
            "absent_days": absent,
            "attendance_pct": (present / school_days * 100).round(2),
        }))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- assignments
def build_assignments(rng: np.random.Generator, students: pd.DataFrame,
                      subjects: pd.DataFrame) -> pd.DataFrame:
    """One aggregated row per student x subject (assignments / homework / projects)."""
    sub_small = subjects[["class_id", "subject_id", "subject_name", "category"]]
    df = students[["student_id", "class_id", "_ability", "_diligence"]].merge(
        sub_small, on="class_id", how="left")
    n = len(df)
    diligence = df["_diligence"].to_numpy()
    ability = df["_ability"].to_numpy()
    assigned = rng.integers(10, 19, n)
    sub_rate = np.clip(0.86 + 0.09 * diligence + rng.normal(0, 0.07, n), 0.15, 1.0)
    submitted = rng.binomial(assigned, sub_rate)
    on_time = rng.binomial(submitted, np.clip(0.85 + 0.07 * diligence + rng.normal(0, 0.06, n), 0.1, 1.0))
    score = np.clip(ability + 6 + 2.5 * diligence + rng.normal(0, 7, n), 5, 100)
    df["assignments_assigned"] = assigned
    df["assignments_submitted"] = submitted
    df["assignments_on_time"] = on_time
    df["submission_rate"] = (submitted / assigned * 100).round(2)
    df["punctuality_rate"] = np.where(submitted > 0, on_time / np.maximum(submitted, 1) * 100, 0).round(2)
    df["avg_assignment_score"] = np.round(score, 2)
    # zero submissions => zero credit for the internal component
    df["assignment_component"] = np.round(df["avg_assignment_score"] * submitted / assigned, 2)
    return df.drop(columns=["_ability", "_diligence"]).rename(columns={"category": "subject_category"})


# --------------------------------------------------------------------- survey
def build_survey(rng: np.random.Generator, students: pd.DataFrame) -> pd.DataFrame:
    """Simulates a Google Form ('Student Wellbeing & Study Habits Survey') export."""
    n = len(students)
    responded = rng.random(n) < 0.88   # not everyone fills the form
    df = students.loc[responded, [
        "student_id", "name", "grade", "section", "campus", "study_hours_per_day",
        "sleep_hours", "screen_time_hours", "extracurricular_hours", "has_tuition",
        "internet_access", "motivation_level", "stress_level", "parent_involvement",
        "career_interest",
    ]].copy()
    m = len(df)
    df.insert(0, "response_id", [f"R{i:05d}" for i in range(1, m + 1)])
    base = pd.Timestamp("2026-02-02")
    df["submitted_at"] = [(base + pd.Timedelta(days=int(d), minutes=int(mi))).isoformat()
                          for d, mi in zip(rng.integers(0, 21, m), rng.integers(0, 1440, m))]
    df["likes_school"] = rng.choice(["Strongly Agree", "Agree", "Neutral", "Disagree"], m,
                                    p=[0.28, 0.42, 0.22, 0.08])
    df["prefers_group_study"] = rng.choice(["Yes", "No"], m, p=[0.55, 0.45])
    df["source"] = "Google Forms (simulated)"
    return df


# -------------------------------------------------- master analytics tables
def build_master(students: pd.DataFrame, marks: pd.DataFrame,
                 assignments: pd.DataFrame, attendance: pd.DataFrame) -> pd.DataFrame:
    """One row per student x subject with weighted grade + rank columns."""
    marks = marks.copy()
    marks["weight"] = marks["exam_type"].map(C.EXAM_WEIGHTS)

    wide = marks.pivot_table(index=["student_id", "class_id", "subject_id", "subject_name",
                                   "subject_category"],
                             columns="exam_type", values="pct").reset_index()
    for exam in C.EXAM_TYPES:
        if exam not in wide.columns:
            wide[exam] = np.nan

    weights = np.array([C.EXAM_WEIGHTS[e] for e in C.EXAM_TYPES])
    exam_matrix = wide[C.EXAM_TYPES].to_numpy(dtype=float)
    wide["weighted_exam_pct"] = np.round(np.nansum(exam_matrix * weights, axis=1) /
                                        np.where(np.isnan(exam_matrix), 0, 1).dot(weights), 2)
    wide["exam_avg_pct"] = np.round(np.nanmean(exam_matrix, axis=1), 2)
    wide["trend_delta"] = np.round(wide["Final Exam"] - wide["Unit Test 1"], 2)
    wide["best_exam_pct"] = np.round(np.nanmax(exam_matrix, axis=1), 2)
    wide["worst_exam_pct"] = np.round(np.nanmin(exam_matrix, axis=1), 2)
    wide["consistency_std"] = np.round(np.nanstd(exam_matrix, axis=1), 2)

    master = wide.merge(
        assignments[["student_id", "subject_id", "assignments_assigned", "assignments_submitted",
                     "assignments_on_time", "submission_rate", "punctuality_rate",
                     "avg_assignment_score", "assignment_component"]],
        on=["student_id", "subject_id"], how="left")

    master["final_subject_score"] = np.round(
        C.EXAM_BLEND_WEIGHT * master["weighted_exam_pct"]
        + C.ASSIGNMENT_WEIGHT * master["assignment_component"].fillna(0), 2)

    letters, gpas, descs = _vector_grades(master["final_subject_score"].to_numpy())
    master["letter_grade"] = letters
    master["gpa_points"] = gpas
    master["grade_descriptor"] = descs
    master["passed"] = master["final_subject_score"] >= C.PASS_MARK_PCT

    stu_cols = ["student_id", "name", "gender", "campus", "grade", "grade_label", "section",
                "class_name", "roll_no", "house"]
    master = master.merge(students[stu_cols], on="student_id", how="left")

    # ranks / percentiles
    g_sub = master.groupby(["class_id", "subject_name"])["final_subject_score"]
    master["rank_in_section_subject"] = g_sub.rank(ascending=False, method="min").astype(int)
    grade_sub = master.groupby(["grade", "subject_name"])["final_subject_score"]
    master["rank_in_grade_subject"] = grade_sub.rank(ascending=False, method="min").astype(int)
    master["percentile_in_grade_subject"] = (grade_sub.rank(pct=True) * 100).round(1)
    master["section_subject_avg"] = g_sub.transform("mean").round(2)
    master["grade_subject_avg"] = grade_sub.transform("mean").round(2)
    master["vs_section_avg"] = (master["final_subject_score"] - master["section_subject_avg"]).round(2)
    master["vs_grade_avg"] = (master["final_subject_score"] - master["grade_subject_avg"]).round(2)

    att = attendance.groupby("student_id")["attendance_pct"].mean().round(2).rename("attendance_pct")
    master = master.merge(att, on="student_id", how="left")

    ordered = ["student_id", "name", "gender", "campus", "grade", "grade_label", "section",
               "class_id", "class_name", "roll_no", "house", "subject_id", "subject_name",
               "subject_category", *C.EXAM_TYPES, "exam_avg_pct", "weighted_exam_pct",
               "best_exam_pct", "worst_exam_pct", "consistency_std", "trend_delta",
               "assignments_assigned", "assignments_submitted", "assignments_on_time",
               "submission_rate", "punctuality_rate", "avg_assignment_score",
               "assignment_component", "final_subject_score", "letter_grade", "gpa_points",
               "grade_descriptor", "passed", "rank_in_section_subject", "rank_in_grade_subject",
               "percentile_in_grade_subject", "section_subject_avg", "grade_subject_avg",
               "vs_section_avg", "vs_grade_avg", "attendance_pct"]
    return master[ordered]


def build_summary(students: pd.DataFrame, master: pd.DataFrame,
                  attendance: pd.DataFrame) -> pd.DataFrame:
    g = master.groupby("student_id")
    summary = pd.DataFrame({
        "overall_pct": g["final_subject_score"].mean().round(2),
        "weighted_exam_pct": g["weighted_exam_pct"].mean().round(2),
        "gpa": g["gpa_points"].mean().round(2),
        "subjects_taken": g["subject_id"].count(),
        "subjects_failed": g["passed"].apply(lambda s: int((~s).sum())),
        "best_subject_pct": g["final_subject_score"].max().round(2),
        "weakest_subject_pct": g["final_subject_score"].min().round(2),
        "subject_spread": (g["final_subject_score"].max() - g["final_subject_score"].min()).round(2),
        "consistency_std": g["final_subject_score"].std().round(2),
        "trend_delta": g["trend_delta"].mean().round(2),
        "submission_rate": g["submission_rate"].mean().round(2),
        "punctuality_rate": g["punctuality_rate"].mean().round(2),
        "avg_assignment_score": g["avg_assignment_score"].mean().round(2),
    }).reset_index()

    idx_best = g["final_subject_score"].idxmax()
    idx_worst = g["final_subject_score"].idxmin()
    summary["best_subject"] = summary["student_id"].map(
        master.loc[idx_best].set_index("student_id")["subject_name"])
    summary["weakest_subject"] = summary["student_id"].map(
        master.loc[idx_worst].set_index("student_id")["subject_name"])

    att = attendance.groupby("student_id").agg(
        attendance_pct=("attendance_pct", "mean"),
        school_days=("school_days", "sum"),
        present_days=("present_days", "sum"),
        absent_days=("absent_days", "sum"),
        late_days=("late_days", "sum"),
    ).round(2).reset_index()
    # attendance momentum: last 3 months vs first 3 months
    early = attendance[attendance["month_index"] <= 3].groupby("student_id")["attendance_pct"].mean()
    late_m = attendance[attendance["month_index"] >= 8].groupby("student_id")["attendance_pct"].mean()
    att["attendance_trend"] = (att["student_id"].map(late_m) - att["student_id"].map(early)).round(2)

    keep = ["student_id", "name", "gender", "age", "campus", "grade", "grade_label", "section",
            "class_id", "class_name", "roll_no", "house", "parent_name", "parent_contact",
            "parent_education", "email", "transport_mode", "has_tuition", "internet_access",
            "is_scholarship", "study_hours_per_day", "sleep_hours", "screen_time_hours",
            "extracurricular_hours", "motivation_level", "stress_level", "parent_involvement",
            "career_interest", "enrollment_date"]
    out = students[keep].merge(summary, on="student_id", how="left").merge(att, on="student_id", how="left")

    letters, gpas, descs = _vector_grades(out["overall_pct"].to_numpy())
    out["letter_grade"] = letters
    out["grade_descriptor"] = descs

    out["rank_in_section"] = out.groupby("class_id")["overall_pct"].rank(ascending=False, method="min").astype(int)
    out["section_size"] = out.groupby("class_id")["student_id"].transform("count")
    out["rank_in_grade"] = out.groupby("grade")["overall_pct"].rank(ascending=False, method="min").astype(int)
    out["grade_size"] = out.groupby("grade")["student_id"].transform("count")
    out["rank_in_school"] = out["overall_pct"].rank(ascending=False, method="min").astype(int)
    out["percentile_in_grade"] = (out.groupby("grade")["overall_pct"].rank(pct=True) * 100).round(1)
    out["percentile_in_section"] = (out.groupby("class_id")["overall_pct"].rank(pct=True) * 100).round(1)
    out["grade_avg_pct"] = out.groupby("grade")["overall_pct"].transform("mean").round(2)
    out["section_avg_pct"] = out.groupby("class_id")["overall_pct"].transform("mean").round(2)
    out["vs_grade_avg"] = (out["overall_pct"] - out["grade_avg_pct"]).round(2)
    return out


def main(n_students: int = C.N_STUDENTS, seed: int = RNG_SEED,
         excel: bool = True, parquet: bool = True) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    print(f"Generating dataset for ~{n_students} students (seed={seed}) ...")

    classes, subjects, teachers = build_reference_tables(rng, n_students)
    students = build_students(rng, classes)
    classes = classes.drop(columns=["target_size"]).merge(
        students.groupby("class_id").size().rename("student_count"), on="class_id", how="left")
    print(f"  students={len(students)}  classes={len(classes)}  subjects={len(subjects)}  teachers={len(teachers)}")

    marks = build_marks(rng, students, subjects)
    print(f"  marks rows={len(marks):,}")
    attendance = build_attendance(rng, students)
    print(f"  attendance rows={len(attendance):,}")
    assignments = build_assignments(rng, students, subjects)
    print(f"  assignment rows={len(assignments):,}")
    survey = build_survey(rng, students)
    print(f"  survey rows={len(survey):,}")

    master = build_master(students, marks, assignments, attendance)
    summary = build_summary(students, master, attendance)
    print(f"  master rows={len(master):,}  summary rows={len(summary):,}")

    # risk / banding needs the analytics module (single source of truth)
    from .core import analytics
    summary = analytics.add_risk_and_bands(summary)

    students_public = students.drop(columns=[c for c in students.columns if c.startswith("_")])
    tables = {
        C.STUDENTS_CSV: students_public,
        C.CLASSES_CSV: classes,
        C.SUBJECTS_CSV: subjects,
        C.TEACHERS_CSV: teachers,
        C.MARKS_CSV: marks,
        C.ATTENDANCE_CSV: attendance,
        C.ASSIGNMENTS_CSV: assignments,
        C.SURVEY_CSV: survey,
        C.MASTER_CSV: master,
        C.SUMMARY_CSV: summary,
    }
    counts = {}
    for path, df in tables.items():
        df.to_csv(path, index=False)
        counts[path.name] = len(df)
        print(f"  wrote {path.name:34s} {len(df):>9,} rows  ({path.stat().st_size/1_048_576:.1f} MB)")

    if parquet:
        # Compressed columnar copies: ~18x smaller than the CSVs and much faster to
        # read. These are what get committed to git so a cloud deploy needs no
        # generation step; the loader prefers them when present.
        total = 0.0
        for path, df in tables.items():
            p = path.with_suffix(".parquet")
            df.to_parquet(p, index=False, compression="zstd")
            total += p.stat().st_size / 1_048_576
        print(f"  wrote {len(tables)} .parquet files            ({total:.1f} MB total)")

    if excel:
        # A single multi-sheet workbook that opens straight in Excel. xlsxwriter is
        # roughly 20x faster than openpyxl here, so prefer it when available.
        try:
            import xlsxwriter  # noqa: F401
            engine = "xlsxwriter"
        except ImportError:
            engine = "openpyxl"
        with pd.ExcelWriter(C.MASTER_XLSX, engine=engine) as xl:
            summary.to_excel(xl, sheet_name="Student Summary", index=False)
            master.head(EXCEL_SHEET_ROWS).to_excel(xl, sheet_name="Student x Subject", index=False)
            classes.to_excel(xl, sheet_name="Classes", index=False)
            subjects.to_excel(xl, sheet_name="Subjects", index=False)
            teachers.to_excel(xl, sheet_name="Teachers", index=False)
        print(f"  wrote {C.MASTER_XLSX.name} via {engine} "
              f"({C.MASTER_XLSX.stat().st_size/1_048_576:.1f} MB)")

    print("\nDone. Launch the dashboard with:  .\\start_analytics_dashboard.ps1")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the student analytics dataset")
    ap.add_argument("--students", type=int, default=C.N_STUDENTS)
    ap.add_argument("--seed", type=int, default=RNG_SEED)
    ap.add_argument("--no-excel", action="store_true", help="skip the Excel workbook (faster)")
    ap.add_argument("--no-parquet", action="store_true", help="skip the .parquet copies")
    args = ap.parse_args()
    main(args.students, args.seed, excel=not args.no_excel, parquet=not args.no_parquet)
