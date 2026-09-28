"""
/api/departments
    GET   /api/departments           (any logged-in user)
    POST  /api/departments           (admin)
    GET   /api/departments/{id}      (any logged-in user)
    PATCH /api/departments/{id}      (admin)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import BusinessRuleError, found_or_404
from app.pagination import list_params
from app.repositories import departments as repo
from app.repositories.teachers import get_teacher
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.security import get_current_user, require_role

router = APIRouter(prefix="/departments", tags=["departments"])


def check_head_teacher(conn: sqlite3.Connection, head_teacher_id: int | None, department_id: int | None) -> None:
    """The head of a department must be a teacher OF that department."""
    if head_teacher_id is None:
        return
    teacher = found_or_404(get_teacher(conn, head_teacher_id), "Teacher", head_teacher_id)
    if department_id is not None and teacher["department_id"] != department_id:
        raise BusinessRuleError("The head teacher must belong to this department", field="head_teacher_id")


@router.get("")
def list_departments(
    list_args: dict = Depends(list_params),
    is_active: bool | None = Query(None),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged list of departments with student/teacher/course counts."""
    return repo.list_departments(conn, list_args, is_active)


@router.post("", status_code=201)
def create_department(body: DepartmentCreate, user: dict = Depends(require_role("admin")),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Create a department. A new department has no teachers yet, so it cannot have a head yet."""
    if body.head_teacher_id is not None:
        raise BusinessRuleError("Create the department first, then add teachers and choose a head",
                                field="head_teacher_id")
    with transaction(conn, user["id"]):
        department_id = repo.insert_department(conn, body.model_dump(mode="json"))
    return repo.get_department(conn, department_id)


@router.get("/{department_id}")
def get_department(department_id: int, user: dict = Depends(get_current_user),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One department."""
    return found_or_404(repo.get_department(conn, department_id), "Department", department_id)


@router.patch("/{department_id}")
def update_department(department_id: int, body: DepartmentUpdate, user: dict = Depends(require_role("admin")),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Change name, code, head teacher or active flag."""
    found_or_404(repo.get_department(conn, department_id), "Department", department_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    check_head_teacher(conn, changes.get("head_teacher_id"), department_id)
    with transaction(conn, user["id"]):
        repo.update_department(conn, department_id, changes)
    return repo.get_department(conn, department_id)
