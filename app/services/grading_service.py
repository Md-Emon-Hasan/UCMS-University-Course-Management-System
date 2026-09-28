"""
Grading services.

Services from the spec:
    #4 calculate_final_marks(enrollment_id)
    #5 marks_to_gpa(marks)
    #6 finalize_grade(enrollment_id, actor_id)
    #7 calculate_cgpa(student_id)

#4, #5 and #7 only READ, so they do not open their own transaction. A single
SELECT is always consistent on its own, and they are also called from inside
other services' transactions (SQLite cannot nest BEGIN). #6 writes, so it runs
in BEGIN IMMEDIATE ... COMMIT.
"""

import sqlite3

from app.database import fetch_one, fetch_value, transaction
from app.errors import BusinessRuleError, not_found

# The university grading scale, from the highest band to the lowest.
# Each entry: (minimum marks, grade point, letter grade)
GRADE_SCALE: list[tuple[float, float, str]] = [
    (80, 4.00, "A+"),
    (75, 3.75, "A"),
    (70, 3.50, "A-"),
    (65, 3.25, "B+"),
    (60, 3.00, "B"),
    (55, 2.75, "B-"),
    (50, 2.50, "C+"),
    (45, 2.25, "C"),
    (40, 2.00, "D"),
    (0, 0.00, "F"),
]

# A course counts as "passed" (for example as a prerequisite) at this grade point or above.
PASS_GRADE_POINT = 2.0


def marks_to_gpa(marks: float) -> tuple[float, str]:
    """
    SERVICE #5: convert final marks into a grade point and a letter grade.

    The spec's bands are written with whole numbers (75-79 -> A). Marks can
    have decimals (79.6), so each band starts at its minimum: 79.6 is below 80,
    so it is an A.

    Args:
        marks: final weighted marks, between 0 and 100.

    Returns:
        (grade_point, letter_grade), for example (3.75, "A").

    Raises:
        ValueError: if marks is outside 0-100.
    """
    if marks < 0 or marks > 100:
        raise ValueError(f"marks must be between 0 and 100, got {marks}")

    for minimum, grade_point, letter in GRADE_SCALE:
        if marks >= minimum:
            return grade_point, letter

    # Not reachable: the last band starts at 0
    return 0.00, "F"


# SUM(marks_obtained / max_marks * weight_percent) over ALL assessments of the
# enrollment's offering. LEFT JOIN: a missing result counts as 0 marks.
FINAL_MARKS_SQL = """
SELECT COALESCE(SUM(COALESCE(r.marks_obtained, 0) / a.max_marks * a.weight_percent), 0)
FROM assessments a
LEFT JOIN assessment_results r ON r.assessment_id = a.id AND r.enrollment_id = :enrollment_id
WHERE a.offering_id = (SELECT offering_id FROM enrollments WHERE id = :enrollment_id)
"""


def calculate_final_marks(conn: sqlite3.Connection, enrollment_id: int) -> float:
    """
    SERVICE #4: the weighted final marks (0-100) of one enrollment.

    Example: quiz 16/20 with weight 10 gives 16 / 20 * 10 = 8.0 points.
    """
    total = fetch_value(conn, FINAL_MARKS_SQL, {"enrollment_id": enrollment_id})
    return round(min(100.0, max(0.0, total)), 2)


def finalize_inside_transaction(conn: sqlite3.Connection, enrollment_id: int) -> dict:
    """
    The work of finalize_grade WITHOUT its own transaction, so close_semester()
    can finalize many enrollments inside ONE transaction.
    """
    enrollment = fetch_one(conn, "SELECT id, offering_id, status FROM enrollments WHERE id = ?", (enrollment_id,))
    if enrollment is None:
        raise not_found("Enrollment", enrollment_id)
    if enrollment["status"] != "enrolled":
        raise BusinessRuleError(f"Only an active enrollment can be graded (current status: {enrollment['status']})")

    weight = fetch_value(
        conn, "SELECT COALESCE(SUM(weight_percent), 0) FROM assessments WHERE offering_id = ?",
        (enrollment["offering_id"],),
    )
    if abs(weight - 100) > 0.001:
        raise BusinessRuleError(
            f"Assessment weights of this offering add up to {weight:g}%. "
            "They must add up to exactly 100% before grades can be finalized."
        )

    # Step 4 -> step 5 -> update the enrollment
    total = calculate_final_marks(conn, enrollment_id)
    grade_point, letter = marks_to_gpa(total)
    conn.execute(
        """UPDATE enrollments
           SET total_marks = ?, grade_point = ?, letter_grade = ?, status = 'completed'
           WHERE id = ?""",
        (total, grade_point, letter, enrollment_id),
    )
    return {"enrollment_id": enrollment_id, "total_marks": total, "grade_point": grade_point,
            "letter_grade": letter, "status": "completed"}


def finalize_grade(conn: sqlite3.Connection, enrollment_id: int, actor_id: int) -> dict:
    """
    SERVICE #6: calculate_final_marks -> marks_to_gpa -> save the grade and
    set status = 'completed'. Everything happens in one transaction.
    """
    with transaction(conn, actor_id):
        return finalize_inside_transaction(conn, enrollment_id)


def calculate_cgpa(conn: sqlite3.Connection, student_id: int) -> dict:
    """
    SERVICE #7: credit-weighted average grade point over completed enrollments.

        CGPA = SUM(grade_point * credits) / SUM(credits)

    Returns:
        {"cgpa": 3.44 or None, "credits_completed": 21.0, "courses_completed": 7}
    """
    row = fetch_one(
        conn,
        """SELECT SUM(e.grade_point * c.credits) AS points, SUM(c.credits) AS credits, COUNT(*) AS courses
           FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id
           JOIN courses c ON c.id = co.course_id
           WHERE e.student_id = ? AND e.status = 'completed' AND e.grade_point IS NOT NULL""",
        (student_id,),
    )
    if not row or not row["credits"]:
        return {"cgpa": None, "credits_completed": 0, "courses_completed": 0}
    return {
        "cgpa": round(row["points"] / row["credits"], 2),
        "credits_completed": row["credits"],
        "courses_completed": row["courses"],
    }
