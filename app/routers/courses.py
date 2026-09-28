"""
/api/courses
    GET   /api/courses                          (any logged-in user)
    POST  /api/courses                          (admin)
    GET   /api/courses/{id}                     (any logged-in user)
    PATCH /api/courses/{id}                     (admin)
    GET   /api/courses/{id}/prerequisite-tree   (any logged-in user, recursive CTE)
    POST  /api/courses/{id}/prerequisites       (admin, replaces the list)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import BusinessRuleError, found_or_404
from app.pagination import list_params
from app.repositories import courses as repo
from app.repositories.departments import get_department
from app.schemas.course import CourseCreate, CourseUpdate, PrerequisitesSet
from app.security import get_current_user, require_role

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(
    list_args: dict = Depends(list_params),
    department_id: int | None = Query(None),
    level: int | None = Query(None, ge=1, le=4),
    is_active: bool | None = Query(None),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged course catalogue."""
    return repo.list_courses(conn, list_args, department_id, level, is_active)


@router.post("", status_code=201)
def create_course(body: CourseCreate, user: dict = Depends(require_role("admin")),
                  conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Add a course to the catalogue."""
    found_or_404(get_department(conn, body.department_id), "Department", body.department_id)
    with transaction(conn, user["id"]):
        course_id = repo.insert_course(conn, body.model_dump(mode="json"))
    return repo.get_course(conn, course_id)


@router.get("/{course_id}")
def get_course(course_id: int, user: dict = Depends(get_current_user),
               conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One course with direct prerequisites and the courses that require it."""
    course = found_or_404(repo.get_course(conn, course_id), "Course", course_id)
    course["required_by"] = repo.get_required_by(conn, course_id)
    return course


@router.patch("/{course_id}")
def update_course(course_id: int, body: CourseUpdate, user: dict = Depends(require_role("admin")),
                  conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Change course fields."""
    found_or_404(repo.get_course(conn, course_id), "Course", course_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    if "department_id" in changes:
        found_or_404(get_department(conn, changes["department_id"]), "Department", changes["department_id"])
    with transaction(conn, user["id"]):
        repo.update_course(conn, course_id, changes)
    return repo.get_course(conn, course_id)


@router.get("/{course_id}/prerequisite-tree")
def prerequisite_tree(course_id: int, user: dict = Depends(get_current_user),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    The FULL prerequisite tree below a course, found with WITH RECURSIVE.
    `edges` has one row per link: parent_id (needs) -> id (the prerequisite).
    """
    course = found_or_404(repo.get_course(conn, course_id), "Course", course_id)
    edges = repo.get_prerequisite_tree(conn, course_id)
    return {
        "course": {k: course[k] for k in ("id", "code", "title", "level", "credits")},
        "edges": edges,
        "max_depth": max((edge["depth"] for edge in edges), default=0),
    }


@router.post("/{course_id}/prerequisites")
def set_prerequisites(course_id: int, body: PrerequisitesSet, user: dict = Depends(require_role("admin")),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Replace a course's prerequisites. Each new link is checked with a
    recursive CTE: it must not create a cycle (A needs B needs ... needs A).
    Everything runs in one transaction, so one bad link cancels the whole change.
    """
    found_or_404(repo.get_course(conn, course_id), "Course", course_id)
    wanted = list(dict.fromkeys(body.prerequisite_course_ids))       # remove duplicates, keep order
    for prerequisite_id in wanted:
        found_or_404(repo.get_course(conn, prerequisite_id), "Course", prerequisite_id)

    with transaction(conn, user["id"]):
        repo.replace_prerequisites(conn, course_id, [])
        for prerequisite_id in wanted:
            if repo.would_create_cycle(conn, course_id, prerequisite_id):
                code = repo.get_course(conn, prerequisite_id)["code"]
                raise BusinessRuleError(
                    f"Adding {code} would create a cycle: it already requires this course (directly or indirectly)",
                    field="prerequisite_course_ids",
                )
            conn.execute("INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (?, ?)",
                         (course_id, prerequisite_id))
    return repo.get_course(conn, course_id)
