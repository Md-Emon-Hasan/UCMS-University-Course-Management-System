"""
Constraint tests: the DATABASE itself must refuse bad data.

The API validates input too, but constraints are the last line of defence:
they also protect against bugs, scripts and manual SQL. Each case below is
one bad statement that SQLite must reject with sqlite3.IntegrityError.

The cases are a table (CASES), and one test function runs them all through
pytest.mark.parametrize. The SQL uses named parameters like :student_id,
filled from the `ids` fixture.

After the table come the tests for foreign-key ACTIONS (CASCADE, RESTRICT,
SET NULL) and for things that must still be ALLOWED.
"""

import sqlite3

import pytest

from app.database import fetch_all, fetch_value
from scripts.init_db import count_core_tables, list_tables
from tests.factory import (add_prerequisite, count, day, make_course, make_enrollment, make_fee, make_invoice,
                           make_payment, make_result, make_schedule, make_semester)

MISSING = 9999   # an id that does not exist in any table


@pytest.fixture
def ids(conn, world) -> dict:
    """
    The world plus one row in most remaining tables, so every UNIQUE rule
    has something to collide with.
    """
    ids = dict(world)
    ids["enrollment_id"] = make_enrollment(conn, world["student_id"], world["offering_id"])
    ids["assessment_id"] = world["assessment_ids"][0]
    make_result(conn, ids["assessment_id"], ids["enrollment_id"], 15, world["teacher_user_id"])
    ids["class_date"] = day(-1)
    conn.execute(
        "INSERT INTO attendance (enrollment_id, class_date, status, recorded_by) VALUES (?, ?, 'present', ?)",
        (ids["enrollment_id"], ids["class_date"], world["teacher_user_id"]),
    )
    ids["course2_id"] = make_course(conn, world["cse_id"], level=2)
    add_prerequisite(conn, ids["course2_id"], world["course_id"])
    make_fee(conn, world["semester_id"], "tuition", 5_000_000)                   # global row
    make_fee(conn, world["semester_id"], "lab", 300_000, world["cse_id"])        # CSE-only row
    ids["invoice_id"] = make_invoice(conn, world["student_id"], world["semester_id"], 5_300_000)
    make_payment(conn, ids["invoice_id"], 100_000, world["accountant_user_id"], "bkash", "REF-1")
    make_schedule(conn, world["offering_id"], world["room_id"])
    ids["missing"] = MISSING
    return ids


# (what is tested, bad SQL, a word that must appear in SQLite's error message)
CASES = [
    # ---- users
    ("users.email is UNIQUE",
     "INSERT INTO users (email, password_hash, role) VALUES ('admin@test.edu', 'x', 'admin')", "UNIQUE"),
    ("users.email UNIQUE ignores upper/lower case (COLLATE NOCASE)",
     "INSERT INTO users (email, password_hash, role) VALUES ('ADMIN@Test.EDU', 'x', 'admin')", "UNIQUE"),
    ("users.email is NOT NULL",
     "INSERT INTO users (email, password_hash, role) VALUES (NULL, 'x', 'admin')", "NOT NULL"),
    ("users.role must be one of the 4 roles",
     "INSERT INTO users (email, password_hash, role) VALUES ('new@test.edu', 'x', 'superuser')", "CHECK"),
    ("users.is_active is 0 or 1",
     "INSERT INTO users (email, password_hash, role, is_active) VALUES ('new@test.edu', 'x', 'admin', 2)", "CHECK"),

    # ---- departments
    ("departments.name is UNIQUE",
     "INSERT INTO departments (name, code) VALUES ('Computer Science', 'CS')", "UNIQUE"),
    ("departments.code is UNIQUE",
     "INSERT INTO departments (name, code) VALUES ('Something New', 'CSE')", "UNIQUE"),
    ("departments.head_teacher_id must be a real teacher (circular FK)",
     "UPDATE departments SET head_teacher_id = :missing WHERE id = :cse_id", "FOREIGN KEY"),

    # ---- teachers
    ("teachers.user_id is UNIQUE (one teacher per user, 1:1)",
     """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name, designation, hired_at)
        VALUES (:teacher_user_id, :cse_id, 'NEW01', 'A', 'B', 'lecturer', '2020-01-01')""", "UNIQUE"),
    ("teachers.department_id must exist",
     """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name, designation, hired_at)
        VALUES (:admin_user_id, :missing, 'NEW01', 'A', 'B', 'lecturer', '2020-01-01')""", "FOREIGN KEY"),
    ("teachers.employee_code is UNIQUE",
     """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name, designation, hired_at)
        VALUES (:admin_user_id, :cse_id, (SELECT employee_code FROM teachers WHERE id = :teacher_id),
                'A', 'B', 'lecturer', '2020-01-01')""", "UNIQUE"),
    ("teachers.designation must be a known rank",
     "UPDATE teachers SET designation = 'dean' WHERE id = :teacher_id", "CHECK"),
    ("teachers.status must be active / on_leave / resigned",
     "UPDATE teachers SET status = 'fired' WHERE id = :teacher_id", "CHECK"),

    # ---- students and profiles
    ("students.user_id is UNIQUE (1:1)",
     """INSERT INTO students (user_id, department_id, student_code, first_name, last_name, admission_date)
        VALUES (:student_user_id, :cse_id, 'NEW0001', 'A', 'B', '2024-01-01')""", "UNIQUE"),
    ("students.department_id must exist",
     """INSERT INTO students (user_id, department_id, student_code, first_name, last_name, admission_date)
        VALUES (:admin_user_id, :missing, 'NEW0001', 'A', 'B', '2024-01-01')""", "FOREIGN KEY"),
    ("students.student_code is UNIQUE",
     """INSERT INTO students (user_id, department_id, student_code, first_name, last_name, admission_date)
        VALUES (:admin_user_id, :cse_id, (SELECT student_code FROM students WHERE id = :student_id),
                'A', 'B', '2024-01-01')""", "UNIQUE"),
    ("students.status must be a known status",
     "UPDATE students SET status = 'expelled' WHERE id = :student_id", "CHECK"),
    ("student_profiles: only ONE profile per student (the PK is also the FK)",
     """INSERT INTO student_profiles (student_id, date_of_birth, gender, guardian_name, guardian_phone,
                                      guardian_relation)
        VALUES (:student_id, '2004-01-01', 'male', 'G', '0170000000', 'Father')""", "UNIQUE"),
    ("student_profiles.student_id must be a real student",
     """INSERT INTO student_profiles (student_id, date_of_birth, gender, guardian_name, guardian_phone,
                                      guardian_relation)
        VALUES (:missing, '2004-01-01', 'male', 'G', '0170000000', 'Father')""", "FOREIGN KEY"),
    ("student_profiles.gender must be male / female / other",
     "UPDATE student_profiles SET gender = 'unknown' WHERE student_id = :student_id", "CHECK"),

    # ---- semesters
    ("semesters.code is UNIQUE",
     """INSERT INTO semesters (name, code, start_date, end_date, registration_start, registration_end)
        VALUES ('X', (SELECT code FROM semesters WHERE id = :semester_id),
                '2030-01-01', '2030-05-01', '2029-12-01', '2029-12-15')""", "UNIQUE"),
    ("semesters: end_date must be after start_date",
     """INSERT INTO semesters (name, code, start_date, end_date, registration_start, registration_end)
        VALUES ('X', 'BAD01', '2030-05-01', '2030-01-01', '2029-12-01', '2029-12-15')""", "CHECK"),
    ("semesters: registration_end must be after registration_start",
     """INSERT INTO semesters (name, code, start_date, end_date, registration_start, registration_end)
        VALUES ('X', 'BAD01', '2030-01-01', '2030-05-01', '2029-12-15', '2029-12-01')""", "CHECK"),
    ("semesters.is_active is 0 or 1",
     "UPDATE semesters SET is_active = 5 WHERE id = :past_semester_id", "CHECK"),
    ("only ONE semester may be active (partial unique index)",
     "UPDATE semesters SET is_active = 1 WHERE id = :past_semester_id", "UNIQUE"),

    # ---- courses and prerequisites
    ("courses.code is UNIQUE",
     """INSERT INTO courses (department_id, code, title, credits, level)
        VALUES (:cse_id, (SELECT code FROM courses WHERE id = :course_id), 'X', 3, 1)""", "UNIQUE"),
    ("courses.department_id must exist",
     "INSERT INTO courses (department_id, code, title, credits, level) VALUES (:missing, 'NEW101', 'X', 3, 1)",
     "FOREIGN KEY"),
    ("courses.credits must be > 0",
     "UPDATE courses SET credits = 0 WHERE id = :course_id", "CHECK"),
    ("courses.credits must be <= 6",
     "UPDATE courses SET credits = 6.5 WHERE id = :course_id", "CHECK"),
    ("courses.level must be 1-4 (not 0)",
     "UPDATE courses SET level = 0 WHERE id = :course_id", "CHECK"),
    ("courses.level must be 1-4 (not 5)",
     "UPDATE courses SET level = 5 WHERE id = :course_id", "CHECK"),
    ("a course cannot be its own prerequisite",
     "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (:course_id, :course_id)",
     "CHECK"),
    ("the same prerequisite pair cannot be added twice",
     "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (:course2_id, :course_id)",
     "UNIQUE"),
    ("a prerequisite must be a real course",
     "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (:course_id, :missing)",
     "FOREIGN KEY"),

    # ---- rooms
    ("(building, room_number) is UNIQUE",
     """INSERT INTO rooms (building, room_number, capacity, room_type)
        SELECT building, room_number, 10, 'lab' FROM rooms WHERE id = :room_id""", "UNIQUE"),
    ("rooms.capacity must be > 0",
     "UPDATE rooms SET capacity = 0 WHERE id = :room_id", "CHECK"),
    ("rooms.room_type must be lecture / lab / seminar",
     "UPDATE rooms SET room_type = 'kitchen' WHERE id = :room_id", "CHECK"),

    # ---- course offerings
    ("(course, semester, section) is UNIQUE",
     """INSERT INTO course_offerings (course_id, semester_id, teacher_id, section, capacity)
        VALUES (:course_id, :semester_id, :teacher_id, 'A', 10)""", "UNIQUE"),
    ("course_offerings.teacher_id must exist",
     """INSERT INTO course_offerings (course_id, semester_id, teacher_id, section, capacity)
        VALUES (:course_id, :semester_id, :missing, 'Z', 10)""", "FOREIGN KEY"),
    ("course_offerings.capacity must be > 0",
     "UPDATE course_offerings SET capacity = 0 WHERE id = :offering_id", "CHECK"),
    ("enrolled_count can never go above capacity",
     "UPDATE course_offerings SET enrolled_count = capacity + 1 WHERE id = :offering_id", "CHECK"),
    ("enrolled_count can never be negative",
     "UPDATE course_offerings SET enrolled_count = -1 WHERE id = :offering_id", "CHECK"),
    ("course_offerings.status must be open / closed / cancelled",
     "UPDATE course_offerings SET status = 'full' WHERE id = :offering_id", "CHECK"),

    # ---- class schedules
    ("class_schedules.day_of_week must be 0-6",
     """INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time)
        VALUES (:offering_id, :room_id, 7, '14:00', '15:00')""", "CHECK"),
    ("class_schedules: end_time must be after start_time",
     """INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time)
        VALUES (:offering_id, :room_id, 3, '15:00', '14:00')""", "CHECK"),
    ("class_schedules.room_id must exist",
     """INSERT INTO class_schedules (offering_id, room_id, day_of_week, start_time, end_time)
        VALUES (:offering_id, :missing, 3, '14:00', '15:00')""", "FOREIGN KEY"),

    # ---- enrollments
    ("(student, offering) is UNIQUE",
     "INSERT INTO enrollments (student_id, offering_id) VALUES (:student_id, :offering_id)", "UNIQUE"),
    ("enrollments.student_id must exist",
     "INSERT INTO enrollments (student_id, offering_id) VALUES (:missing, :offering_id)", "FOREIGN KEY"),
    ("enrollments.status must be enrolled / dropped / completed",
     "UPDATE enrollments SET status = 'waitlisted' WHERE id = :enrollment_id", "CHECK"),
    ("enrollments.total_marks must be 0-100",
     "UPDATE enrollments SET total_marks = 101 WHERE id = :enrollment_id", "CHECK"),
    ("enrollments.grade_point must be 0-4",
     "UPDATE enrollments SET grade_point = 4.5 WHERE id = :enrollment_id", "CHECK"),
    ("a dropped enrollment must have dropped_at",
     "UPDATE enrollments SET status = 'dropped' WHERE id = :enrollment_id", "CHECK"),

    # ---- attendance
    ("one attendance row per enrollment per date",
     """INSERT INTO attendance (enrollment_id, class_date, status, recorded_by)
        VALUES (:enrollment_id, :class_date, 'absent', :teacher_user_id)""", "UNIQUE"),
    ("attendance.status must be present / absent / late / excused",
     "UPDATE attendance SET status = 'sleeping' WHERE enrollment_id = :enrollment_id", "CHECK"),
    ("attendance.recorded_by must be a real user",
     """INSERT INTO attendance (enrollment_id, class_date, status, recorded_by)
        VALUES (:enrollment_id, '2030-01-01', 'present', :missing)""", "FOREIGN KEY"),

    # ---- assessments and results
    ("assessments.type must be a known type",
     "UPDATE assessments SET type = 'essay' WHERE id = :assessment_id", "CHECK"),
    ("assessments.max_marks must be > 0",
     "UPDATE assessments SET max_marks = 0 WHERE id = :assessment_id", "CHECK"),
    ("assessments.weight_percent must be > 0",
     "UPDATE assessments SET weight_percent = 0 WHERE id = :assessment_id", "CHECK"),
    ("assessments.weight_percent must be <= 100",
     "UPDATE assessments SET weight_percent = 101 WHERE id = :assessment_id", "CHECK"),
    ("one result per assessment per enrollment",
     """INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, graded_by)
        VALUES (:assessment_id, :enrollment_id, 10, :teacher_user_id)""", "UNIQUE"),
    ("assessment_results.marks_obtained must be >= 0",
     "UPDATE assessment_results SET marks_obtained = -1 WHERE assessment_id = :assessment_id", "CHECK"),

    # ---- fee structures
    ("fee_structures.fee_type must be a known type",
     "INSERT INTO fee_structures (semester_id, fee_type, amount) VALUES (:semester_id, 'parking', 100)", "CHECK"),
    ("fee_structures.amount must be >= 0",
     "INSERT INTO fee_structures (semester_id, fee_type, amount) VALUES (:semester_id, 'exam', -1)", "CHECK"),
    ("one department-specific row per (semester, department, fee type)",
     """INSERT INTO fee_structures (semester_id, department_id, fee_type, amount)
        VALUES (:semester_id, :cse_id, 'lab', 1)""", "UNIQUE"),
    ("one GLOBAL row per (semester, fee type): NULL department (partial unique index)",
     "INSERT INTO fee_structures (semester_id, department_id, fee_type, amount) VALUES (:semester_id, NULL, 'tuition', 1)",
     "UNIQUE"),

    # ---- invoices, items, payments
    ("invoices.invoice_no is UNIQUE",
     """INSERT INTO invoices (student_id, semester_id, invoice_no, total_amount, issued_at, due_date)
        VALUES (:other_student_id, :semester_id, (SELECT invoice_no FROM invoices WHERE id = :invoice_id),
                100, '2026-01-01', '2026-02-01')""", "UNIQUE"),
    ("one invoice per student per semester",
     """INSERT INTO invoices (student_id, semester_id, invoice_no, total_amount, issued_at, due_date)
        VALUES (:student_id, :semester_id, 'INV-NEW', 100, '2026-01-01', '2026-02-01')""", "UNIQUE"),
    ("invoices.total_amount must be >= 0",
     "UPDATE invoices SET total_amount = -1 WHERE id = :invoice_id", "CHECK"),
    ("an invoice can never be over-paid (paid_amount <= total_amount)",
     "UPDATE invoices SET paid_amount = total_amount + 1 WHERE id = :invoice_id", "CHECK"),
    ("invoices.status must be unpaid / partial / paid / overdue",
     "UPDATE invoices SET status = 'cancelled' WHERE id = :invoice_id", "CHECK"),
    ("invoice_items.amount must be >= 0",
     "INSERT INTO invoice_items (invoice_id, description, amount) VALUES (:invoice_id, 'X', -5)", "CHECK"),
    ("invoice_items.invoice_id must exist",
     "INSERT INTO invoice_items (invoice_id, description, amount) VALUES (:missing, 'X', 5)", "FOREIGN KEY"),
    ("payments.amount must be > 0",
     "INSERT INTO payments (invoice_id, amount, method, received_by) VALUES (:invoice_id, 0, 'cash', :accountant_user_id)",
     "CHECK"),
    ("payments.method must be a known method",
     "INSERT INTO payments (invoice_id, amount, method, received_by) VALUES (:invoice_id, 10, 'cheque', :accountant_user_id)",
     "CHECK"),
    ("payments.transaction_ref is UNIQUE",
     """INSERT INTO payments (invoice_id, amount, method, transaction_ref, received_by)
        VALUES (:invoice_id, 10, 'bkash', 'REF-1', :accountant_user_id)""", "UNIQUE"),
    ("payments.invoice_id must exist",
     "INSERT INTO payments (invoice_id, amount, method, received_by) VALUES (:missing, 10, 'cash', :accountant_user_id)",
     "FOREIGN KEY"),

    # ---- announcements, audit logs, helper tables
    ("announcements.target_role must be NULL or a role",
     "INSERT INTO announcements (title, body, posted_by, target_role) VALUES ('T', 'B', :admin_user_id, 'everyone')",
     "CHECK"),
    ("audit_logs.action must be INSERT / UPDATE / DELETE",
     "INSERT INTO audit_logs (table_name, record_id, action) VALUES ('users', 1, 'SELECT')", "CHECK"),
    ("mv_department_performance: one row per (department, semester)",
     """INSERT INTO mv_department_performance (department_id, semester_id, avg_gpa, pass_rate, total_students)
        VALUES (:cse_id, :semester_id, 3.0, 90, 10), (:cse_id, :semester_id, 3.1, 91, 11)""", "UNIQUE"),
    ("_audit_actor can only ever have the row id = 1",
     "INSERT INTO _audit_actor (id, user_id) VALUES (2, NULL)", "CHECK"),
]


@pytest.mark.parametrize("sql, error_word", [case[1:] for case in CASES], ids=[case[0] for case in CASES])
def test_database_rejects_bad_data(conn, ids, sql, error_word):
    """SQLite must raise IntegrityError, and the message must say which kind of rule broke."""
    with pytest.raises(sqlite3.IntegrityError) as error:
        conn.execute(sql, ids)
    assert error_word in str(error.value)


def test_every_table_is_covered():
    """Guard against forgetting a table: every core table appears in at least one case."""
    all_sql = " ".join(sql for _, sql, _ in CASES)
    tables = ["users", "departments", "teachers", "students", "student_profiles", "semesters", "courses",
              "course_prerequisites", "rooms", "course_offerings", "class_schedules", "enrollments",
              "attendance", "assessments", "assessment_results", "fee_structures", "invoices",
              "invoice_items", "payments", "announcements", "audit_logs"]
    assert len(tables) == 21
    missing = [table for table in tables if f" {table} " not in all_sql and f" {table}\n" not in all_sql]
    assert missing == []


def test_failed_statement_changes_nothing(conn, ids):
    """
    A statement is atomic: the mv INSERT above has 2 rows and only the SECOND
    one breaks UNIQUE, yet the first row is not kept either.
    """
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO mv_department_performance (department_id, semester_id, total_students)
               VALUES (:cse_id, :semester_id, 1), (:cse_id, :semester_id, 2)""", ids)
    assert count(conn, "mv_department_performance") == 0


# ---------------------------------------------------------------------------
# Foreign keys: they are ON, and their ON DELETE actions work
# ---------------------------------------------------------------------------
def test_foreign_keys_are_on_for_our_connections(conn):
    assert fetch_value(conn, "PRAGMA foreign_keys") == 1


def test_foreign_keys_are_off_on_a_raw_connection(db_path, world):
    """
    DB LESSON: SQLite's default is foreign_keys = OFF, per connection. A raw
    sqlite3.connect() happily inserts a teacher into a department that does
    not exist. That is why get_connection() always switches it on.
    """
    raw = sqlite3.connect(db_path)
    try:
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        raw.execute("BEGIN")
        raw.execute(
            """INSERT INTO teachers (user_id, department_id, employee_code, first_name, last_name, designation, hired_at)
               VALUES (?, ?, 'GHOST', 'No', 'Department', 'lecturer', '2020-01-01')""",
            (world["admin_user_id"], MISSING),
        )   # no error!
        raw.execute("ROLLBACK")
    finally:
        raw.close()


def test_circular_fk_departments_to_teachers_exists(conn):
    """02_rebuild_circular_fk.sql added departments.head_teacher_id -> teachers(id) ON DELETE SET NULL."""
    fks = fetch_all(conn, "PRAGMA foreign_key_list('departments')")
    assert [(fk["from"], fk["table"], fk["to"], fk["on_delete"]) for fk in fks] == [
        ("head_teacher_id", "teachers", "id", "SET NULL")
    ]
    # The rebuild must not leave its temporary table behind
    assert "departments_new" not in list_tables(conn)


def test_on_delete_cascade_removes_the_profile(conn, world):
    """student_profiles.student_id ... ON DELETE CASCADE: the profile goes with the student."""
    conn.execute("DELETE FROM students WHERE id = ?", (world["other_student_id"],))
    assert count(conn, "student_profiles", "student_id = ?", (world["other_student_id"],)) == 0


def test_on_delete_restrict_protects_a_department_in_use(conn, world):
    """teachers.department_id ... ON DELETE RESTRICT: a department with teachers cannot be deleted."""
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("DELETE FROM departments WHERE id = ?", (world["cse_id"],))
    assert count(conn, "departments", "id = ?", (world["cse_id"],)) == 1


def test_on_delete_set_null_clears_the_department_head(conn, world):
    """departments.head_teacher_id ... ON DELETE SET NULL: the department stays, without a head."""
    conn.execute("UPDATE departments SET head_teacher_id = ? WHERE id = ?", (world["other_teacher_id"], world["eee_id"]))
    conn.execute("DELETE FROM teachers WHERE id = ?", (world["other_teacher_id"],))
    assert fetch_value(conn, "SELECT head_teacher_id FROM departments WHERE id = ?", (world["eee_id"],)) is None


def test_on_delete_set_null_keeps_the_invoice_line(conn, world):
    """invoice_items.fee_structure_id ... ON DELETE SET NULL: the line and its amount stay on the invoice."""
    fee_id = make_fee(conn, world["semester_id"], "exam", 200_000)
    invoice_id = make_invoice(conn, world["student_id"], world["semester_id"], 200_000)
    conn.execute("INSERT INTO invoice_items (invoice_id, fee_structure_id, description, amount) VALUES (?, ?, 'Exam fee', 200000)",
                 (invoice_id, fee_id))
    conn.execute("DELETE FROM fee_structures WHERE id = ?", (fee_id,))
    item = conn.execute("SELECT fee_structure_id, amount FROM invoice_items WHERE invoice_id = ?", (invoice_id,)).fetchone()
    assert (item["fee_structure_id"], item["amount"]) == (None, 200_000)


# ---------------------------------------------------------------------------
# Things that must still be ALLOWED (a constraint that is too strict is a bug too)
# ---------------------------------------------------------------------------
def test_many_cash_payments_without_reference_are_allowed(conn, ids):
    """UNIQUE ignores NULLs: any number of payments may have transaction_ref = NULL."""
    make_payment(conn, ids["invoice_id"], 1_000, ids["accountant_user_id"])
    make_payment(conn, ids["invoice_id"], 1_000, ids["accountant_user_id"])
    assert count(conn, "payments", "transaction_ref IS NULL") == 2


def test_global_and_department_fee_rows_can_coexist(conn, ids):
    """The global tuition row already exists; a CSE-only tuition row is still fine."""
    make_fee(conn, ids["semester_id"], "tuition", 6_000_000, ids["cse_id"])
    assert count(conn, "fee_structures", "fee_type = 'tuition'") == 2


def test_many_inactive_semesters_are_allowed(conn, world):
    """The partial unique index only covers is_active = 1 rows."""
    make_semester(conn, "past")
    make_semester(conn, "future")
    assert count(conn, "semesters", "is_active = 0") == 3


def test_offering_may_be_exactly_full(conn, world):
    """enrolled_count = capacity is allowed; only capacity + 1 is not."""
    conn.execute("UPDATE course_offerings SET enrolled_count = capacity WHERE id = ?", (world["offering_id"],))


# ---------------------------------------------------------------------------
# The schema as a whole
# ---------------------------------------------------------------------------
def test_schema_has_all_objects(conn):
    tables = list_tables(conn)
    assert count_core_tables(tables) == 21
    assert "mv_department_performance" in tables

    def number_of(kind: str) -> int:
        return fetch_value(conn, "SELECT COUNT(*) FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
                           (kind,))

    assert number_of("view") == 5
    assert number_of("trigger") == 34
    assert number_of("index") >= 26
    assert fetch_value(conn, "PRAGMA journal_mode") == "wal"
