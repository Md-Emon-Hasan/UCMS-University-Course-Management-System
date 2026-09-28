"""
Tiny helpers that insert test rows with sensible defaults.

Every function inserts ONE kind of row with plain SQL and returns the new id,
so a test can build exactly the situation it needs in a few lines:

    dept = make_department(conn, "CSE")
    teacher = make_teacher(conn, dept)
    course = make_course(conn, dept, credits=3)

The rows are written in autocommit mode (no BEGIN), so each INSERT is saved
at once. The triggers still fire as usual.

build_world() creates the standard small data set most tests start from.
"""

import itertools
import sqlite3
from datetime import date, timedelta

from app.database import execute, fetch_value
from app.security import create_access_token, hash_password

TEST_PASSWORD = "Password123!"
# bcrypt is slow on purpose (~0.2 s per hash), so hash the test password ONCE
PASSWORD_HASH = hash_password(TEST_PASSWORD)

# A counter that makes codes and emails unique: 1, 2, 3, ...
numbers = itertools.count(1)

# The 4 assessments every test offering gets: (type, max_marks, weight_percent).
# The weights add up to 100, as finalize_grade() requires.
DEFAULT_ASSESSMENTS = [("quiz", 20, 10), ("assignment", 20, 20), ("midterm", 30, 30), ("final", 40, 40)]


def day(offset: int) -> str:
    """Today + `offset` days as 'YYYY-MM-DD' (offset can be negative)."""
    return (date.today() + timedelta(days=offset)).isoformat()


def letters(n: int) -> str:
    """1 -> 'A', 2 -> 'B', ..., 27 -> 'AA'. Used for unique section names."""
    text = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        text = chr(ord("A") + remainder) + text
    return text


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
def make_user(conn: sqlite3.Connection, role: str, email: str | None = None, is_active: int = 1) -> int:
    """Insert a login account. The password is always TEST_PASSWORD."""
    email = email or f"{role}{next(numbers)}@test.edu"
    return execute(conn, "INSERT INTO users (email, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                   (email, PASSWORD_HASH, role, is_active))


def make_department(conn: sqlite3.Connection, code: str | None = None, name: str | None = None) -> int:
    """Insert a department (without a head teacher)."""
    code = code or f"D{letters(next(numbers))}"
    return execute(conn, "INSERT INTO departments (name, code) VALUES (?, ?)", (name or f"Department {code}", code))


def make_teacher(conn: sqlite3.Connection, department_id: int, email: str | None = None) -> dict:
    """Insert a user + teacher. Returns {"id": teacher id, "user_id": user id}."""
    user_id = make_user(conn, "teacher", email)
    n = next(numbers)
    teacher_id = execute(
        conn,
        """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name, designation, hired_at)
           VALUES (?, ?, ?, 'Test', ?, 'lecturer', '2020-01-01')""",
        (user_id, department_id, f"EMP{n:04d}", f"Teacher{n}"),
    )
    return {"id": teacher_id, "user_id": user_id}


def make_student(conn: sqlite3.Connection, department_id: int, email: str | None = None,
                 status: str = "active") -> dict:
    """Insert a user + student + profile. Returns {"id": student id, "user_id": user id}."""
    user_id = make_user(conn, "student", email)
    n = next(numbers)
    student_id = execute(
        conn,
        """INSERT INTO students (user_id, department_id, student_code, first_name, last_name, admission_date, status)
           VALUES (?, ?, ?, 'Test', ?, '2024-01-01', ?)""",
        (user_id, department_id, f"STU{n:05d}", f"Student{n}", status),
    )
    execute(
        conn,
        """INSERT INTO student_profiles (student_id, date_of_birth, gender, guardian_name, guardian_phone,
                                         guardian_relation)
           VALUES (?, '2004-05-06', 'female', 'Guardian', '01700000000', 'Mother')""",
        (student_id,),
    )
    return {"id": student_id, "user_id": user_id}


# ---------------------------------------------------------------------------
# Semesters, courses, offerings
# ---------------------------------------------------------------------------
# Dates relative to today for each kind of semester:
#   (start, end, registration_start, registration_end) as day offsets
SEMESTER_DATES = {
    "past":    (-200, -100, -210, -195),   # finished long ago, registration closed
    "current": (-10, 100, -5, 10),         # running now, registration OPEN today
    "future":  (40, 150, 20, 30),          # registration has not started yet
}


def make_semester(conn: sqlite3.Connection, when: str = "current", active: bool = False) -> int:
    """Insert a semester. `when` is 'past', 'current' or 'future' (see SEMESTER_DATES)."""
    start, end, reg_start, reg_end = SEMESTER_DATES[when]
    n = next(numbers)
    return execute(
        conn,
        """INSERT INTO semesters (name, code, start_date, end_date, registration_start, registration_end, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (f"Semester {n}", f"SEM{n % 100:02d}", day(start), day(end), day(reg_start), day(reg_end), int(active)),
    )


def make_course(conn: sqlite3.Connection, department_id: int, credits: float = 3, level: int = 1,
                code: str | None = None) -> int:
    """Insert a course into the catalogue."""
    code = code or f"TST{next(numbers):03d}"
    return execute(
        conn, "INSERT INTO courses (department_id, code, title, credits, level) VALUES (?, ?, ?, ?, ?)",
        (department_id, code, f"Course {code}", credits, level),
    )


def add_prerequisite(conn: sqlite3.Connection, course_id: int, prerequisite_course_id: int) -> int:
    """"course_id requires prerequisite_course_id"."""
    return execute(conn, "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (?, ?)",
                   (course_id, prerequisite_course_id))


def make_offering(conn: sqlite3.Connection, course_id: int, semester_id: int, teacher_id: int,
                  capacity: int = 30, status: str = "open", section: str | None = None) -> int:
    """Insert a course offering. A unique section name is chosen if none is given."""
    return execute(
        conn,
        """INSERT INTO course_offerings (course_id, semester_id, teacher_id, section, capacity, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (course_id, semester_id, teacher_id, section or letters(next(numbers)), capacity, status),
    )


def make_assessments(conn: sqlite3.Connection, offering_id: int,
                     plan: list[tuple[str, float, float]] = DEFAULT_ASSESSMENTS) -> list[int]:
    """Insert the assessments of an offering. Returns their ids in the same order as `plan`."""
    return [
        execute(
            conn,
            """INSERT INTO assessments (offering_id, title, type, max_marks, weight_percent, due_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (offering_id, kind.title(), kind, max_marks, weight, day(30)),
        )
        for kind, max_marks, weight in plan
    ]


def make_room(conn: sqlite3.Connection, capacity: int = 60, room_type: str = "lecture") -> int:
    """Insert a room with a unique number."""
    return execute(conn, "INSERT INTO rooms (building, room_number, capacity, room_type) VALUES (?, ?, ?, ?)",
                   ("Test Building", f"R{next(numbers)}", capacity, room_type))


def make_schedule(conn: sqlite3.Connection, offering_id: int, room_id: int, day_of_week: int = 1,
                  start: str = "09:00", end: str = "10:30") -> int:
    """Insert one weekly class slot (the conflict triggers check it)."""
    return execute(
        conn,
        "INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        (offering_id, room_id, day_of_week, start, end),
    )


# ---------------------------------------------------------------------------
# Enrollments and marks
# ---------------------------------------------------------------------------
def make_enrollment(conn: sqlite3.Connection, student_id: int, offering_id: int, status: str = "enrolled",
                    grade_point: float | None = None) -> int:
    """
    Insert an enrollment directly (skipping the service rules).
    A 'dropped' row gets a dropped_at date, because a CHECK demands it.
    """
    dropped_at = "2025-01-01 10:00:00" if status == "dropped" else None
    return execute(
        conn,
        "INSERT INTO enrollments (student_id, offering_id, status, grade_point, dropped_at) VALUES (?, ?, ?, ?, ?)",
        (student_id, offering_id, status, grade_point, dropped_at),
    )


def make_passed_course(conn: sqlite3.Connection, student_id: int, course_id: int, semester_id: int,
                       teacher_id: int, grade_point: float) -> int:
    """Give a student a COMPLETED enrollment in a course (a new offering in `semester_id`)."""
    offering_id = make_offering(conn, course_id, semester_id, teacher_id, status="closed")
    return make_enrollment(conn, student_id, offering_id, status="completed", grade_point=grade_point)


def make_result(conn: sqlite3.Connection, assessment_id: int, enrollment_id: int, marks: float,
                graded_by: int) -> int:
    """Insert the marks of one enrollment in one assessment."""
    return execute(
        conn,
        "INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, graded_by) VALUES (?, ?, ?, ?)",
        (assessment_id, enrollment_id, marks, graded_by),
    )


# ---------------------------------------------------------------------------
# Money (all amounts are INTEGER paisa)
# ---------------------------------------------------------------------------
def make_fee(conn: sqlite3.Connection, semester_id: int, fee_type: str, amount_paisa: int,
             department_id: int | None = None) -> int:
    """Insert a fee structure row. department_id None = the global row."""
    return execute(
        conn, "INSERT INTO fee_structures (semester_id, department_id, fee_type, amount) VALUES (?, ?, ?, ?)",
        (semester_id, department_id, fee_type, amount_paisa),
    )


def make_invoice(conn: sqlite3.Connection, student_id: int, semester_id: int, total_paisa: int) -> int:
    """Insert an unpaid invoice (no items), due in 30 days."""
    return execute(
        conn,
        """INSERT INTO invoices (student_id, semester_id, invoice_no, total_amount, issued_at, due_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (student_id, semester_id, f"INV-TEST-{next(numbers)}", total_paisa, day(0), day(30)),
    )


def make_payment(conn: sqlite3.Connection, invoice_id: int, amount_paisa: int, received_by: int,
                 method: str = "cash", transaction_ref: str | None = None) -> int:
    """Insert a payment directly (the invoice trigger updates paid_amount and status)."""
    return execute(
        conn,
        "INSERT INTO payments (invoice_id, amount, method, transaction_ref, received_by) VALUES (?, ?, ?, ?, ?)",
        (invoice_id, amount_paisa, method, transaction_ref, received_by),
    )


# ---------------------------------------------------------------------------
# Small read helpers used by many tests
# ---------------------------------------------------------------------------
def count(conn: sqlite3.Connection, table: str, where: str = "1 = 1", params: tuple = ()) -> int:
    """SELECT COUNT(*) FROM <table> WHERE <where>. Table names come from the tests, never from users."""
    return fetch_value(conn, f"SELECT COUNT(*) FROM {table} WHERE {where}", params)


def enrolled_count(conn: sqlite3.Connection, offering_id: int) -> int:
    """The stored counter course_offerings.enrolled_count."""
    return fetch_value(conn, "SELECT enrolled_count FROM course_offerings WHERE id = ?", (offering_id,))


def auth_headers(user_id: int, role: str) -> dict:
    """HTTP headers with a valid JWT for this user (no login request needed)."""
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


# ---------------------------------------------------------------------------
# The standard small data set
# ---------------------------------------------------------------------------
def build_world(conn: sqlite3.Connection) -> dict:
    """
    Create the rows most tests need and return their ids in a dict:

        admin, accountant             one user each
        CSE, EEE                      two departments
        teacher (CSE), other_teacher (EEE)
        student, other_student        both in CSE, both active
        past_semester, semester       'semester' is ACTIVE with registration open today
        course (CSE, 3 credits) -> offering (capacity 30, taught by teacher, 4 assessments = 100%)
        room                          capacity 60

    The dict can be passed straight to conn.execute() as named parameters:
        conn.execute("SELECT * FROM students WHERE id = :student_id", world)
    """
    world: dict = {}
    world["admin_user_id"] = make_user(conn, "admin", "admin@test.edu")
    world["accountant_user_id"] = make_user(conn, "accountant", "accountant@test.edu")
    world["cse_id"] = make_department(conn, "CSE", "Computer Science")
    world["eee_id"] = make_department(conn, "EEE", "Electrical Engineering")

    teacher = make_teacher(conn, world["cse_id"], "teacher@test.edu")
    other_teacher = make_teacher(conn, world["eee_id"], "teacher2@test.edu")
    world["teacher_id"], world["teacher_user_id"] = teacher["id"], teacher["user_id"]
    world["other_teacher_id"], world["other_teacher_user_id"] = other_teacher["id"], other_teacher["user_id"]

    student = make_student(conn, world["cse_id"], "student@test.edu")
    other_student = make_student(conn, world["cse_id"], "student2@test.edu")
    world["student_id"], world["student_user_id"] = student["id"], student["user_id"]
    world["other_student_id"], world["other_student_user_id"] = other_student["id"], other_student["user_id"]

    world["past_semester_id"] = make_semester(conn, "past")
    world["semester_id"] = make_semester(conn, "current", active=True)
    world["course_id"] = make_course(conn, world["cse_id"], credits=3)
    world["offering_id"] = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"],
                                         capacity=30, section="A")
    world["assessment_ids"] = make_assessments(conn, world["offering_id"])
    world["room_id"] = make_room(conn, capacity=60)
    return world
