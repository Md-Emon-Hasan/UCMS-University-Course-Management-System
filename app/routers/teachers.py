"""
/api/teachers
    GET   /api/teachers                 (admin)
    POST  /api/teachers                 (admin)
    GET   /api/teachers/{id}            (admin, or the teacher themself)
    PATCH /api/teachers/{id}            (admin)
    GET   /api/teachers/{id}/workload   (admin, or the teacher themself)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import found_or_404
from app.pagination import list_params
from app.repositories import teachers as repo
from app.repositories.departments import get_department
from app.repositories.users import insert_user, set_user_active
from app.schemas.teacher import TeacherCreate, TeacherUpdate
from app.security import ensure_self_teacher, get_current_user, hash_password, require_role

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("")
def list_teachers(
    list_args: dict = Depends(list_params),
    department_id: int | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(require_role("admin")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged list of teachers, filterable by department and status."""
    return repo.list_teachers(conn, list_args, department_id, status)


@router.post("", status_code=201)
def create_teacher(body: TeacherCreate, user: dict = Depends(require_role("admin")),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Create the login account AND the teacher row in ONE transaction.
    If the teacher insert fails (e.g. duplicate employee_code), the user row
    is rolled back too, so no half-created account is left behind.
    """
    data = body.model_dump(mode="json")
    found_or_404(get_department(conn, data["department_id"]), "Department", data["department_id"])
    # Hash BEFORE taking the write lock: bcrypt is slow, and while we hold the
    # lock no other request can write.
    password_hash = hash_password(data.pop("password"))
    with transaction(conn, user["id"]):
        user_id = insert_user(conn, data["email"], password_hash, "teacher")
        teacher_id = repo.insert_teacher(conn, user_id, data)
    return repo.get_teacher(conn, teacher_id)


@router.get("/{teacher_id}")
def get_teacher(teacher_id: int, user: dict = Depends(get_current_user),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One teacher."""
    ensure_self_teacher(user, teacher_id)
    return found_or_404(repo.get_teacher(conn, teacher_id), "Teacher", teacher_id)


@router.patch("/{teacher_id}")
def update_teacher(teacher_id: int, body: TeacherUpdate, user: dict = Depends(require_role("admin")),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Change teacher fields; is_active enables/disables the login account."""
    teacher = found_or_404(repo.get_teacher(conn, teacher_id), "Teacher", teacher_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    is_active = changes.pop("is_active", None)
    if "department_id" in changes:
        found_or_404(get_department(conn, changes["department_id"]), "Department", changes["department_id"])
    with transaction(conn, user["id"]):
        repo.update_teacher(conn, teacher_id, changes)
        if is_active is not None:
            set_user_active(conn, teacher["user_id"], is_active)
    return repo.get_teacher(conn, teacher_id)


@router.get("/{teacher_id}/workload")
def teacher_workload(teacher_id: int, user: dict = Depends(get_current_user),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Workload per semester (v_teacher_workload) + this semester's offerings."""
    ensure_self_teacher(user, teacher_id)
    teacher = found_or_404(repo.get_teacher(conn, teacher_id), "Teacher", teacher_id)
    return {"teacher": teacher, **repo.get_workload(conn, teacher_id)}
