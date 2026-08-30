from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import auth, report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/student/{student_id}")
def generate_report(student_id: str, user: dict = Depends(auth.get_current_user)):
    if user["role"] == "student" and user.get("linked_id") != student_id:
        raise HTTPException(status_code=403, detail="Cannot generate report for another student")
    try:
        path = report_service.generate_student_report(student_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "generated", "path": path, "download_url": f"/reports/student/{student_id}/download"}


@router.get("/student/{student_id}/download")
def download_report(student_id: str, user: dict = Depends(auth.get_current_user)):
    if user["role"] == "student" and user.get("linked_id") != student_id:
        raise HTTPException(status_code=403, detail="Cannot download another student's report")
    from .. import config
    path = config.REPORTS_DIR / f"report_{student_id}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return FileResponse(str(path), media_type="application/pdf", filename=f"report_{student_id}.pdf")
