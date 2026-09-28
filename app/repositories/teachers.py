"""Raw SQL for teachers."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, update_by_id, where_clause
from app.pagination import paginate

TEACHER_SELECT = """
SELECT
    t.id, t.user_id, u.email, u.is_active, u.last_login_at,
    t.department_id, d.code AS department_code, d.name AS department_name,
    t.employee_code, t.first_name, t.last_name,
    t.first_name || ' ' || t.last_name AS full_name,
    t.phone, t.designation, t.hired_at, t.status,
    (d.head_teacher_id = t.id) AS is_head,
    t.created_at, t.updated_at
FROM teachers t
JOIN users       u ON u.id = t.user_id
JOIN departments d ON d.id = t.department_id
"""


def list_teachers(conn: sqlite3.Connection, list_args: dict, department_id: int | None = None,
                  status: str | None = None) -> dict:
    """One page of teachers, with optional department and status filters."""
    conditions, params = [], []
    if department_id is not None:
        conditions.append("t.department_id = ?")
        params.append(department_id)
    if status:
        conditions.append("t.status = ?")
        params.append(status)
    return paginate(
        conn, TEACHER_SELECT + where_clause(conditions), params, list_args,
        search_columns=["full_name", "employee_code", "email"],
        sort_columns=["id", "full_name", "employee_code", "department_code", "designation", "hired_at", "status"],
        default_sort="full_name",
    )


def get_teacher(conn: sqlite3.Connection, teacher_id: int) -> dict | None:
    """One teacher with account and department info."""
    return fetch_one(conn, TEACHER_SELECT + " WHERE t.id = ?", (teacher_id,))


def insert_teacher(conn: sqlite3.Connection, user_id: int, data: dict) -> int:
    """Create the teacher row for an existing user account."""
    return execute(
        conn,
        """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name,
                                 phone, designation, hired_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, data["department_id"], data["employee_code"], data["first_name"], data["last_name"],
         data.get("phone"), data["designation"], data["hired_at"], data.get("status", "active")),
    )


def update_teacher(conn: sqlite3.Connection, teacher_id: int, changes: dict) -> int:
    """Change some columns of a teacher."""
    return update_by_id(conn, "teachers", teacher_id, changes)


def get_workload(conn: sqlite3.Connection, teacher_id: int) -> dict:
    """
    Workload per semester (from the v_teacher_workload view) plus the
    offerings of the active semester.
    """
    per_semester = fetch_all(
        conn,
        """SELECT w.* FROM v_teacher_workload w
           JOIN semesters s ON s.id = w.semester_id
           WHERE w.teacher_id = ?
           ORDER BY s.start_date DESC""",
        (teacher_id,),
    )
    current_offerings = fetch_all(
        conn,
        """SELECT v.offering_id AS id, v.course_code, v.title, v.section, v.credits,
                  v.capacity, v.enrolled_count, v.fill_percent, v.status
           FROM v_offering_summary v
           JOIN semesters s ON s.id = v.semester_id
           WHERE v.teacher_id = ? AND s.is_active = 1
           ORDER BY v.course_code, v.section""",
        (teacher_id,),
    )
    return {"per_semester": per_semester, "current_offerings": current_offerings}
