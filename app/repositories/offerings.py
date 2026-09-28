"""Raw SQL for course_offerings and class_schedules."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, update_by_id, where_clause
from app.pagination import paginate

# We REUSE the v_offering_summary view here instead of repeating its 4-table JOIN.
OFFERING_SELECT = """
SELECT
    v.offering_id AS id, v.*,
    (SELECT COUNT(*) FROM class_schedules cs WHERE cs.offering_id = v.offering_id) AS schedule_count
FROM v_offering_summary v
"""

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def list_offerings(conn: sqlite3.Connection, list_args: dict, semester_id: int | None = None,
                   teacher_id: int | None = None, department_id: int | None = None,
                   course_id: int | None = None, status: str | None = None) -> dict:
    """One page of offerings with the usual filters."""
    conditions, params = [], []
    for column, value in (("v.semester_id", semester_id), ("v.teacher_id", teacher_id),
                          ("v.department_id", department_id), ("v.course_id", course_id),
                          ("v.status", status)):
        if value is not None and value != "":
            conditions.append(f"{column} = ?")
            params.append(value)
    return paginate(
        conn, OFFERING_SELECT + where_clause(conditions), params, list_args,
        search_columns=["course_code", "title", "teacher_name"],
        sort_columns=["id", "course_code", "title", "section", "teacher_name", "capacity",
                      "enrolled_count", "fill_percent", "status", "semester_code"],
        default_sort="course_code",
    )


def get_offering(conn: sqlite3.Connection, offering_id: int) -> dict | None:
    """One offering with its weekly schedule."""
    offering = fetch_one(conn, OFFERING_SELECT + " WHERE v.offering_id = ?", (offering_id,))
    if offering is None:
        return None
    offering["schedules"] = get_schedules(conn, offering_id)
    return offering


def insert_offering(conn: sqlite3.Connection, data: dict) -> int:
    """Create an offering and return its id."""
    return execute(
        conn,
        """INSERT INTO course_offerings (course_id, semester_id, teacher_id, section, capacity, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["course_id"], data["semester_id"], data["teacher_id"], data["section"],
         data["capacity"], data.get("status", "open")),
    )


def update_offering(conn: sqlite3.Connection, offering_id: int, changes: dict) -> int:
    """Change some columns of an offering."""
    return update_by_id(conn, "course_offerings", offering_id, changes)


def get_roster(conn: sqlite3.Connection, offering_id: int) -> list[dict]:
    """Students of an offering with attendance % and grade (dropped students listed last)."""
    return fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, s.id AS student_id, s.student_code,
                  s.first_name || ' ' || s.last_name AS full_name, u.email,
                  e.status, e.enrolled_at, e.dropped_at,
                  e.total_marks, e.grade_point, e.letter_grade,
                  v.total_classes, v.present_count, v.attendance_percent
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           JOIN users    u ON u.id = s.user_id
           LEFT JOIN v_attendance_percentage v ON v.enrollment_id = e.id
           WHERE e.offering_id = ?
           ORDER BY (e.status = 'dropped'), s.student_code""",
        (offering_id,),
    )


def get_schedules(conn: sqlite3.Connection, offering_id: int) -> list[dict]:
    """Weekly time slots of one offering."""
    rows = fetch_all(
        conn,
        """SELECT cs.id, cs.room_id, r.building, r.room_number, cs.day_of_week, cs.start_time, cs.end_time
           FROM class_schedules cs
           JOIN rooms r ON r.id = cs.room_id
           WHERE cs.offering_id = ?
           ORDER BY cs.day_of_week, cs.start_time""",
        (offering_id,),
    )
    for row in rows:
        row["day_name"] = DAY_NAMES[row["day_of_week"]]
    return rows


def insert_schedule(conn: sqlite3.Connection, offering_id: int, data: dict) -> int:
    """
    Add a weekly slot. The triggers trg_no_room_conflict and
    trg_no_teacher_conflict reject clashes with RAISE(ABORT, ...).
    """
    return execute(
        conn,
        """INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time)
           VALUES (?, ?, ?, ?, ?)""",
        (offering_id, data["room_id"], data["day_of_week"], data["start_time"], data["end_time"]),
    )


def get_weekly_schedule(conn: sqlite3.Connection, semester_id: int, teacher_id: int | None = None,
                        room_id: int | None = None, student_id: int | None = None,
                        department_id: int | None = None) -> list[dict]:
    """
    Every class slot of a semester, optionally only for one teacher, room,
    department or student (a student sees the classes they are enrolled in).
    """
    conditions = ["co.semester_id = ?", "co.status <> 'cancelled'"]
    params: list = [semester_id]
    if teacher_id is not None:
        conditions.append("co.teacher_id = ?")
        params.append(teacher_id)
    if room_id is not None:
        conditions.append("cs.room_id = ?")
        params.append(room_id)
    if department_id is not None:
        conditions.append("c.department_id = ?")
        params.append(department_id)
    if student_id is not None:
        conditions.append("""co.id IN (SELECT offering_id FROM enrollments
                                        WHERE student_id = ? AND status = 'enrolled')""")
        params.append(student_id)
    rows = fetch_all(
        conn,
        """SELECT cs.id, cs.offering_id, cs.day_of_week, cs.start_time, cs.end_time,
                  c.code AS course_code, c.title, co.section, c.department_id,
                  r.building || ' ' || r.room_number AS room,
                  t.first_name || ' ' || t.last_name AS teacher_name
           FROM class_schedules cs
           JOIN course_offerings co ON co.id = cs.offering_id
           JOIN courses  c ON c.id = co.course_id
           JOIN rooms    r ON r.id = cs.room_id
           JOIN teachers t ON t.id = co.teacher_id"""
        + where_clause(conditions)
        + " ORDER BY cs.day_of_week, cs.start_time, c.code",
        params,
    )
    for row in rows:
        row["day_name"] = DAY_NAMES[row["day_of_week"]]
    return rows
