"""
Report services.

Service #10 from the spec lives here:
    refresh_department_performance()  - rebuild the mv_department_performance table

Plus the read-only report queries behind /api/reports/* and the
role-aware numbers behind /api/dashboard/stats.
"""

import sqlite3

from app.database import fetch_all, fetch_one, fetch_value, transaction
from app.schemas.common import add_taka_fields
from app.services.grading_service import calculate_cgpa

# ---------------------------------------------------------------------------
# #10 materialized-view refresh
# ---------------------------------------------------------------------------
# The query that calculates every (department, semester) row.
# A department's performance is measured by ITS OWN STUDENTS
# (students.department_id), over their completed enrollments.
REFRESH_SQL = """
INSERT INTO mv_department_performance
    (department_id, semester_id, avg_gpa, pass_rate, total_students, refreshed_at)
SELECT
    st.department_id,
    co.semester_id,
    ROUND(AVG(e.grade_point), 2)                                   AS avg_gpa,
    -- (grade_point >= 2.0) is 1 or 0, so its SUM counts the passes
    ROUND(100.0 * SUM(e.grade_point >= 2.0) / COUNT(*), 1)         AS pass_rate,
    COUNT(DISTINCT e.student_id)                                   AS total_students,
    datetime('now')                                                AS refreshed_at
FROM enrollments e
JOIN students         st ON st.id = e.student_id
JOIN course_offerings co ON co.id = e.offering_id
WHERE e.status = 'completed'
  AND e.grade_point IS NOT NULL
GROUP BY st.department_id, co.semester_id
"""


def refresh_department_performance(conn: sqlite3.Connection, actor_id: int | None = None) -> int:
    """
    SERVICE #10: recalculate the whole mv_department_performance table.

    We delete everything and insert fresh rows inside ONE transaction.
    Other connections therefore see either the old numbers or the new
    numbers, never a half-empty table (that is the "A" = Atomic in ACID).

    Returns:
        The number of rows now in the table.
    """
    with transaction(conn, actor_id):
        conn.execute("DELETE FROM mv_department_performance")
        conn.execute(REFRESH_SQL)
    return fetch_value(conn, "SELECT COUNT(*) FROM mv_department_performance")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
LETTER_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "F"]


def grade_distribution(conn: sqlite3.Connection, offering_id: int | None = None,
                       teacher_id: int | None = None) -> list[dict]:
    """
    Count of each letter grade (completed enrollments), for one offering, one
    teacher's offerings, or everything. Every letter is returned, even with
    count 0, so charts always show the full scale.
    """
    conditions, params = ["e.status = 'completed'"], []
    if offering_id is not None:
        conditions.append("e.offering_id = ?")
        params.append(offering_id)
    if teacher_id is not None:
        conditions.append("co.teacher_id = ?")
        params.append(teacher_id)
    rows = fetch_all(
        conn,
        f"""SELECT e.letter_grade, COUNT(*) AS count
            FROM enrollments e
            JOIN course_offerings co ON co.id = e.offering_id
            WHERE {' AND '.join(conditions)}
            GROUP BY e.letter_grade""",
        params,
    )
    counts = {row["letter_grade"]: row["count"] for row in rows}
    total = sum(counts.values()) or 1
    return [{"letter_grade": letter, "count": counts.get(letter, 0),
             "percent": round(100 * counts.get(letter, 0) / total, 1)} for letter in LETTER_ORDER]


def department_performance(conn: sqlite3.Connection) -> dict:
    """Read the pre-calculated mv_department_performance table (fast, but only as fresh as refreshed_at)."""
    rows = fetch_all(
        conn,
        """SELECT m.department_id, d.code AS department_code, d.name AS department_name,
                  m.semester_id, s.code AS semester_code, m.avg_gpa, m.pass_rate,
                  m.total_students, m.refreshed_at
           FROM mv_department_performance m
           JOIN departments d ON d.id = m.department_id
           JOIN semesters   s ON s.id = m.semester_id
           ORDER BY s.start_date, d.code""",
    )
    refreshed_at = fetch_value(conn, "SELECT MAX(refreshed_at) FROM mv_department_performance")
    return {"rows": rows, "refreshed_at": refreshed_at}


def collection_summary(conn: sqlite3.Connection, semester_id: int) -> dict:
    """Billed vs collected for one semester: totals, per payment method, and per department."""
    totals = fetch_one(
        conn,
        """SELECT COUNT(*) AS invoices,
                  COALESCE(SUM(total_amount), 0) AS billed,
                  COALESCE(SUM(paid_amount), 0)  AS collected,
                  COALESCE(SUM(total_amount - paid_amount), 0) AS outstanding,
                  SUM(paid_amount >= total_amount) AS paid_invoices,
                  SUM(paid_amount < total_amount AND due_date < date('now')) AS overdue_invoices
           FROM invoices WHERE semester_id = ?""",
        (semester_id,),
    )
    totals["collection_rate"] = round(100 * totals["collected"] / totals["billed"], 1) if totals["billed"] else 0
    add_taka_fields(totals, "billed", "collected", "outstanding")

    by_method = [
        add_taka_fields(row, "amount")
        for row in fetch_all(
            conn,
            """SELECT p.method, COUNT(*) AS payments, SUM(p.amount) AS amount
               FROM payments p JOIN invoices i ON i.id = p.invoice_id
               WHERE i.semester_id = ?
               GROUP BY p.method ORDER BY amount DESC""",
            (semester_id,),
        )
    ]
    by_department = [
        add_taka_fields(row, "billed", "collected", "outstanding")
        for row in fetch_all(
            conn,
            """SELECT d.code AS department_code, COUNT(*) AS invoices,
                      SUM(i.total_amount) AS billed, SUM(i.paid_amount) AS collected,
                      SUM(i.total_amount - i.paid_amount) AS outstanding
               FROM invoices i
               JOIN students s ON s.id = i.student_id
               JOIN departments d ON d.id = s.department_id
               WHERE i.semester_id = ?
               GROUP BY d.id ORDER BY d.code""",
            (semester_id,),
        )
    ]
    return {"semester_id": semester_id, "totals": totals, "by_method": by_method, "by_department": by_department}


def low_attendance(conn: sqlite3.Connection, threshold: float, semester_id: int,
                   teacher_id: int | None = None) -> list[dict]:
    """Enrollments of a semester whose attendance is below `threshold` percent, worst first."""
    conditions, params = ["co.semester_id = ?", "v.total_classes > 0", "v.attendance_percent < ?"], [semester_id, threshold]
    if teacher_id is not None:
        conditions.append("co.teacher_id = ?")
        params.append(teacher_id)
    return fetch_all(
        conn,
        f"""SELECT v.enrollment_id, s.id AS student_id, s.student_code,
                   s.first_name || ' ' || s.last_name AS student_name,
                   c.code AS course_code, co.section, co.id AS offering_id,
                   v.total_classes, v.present_count, v.attendance_percent
            FROM v_attendance_percentage v
            JOIN students         s  ON s.id  = v.student_id
            JOIN course_offerings co ON co.id = v.offering_id
            JOIN courses          c  ON c.id  = co.course_id
            WHERE {' AND '.join(conditions)}
            ORDER BY v.attendance_percent, s.student_code""",
        params,
    )


# ---------------------------------------------------------------------------
# Dashboard (one function per role, picked by dashboard_stats)
# ---------------------------------------------------------------------------
def card(label: str, value, value_format: str, icon: str, delta: str | None = None,
         delta_type: str = "muted") -> dict:
    """One stat card. value_format tells the frontend how to show the value: number/money/percent/gpa."""
    return {"label": label, "value": value, "format": value_format, "icon": icon,
            "delta": delta, "delta_type": delta_type}


def enrollment_trend(conn: sqlite3.Connection, teacher_id: int | None = None) -> dict:
    """Number of (non-dropped) enrollments per semester, oldest first."""
    extra = "AND co.teacher_id = ?" if teacher_id is not None else ""
    rows = fetch_all(
        conn,
        f"""SELECT s.code, COUNT(e.id) AS total
            FROM semesters s
            LEFT JOIN course_offerings co ON co.semester_id = s.id {extra}
            LEFT JOIN enrollments e ON e.offering_id = co.id AND e.status <> 'dropped'
            GROUP BY s.id ORDER BY s.start_date""",
        [teacher_id] if teacher_id is not None else [],
    )
    return {"title": "Enrollment trend", "labels": [r["code"] for r in rows], "values": [r["total"] for r in rows]}


def grade_chart(conn: sqlite3.Connection, **filters) -> dict:
    """Grade distribution shaped for a bar chart."""
    rows = grade_distribution(conn, **filters)
    return {"title": "Grade distribution", "labels": [r["letter_grade"] for r in rows],
            "values": [r["count"] for r in rows]}


def admin_dashboard(conn: sqlite3.Connection, semester: dict | None) -> dict:
    """University-wide numbers for the admin."""
    semester_id = semester["id"] if semester else None
    students = fetch_value(conn, "SELECT COUNT(*) FROM students WHERE status = 'active'")
    new_students = fetch_value(conn, "SELECT COUNT(*) FROM students WHERE admission_date >= date('now', '-30 days')")
    teachers = fetch_value(conn, "SELECT COUNT(*) FROM teachers WHERE status = 'active'")
    on_leave = fetch_value(conn, "SELECT COUNT(*) FROM teachers WHERE status = 'on_leave'")
    open_offerings = fetch_value(conn, "SELECT COUNT(*) FROM course_offerings WHERE semester_id = ? AND status = 'open'",
                                 (semester_id,))
    full_offerings = fetch_value(
        conn, "SELECT COUNT(*) FROM course_offerings WHERE semester_id = ? AND status = 'open' AND enrolled_count >= capacity",
        (semester_id,))
    money = fetch_one(conn, "SELECT COALESCE(SUM(total_amount), 0) AS billed, COALESCE(SUM(paid_amount), 0) AS paid "
                            "FROM invoices WHERE semester_id = ?", (semester_id,))
    rate = round(100 * money["paid"] / money["billed"], 1) if money["billed"] else 0
    return {
        "cards": [
            card("Active students", students, "number", "graduation-cap", f"+{new_students} admitted in the last 30 days", "success"),
            card("Active teachers", teachers, "number", "users", f"{on_leave} on leave", "muted"),
            card("Open offerings", open_offerings, "number", "book-open", f"{full_offerings} full", "danger" if full_offerings else "muted"),
            card("Fee collection", rate, "percent", "wallet", "of this semester's invoices", "success" if rate >= 75 else "danger"),
        ],
        "charts": {"trend": enrollment_trend(conn), "distribution": grade_chart(conn)},
    }


def teacher_dashboard(conn: sqlite3.Connection, user: dict, semester: dict | None) -> dict:
    """Numbers about the teacher's own classes."""
    semester_id = semester["id"] if semester else None
    teacher_id = user["teacher_id"]
    my = fetch_one(
        conn,
        """SELECT COUNT(*) AS offerings, COALESCE(SUM(enrolled_count), 0) AS students
           FROM course_offerings WHERE teacher_id = ? AND semester_id = ? AND status <> 'cancelled'""",
        (teacher_id, semester_id),
    )
    attendance = fetch_value(
        conn,
        """SELECT ROUND(AVG(v.attendance_percent), 1) FROM v_attendance_percentage v
           JOIN course_offerings co ON co.id = v.offering_id
           WHERE co.teacher_id = ? AND co.semester_id = ? AND v.total_classes > 0""",
        (teacher_id, semester_id),
    ) or 0
    low = len(low_attendance(conn, 75, semester_id, teacher_id)) if semester_id else 0
    # Marks still missing: (enrolled student x assessment already due) pairs without a result row
    missing_marks = fetch_value(
        conn,
        """SELECT COUNT(*)
           FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id
           JOIN assessments a ON a.offering_id = co.id
           LEFT JOIN assessment_results r ON r.assessment_id = a.id AND r.enrollment_id = e.id
           WHERE co.teacher_id = ? AND co.semester_id = ? AND e.status = 'enrolled'
             AND a.due_date < date('now') AND r.id IS NULL""",
        (teacher_id, semester_id),
    )
    return {
        "cards": [
            card("My offerings", my["offerings"], "number", "book-open", f"in {semester['code']}" if semester else None),
            card("My students", my["students"], "number", "users", "currently enrolled"),
            card("Avg attendance", attendance, "percent", "calendar-check",
                 f"{low} students below 75%", "danger" if low else "success"),
            card("Marks to enter", missing_marks, "number", "clipboard-check",
                 "for assessments already due", "danger" if missing_marks else "success"),
        ],
        "charts": {"trend": enrollment_trend(conn, teacher_id=teacher_id),
                   "distribution": grade_chart(conn, teacher_id=teacher_id)},
    }


def student_dashboard(conn: sqlite3.Connection, user: dict, semester: dict | None) -> dict:
    """Numbers about the student themself."""
    student_id = user["student_id"]
    semester_id = semester["id"] if semester else None
    cgpa = calculate_cgpa(conn, student_id)
    credits = fetch_value(
        conn,
        """SELECT COALESCE(SUM(c.credits), 0) FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id JOIN courses c ON c.id = co.course_id
           WHERE e.student_id = ? AND co.semester_id = ? AND e.status = 'enrolled'""",
        (student_id, semester_id),
    )
    attendance = fetch_value(
        conn,
        """SELECT ROUND(100.0 * SUM(v.present_count) / NULLIF(SUM(v.total_classes), 0), 1)
           FROM v_attendance_percentage v JOIN course_offerings co ON co.id = v.offering_id
           WHERE v.student_id = ? AND co.semester_id = ?""",
        (student_id, semester_id),
    ) or 0
    due = fetch_value(conn, "SELECT COALESCE(SUM(total_amount - paid_amount), 0) FROM invoices WHERE student_id = ?",
                      (student_id,))
    gpa_rows = fetch_all(
        conn,
        """SELECT s.code, ROUND(SUM(e.grade_point * c.credits) / SUM(c.credits), 2) AS gpa
           FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id
           JOIN courses c ON c.id = co.course_id
           JOIN semesters s ON s.id = co.semester_id
           WHERE e.student_id = ? AND e.status = 'completed'
           GROUP BY s.id ORDER BY s.start_date""",
        (student_id,),
    )
    grade_rows = fetch_all(
        conn,
        "SELECT letter_grade, COUNT(*) AS n FROM enrollments WHERE student_id = ? AND status = 'completed' GROUP BY letter_grade",
        (student_id,),
    )
    grade_counts = {r["letter_grade"]: r["n"] for r in grade_rows}
    return {
        "cards": [
            card("CGPA", cgpa["cgpa"], "gpa", "award", f"{cgpa['credits_completed']:g} credits completed", "success"),
            card("Current credits", credits, "number", "book-open", "max 21 per semester"),
            card("Attendance", attendance, "percent", "calendar-check",
                 "below 75% requirement" if attendance < 75 else "good standing",
                 "danger" if attendance < 75 else "success"),
            card("Amount due", due, "money", "wallet", "all invoices", "danger" if due else "success"),
        ],
        "charts": {
            "trend": {"title": "GPA per semester", "labels": [r["code"] for r in gpa_rows],
                      "values": [r["gpa"] for r in gpa_rows]},
            "distribution": {"title": "My grades", "labels": LETTER_ORDER,
                             "values": [grade_counts.get(letter, 0) for letter in LETTER_ORDER]},
        },
    }


def accountant_dashboard(conn: sqlite3.Connection, semester: dict | None) -> dict:
    """Money numbers for the accountant."""
    semester_id = semester["id"] if semester else None
    empty = {"billed": 0, "collected": 0, "outstanding": 0, "invoices": 0,
             "collection_rate": 0, "overdue_invoices": 0}
    summary = collection_summary(conn, semester_id)["totals"] if semester_id else empty
    trend = fetch_all(
        conn,
        """SELECT s.code, COALESCE(SUM(i.paid_amount), 0) AS collected
           FROM semesters s LEFT JOIN invoices i ON i.semester_id = s.id
           GROUP BY s.id ORDER BY s.start_date""",
    )
    statuses = fetch_all(
        conn,
        """SELECT CASE WHEN paid_amount < total_amount AND due_date < date('now') THEN 'overdue' ELSE status END AS status,
                  COUNT(*) AS n
           FROM invoices WHERE semester_id = ? GROUP BY 1""",
        (semester_id,),
    )
    status_counts = {r["status"]: r["n"] for r in statuses}
    status_order = ["paid", "partial", "unpaid", "overdue"]
    return {
        "cards": [
            card("Billed this semester", summary["billed"], "money", "file-text", f"{summary['invoices']} invoices"),
            card("Collected", summary["collected"], "money", "wallet",
                 f"{summary['collection_rate']}% collection rate", "success"),
            card("Outstanding", summary["outstanding"], "money", "alert-circle", "still to collect", "danger"),
            card("Overdue invoices", summary["overdue_invoices"] or 0, "number", "clock",
                 "past their due date", "danger"),
        ],
        "charts": {
            "trend": {"title": "Collections per semester (paisa)", "labels": [r["code"] for r in trend],
                      "values": [r["collected"] for r in trend], "money": True},
            "distribution": {"title": "Invoice status (this semester)", "labels": status_order,
                             "values": [status_counts.get(s, 0) for s in status_order]},
        },
    }


def dashboard_stats(conn: sqlite3.Connection, user: dict) -> dict:
    """Pick the right dashboard for the user's role."""
    semester = fetch_one(conn, "SELECT id, code, name FROM semesters WHERE is_active = 1")
    if user["role"] == "admin":
        data = admin_dashboard(conn, semester)
    elif user["role"] == "teacher":
        data = teacher_dashboard(conn, user, semester)
    elif user["role"] == "student":
        data = student_dashboard(conn, user, semester)
    else:
        data = accountant_dashboard(conn, semester)
    data["role"] = user["role"]
    data["semester"] = semester
    return data
