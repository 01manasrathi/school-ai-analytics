"""School AI — FastAPI backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
(from inside the backend/ directory)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import data_store
from .routers import ai_router, analytics, attendance, auth_router, classes, marks, reports, students, teachers

app = FastAPI(
    title="School AI",
    description="Open-source, local-first school management system with an agentic AI assistant.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    data_store.ensure_all_tables()


@app.get("/")
def root():
    return {"status": "ok", "service": "School AI backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}


app.include_router(auth_router.router)
app.include_router(students.router)
app.include_router(teachers.router)
app.include_router(classes.router)
app.include_router(attendance.router)
app.include_router(marks.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(ai_router.router)
