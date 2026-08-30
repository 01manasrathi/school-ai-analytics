"""Dataset loading with caching.

Uses Streamlit's cache when running inside Streamlit, and a plain module-level
cache otherwise, so the same loader works in the dashboard, in scripts and in
the PDF batch generator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .. import config as C

_MEM: dict[str, pd.DataFrame] = {}

DTYPES = {
    "grade": "int16",
    "roll_no": "int16",
    "max_marks": "int16",
}


def _resolve(path: Path) -> Path:
    """Prefer the compressed .parquet copy, fall back to the .csv.

    The Parquet files are ~18x smaller and much faster to read, so they are what
    ships in git for cloud deployments. The CSVs stay authoritative locally
    (human-readable and Excel-friendly) and win only if Parquet is absent.
    """
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return parquet
    return path


def _read(path: Path) -> pd.DataFrame:
    path = _resolve(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} not found in {C.DATA_DIR}.\n"
            "Generate the dataset first:  python -m student_analytics.generate_dataset"
        )
    key = str(path)
    if key not in _MEM:
        df = (pd.read_parquet(path) if path.suffix == ".parquet"
              else pd.read_csv(path, low_memory=False))
        for col, dt in DTYPES.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dt)
                except (ValueError, TypeError):
                    pass
        _MEM[key] = df
    return _MEM[key]


@dataclass
class Dataset:
    summary: pd.DataFrame          # 1 row per student (all KPIs, ranks, risk)
    master: pd.DataFrame           # 1 row per student x subject
    marks: pd.DataFrame            # 1 row per student x subject x exam
    attendance: pd.DataFrame       # 1 row per student x month
    assignments: pd.DataFrame
    survey: pd.DataFrame
    students: pd.DataFrame
    classes: pd.DataFrame
    subjects: pd.DataFrame
    teachers: pd.DataFrame
    meta: dict = field(default_factory=dict)

    @property
    def grades(self) -> list[int]:
        return sorted(self.summary["grade"].unique().tolist())

    @property
    def campuses(self) -> list[str]:
        return sorted(self.summary["campus"].unique().tolist())

    def sections_for(self, grade: int) -> list[str]:
        return sorted(self.summary.loc[self.summary["grade"] == grade, "section"].unique().tolist())

    def subject_names(self) -> list[str]:
        return sorted(self.master["subject_name"].unique().tolist())

    def student_row(self, student_id: str) -> pd.Series | None:
        hit = self.summary[self.summary["student_id"] == student_id]
        return None if hit.empty else hit.iloc[0]

    def find_students(self, query: str, limit: int = 25) -> pd.DataFrame:
        q = (query or "").strip().lower()
        if not q:
            return self.summary.head(limit)
        m = (self.summary["name"].str.lower().str.contains(q, na=False)
             | self.summary["student_id"].str.lower().str.contains(q, na=False))
        return self.summary[m].head(limit)


def load_dataset() -> Dataset:
    ds = Dataset(
        summary=_read(C.SUMMARY_CSV),
        master=_read(C.MASTER_CSV),
        marks=_read(C.MARKS_CSV),
        attendance=_read(C.ATTENDANCE_CSV),
        assignments=_read(C.ASSIGNMENTS_CSV),
        survey=_read(C.SURVEY_CSV),
        students=_read(C.STUDENTS_CSV),
        classes=_read(C.CLASSES_CSV),
        subjects=_read(C.SUBJECTS_CSV),
        teachers=_read(C.TEACHERS_CSV),
    )
    ds.meta = {
        "source_format": _resolve(C.SUMMARY_CSV).suffix.lstrip("."),
        "academic_year": C.ACADEMIC_YEAR,
        "n_students": len(ds.summary),
        "n_mark_rows": len(ds.marks),
        "n_master_rows": len(ds.master),
        "n_classes": len(ds.classes),
        "data_dir": str(C.DATA_DIR),
        "total_rows": sum(len(x) for x in (ds.summary, ds.master, ds.marks, ds.attendance,
                                          ds.assignments, ds.survey, ds.students,
                                          ds.classes, ds.subjects, ds.teachers)),
    }
    return ds


def dataset_exists() -> bool:
    return _resolve(C.SUMMARY_CSV).exists() and _resolve(C.MASTER_CSV).exists()


def clear_cache() -> None:
    _MEM.clear()
