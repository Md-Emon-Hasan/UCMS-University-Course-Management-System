"""Raw SQL for enrollments (the core many-to-many junction table)."""

import sqlite3

from app.database import fetch_one, where_clause
from app.pagination import paginate

ENROLLMENT_SELECT = """
SELECT
    e.id, e.student_id, s.student_code, s.first_name || ' ' || s.last_name AS student_name,
    e.offering_id, co.course_id, c.code AS course_code, c.title AS course_title, c.credits,
    co.section, co.semester_id, sem.code AS semester_code, co.teacher_id,
    t.first_name || ' ' || t.last_name AS teacher_name,
    e.status, e.enrolled_at, e.dropped_at, e.total_marks, e.grade_point, e.letter_grade,
    e.created_at, e.updated_at
FROM enrollments e
JOIN students         s   ON s.id   = e.student_id
JOIN course_offerings co  ON co.id  = e.offering_id
JOIN courses          c   ON c.id   = co.course_id
JOIN semesters        sem ON sem.id = co.semester_id
JOIN teachers         t   ON t.id   = co.teacher_id
"""


def list_enrollments(conn: sqlite3.Connection, list_args: dict, student_id: int | None = None,
                     offering_id: int | None = None, semester_id: int | None = None,
                     teacher_id: int | None = None, status: str | None = None) -> dict:
    """One page of enrollments with the usual filters."""
    conditions, params = [], []
    for column, value in (("e.student_id", student_id), ("e.offering_id", offering_id),
                          ("co.semester_id", semester_id), ("co.teacher_id", teacher_id),
                          ("e.status", status)):
        if value is not None and value != "":
            conditions.append(f"{column} = ?")
            params.append(value)
    return paginate(
        conn, ENROLLMENT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["student_code", "student_name", "course_code", "course_title"],
        sort_columns=["id", "student_code", "student_name", "course_code", "semester_code",
                      "status", "enrolled_at", "total_marks", "grade_point"],
        default_sort="enrolled_at",
    )


def get_enrollment(conn: sqlite3.Connection, enrollment_id: int) -> dict | None:
    """One enrollment with student, course and semester info."""
    return fetch_one(conn, ENROLLMENT_SELECT + " WHERE e.id = ?", (enrollment_id,))
