"""
The FastAPI application: API under /api, frontend files under /.

Start it with:  python run.py      (or: uvicorn app.main:app --reload)
API docs:       http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.database import enable_wal, get_connection
from app.errors import register_exception_handlers
from app.routers import (announcements, assessments, attendance, audit_logs, auth, billing, courses,
                         dashboard, departments, enrollments, offerings, reports, rooms, schedules,
                         semesters, students, teachers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once at startup: make sure the schema exists and WAL mode is on.
    (Seeding demo data is done by run.py / scripts/seed.py, not here.)
    """
    from scripts.init_db import init_database, list_tables   # imported here: only needed at startup

    conn = get_connection()
    try:
        has_tables = bool(list_tables(conn))
        if has_tables:
            enable_wal(conn)
    finally:
        conn.close()
    if not has_tables:
        init_database(config.DB_PATH, verbose=False)
    yield


app = FastAPI(
    title="UCMS API",
    description="University Course Management System: FastAPI + raw SQLite (no ORM).",
    version="1.0.0",
    lifespan=lifespan,
)
register_exception_handlers(app)

# Every router lives under /api
for module in (auth, dashboard, departments, teachers, students, courses, rooms, semesters, offerings,
               schedules, enrollments, attendance, assessments, billing, announcements, audit_logs, reports):
    app.include_router(module.router, prefix="/api")

# The frontend: plain files. Mounted LAST, so /api/... routes win.
# html=True serves index.html for "/".
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
