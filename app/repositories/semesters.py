"""Raw SQL for semesters."""

import sqlite3

from app.database import execute, fetch_one
from app.pagination import paginate

SEMESTER_SELECT = """
SELECT
    s.id, s.name, s.code, s.start_date, s.end_date,
    s.registration_start, s.registration_end, s.is_active,
    (date('now') BETWEEN s.registration_start AND s.registration_end) AS registration_open,
    (SELECT COUNT(*) FROM course_offerings co WHERE co.semester_id = s.id) AS offering_count,
    (SELECT COUNT(*) FROM enrollments e JOIN course_offerings co ON co.id = e.offering_id
      WHERE co.semester_id = s.id AND e.status <> 'dropped')              AS enrollment_count,
    s.created_at, s.updated_at
FROM semesters s
"""


def list_semesters(conn: sqlite3.Connection, list_args: dict) -> dict:
    """One page of semesters (newest first by default)."""
    if not list_args["sort"]:
        list_args = {**list_args, "sort": "start_date", "order": "desc"}
    return paginate(
        conn, SEMESTER_SELECT, [], list_args,
        search_columns=["name", "code"],
        sort_columns=["id", "name", "code", "start_date", "end_date", "is_active"],
        default_sort="start_date",
    )


def get_semester(conn: sqlite3.Connection, semester_id: int) -> dict | None:
    """One semester."""
    return fetch_one(conn, SEMESTER_SELECT + " WHERE s.id = ?", (semester_id,))


def get_active_semester(conn: sqlite3.Connection) -> dict | None:
    """The one active semester (the partial unique index guarantees at most one)."""
    return fetch_one(conn, SEMESTER_SELECT + " WHERE s.is_active = 1")


def insert_semester(conn: sqlite3.Connection, data: dict) -> int:
    """Create a semester (always inactive at first) and return its id."""
    return execute(
        conn,
        """INSERT INTO semesters (name, code, start_date, end_date, registration_start, registration_end)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["name"], data["code"], data["start_date"], data["end_date"],
         data["registration_start"], data["registration_end"]),
    )
