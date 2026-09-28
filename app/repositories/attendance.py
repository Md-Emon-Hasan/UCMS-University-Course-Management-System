"""Raw SQL for attendance."""

import sqlite3

from app.database import fetch_all


def get_roster_for_date(conn: sqlite3.Connection, offering_id: int, class_date: str) -> list[dict]:
    """
    Enrolled students of an offering, with their attendance on one date
    (status is NULL if not recorded yet). The date condition sits in the
    LEFT JOIN's ON clause so that students without a record are kept.
    """
    return fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, s.id AS student_id, s.student_code,
                  s.first_name || ' ' || s.last_name AS full_name,
                  e.status AS enrollment_status,     -- only 'enrolled' rows can still be changed
                  a.status, a.remarks
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           LEFT JOIN attendance a ON a.enrollment_id = e.id AND a.class_date = ?
           WHERE e.offering_id = ? AND e.status IN ('enrolled', 'completed')
           ORDER BY s.student_code""",
        (class_date, offering_id),
    )


def upsert_attendance(conn: sqlite3.Connection, class_date: str, records: list[dict], recorded_by: int) -> int:
    """
    Save attendance for one date. Existing rows are updated, new ones inserted.

    DB LESSON: "UPSERT" = INSERT ... ON CONFLICT (...) DO UPDATE.
    UNIQUE(enrollment_id, class_date) is the conflict target: saving the same
    day twice updates the row instead of failing. `excluded` is the row we
    tried to insert.
    """
    conn.executemany(
        """INSERT INTO attendance (enrollment_id, class_date, status, remarks, recorded_by)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (enrollment_id, class_date) DO UPDATE SET
               status      = excluded.status,
               remarks     = excluded.remarks,
               recorded_by = excluded.recorded_by""",
        [(r["enrollment_id"], class_date, r["status"], r.get("remarks"), recorded_by) for r in records],
    )
    return len(records)


def get_attendance_report(conn: sqlite3.Connection, offering_id: int) -> dict:
    """Per-student totals for one offering, plus the list of class dates recorded so far."""
    students = fetch_all(
        conn,
        """SELECT v.enrollment_id, s.student_code, s.first_name || ' ' || s.last_name AS full_name,
                  v.total_classes, v.present_count, v.attendance_percent,
                  SUM(a.status = 'present') AS present_only,
                  SUM(a.status = 'late')    AS late_count,
                  SUM(a.status = 'absent')  AS absent_count,
                  SUM(a.status = 'excused') AS excused_count
           FROM v_attendance_percentage v
           JOIN students s ON s.id = v.student_id
           LEFT JOIN attendance a ON a.enrollment_id = v.enrollment_id
           WHERE v.offering_id = ?
           GROUP BY v.enrollment_id
           ORDER BY v.attendance_percent, s.student_code""",
        (offering_id,),
    )
    dates = fetch_all(
        conn,
        """SELECT a.class_date, COUNT(*) AS recorded,
                  SUM(a.status IN ('present', 'late')) AS attended
           FROM attendance a
           JOIN enrollments e ON e.id = a.enrollment_id
           WHERE e.offering_id = ?
           GROUP BY a.class_date
           ORDER BY a.class_date""",
        (offering_id,),
    )
    return {"students": students, "dates": dates}
