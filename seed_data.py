"""Generate realistic sample data for the School AI system.

Run this once (or re-run to reset) to populate data/*.csv with a demo
school: teachers, classes, subjects, students, attendance history and
marks, plus login users for admin / a teacher / a student.

Usage:
    python seed_data.py
"""
import datetime as dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app import config, data_store  # noqa: E402
from app.auth import hash_password  # noqa: E402

random.seed(42)

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Ishaan", "Krishna", "Ananya", "Diya", "Saanvi", "Aadhya", "Kiara", "Myra",
    "Pari", "Anika", "Navya", "Riya",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Reddy", "Rao", "Khan",
    "Mehta", "Kapoor", "Joshi", "Singh", "Das", "Chatterjee", "Pillai",
]

CLASS_DEFS = [("6", "A"), ("6", "B"), ("7", "A"), ("8", "A"), ("9", "A")]
SUBJECT_NAMES = ["Mathematics", "Science", "English", "Social Studies", "Computer Science"]


def rand_name(used: set) -> str:
    while True:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name


def main():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_store.ensure_all_tables()

    teachers, classes, subjects, students, attendance, marks, users = [], [], [], [], [], [], []
    used_names = set()

    # --- Teachers ---
    for i in range(1, 6):
        name = rand_name(used_names)
        teachers.append({
            "teacher_id": f"T{i}",
            "name": name,
            "email": f"{name.split()[0].lower()}.t{i}@school.edu",
            "phone": f"98765{10000 + i}",
            "subject_specialization": SUBJECT_NAMES[(i - 1) % len(SUBJECT_NAMES)],
        })

    # --- Classes ---
    for idx, (grade, section) in enumerate(CLASS_DEFS, start=1):
        classes.append({
            "class_id": f"C{idx}",
            "class_name": f"Grade {grade}",
            "section": section,
            "class_teacher_id": teachers[(idx - 1) % len(teachers)]["teacher_id"],
        })

    # --- Subjects (each class gets all 5 subjects, taught by rotating teachers) ---
    sid = 1
    for c in classes:
        for j, subj in enumerate(SUBJECT_NAMES):
            subjects.append({
                "subject_id": f"S{sid}",
                "subject_name": subj,
                "class_id": c["class_id"],
                "teacher_id": teachers[j % len(teachers)]["teacher_id"],
            })
            sid += 1

    # --- Students (18-22 per class) ---
    student_counter = 1
    today = dt.date.today()
    for c in classes:
        n_students = random.randint(18, 22)
        for roll in range(1, n_students + 1):
            name = rand_name(used_names)
            sidn = f"ST{student_counter:04d}"
            dob = today - dt.timedelta(days=random.randint(11 * 365, 14 * 365))
            students.append({
                "student_id": sidn,
                "name": name,
                "gender": random.choice(["M", "F"]),
                "dob": dob.isoformat(),
                "class_id": c["class_id"],
                "roll_no": roll,
                "parent_name": f"{random.choice(LAST_NAMES)} family",
                "parent_contact": f"9{random.randint(100000000, 999999999)}",
                "email": f"{name.split()[0].lower()}{student_counter}@student.school.edu",
                "address": f"{random.randint(1, 200)} MG Road, City",
                "enrollment_date": (today - dt.timedelta(days=random.randint(30, 900))).isoformat(),
            })
            student_counter += 1

    # --- Attendance (last 60 school days, skip weekends) ---
    att_id = 1
    day = today - dt.timedelta(days=90)
    school_days = []
    while day <= today:
        if day.weekday() < 5:
            school_days.append(day)
        day += dt.timedelta(days=1)
    school_days = school_days[-60:]

    for s in students:
        # give each student an attendance "reliability" so data looks organic
        reliability = random.uniform(0.65, 0.99)
        for d in school_days:
            roll = random.random()
            if roll < reliability:
                status = "Present"
            elif roll < reliability + (1 - reliability) * 0.4:
                status = "Late"
            else:
                status = "Absent"
            attendance.append({
                "id": att_id,
                "student_id": s["student_id"],
                "class_id": s["class_id"],
                "date": d.isoformat(),
                "status": status,
                "marked_by": next(c["class_teacher_id"] for c in classes if c["class_id"] == s["class_id"]),
                "remarks": "",
            })
            att_id += 1

    # --- Marks (Test1, Test2, Final per subject) ---
    mid = 1
    for s in students:
        class_subjects = [sub for sub in subjects if sub["class_id"] == s["class_id"]]
        base_ability = random.uniform(0.45, 0.98)
        for sub in class_subjects:
            for exam in ["Test1", "Test2", "Final"]:
                max_marks = 100 if exam == "Final" else 50
                noise = random.uniform(-0.12, 0.12)
                score = max(0, min(1, base_ability + noise)) * max_marks
                marks.append({
                    "id": mid,
                    "student_id": s["student_id"],
                    "subject_id": sub["subject_id"],
                    "exam_type": exam,
                    "marks_obtained": round(score, 1),
                    "max_marks": max_marks,
                    "date": (today - dt.timedelta(days=random.randint(5, 80))).isoformat(),
                })
                mid += 1

    # --- Users (login accounts) ---
    users.append({
        "username": "admin",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "full_name": "School Administrator",
        "linked_id": "",
        "created_at": today.isoformat(),
    })
    users.append({
        "username": "teacher1",
        "password_hash": hash_password("teacher123"),
        "role": "teacher",
        "full_name": teachers[0]["name"],
        "linked_id": teachers[0]["teacher_id"],
        "created_at": today.isoformat(),
    })
    users.append({
        "username": "student1",
        "password_hash": hash_password("student123"),
        "role": "student",
        "full_name": students[0]["name"],
        "linked_id": students[0]["student_id"],
        "created_at": today.isoformat(),
    })

    import pandas as pd
    data_store.write_table("teachers", pd.DataFrame(teachers))
    data_store.write_table("classes", pd.DataFrame(classes))
    data_store.write_table("subjects", pd.DataFrame(subjects))
    data_store.write_table("students", pd.DataFrame(students))
    data_store.write_table("attendance", pd.DataFrame(attendance))
    data_store.write_table("marks", pd.DataFrame(marks))
    data_store.write_table("users", pd.DataFrame(users))

    print(f"Seeded {len(teachers)} teachers, {len(classes)} classes, {len(subjects)} subjects, "
          f"{len(students)} students, {len(attendance)} attendance rows, {len(marks)} marks rows.")
    print("Login users -> admin/admin123 (admin), teacher1/teacher123 (teacher), student1/student123 (student)")


if __name__ == "__main__":
    main()
