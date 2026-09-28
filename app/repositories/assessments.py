"""Raw SQL for assessments and assessment_results."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, fetch_value


def list_for_offering(conn: sqlite3.Connection, offering_id: int) -> list[dict]:
    """Assessments of an offering in due-date order, with how many students have marks."""
    return fetch_all(
        conn,
        """SELECT a.id, a.offering_id, a.title, a.type, a.max_marks, a.weight_percent, a.due_date,
                  (SELECT COUNT(*) FROM assessment_results r WHERE r.assessment_id = a.id) AS graded_count,
                  (SELECT ROUND(AVG(r.marks_obtained), 2) FROM assessment_results r
                    WHERE r.assessment_id = a.id)                                        AS average_marks
           FROM assessments a
           WHERE a.offering_id = ?
           ORDER BY a.due_date, a.id""",
        (offering_id,),
    )


def get_assessment(conn: sqlite3.Connection, assessment_id: int) -> dict | None:
    """One assessment."""
    return fetch_one(conn, "SELECT * FROM assessments WHERE id = ?", (assessment_id,))


def weight_total(conn: sqlite3.Connection, offering_id: int) -> float:
    """Sum of weight_percent of all assessments of an offering (should end at 100)."""
    return fetch_value(
        conn, "SELECT COALESCE(SUM(weight_percent), 0) FROM assessments WHERE offering_id = ?", (offering_id,)
    )


def insert_assessment(conn: sqlite3.Connection, data: dict) -> int:
    """Create an assessment and return its id."""
    return execute(
        conn,
        """INSERT INTO assessments (offering_id, title, type, max_marks, weight_percent, due_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["offering_id"], data["title"], data["type"], data["max_marks"],
         data["weight_percent"], data["due_date"]),
    )


def upsert_results(conn: sqlite3.Connection, assessment_id: int, results: list[dict], graded_by: int) -> int:
    """
    Save marks. New rows are inserted and existing ones updated (UPSERT on
    UNIQUE(assessment_id, enrollment_id)). trg_validate_marks_ins/_upd reject
    marks above max_marks on both paths.
    """
    conn.executemany(
        """INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, submitted_at, graded_by)
           VALUES (?, ?, ?, datetime('now'), ?)
           ON CONFLICT (assessment_id, enrollment_id) DO UPDATE SET
               marks_obtained = excluded.marks_obtained,
               graded_by      = excluded.graded_by""",
        [(assessment_id, r["enrollment_id"], r["marks_obtained"], graded_by) for r in results],
    )
    return len(results)


def get_gradebook(conn: sqlite3.Connection, offering_id: int) -> dict:
    """
    Everything the gradebook grid needs:
      assessments = the columns, students = the rows, marks = the cells.
    The weighted total uses the same formula as calculate_final_marks().
    """
    assessments = list_for_offering(conn, offering_id)
    students = fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, s.id AS student_id, s.student_code,
                  s.first_name || ' ' || s.last_name AS full_name,
                  e.status, e.total_marks, e.grade_point, e.letter_grade,
                  ROUND(COALESCE((SELECT SUM(r.marks_obtained / a.max_marks * a.weight_percent)
                                    FROM assessment_results r
                                    JOIN assessments a ON a.id = r.assessment_id
                                   WHERE r.enrollment_id = e.id), 0), 2) AS weighted_total
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           WHERE e.offering_id = ? AND e.status IN ('enrolled', 'completed')
           ORDER BY s.student_code""",
        (offering_id,),
    )
    rows = fetch_all(
        conn,
        """SELECT r.enrollment_id, r.assessment_id, r.marks_obtained
           FROM assessment_results r
           JOIN assessments a ON a.id = r.assessment_id
           WHERE a.offering_id = ?""",
        (offering_id,),
    )
    # marks[enrollment_id][assessment_id] = marks  (JSON keys become strings)
    marks: dict[int, dict[int, float]] = {}
    for row in rows:
        marks.setdefault(row["enrollment_id"], {})[row["assessment_id"]] = row["marks_obtained"]
    for student in students:
        student["marks"] = marks.get(student["enrollment_id"], {})
    return {
        "assessments": assessments,
        "students": students,
        "weight_total": sum(a["weight_percent"] for a in assessments),
    }
