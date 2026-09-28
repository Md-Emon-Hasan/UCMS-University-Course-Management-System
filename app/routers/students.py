"""
/api/students
    GET   /api/students                    (admin)
    POST  /api/students                    (admin)
    GET   /api/students/{id}               (admin, or the student themself)
    PATCH /api/students/{id}               (admin)
    GET   /api/students/{id}/transcript    (admin, or self)
    GET   /api/students/{id}/dues          (admin, or self)
    GET   /api/students/{id}/attendance    (admin, or self)

A student asking for ANOTHER student's data gets 403 (ensure_self_student).
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import found_or_404
from app.pagination import list_params
from app.repositories import students as repo
from app.repositories.departments import get_department
from app.repositories.users import insert_user, set_user_active
from app.schemas.student import StudentCreate, StudentUpdate
from app.security import ensure_self_student, get_current_user, hash_password, require_role
from app.services.grading_service import calculate_cgpa

router = APIRouter(prefix="/students", tags=["students"])


@router.get("")
def list_students(
    list_args: dict = Depends(list_params),
    department_id: int | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(require_role("admin")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged list of students with CGPA, filterable by department and status."""
    return repo.list_students(conn, list_args, department_id, status)


@router.post("", status_code=201)
def create_student(body: StudentCreate, user: dict = Depends(require_role("admin")),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Create account + student + profile (three tables) in ONE transaction: all or nothing."""
    data = body.model_dump(mode="json")
    found_or_404(get_department(conn, data["department_id"]), "Department", data["department_id"])
    password_hash = hash_password(data.pop("password"))     # slow: do it before taking the lock
    profile = data.pop("profile")
    with transaction(conn, user["id"]):
        user_id = insert_user(conn, data["email"], password_hash, "student")
        student_id = repo.insert_student(conn, user_id, data)
        repo.insert_profile(conn, student_id, profile)
    return repo.get_student(conn, student_id)


@router.get("/{student_id}")
def get_student(student_id: int, user: dict = Depends(get_current_user),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One student with profile and CGPA."""
    ensure_self_student(user, student_id)
    return found_or_404(repo.get_student(conn, student_id), "Student", student_id)


@router.patch("/{student_id}")
def update_student(student_id: int, body: StudentUpdate, user: dict = Depends(require_role("admin")),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Change student and/or profile fields; is_active enables/disables the login."""
    student = found_or_404(repo.get_student(conn, student_id), "Student", student_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    profile_changes = changes.pop("profile", None) or {}
    is_active = changes.pop("is_active", None)
    if "department_id" in changes:
        found_or_404(get_department(conn, changes["department_id"]), "Department", changes["department_id"])
    with transaction(conn, user["id"]):
        repo.update_student(conn, student_id, changes)
        repo.update_profile(conn, student_id, profile_changes)
        if is_active is not None:
            set_user_active(conn, student["user_id"], is_active)
    return repo.get_student(conn, student_id)


@router.get("/{student_id}/transcript")
def student_transcript(student_id: int, user: dict = Depends(get_current_user),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Completed courses grouped by semester, with semester GPA and overall CGPA."""
    ensure_self_student(user, student_id)
    student = found_or_404(repo.get_student(conn, student_id), "Student", student_id)
    rows = repo.get_transcript(conn, student_id)

    semesters: dict[str, dict] = {}
    for row in rows:
        group = semesters.setdefault(row["semester_code"], {"semester_code": row["semester_code"],
                                                            "courses": [], "points": 0.0, "credits": 0.0})
        group["courses"].append(row)
        group["points"] += row["grade_point"] * row["credits"]
        group["credits"] += row["credits"]
    for group in semesters.values():
        group["gpa"] = round(group.pop("points") / group["credits"], 2) if group["credits"] else None

    return {"student": student, "semesters": list(semesters.values()), **calculate_cgpa(conn, student_id)}


@router.get("/{student_id}/dues")
def student_dues(student_id: int, user: dict = Depends(get_current_user),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """All invoices of the student and the total still owed."""
    ensure_self_student(user, student_id)
    found_or_404(repo.get_student(conn, student_id), "Student", student_id)
    return repo.get_dues(conn, student_id)


@router.get("/{student_id}/attendance")
def student_attendance(student_id: int, user: dict = Depends(get_current_user),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Attendance percentage per course."""
    ensure_self_student(user, student_id)
    found_or_404(repo.get_student(conn, student_id), "Student", student_id)
    return {"items": repo.get_attendance(conn, student_id)}
