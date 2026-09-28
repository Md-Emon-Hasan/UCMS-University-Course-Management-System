"""
/api/enrollments
    POST  /api/enrollments                     (admin, or a student enrolling themself)
    GET   /api/enrollments                     (admin: all; teacher: their offerings; student: own)
    GET   /api/enrollments/eligibility         (student: own; admin: ?student_id=)
    PATCH /api/enrollments/{id}/drop           (admin, or the student who owns it)
    POST  /api/enrollments/{id}/finalize-grade (admin, or the teacher of the offering)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import fetch_value, get_db
from app.errors import BusinessRuleError, not_found
from app.pagination import list_params
from app.repositories import enrollments as repo
from app.repositories.semesters import get_active_semester
from app.schemas.enrollment import EnrollRequest
from app.security import (ensure_self_student, ensure_teacher_owns_offering, forbidden,
                          get_current_user, require_role)
from app.services.enrollment_service import drop_enrollment, enroll_student, list_eligibility
from app.services.grading_service import finalize_grade

router = APIRouter(prefix="/enrollments", tags=["enrollments"])


@router.post("", status_code=201)
def enroll(body: EnrollRequest, user: dict = Depends(require_role("admin", "student")),
           conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Enroll into an offering. All 7 business rules are checked in enroll_student()."""
    if user["role"] == "student":
        student_id = user["student_id"]            # a student can only enroll THEMSELF
    elif body.student_id is None:
        raise BusinessRuleError("student_id is required", field="student_id")
    else:
        student_id = body.student_id
    return enroll_student(conn, student_id, body.offering_id, user["id"])


@router.get("")
def list_enrollments(
    list_args: dict = Depends(list_params),
    student_id: int | None = Query(None),
    offering_id: int | None = Query(None),
    semester_id: int | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(require_role("admin", "teacher", "student")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged enrollments. Students see only their own; teachers only those of their offerings."""
    teacher_id = None
    if user["role"] == "student":
        if student_id is not None and student_id != user["student_id"]:
            raise forbidden("You can only see your own enrollments")
        student_id = user["student_id"]
    elif user["role"] == "teacher":
        teacher_id = user["teacher_id"]
    return repo.list_enrollments(conn, list_args, student_id, offering_id, semester_id, teacher_id, status)


@router.get("/eligibility")
def eligibility(
    student_id: int | None = Query(None),
    semester_id: int | None = Query(None, description="Default: the active semester"),
    user: dict = Depends(require_role("admin", "student")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """
    Every offering of the semester with eligible = true/false and the reason.
    It is a dry run of the same checks enroll_student() uses, and writes nothing.
    """
    if user["role"] == "student":
        student_id = user["student_id"]
    elif student_id is None:
        raise BusinessRuleError("student_id is required", field="student_id")
    ensure_self_student(user, student_id)
    if semester_id is None:
        active = get_active_semester(conn)
        if active is None:
            raise BusinessRuleError("No active semester", status_code=404)
        semester_id = active["id"]
    return {"semester_id": semester_id, "items": list_eligibility(conn, student_id, semester_id)}


@router.patch("/{enrollment_id}/drop")
def drop(enrollment_id: int, user: dict = Depends(require_role("admin", "student")),
         conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Drop a course (status -> dropped, dropped_at -> now)."""
    owner_id = fetch_value(conn, "SELECT student_id FROM enrollments WHERE id = ?", (enrollment_id,))
    if owner_id is None:
        raise not_found("Enrollment", enrollment_id)
    ensure_self_student(user, owner_id)
    return drop_enrollment(conn, enrollment_id, user["id"])


@router.post("/{enrollment_id}/finalize-grade")
def finalize(enrollment_id: int, user: dict = Depends(require_role("admin", "teacher")),
             conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """calculate_final_marks -> marks_to_gpa -> save the grade, status = completed."""
    offering_id = fetch_value(conn, "SELECT offering_id FROM enrollments WHERE id = ?", (enrollment_id,))
    if offering_id is None:
        raise not_found("Enrollment", enrollment_id)
    ensure_teacher_owns_offering(conn, user, offering_id)
    finalize_grade(conn, enrollment_id, user["id"])
    return repo.get_enrollment(conn, enrollment_id)
