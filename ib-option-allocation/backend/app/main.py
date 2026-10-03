from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .routers import allocation, auth_routes, change_requests, feasibility, imports, meta, reports, settings, students

app = FastAPI(
    title="IB Option Allocation & Change Feasibility Tool",
    version="1.0.0",
    description="Local API for IBDP/IGCSE option allocation, change-request feasibility, overrides and reports.",
)

app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth_routes, meta, students, allocation, feasibility, change_requests, reports, imports, settings):
    app.include_router(r.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
