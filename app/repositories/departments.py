"""Raw SQL for departments."""

import sqlite3

from app.database import execute, fetch_one, update_by_id, where_clause
from app.pagination import paginate

# Correlated sub-queries count the related rows for each department.
DEPARTMENT_SELECT = """
SELECT
    d.id, d.name, d.code, d.is_active, d.head_teacher_id,
    t.first_name || ' ' || t.last_name                               AS head_teacher_name,
    (SELECT COUNT(*) FROM students s WHERE s.department_id = d.id)   AS student_count,
    (SELECT COUNT(*) FROM teachers x WHERE x.department_id = d.id)   AS teacher_count,
    (SELECT COUNT(*) FROM courses  c WHERE c.department_id = d.id)   AS course_count,
    d.created_at, d.updated_at
FROM departments d
LEFT JOIN teachers t ON t.id = d.head_teacher_id
"""


def list_departments(conn: sqlite3.Connection, list_args: dict, is_active: bool | None = None) -> dict:
    """One page of departments, optionally only active or inactive ones."""
    conditions, params = [], []
    if is_active is not None:
        conditions.append("d.is_active = ?")
        params.append(1 if is_active else 0)
    return paginate(
        conn, DEPARTMENT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["name", "code", "head_teacher_name"],
        sort_columns=["id", "name", "code", "student_count", "teacher_count", "course_count"],
        default_sort="code",
    )


def get_department(conn: sqlite3.Connection, department_id: int) -> dict | None:
    """One department with its counts."""
    return fetch_one(conn, DEPARTMENT_SELECT + " WHERE d.id = ?", (department_id,))


def insert_department(conn: sqlite3.Connection, data: dict) -> int:
    """Create a department and return its id."""
    return execute(
        conn,
        "INSERT INTO departments (name, code, head_teacher_id, is_active) VALUES (?, ?, ?, ?)",
        (data["name"], data["code"], data.get("head_teacher_id"), data.get("is_active", True)),
    )


def update_department(conn: sqlite3.Connection, department_id: int, changes: dict) -> int:
    """Change some columns of a department."""
    return update_by_id(conn, "departments", department_id, changes)
