"""Raw SQL for students and student_profiles (1:1)."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, update_by_id, where_clause
from app.pagination import paginate
from app.schemas.common import add_taka_fields

STUDENT_SELECT = """
SELECT
    s.id, s.user_id, u.email, u.is_active, u.last_login_at,
    s.department_id, d.code AS department_code, d.name AS department_name,
    s.student_code, s.first_name, s.last_name,
    s.first_name || ' ' || s.last_name AS full_name,
    s.admission_date, s.status,
    -- CGPA = credit-weighted average over completed courses (NULL if none yet)
    (SELECT ROUND(SUM(e.grade_point * c.credits) / SUM(c.credits), 2)
       FROM enrollments e
       JOIN course_offerings co ON co.id = e.offering_id
       JOIN courses c ON c.id = co.course_id
      WHERE e.student_id = s.id AND e.status = 'completed') AS cgpa,
    s.created_at, s.updated_at
FROM students s
JOIN users       u ON u.id = s.user_id
JOIN departments d ON d.id = s.department_id
"""

PROFILE_COLUMNS = ["date_of_birth", "gender", "blood_group", "address_line", "city", "postal_code",
                   "guardian_name", "guardian_phone", "guardian_relation"]


def list_students(conn: sqlite3.Connection, list_args: dict, department_id: int | None = None,
                  status: str | None = None) -> dict:
    """One page of students, with optional department and status filters."""
    conditions, params = [], []
    if department_id is not None:
        conditions.append("s.department_id = ?")
        params.append(department_id)
    if status:
        conditions.append("s.status = ?")
        params.append(status)
    return paginate(
        conn, STUDENT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["full_name", "student_code", "email"],
        sort_columns=["id", "full_name", "student_code", "department_code", "admission_date", "status", "cgpa"],
        default_sort="student_code",
    )


def get_student(conn: sqlite3.Connection, student_id: int) -> dict | None:
    """One student, with the 1:1 profile nested under "profile"."""
    student = fetch_one(conn, STUDENT_SELECT + " WHERE s.id = ?", (student_id,))
    if student is None:
        return None
    student["profile"] = fetch_one(conn, "SELECT * FROM student_profiles WHERE student_id = ?", (student_id,))
    return student


def insert_student(conn: sqlite3.Connection, user_id: int, data: dict) -> int:
    """Create the student row for an existing user account."""
    return execute(
        conn,
        """INSERT INTO students (user_id, department_id, student_code, first_name, last_name,
                                 admission_date, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, data["department_id"], data["student_code"], data["first_name"], data["last_name"],
         data["admission_date"], data.get("status", "active")),
    )


def insert_profile(conn: sqlite3.Connection, student_id: int, profile: dict) -> None:
    """Create the 1:1 profile. student_id is both its primary key and its foreign key."""
    columns = ["student_id"] + PROFILE_COLUMNS
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO student_profiles ({', '.join(columns)}) VALUES ({placeholders})",
        [student_id] + [profile.get(column) for column in PROFILE_COLUMNS],
    )


def update_student(conn: sqlite3.Connection, student_id: int, changes: dict) -> int:
    """Change some columns of a student."""
    return update_by_id(conn, "students", student_id, changes)


def update_profile(conn: sqlite3.Connection, student_id: int, changes: dict) -> int:
    """Change some profile columns (the key column is student_id, not id)."""
    return update_by_id(conn, "student_profiles", student_id, changes, id_column="student_id")


def get_transcript(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """Completed courses, oldest semester first (from the v_student_transcript view)."""
    return fetch_all(
        conn,
        """SELECT * FROM v_student_transcript
           WHERE student_id = ?
           ORDER BY semester_start, course_code""",
        (student_id,),
    )


def get_dues(conn: sqlite3.Connection, student_id: int) -> dict:
    """All invoices of the student, newest first, plus a total of what is still owed."""
    invoices = fetch_all(
        conn,
        """SELECT i.id, i.invoice_no, sem.code AS semester_code, i.total_amount, i.paid_amount,
                  i.total_amount - i.paid_amount AS due_amount, i.issued_at, i.due_date,
                  CASE WHEN i.paid_amount < i.total_amount AND i.due_date < date('now')
                       THEN 'overdue' ELSE i.status END AS status,
                  MAX(0, CAST(julianday(date('now')) - julianday(i.due_date) AS INTEGER)) AS days_overdue
           FROM invoices i
           JOIN semesters sem ON sem.id = i.semester_id
           WHERE i.student_id = ?
           ORDER BY sem.start_date DESC""",
        (student_id,),
    )
    for invoice in invoices:
        add_taka_fields(invoice, "total_amount", "paid_amount", "due_amount")
        if invoice["due_amount"] == 0:
            invoice["days_overdue"] = 0
    total_due = sum(invoice["due_amount"] for invoice in invoices)
    return add_taka_fields({"invoices": invoices, "total_due": total_due}, "total_due")


def get_attendance(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """Attendance summary per course (from the v_attendance_percentage view), newest semester first."""
    return fetch_all(
        conn,
        """SELECT v.enrollment_id, v.offering_id, sem.code AS semester_code, c.code AS course_code,
                  c.title, co.section, v.total_classes, v.present_count, v.attendance_percent,
                  (SELECT COUNT(*) FROM attendance a WHERE a.enrollment_id = v.enrollment_id
                                                       AND a.status = 'absent')  AS absent_count,
                  (SELECT COUNT(*) FROM attendance a WHERE a.enrollment_id = v.enrollment_id
                                                       AND a.status = 'late')    AS late_count,
                  (SELECT COUNT(*) FROM attendance a WHERE a.enrollment_id = v.enrollment_id
                                                       AND a.status = 'excused') AS excused_count
           FROM v_attendance_percentage v
           JOIN course_offerings co  ON co.id  = v.offering_id
           JOIN courses          c   ON c.id   = co.course_id
           JOIN semesters        sem ON sem.id = co.semester_id
           WHERE v.student_id = ?
           ORDER BY sem.start_date DESC, c.code""",
        (student_id,),
    )
