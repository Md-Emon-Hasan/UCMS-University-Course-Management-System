"""
Attendance (all under /api/offerings/{id}):
    POST /api/offerings/{id}/attendance            (admin, owning teacher; whole roster for one date)
    GET  /api/offerings/{id}/attendance?class_date (admin, owning teacher; roster + saved statuses)
    GET  /api/offerings/{id}/attendance-report     (admin, owning teacher)
"""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.database import fetch_all, fetch_one, get_db, transaction
from app.errors import BusinessRuleError
from app.repositories import attendance as repo
from app.schemas.attendance import AttendanceBulk
from app.security import ensure_teacher_owns_offering, require_role

router = APIRouter(prefix="/offerings", tags=["attendance"])


@router.post("/{offering_id}/attendance")
def save_attendance(offering_id: int, body: AttendanceBulk,
                    user: dict = Depends(require_role("admin", "teacher")),
                    conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Save the attendance of ONE date for many students at once.
    All rows are saved in one transaction: if one is invalid, none are saved.
    """
    ensure_teacher_owns_offering(conn, user, offering_id)
    semester = fetch_one(
        conn,
        """SELECT s.start_date, s.end_date FROM course_offerings co
           JOIN semesters s ON s.id = co.semester_id WHERE co.id = ?""",
        (offering_id,),
    )
    class_date = body.class_date.isoformat()
    if not (semester["start_date"] <= class_date <= semester["end_date"]):
        raise BusinessRuleError(
            f"The date must be inside the semester ({semester['start_date']} to {semester['end_date']})",
            field="class_date",
        )

    # Every enrollment in the request must be an ACTIVE student of THIS offering
    valid_ids = {row["id"] for row in fetch_all(
        conn, "SELECT id FROM enrollments WHERE offering_id = ? AND status = 'enrolled'", (offering_id,))}
    invalid = [r.enrollment_id for r in body.records if r.enrollment_id not in valid_ids]
    if invalid:
        raise BusinessRuleError(f"These enrollments are not active in this offering: {invalid}", field="records")

    records = [r.model_dump() for r in body.records]
    with transaction(conn, user["id"]):
        saved = repo.upsert_attendance(conn, class_date, records, user["id"])
    return {"offering_id": offering_id, "class_date": class_date, "saved": saved}


@router.get("/{offering_id}/attendance")
def attendance_for_date(offering_id: int, class_date: date = Query(...),
                        user: dict = Depends(require_role("admin", "teacher")),
                        conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """The roster with the status already saved for that date (null = not taken yet)."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    items = repo.get_roster_for_date(conn, offering_id, class_date.isoformat())
    return {"offering_id": offering_id, "class_date": class_date.isoformat(),
            "already_recorded": any(item["status"] for item in items), "items": items}


@router.get("/{offering_id}/attendance-report")
def attendance_report(offering_id: int, user: dict = Depends(require_role("admin", "teacher")),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Per-student totals and the recorded class dates of an offering."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    return {"offering_id": offering_id, **repo.get_attendance_report(conn, offering_id)}
