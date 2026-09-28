"""
Semester services.

Service from the spec:
    #9 close_semester(semester_id, next_semester_id, actor_id)
Plus:
    activate_semester(semester_id, actor_id)
"""

import sqlite3

from app.database import fetch_all, fetch_one, transaction
from app.errors import BusinessRuleError, not_found
from app.services.grading_service import finalize_inside_transaction


def switch_active_semester(conn: sqlite3.Connection, new_active_id: int) -> None:
    """
    Make `new_active_id` the only active semester.

    DB LESSON: the ORDER of these two UPDATEs matters. The partial unique index
    uq_one_active_semester allows only ONE row with is_active = 1, and SQLite
    checks it after every statement. Activating first would briefly create two
    active rows and fail, so we deactivate first.
    """
    conn.execute("UPDATE semesters SET is_active = 0 WHERE is_active = 1 AND id <> ?", (new_active_id,))
    conn.execute("UPDATE semesters SET is_active = 1 WHERE id = ?", (new_active_id,))


def activate_semester(conn: sqlite3.Connection, semester_id: int, actor_id: int) -> dict:
    """Set one semester active (and every other one inactive) in a single transaction."""
    with transaction(conn, actor_id):
        if fetch_one(conn, "SELECT id FROM semesters WHERE id = ?", (semester_id,)) is None:
            raise not_found("Semester", semester_id)
        switch_active_semester(conn, semester_id)
    return {"active_semester_id": semester_id}


def close_semester(conn: sqlite3.Connection, semester_id: int, next_semester_id: int, actor_id: int) -> dict:
    """
    SERVICE #9: end a semester.
      1. finalize the grade of every enrollment still 'enrolled'
      2. mark its open offerings as 'closed'
      3. make next_semester_id the active semester

    ONE transaction for everything: if any grade cannot be finalized (for
    example weights that do not add up to 100), nothing at all is changed.
    """
    if semester_id == next_semester_id:
        raise BusinessRuleError("The next semester must be different from the one being closed",
                                field="next_semester_id")

    with transaction(conn, actor_id):
        semester = fetch_one(conn, "SELECT id, code FROM semesters WHERE id = ?", (semester_id,))
        if semester is None:
            raise not_found("Semester", semester_id)
        if fetch_one(conn, "SELECT id FROM semesters WHERE id = ?", (next_semester_id,)) is None:
            raise not_found("Semester", next_semester_id)

        pending = fetch_all(
            conn,
            """SELECT e.id FROM enrollments e
               JOIN course_offerings co ON co.id = e.offering_id
               WHERE co.semester_id = ? AND e.status = 'enrolled'
               ORDER BY e.id""",
            (semester_id,),
        )
        for row in pending:
            finalize_inside_transaction(conn, row["id"])

        closed = conn.execute(
            "UPDATE course_offerings SET status = 'closed' WHERE semester_id = ? AND status = 'open'",
            (semester_id,),
        ).rowcount
        switch_active_semester(conn, next_semester_id)

    return {
        "closed_semester": semester["code"],
        "grades_finalized": len(pending),
        "offerings_closed": closed,
        "active_semester_id": next_semester_id,
    }
