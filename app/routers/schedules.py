"""
/api/schedules
    GET    /api/schedules/weekly    (role-aware: a student sees their classes, a teacher sees theirs)
    DELETE /api/schedules/{id}      (admin: remove one weekly slot)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import fetch_value, get_db, transaction
from app.errors import BusinessRuleError, not_found
from app.repositories.offerings import get_weekly_schedule
from app.repositories.semesters import get_active_semester
from app.security import get_current_user, require_role

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("/weekly")
def weekly(
    semester_id: int | None = Query(None, description="Default: the active semester"),
    teacher_id: int | None = Query(None),
    room_id: int | None = Query(None),
    student_id: int | None = Query(None),
    department_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """
    All class slots of a week. Students and teachers are always limited to
    their own classes, whatever filters they send.
    """
    if semester_id is None:
        active = get_active_semester(conn)
        if active is None:
            raise BusinessRuleError("No active semester", status_code=404)
        semester_id = active["id"]
    if user["role"] == "student":
        student_id, teacher_id = user["student_id"], None
    elif user["role"] == "teacher":
        teacher_id, student_id = user["teacher_id"], None
    items = get_weekly_schedule(conn, semester_id, teacher_id, room_id, student_id, department_id)
    return {"semester_id": semester_id, "items": items}


@router.delete("/{schedule_id}", status_code=200)
def delete_schedule(schedule_id: int, user: dict = Depends(require_role("admin")),
                    conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Remove one weekly slot of an offering."""
    if fetch_value(conn, "SELECT id FROM class_schedules WHERE id = ?", (schedule_id,)) is None:
        raise not_found("Schedule", schedule_id)
    with transaction(conn, user["id"]):
        conn.execute("DELETE FROM class_schedules WHERE id = ?", (schedule_id,))
    return {"deleted": schedule_id}
