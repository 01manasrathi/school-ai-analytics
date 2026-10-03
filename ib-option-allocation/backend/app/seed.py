"""Seed the database with the dummy IBDP data.

Usage (from backend/):  python -m app.seed
This runs the Alembic migrations, WIPES all existing rows, then inserts:
  * programmes, 7 option blocks (A-G), 27 subjects, offerings for every subject/level
  * default rules (Rule table)
  * 60 EXISTING Grade 11 students with valid 4 HL + 3 SL allocations generated programmatically
  * 15 NEW students (10 with ranked preferences) and no choices
  * 5 pending change requests covering the main feasibility outcomes
  * users admin/admin123 (ADMIN) and viewer/viewer123 (READONLY)
"""
from __future__ import annotations

import json
import random
from collections import Counter
from itertools import combinations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import models as M
from .auth import hash_password
from .rules import DEFAULT_RULES
from .services import get_student, recompute_enrollment, run_feasibility

BLOCKS = [
    ("A", "Language A"), ("B", "Language B / Ab Initio"), ("C", "Individuals & Societies"), ("D", "Sciences"),
    ("E", "Mathematics"), ("F", "Arts / Computer Science"), ("G", "Electives / Cross-group"),
]

# code, name, group, HL?, SL?, block
SUBJECTS = [
    ("ENG_LIT", "English A: Literature", 1, True, True, "A"),
    ("ENG_LL", "English A: Language & Literature", 1, True, True, "A"),
    ("CHI_LIT", "Chinese A: Literature", 1, True, True, "A"),
    ("CHI_B", "Chinese B", 2, True, True, "B"),
    ("FRE_B", "French B", 2, True, True, "B"),
    ("SPA_B", "Spanish B", 2, True, True, "B"),
    ("FRE_AB", "French Ab Initio", 2, False, True, "B"),
    ("SPA_AB", "Spanish Ab Initio", 2, False, True, "B"),
    ("CHI_AB", "Chinese Ab Initio", 2, False, True, "B"),
    ("BM", "Business Management", 3, True, True, "C"),
    ("ECON", "Economics", 3, True, True, "C"),
    ("HIST", "History", 3, True, True, "C"),
    ("PSYCH", "Psychology", 3, True, True, "C"),
    ("GEOG", "Geography", 3, True, True, "G"),
    ("DS", "Digital Society", 3, True, True, "G"),
    ("BIO", "Biology", 4, True, True, "D"),
    ("CHEM", "Chemistry", 4, True, True, "D"),
    ("PHYS", "Physics", 4, True, True, "D"),
    ("CS", "Computer Science", 4, True, True, "F"),
    ("SEHS", "Sports, Exercise & Health Science", 4, True, True, "D"),
    ("ESS", "Environmental Systems & Societies", 4, False, True, "G"),
    ("MAA", "Mathematics: Analysis & Approaches", 5, True, True, "E"),
    ("MAI", "Mathematics: Applications & Interpretation", 5, True, True, "E"),
    ("VA", "Visual Arts", 6, True, True, "F"),
    ("MUS", "Music", 6, True, True, "F"),
    ("THE", "Theatre", 6, True, True, "F"),
    ("FILM", "Film", 6, True, True, "G"),
]

DEFAULT_CAPACITY, DEFAULT_MIN = 18, 8
CAPACITY_OVERRIDES = {"MAA": 20, "MAI": 20}  # 4 Maths offerings must seat all 75 students (configurable in Settings)
SEED_HEADROOM = 3  # existing students fill each offering to at most capacity - 3, leaving seats for NEW students

FIRST = ["Aarav", "Mei", "Lucas", "Sofia", "Hiroshi", "Ananya", "Ethan", "Chloe", "Wei", "Isabella", "Arjun", "Yuki",
         "Noah", "Emma", "Jun", "Priya", "Oliver", "Mia", "Ravi", "Zara", "Kai", "Lena", "Daniel", "Siti", "Leo"]
LAST = ["Tan", "Lim", "Sharma", "Wong", "Garcia", "Nakamura", "Smith", "Chen", "Patel", "Muller", "Lee", "Kim",
        "Rossi", "Ng", "Dubois", "Singh", "Ong", "Brown", "Koh", "Martin"]
NATIONALITIES = ["Singaporean", "Indian", "Chinese", "British", "Japanese", "Korean", "French", "Australian", "American", "Indonesian"]

# Existing students with fixed placements (index -> {block: (code, level)}) so the demo change requests behave predictably.
FORCED = {i: {"D": ("CHEM", "HL")} for i in range(18)}  # fills Chemistry HL to exactly 18/18 (full)
FORCED.update({
    19: {"C": ("PSYCH", "HL")},                       # S1020: Psychology HL -> Economics HL (same block)
    20: {"F": ("VA", "SL"), "G": ("GEOG", "SL")},     # S1021: Visual Arts SL -> Film SL (+ compensating Geography -> Music)
    21: {"D": ("BIO", "HL")},                          # S1022: Biology HL -> Chemistry HL (full class)
    22: {"G": ("GEOG", "SL")},                         # S1023: cross-block Geography SL -> Computer Science SL
    23: {"C": ("HIST", "HL")},                         # S1024: History HL -> History SL (breaks 4 HL / 3 SL)
})

NEW_PREFS = [
    ["ENG_LL:HL", "CHI_B:SL", "ECON:HL", "CHEM:HL", "MAA:HL", "CS:SL", "GEOG:SL"],
    ["ENG_LIT:SL", "FRE_AB:SL", "PSYCH:HL", "BIO:HL", "MAI:SL", "VA:HL", "FILM:HL"],
    ["CHI_LIT:HL", "SPA_B:SL", "BM:HL", "PHYS:HL", "MAA:HL", "MUS:SL", "ESS:SL"],
    ["ENG_LL:HL", "FRE_B:HL", "HIST:HL", "SEHS:SL", "MAI:SL", "THE:HL", "DS:SL"],
    ["ENG_LIT:HL", "SPA_AB:SL", "ECON:HL", "CHEM:HL", "MAA:HL", "VA:SL", "GEOG:SL"],
]


def reset(db: Session) -> None:
    for model in (M.AuditLog, M.ChangeRequest, M.StudentPreference, M.StudentChoice, M.Student, M.SubjectOffering,
                  M.OptionBlock, M.Subject, M.Rule, M.User, M.Programme):
        db.execute(delete(model))
    db.flush()


def seed_data(db: Session, rng_seed: int = 2027) -> dict:
    rng = random.Random(rng_seed)
    reset(db)

    igcse = M.Programme(name="IGCSE", grade_range="7-10")
    ibdp = M.Programme(name="IBDP", grade_range="11-12")
    db.add_all([igcse, ibdp])
    db.flush()

    for r in DEFAULT_RULES:
        db.add(M.Rule(programme_id=ibdp.id, rule_type=r["rule_type"], condition_json=json.dumps(r["condition"]),
                      value=r["value"], priority=r["priority"], is_active=True, description=r["description"]))

    blocks = {}
    for i, (name, label) in enumerate(BLOCKS):
        blocks[name] = M.OptionBlock(name=name, label=label, programme_id=ibdp.id, grade="11-12",
                                     period=f"Line {i + 1}", max_choices_per_student=1, sort_order=i + 1)
    db.add_all(blocks.values())

    subjects, offerings = {}, {}  # offerings keyed by (code, level)
    for n, (code, name, group, hl, sl, block) in enumerate(SUBJECTS):
        levels = [lv for lv, ok in (("HL", hl), ("SL", sl)) if ok]
        subj = M.Subject(code=code, name=name, programme_id=ibdp.id, ib_group=group, offered_levels=",".join(levels),
                         prerequisites="[]", is_active=True)
        subjects[code] = subj
        db.add(subj)
        db.flush()
        for lv in levels:
            o = M.SubjectOffering(subject_id=subj.id, block_id=blocks[block].id, level=lv,
                                  teacher=f"{LAST[n % len(LAST)]} ({code})", room=f"R{101 + n}",
                                  capacity=CAPACITY_OVERRIDES.get(code, DEFAULT_CAPACITY), min_enrollment=DEFAULT_MIN,
                                  current_enrollment=0, is_active=True)
            offerings[(code, lv)] = o
            db.add(o)
    db.flush()

    by_block_level: dict[tuple[str, str], list[str]] = {}
    for code, _, _, hl, sl, block in SUBJECTS:
        for lv, ok in (("HL", hl), ("SL", sl)):
            if ok:
                by_block_level.setdefault((block, lv), []).append(code)

    def seed_cap(code, lv):
        o = offerings[(code, lv)]
        return o.capacity if (code, lv) == ("CHEM", "HL") else o.capacity - SEED_HEADROOM

    counts: Counter = Counter()
    block_names = [b for b, _ in BLOCKS]
    all_combos = list(combinations(block_names, 4))

    def name_for(i):
        return f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"

    def build_programme(i):
        forced = FORCED.get(i, {})
        combos = all_combos[:]
        rng.shuffle(combos)
        for hl_blocks in combos:
            if any((lv == "HL") != (b in hl_blocks) for b, (_, lv) in forced.items()):
                continue
            picks = []
            for b in block_names:
                lv = "HL" if b in hl_blocks else "SL"
                if b in forced:
                    picks.append(forced[b])
                    continue
                pool = [c for c in by_block_level.get((b, lv), []) if counts[(c, lv)] < seed_cap(c, lv)]
                if not pool:
                    break
                picks.append((rng.choice(pool), lv))
            if len(picks) == len(block_names):
                return picks
        raise RuntimeError(f"Could not build a valid programme for existing student {i}")

    for i in range(60):
        picks = build_programme(i)
        codes = {c for c, _ in picks}
        lang_a = "Chinese" if "CHI_LIT" in codes else "English"
        lang_b = next((subjects[c].name.split(" ")[0] for c, _ in picks if subjects[c].ib_group == 2), "")
        st = M.Student(student_id=f"S{1001 + i}", name=name_for(i), grade=11, programme_id=ibdp.id, cohort_year=2027,
                       status=M.StudentStatus.EXISTING, nationality=NATIONALITIES[i % len(NATIONALITIES)],
                       language_profile=f"{lang_a} (A), {lang_b} (B)", prior_subjects="", priority=100)
        db.add(st)
        db.flush()
        for code, lv in picks:
            counts[(code, lv)] += 1
            db.add(M.StudentChoice(student_id=st.id, offering_id=offerings[(code, lv)].id, status=M.ChoiceStatus.APPROVED,
                                   source=M.ChoiceSource.EXISTING_ALLOCATION, approved_by="seed"))

    for j in range(15):
        st = M.Student(student_id=f"S{2001 + j}", name=name_for(60 + j * 3), grade=11, programme_id=ibdp.id,
                       cohort_year=2027, status=M.StudentStatus.NEW, nationality=NATIONALITIES[(j * 3) % len(NATIONALITIES)],
                       language_profile="", prior_subjects="", priority=j + 1)
        db.add(st)
        db.flush()
        if j < 10:
            for rank, pref in enumerate(NEW_PREFS[j % len(NEW_PREFS)], start=1):
                code, lv = pref.split(":")
                db.add(M.StudentPreference(student_id=st.id, rank=rank, subject_id=subjects[code].id, level=lv))

    db.flush()
    recompute_enrollment(db)
    db.flush()

    def off(code, lv):
        return offerings[(code, lv)].id

    crs = [
        ("S1020", off("PSYCH", "HL"), off("ECON", "HL"), None, None, "Wants to pursue Economics at university", 1),
        ("S1021", off("VA", "SL"), off("FILM", "SL"), off("GEOG", "SL"), off("MUS", "SL"),
         "Prefers Film; moves Geography out of Block G to Music in Block F to free the slot", 2),
        ("S1022", off("BIO", "HL"), off("CHEM", "HL"), None, None, "Needs Chemistry HL for Medicine", 1),
        ("S1023", off("GEOG", "SL"), off("CS", "SL"), None, None, "Wants Computer Science instead of Geography", 3),
        ("S1024", off("HIST", "HL"), off("HIST", "SL"), None, None, "Workload - wants History at SL", 2),
    ]
    for sid, cur, req, ccur, creq, reason, prio in crs:
        s = get_student(db, sid)
        result = run_feasibility(db, s, cur, req, ccur, creq)
        db.add(M.ChangeRequest(student_id=s.id, current_offering_id=cur, requested_offering_id=req,
                               compensating_current_offering_id=ccur, compensating_requested_offering_id=creq,
                               reason=reason, priority=prio, status=M.CRStatus.PENDING,
                               feasibility_status=result["status"], feasibility_reasons_json=json.dumps(result)))

    db.add_all([
        M.User(username="admin", password_hash=hash_password("admin123"), role=M.Role.ADMIN),
        M.User(username="viewer", password_hash=hash_password("viewer123"), role=M.Role.READONLY),
    ])
    db.add(M.AuditLog(user="seed", action="SEED", entity="database", entity_id="*", new_value="Dummy data loaded"))
    db.commit()
    return {"existing": 60, "new": 15, "change_requests": len(crs), "offerings": len(offerings)}


def main():
    from alembic import command
    from alembic.config import Config

    from .config import BASE_DIR
    from .database import SessionLocal

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        summary = seed_data(db)
    print("Seed complete:", summary)
    print("Logins: admin / admin123 (Admin/Timetabler), viewer / viewer123 (Read-only)")


if __name__ == "__main__":
    main()
