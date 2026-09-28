"""
Enrollment services.

Services from the spec:
    #1 enroll_student(student_id, offering_id, actor_id)
    #2 drop_enrollment(enrollment_id, actor_id)

Plus helpers that run the same checks without writing (used by the
enrollment page to show "disabled + reason").

WHY "BEGIN IMMEDIATE" MATTERS HERE
    Enrolling is read-then-write: read "39 of 40 seats taken", then insert.
    With a normal (deferred) BEGIN, two students could both read 39/40 at the
    same time and both insert, giving 41/40. BEGIN IMMEDIATE takes the write
    lock BEFORE the reads, so the second request waits until the first one
    has committed. It then reads 40/40 and is rejected. tests/test_concurrency.py
    proves this. (The CHECK enrolled_count <= capacity is a last safety net.)
"""

import sqlite3

from app.database import execute, fetch_all, fetch_one, fetch_value, transaction
from app.errors import BusinessRuleError, not_found
from app.repositories.enrollments import get_enrollment
from app.services.grading_service import PASS_GRADE_POINT

MAX_CREDITS_PER_SEMESTER = 21

OFFERING_INFO_SQL = """
SELECT co.id, co.status, co.capacity, co.enrolled_count, co.course_id, co.semester_id,
       c.code AS course_code, c.title AS course_title, c.credits,
       sem.code AS semester_code, sem.registration_start, sem.registration_end,
       date('now') AS today
FROM course_offerings co
JOIN courses   c   ON c.id   = co.course_id
JOIN semesters sem ON sem.id = co.semester_id
WHERE co.id = ?
"""


def check_enrollment_rules(conn: sqlite3.Connection, student_id: int, offering_id: int) -> dict:
    """
    Run the 7 enrollment checks IN THE SPEC'S ORDER and stop at the first failure.

    Returns:
        Information about the offering (used by the caller).

    Raises:
        BusinessRuleError with a clear message, or 404 if the student/offering does not exist.
    """
    # 1. The student must be active
    student = fetch_one(conn, "SELECT id, status FROM students WHERE id = ?", (student_id,))
    if student is None:
        raise not_found("Student", student_id)
    if student["status"] != "active":
        raise BusinessRuleError(f"Student is not active (status: {student['status']})")

    offering = fetch_one(conn, OFFERING_INFO_SQL, (offering_id,))
    if offering is None:
        raise not_found("Offering", offering_id)

    # 2. The semester's registration window must be open today
    if not (offering["registration_start"] <= offering["today"] <= offering["registration_end"]):
        raise BusinessRuleError(
            f"Registration for {offering['semester_code']} is closed "
            f"(open from {offering['registration_start']} to {offering['registration_end']})"
        )

    # 3. The offering must be open
    if offering["status"] != "open":
        raise BusinessRuleError(f"This offering is not open for enrollment (status: {offering['status']})")

    # 4. Not already enrolled: neither in this offering nor in another section of the same course
    existing = fetch_one(
        conn,
        """SELECT co.section FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id
           WHERE e.student_id = ? AND co.course_id = ? AND co.semester_id = ? AND e.status = 'enrolled'""",
        (student_id, offering["course_id"], offering["semester_id"]),
    )
    if existing:
        raise BusinessRuleError(
            f"Already enrolled in {offering['course_code']} this semester (section {existing['section']})"
        )

    # 5. There must be a free seat
    if offering["enrolled_count"] >= offering["capacity"]:
        raise BusinessRuleError(f"This offering is full ({offering['enrolled_count']}/{offering['capacity']})")

    # 6. Every prerequisite must be PASSED: a completed enrollment with grade_point >= 2.0
    missing = fetch_all(
        conn,
        """SELECT p.code, p.title
           FROM course_prerequisites cp
           JOIN courses p ON p.id = cp.prerequisite_course_id
           WHERE cp.course_id = ?
             AND NOT EXISTS (
                 SELECT 1 FROM enrollments e
                 JOIN course_offerings co ON co.id = e.offering_id
                 WHERE e.student_id = ?
                   AND co.course_id = cp.prerequisite_course_id
                   AND e.status = 'completed'
                   AND e.grade_point >= ?)
           ORDER BY p.code""",
        (offering["course_id"], student_id, PASS_GRADE_POINT),
    )
    if missing:
        names = ", ".join(f"{row['code']} {row['title']}" for row in missing)
        raise BusinessRuleError(f"Missing prerequisite(s): {names}")

    # 7. The semester credit total must stay at or below 21
    current_credits = fetch_value(
        conn,
        """SELECT COALESCE(SUM(c.credits), 0)
           FROM enrollments e
           JOIN course_offerings co ON co.id = e.offering_id
           JOIN courses c ON c.id = co.course_id
           WHERE e.student_id = ? AND co.semester_id = ? AND e.status = 'enrolled'""",
        (student_id, offering["semester_id"]),
    )
    if current_credits + offering["credits"] > MAX_CREDITS_PER_SEMESTER:
        raise BusinessRuleError(
            f"Credit limit exceeded: {current_credits:g} + {offering['credits']:g} "
            f"> {MAX_CREDITS_PER_SEMESTER} credits"
        )

    return offering


def enroll_student(conn: sqlite3.Connection, student_id: int, offering_id: int, actor_id: int) -> dict:
    """
    SERVICE #1: enroll a student into an offering.

    If the student dropped this same offering earlier, that row is reused
    (UNIQUE(student_id, offering_id) allows only one row per pair).
    The trigger trg_enroll_count_* keeps enrolled_count correct either way.

    Returns:
        The enrollment row.
    """
    with transaction(conn, actor_id):          # BEGIN IMMEDIATE: take the write lock first
        check_enrollment_rules(conn, student_id, offering_id)

        dropped_id = fetch_value(
            conn,
            "SELECT id FROM enrollments WHERE student_id = ? AND offering_id = ? AND status = 'dropped'",
            (student_id, offering_id),
        )
        if dropped_id:
            conn.execute(
                """UPDATE enrollments
                   SET status = 'enrolled', dropped_at = NULL, enrolled_at = datetime('now')
                   WHERE id = ?""",
                (dropped_id,),
            )
            enrollment_id = dropped_id
        else:
            enrollment_id = execute(
                conn, "INSERT INTO enrollments (student_id, offering_id) VALUES (?, ?)", (student_id, offering_id)
            )
    return get_enrollment(conn, enrollment_id)


def drop_enrollment(conn: sqlite3.Connection, enrollment_id: int, actor_id: int) -> dict:
    """
    SERVICE #2: drop a course. Sets status = 'dropped' and dropped_at = now.
    (The CHECK "status <> 'dropped' OR dropped_at IS NOT NULL" demands the date.)
    """
    with transaction(conn, actor_id):
        status = fetch_value(conn, "SELECT status FROM enrollments WHERE id = ?", (enrollment_id,))
        if status is None:
            raise not_found("Enrollment", enrollment_id)
        if status != "enrolled":
            raise BusinessRuleError(f"Only an active enrollment can be dropped (current status: {status})")
        conn.execute(
            "UPDATE enrollments SET status = 'dropped', dropped_at = datetime('now') WHERE id = ?",
            (enrollment_id,),
        )
    return get_enrollment(conn, enrollment_id)


def check_eligibility(conn: sqlite3.Connection, student_id: int, offering_id: int) -> tuple[bool, str | None]:
    """Dry run of the 7 checks (read-only). Returns (True, None) or (False, reason)."""
    try:
        check_enrollment_rules(conn, student_id, offering_id)
    except BusinessRuleError as error:
        return False, error.message
    return True, None


def list_eligibility(conn: sqlite3.Connection, student_id: int, semester_id: int) -> list[dict]:
    """
    Every offering of a semester, marked with whether this student may enroll
    and, if not, why. Offerings the student is already in are flagged separately.
    """
    offerings = fetch_all(
        conn,
        """SELECT v.offering_id AS id, v.course_code, v.title, v.section, v.teacher_name, v.credits,
                  v.capacity, v.enrolled_count, v.fill_percent, v.status, v.department_id,
                  (SELECT d.code FROM departments d WHERE d.id = v.department_id) AS department_code,
                  (SELECT e.id FROM enrollments e WHERE e.offering_id = v.offering_id
                      AND e.student_id = ? AND e.status = 'enrolled') AS my_enrollment_id,
                  (SELECT group_concat(p.code, ', ') FROM course_prerequisites cp
                      JOIN courses p ON p.id = cp.prerequisite_course_id
                     WHERE cp.course_id = v.course_id) AS prerequisite_codes
           FROM v_offering_summary v
           WHERE v.semester_id = ? AND v.status <> 'cancelled'
           ORDER BY v.course_code, v.section""",
        (student_id, semester_id),
    )
    for offering in offerings:
        if offering["my_enrollment_id"]:
            offering["eligible"], offering["reason"] = False, "You are enrolled in this offering"
        else:
            offering["eligible"], offering["reason"] = check_eligibility(conn, student_id, offering["id"])
    return offerings
