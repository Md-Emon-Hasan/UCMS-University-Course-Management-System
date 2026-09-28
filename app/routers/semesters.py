"""
/api/semesters
    GET   /api/semesters                  (any logged-in user)
    POST  /api/semesters                  (admin)
    GET   /api/semesters/active           (any logged-in user)
    GET   /api/semesters/{id}             (any logged-in user)
    PATCH /api/semesters/{id}/activate    (admin)
    POST  /api/semesters/{id}/close       (admin: finalize all grades + switch the active semester)
"""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import get_db, transaction
from app.errors import found_or_404
from app.pagination import list_params
from app.repositories import semesters as repo
from app.schemas.semester import SemesterClose, SemesterCreate
from app.security import get_current_user, require_role
from app.services.semester_service import activate_semester, close_semester

router = APIRouter(prefix="/semesters", tags=["semesters"])


@router.get("")
def list_semesters(list_args: dict = Depends(list_params), user: dict = Depends(get_current_user),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Paged list of semesters, newest first."""
    return repo.list_semesters(conn, list_args)


@router.post("", status_code=201)
def create_semester(body: SemesterCreate, user: dict = Depends(require_role("admin")),
                    conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Create a semester. It starts inactive; use /activate to switch to it."""
    with transaction(conn, user["id"]):
        semester_id = repo.insert_semester(conn, body.model_dump(mode="json"))
    return repo.get_semester(conn, semester_id)


# Declared BEFORE /{semester_id}, so "active" is not treated as an id
@router.get("/active")
def active_semester(user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)) -> dict | None:
    """The current semester, or null if none is active."""
    return repo.get_active_semester(conn)


@router.get("/{semester_id}")
def get_semester(semester_id: int, user: dict = Depends(get_current_user),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One semester."""
    return found_or_404(repo.get_semester(conn, semester_id), "Semester", semester_id)


@router.patch("/{semester_id}/activate")
def activate(semester_id: int, user: dict = Depends(require_role("admin")),
             conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Make this the only active semester."""
    activate_semester(conn, semester_id, user["id"])
    return repo.get_semester(conn, semester_id)


@router.post("/{semester_id}/close")
def close(semester_id: int, body: SemesterClose, user: dict = Depends(require_role("admin")),
          conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Finalize every grade of the semester, close its offerings and activate the next semester."""
    return close_semester(conn, semester_id, body.next_semester_id, user["id"])
