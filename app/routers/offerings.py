"""
/api/offerings
    GET   /api/offerings                   (admin: all; teacher: only their own)
    POST  /api/offerings                   (admin)
    GET   /api/offerings/{id}              (admin, owning teacher)
    PATCH /api/offerings/{id}              (admin)
    GET   /api/offerings/{id}/roster       (admin, owning teacher)
    POST  /api/offerings/{id}/schedules    (admin; clashes are rejected by triggers)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import fetch_one, get_db, transaction
from app.errors import BusinessRuleError, found_or_404
from app.pagination import list_params
from app.repositories import offerings as repo
from app.repositories.courses import get_course
from app.repositories.rooms import get_room
from app.repositories.semesters import get_semester
from app.repositories.teachers import get_teacher
from app.schemas.offering import OfferingCreate, OfferingUpdate, ScheduleCreate
from app.security import ensure_teacher_owns_offering, require_role

router = APIRouter(prefix="/offerings", tags=["offerings"])


def check_teacher_can_teach(conn: sqlite3.Connection, teacher_id: int) -> None:
    """Only an ACTIVE teacher can be assigned to an offering."""
    teacher = found_or_404(get_teacher(conn, teacher_id), "Teacher", teacher_id)
    if teacher["status"] != "active":
        raise BusinessRuleError(f"{teacher['full_name']} is {teacher['status']} and cannot be assigned",
                                field="teacher_id")


@router.get("")
def list_offerings(
    list_args: dict = Depends(list_params),
    semester_id: int | None = Query(None),
    teacher_id: int | None = Query(None),
    department_id: int | None = Query(None),
    course_id: int | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(require_role("admin", "teacher")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged offerings with fill percent. A teacher always gets only their own offerings."""
    if user["role"] == "teacher":
        teacher_id = user["teacher_id"]
    return repo.list_offerings(conn, list_args, semester_id, teacher_id, department_id, course_id, status)


@router.post("", status_code=201)
def create_offering(body: OfferingCreate, user: dict = Depends(require_role("admin")),
                    conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Open a course in a semester and assign a teacher."""
    course = found_or_404(get_course(conn, body.course_id), "Course", body.course_id)
    if not course["is_active"]:
        raise BusinessRuleError("This course is inactive", field="course_id")
    found_or_404(get_semester(conn, body.semester_id), "Semester", body.semester_id)
    check_teacher_can_teach(conn, body.teacher_id)
    with transaction(conn, user["id"]):
        offering_id = repo.insert_offering(conn, body.model_dump(mode="json"))
    return repo.get_offering(conn, offering_id)


@router.get("/{offering_id}")
def get_offering(offering_id: int, user: dict = Depends(require_role("admin", "teacher")),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One offering with its weekly schedule."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    return found_or_404(repo.get_offering(conn, offering_id), "Offering", offering_id)


@router.patch("/{offering_id}")
def update_offering(offering_id: int, body: OfferingUpdate, user: dict = Depends(require_role("admin")),
                    conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Change teacher, section, capacity or status.
    Lowering capacity below enrolled_count is refused by the CHECK constraint
    chk_offering_not_over_capacity (the error handler turns it into a friendly 409).
    """
    found_or_404(repo.get_offering(conn, offering_id), "Offering", offering_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    if "teacher_id" in changes:
        check_teacher_can_teach(conn, changes["teacher_id"])
    with transaction(conn, user["id"]):
        repo.update_offering(conn, offering_id, changes)
    return repo.get_offering(conn, offering_id)


@router.get("/{offering_id}/roster")
def roster(offering_id: int, user: dict = Depends(require_role("admin", "teacher")),
           conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Students of the offering with attendance and grades."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    offering = found_or_404(repo.get_offering(conn, offering_id), "Offering", offering_id)
    return {"offering": offering, "items": repo.get_roster(conn, offering_id)}


@router.post("/{offering_id}/schedules", status_code=201)
def add_schedule(offering_id: int, body: ScheduleCreate, user: dict = Depends(require_role("admin")),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Add a weekly slot. Room clashes and teacher clashes are rejected by the
    triggers trg_no_room_conflict / trg_no_teacher_conflict -> 409 with their message.
    """
    offering = found_or_404(fetch_one(conn, "SELECT id, capacity, status FROM course_offerings WHERE id = ?",
                                      (offering_id,)), "Offering", offering_id)
    if offering["status"] == "cancelled":
        raise BusinessRuleError("A cancelled offering cannot be scheduled")
    room = found_or_404(get_room(conn, body.room_id), "Room", body.room_id)
    if room["capacity"] < offering["capacity"]:
        raise BusinessRuleError(
            f"Room holds {room['capacity']} people but the offering allows {offering['capacity']} students",
            field="room_id",
        )
    with transaction(conn, user["id"]):
        repo.insert_schedule(conn, offering_id, body.model_dump(mode="json"))
    return repo.get_offering(conn, offering_id)
