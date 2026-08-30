"""Canvas LMS REST API client (the 'grade-tracking-Canvas-API' half of this project).

The reference project was a Google Apps Script bound to a spreadsheet; this is
the same idea in Python: pull course users, assignments and the full gradebook
into DataFrames that slot straight into this project's schema, and push grades
back up.

Credentials (see student_analytics/API_SETUP.md):
    CANVAS_DOMAIN     e.g. https://canvas.instructure.com
    CANVAS_API_TOKEN  Account > Settings > Approved Integrations > New Access Token
    CANVAS_COURSE_ID  the number in /courses/<id>

Only the standard library + requests are used, so there is no extra dependency.
"""
from __future__ import annotations

import pandas as pd
import requests

from .. import config as C

TIMEOUT = 30


class CanvasClient:
    def __init__(self, domain: str | None = None, token: str | None = None,
                 course_id: str | int | None = None):
        self.domain = (domain or C.CANVAS_DOMAIN).rstrip("/")
        self.token = token or C.CANVAS_API_TOKEN
        self.course_id = str(course_id or C.CANVAS_COURSE_ID or "")

    # ------------------------------------------------------------------ plumbing
    @property
    def available(self) -> bool:
        return bool(self.domain and self.token)

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        """GET with Canvas link-header pagination followed to the end."""
        if not self.available:
            raise RuntimeError("Canvas is not configured (set CANVAS_DOMAIN and CANVAS_API_TOKEN).")
        url = f"{self.domain}/api/v1/{path.lstrip('/')}"
        params = {"per_page": 100, **(params or {})}
        out: list = []
        while url:
            r = requests.get(url, headers=self._headers, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, dict):
                return payload
            out.extend(payload)
            url = (r.links.get("next") or {}).get("url")
            params = None      # the `next` URL already carries the query string
        return out

    def test_connection(self) -> tuple[bool, str]:
        if not self.available:
            return False, "Not configured — set CANVAS_DOMAIN and CANVAS_API_TOKEN."
        try:
            me = self._get("users/self")
            return True, f"Connected to {self.domain} as {me.get('name', 'unknown')}."
        except requests.HTTPError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # -------------------------------------------------------------------- fetch
    def fetch_courses(self) -> pd.DataFrame:
        data = self._get("courses", {"enrollment_state": "active"})
        return pd.DataFrame([{
            "course_id": c.get("id"), "name": c.get("name"),
            "course_code": c.get("course_code"), "term_id": c.get("enrollment_term_id"),
            "start_at": c.get("start_at"), "workflow_state": c.get("workflow_state"),
        } for c in data])

    def fetch_students(self, course_id=None) -> pd.DataFrame:
        cid = str(course_id or self.course_id)
        data = self._get(f"courses/{cid}/users", {"enrollment_type[]": "student"})
        return pd.DataFrame([{
            "canvas_user_id": u.get("id"),
            "student_id": str(u.get("sis_user_id") or u.get("id")),
            "name": u.get("sortable_name") or u.get("name"),
            "email": u.get("email") or u.get("login_id"),
            "source": "canvas",
        } for u in data])

    def fetch_assignments(self, course_id=None) -> pd.DataFrame:
        cid = str(course_id or self.course_id)
        data = self._get(f"courses/{cid}/assignments")
        return pd.DataFrame([{
            "assignment_id": a.get("id"), "title": a.get("name"),
            "points_possible": a.get("points_possible"), "due_at": a.get("due_at"),
            "group_id": a.get("assignment_group_id"), "published": a.get("published"),
        } for a in data])

    def fetch_gradebook(self, course_id=None) -> pd.DataFrame:
        """Full gradebook in this project's long `marks` shape.

        Returns columns: student_id, canvas_user_id, subject_name (course),
        exam_type (assignment title), marks_obtained, max_marks, pct, exam_date.
        """
        cid = str(course_id or self.course_id)
        assignments = self.fetch_assignments(cid).set_index("assignment_id")
        students = self.fetch_students(cid).set_index("canvas_user_id")
        subs = self._get(f"courses/{cid}/students/submissions",
                         {"student_ids[]": "all", "include[]": "assignment"})
        rows = []
        for s in subs:
            aid = s.get("assignment_id")
            a = assignments.loc[aid] if aid in assignments.index else None
            uid = s.get("user_id")
            stu = students.loc[uid] if uid in students.index else None
            maxm = float(a["points_possible"]) if a is not None and a["points_possible"] else None
            score = s.get("score")
            rows.append({
                "student_id": stu["student_id"] if stu is not None else str(uid),
                "canvas_user_id": uid,
                "student_name": stu["name"] if stu is not None else None,
                "subject_name": f"Canvas course {cid}",
                "exam_type": a["title"] if a is not None else str(aid),
                "marks_obtained": score,
                "max_marks": maxm,
                "pct": round(score / maxm * 100, 2) if score is not None and maxm else None,
                "exam_date": (s.get("submitted_at") or "")[:10] or None,
                "late": s.get("late"),
                "missing": s.get("missing"),
                "workflow_state": s.get("workflow_state"),
            })
        return pd.DataFrame(rows)

    def fetch_enrollment_grades(self, course_id=None) -> pd.DataFrame:
        """Canvas' own computed current/final course score per student."""
        cid = str(course_id or self.course_id)
        data = self._get(f"courses/{cid}/enrollments", {"type[]": "StudentEnrollment"})
        return pd.DataFrame([{
            "canvas_user_id": e.get("user_id"),
            "student_id": str((e.get("sis_user_id") or e.get("user_id"))),
            "current_score": (e.get("grades") or {}).get("current_score"),
            "final_score": (e.get("grades") or {}).get("final_score"),
            "current_grade": (e.get("grades") or {}).get("current_grade"),
        } for e in data])

    # --------------------------------------------------------------------- push
    def upload_grade(self, assignment_id: int, canvas_user_id: int, score: float,
                     comment: str | None = None, course_id=None) -> dict:
        cid = str(course_id or self.course_id)
        url = (f"{self.domain}/api/v1/courses/{cid}/assignments/{assignment_id}"
               f"/submissions/{canvas_user_id}")
        payload = {"submission[posted_grade]": score}
        if comment:
            payload["comment[text_comment]"] = comment
        r = requests.put(url, headers=self._headers, data=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def upload_grades_bulk(self, assignment_id: int, grades: dict[int, float],
                           course_id=None) -> dict:
        """grades = {canvas_user_id: score}. Uses Canvas' bulk update endpoint."""
        cid = str(course_id or self.course_id)
        url = (f"{self.domain}/api/v1/courses/{cid}/assignments/{assignment_id}"
               f"/submissions/update_grades")
        payload = {f"grade_data[{uid}][posted_grade]": sc for uid, sc in grades.items()}
        r = requests.post(url, headers=self._headers, data=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
