"""
/api/reports
    GET  /api/reports/grade-distribution?offering_id=     (admin; teacher for own offerings)
    GET  /api/reports/department-performance             (admin; reads the "materialized view")
    POST /api/reports/department-performance/refresh     (admin; runs refresh_department_performance)
    GET  /api/reports/collection-summary?semester_id=    (admin, accountant)
    GET  /api/reports/low-attendance?threshold=75        (admin; teacher for own offerings)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import BusinessRuleError, found_or_404
from app.repositories.semesters import get_active_semester, get_semester
from app.security import ensure_teacher_owns_offering, require_role
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


def resolve_semester(conn: sqlite3.Connection, semester_id: int | None) -> dict:
    """The requested semester, or the active one when none is given."""
    if semester_id is not None:
        return found_or_404(get_semester(conn, semester_id), "Semester", semester_id)
    active = get_active_semester(conn)
    if active is None:
        raise BusinessRuleError("No active semester", status_code=404)
    return active


@router.get("/grade-distribution")
def grade_distribution(offering_id: int | None = Query(None),
                       user: dict = Depends(require_role("admin", "teacher")),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Letter-grade counts for one offering, or for everything the user may see."""
    teacher_id = None
    if offering_id is not None:
        ensure_teacher_owns_offering(conn, user, offering_id)
    elif user["role"] == "teacher":
        teacher_id = user["teacher_id"]
    return {"offering_id": offering_id,
            "items": report_service.grade_distribution(conn, offering_id=offering_id, teacher_id=teacher_id)}


@router.get("/department-performance")
def department_performance(user: dict = Depends(require_role("admin")),
                           conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Pre-calculated numbers from mv_department_performance (see refreshed_at)."""
    return report_service.department_performance(conn)


@router.post("/department-performance/refresh")
def refresh_department_performance(user: dict = Depends(require_role("admin")),
                                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Recalculate the materialized-view table now."""
    rows = report_service.refresh_department_performance(conn, user["id"])
    return {"rows": rows, **report_service.department_performance(conn)}


@router.get("/collection-summary")
def collection_summary(semester_id: int | None = Query(None),
                       user: dict = Depends(require_role("admin", "accountant")),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Billed vs collected for a semester (default: active), by method and by department."""
    semester = resolve_semester(conn, semester_id)
    return {"semester_code": semester["code"], **report_service.collection_summary(conn, semester["id"])}


@router.get("/low-attendance")
def low_attendance(threshold: float = Query(75, gt=0, le=100),
                   semester_id: int | None = Query(None),
                   user: dict = Depends(require_role("admin", "teacher")),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Students below `threshold` % attendance. Teachers only see their own offerings."""
    semester = resolve_semester(conn, semester_id)
    teacher_id = user["teacher_id"] if user["role"] == "teacher" else None
    items = report_service.low_attendance(conn, threshold, semester["id"], teacher_id)
    return {"threshold": threshold, "semester_code": semester["code"], "items": items}
