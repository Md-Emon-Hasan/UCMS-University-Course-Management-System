"""
Trigger tests: the database does extra work (or refuses work) by itself.

    1. updated_at is refreshed on every UPDATE                (20 tables)
    2. enrolled_count follows the enrollments                 (insert / update / delete)
    3. marks can never be higher than max_marks               (RAISE(ABORT))
    4. a payment recomputes its invoice's paid_amount/status
    5. enrollments and payments are written to audit_logs     (json_object + _audit_actor)
    6. a room or a teacher can never be double-booked         (RAISE(ABORT))
"""

import json
import sqlite3

import pytest

from app.database import fetch_all, fetch_one, fetch_value, transaction
from tests.factory import (count, enrolled_count, make_course, make_enrollment, make_invoice, make_offering,
                           make_payment, make_result, make_room, make_schedule, make_semester)

OLD_TIME = "2000-01-01 00:00:00"


# ---------------------------------------------------------------------------
# 1) updated_at
# ---------------------------------------------------------------------------
def tables_with_updated_at(conn: sqlite3.Connection) -> list[str]:
    """Every table that has an updated_at column (found by reading the schema)."""
    tables = [row["name"] for row in fetch_all(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")]
    return [t for t in tables if any(col["name"] == "updated_at" for col in fetch_all(conn, f"PRAGMA table_info({t})"))]


def test_every_table_with_updated_at_has_a_trigger(conn):
    tables = tables_with_updated_at(conn)
    assert len(tables) == 20        # all core tables except audit_logs
    triggers = {row["name"] for row in fetch_all(conn, "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert [t for t in tables if f"trg_{t}_updated_at" not in triggers] == []


def test_updated_at_changes_on_update(conn, world):
    conn.execute("UPDATE courses SET updated_at = ? WHERE id = ?", (OLD_TIME, world["course_id"]))
    before = fetch_value(conn, "SELECT datetime('now')")
    conn.execute("UPDATE courses SET title = 'New title' WHERE id = ?", (world["course_id"],))
    new_time = fetch_value(conn, "SELECT updated_at FROM courses WHERE id = ?", (world["course_id"],))
    assert new_time >= before          # the trigger wrote "now", replacing the year-2000 value


def test_updated_at_trigger_does_not_loop(conn, world):
    """
    The trigger's own UPDATE fires the trigger again. The guard
    WHEN NEW.updated_at = OLD.updated_at stops that second round, so an
    explicitly written updated_at is kept (and there is no endless loop).
    """
    conn.execute("UPDATE courses SET updated_at = ? WHERE id = ?", (OLD_TIME, world["course_id"]))
    assert fetch_value(conn, "SELECT updated_at FROM courses WHERE id = ?", (world["course_id"],)) == OLD_TIME


def test_student_profiles_updated_at_uses_student_id(conn, world):
    """student_profiles has no id column; its trigger matches on student_id."""
    conn.execute("UPDATE student_profiles SET updated_at = ? WHERE student_id = ?", (OLD_TIME, world["student_id"]))
    conn.execute("UPDATE student_profiles SET city = 'Dhaka' WHERE student_id = ?", (world["student_id"],))
    assert fetch_value(conn, "SELECT updated_at FROM student_profiles WHERE student_id = ?",
                       (world["student_id"],)) > OLD_TIME


# ---------------------------------------------------------------------------
# 2) enrolled_count
# ---------------------------------------------------------------------------
def test_enrolled_count_follows_every_change(conn, world):
    offering = world["offering_id"]
    assert enrolled_count(conn, offering) == 0

    first = make_enrollment(conn, world["student_id"], offering)                 # INSERT enrolled   -> +1
    second = make_enrollment(conn, world["other_student_id"], offering)          # INSERT enrolled   -> +1
    assert enrolled_count(conn, offering) == 2

    conn.execute("UPDATE enrollments SET status = 'dropped', dropped_at = datetime('now') WHERE id = ?", (first,))
    assert enrolled_count(conn, offering) == 1                                    # enrolled -> dropped: -1

    conn.execute("UPDATE enrollments SET status = 'enrolled', dropped_at = NULL WHERE id = ?", (first,))
    assert enrolled_count(conn, offering) == 2                                    # dropped -> enrolled: +1

    conn.execute("UPDATE enrollments SET status = 'completed', grade_point = 3.5 WHERE id = ?", (second,))
    assert enrolled_count(conn, offering) == 1                                    # enrolled -> completed: -1

    conn.execute("UPDATE enrollments SET total_marks = 50 WHERE id = ?", (first,))
    assert enrolled_count(conn, offering) == 1                                    # other column: no change

    conn.execute("DELETE FROM enrollments WHERE id = ?", (first,))
    assert enrolled_count(conn, offering) == 0                                    # DELETE enrolled: -1


def test_rows_that_do_not_hold_a_seat_are_not_counted(conn, world):
    make_enrollment(conn, world["student_id"], world["offering_id"], status="completed", grade_point=3.0)
    make_enrollment(conn, world["other_student_id"], world["offering_id"], status="dropped")
    assert enrolled_count(conn, world["offering_id"]) == 0


def test_moving_to_another_offering_moves_the_seat(conn, world):
    section_b = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], section="B")
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    conn.execute("UPDATE enrollments SET offering_id = ? WHERE id = ?", (section_b, enrollment))
    assert (enrolled_count(conn, world["offering_id"]), enrolled_count(conn, section_b)) == (0, 1)


def test_capacity_is_enforced_by_the_database(conn, world):
    """
    The trigger's +1 on a full offering breaks CHECK (enrolled_count <= capacity),
    so the whole INSERT is undone, even though no Python rule was checked.
    """
    tiny = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=1, section="T")
    make_enrollment(conn, world["student_id"], tiny)
    with pytest.raises(sqlite3.IntegrityError, match="chk_offering_not_over_capacity"):
        make_enrollment(conn, world["other_student_id"], tiny)
    assert enrolled_count(conn, tiny) == 1
    assert count(conn, "enrollments", "offering_id = ?", (tiny,)) == 1      # the row itself was undone too


def test_stored_counts_match_live_counts_in_seed_data(seeded_db_path):
    """In the full demo data set, every stored counter equals a real COUNT(*)."""
    from app.database import get_connection
    seeded = get_connection(seeded_db_path)
    try:
        wrong = fetch_value(seeded, """
            SELECT COUNT(*) FROM course_offerings co
            WHERE co.enrolled_count <> (SELECT COUNT(*) FROM enrollments e
                                        WHERE e.offering_id = co.id AND e.status = 'enrolled')""")
        assert wrong == 0
    finally:
        seeded.close()


# ---------------------------------------------------------------------------
# 3) marks <= max_marks
# ---------------------------------------------------------------------------
@pytest.fixture
def enrollment(conn, world) -> int:
    return make_enrollment(conn, world["student_id"], world["offering_id"])


def test_marks_above_max_are_rejected_on_insert(conn, world, enrollment):
    quiz = world["assessment_ids"][0]                      # max_marks 20
    with pytest.raises(sqlite3.IntegrityError, match="marks exceed max_marks"):
        make_result(conn, quiz, enrollment, 20.5, world["teacher_user_id"])
    assert count(conn, "assessment_results") == 0


def test_marks_above_max_are_rejected_on_update(conn, world, enrollment):
    quiz = world["assessment_ids"][0]
    result = make_result(conn, quiz, enrollment, 20, world["teacher_user_id"])   # exactly max: allowed
    with pytest.raises(sqlite3.IntegrityError, match="marks exceed max_marks"):
        conn.execute("UPDATE assessment_results SET marks_obtained = 25 WHERE id = ?", (result,))
    assert fetch_value(conn, "SELECT marks_obtained FROM assessment_results WHERE id = ?", (result,)) == 20


def test_rejected_marks_inside_a_transaction_roll_everything_back(conn, world, enrollment):
    """One bad row in a bulk save: transaction() rolls back the good rows too (all or nothing)."""
    quiz, assignment = world["assessment_ids"][:2]
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(conn, world["teacher_user_id"]):
            make_result(conn, quiz, enrollment, 18, world["teacher_user_id"])          # fine
            make_result(conn, assignment, enrollment, 99, world["teacher_user_id"])    # max is 20
    assert count(conn, "assessment_results") == 0


# ---------------------------------------------------------------------------
# 4) payment -> invoice
# ---------------------------------------------------------------------------
def invoice_state(conn, invoice_id: int) -> tuple:
    row = fetch_one(conn, "SELECT paid_amount, status FROM invoices WHERE id = ?", (invoice_id,))
    return row["paid_amount"], row["status"]


def test_payments_update_the_invoice(conn, world):
    invoice = make_invoice(conn, world["student_id"], world["semester_id"], 10_000_00)    # ৳10,000.00
    assert invoice_state(conn, invoice) == (0, "unpaid")
    make_payment(conn, invoice, 4_000_00, world["accountant_user_id"])
    assert invoice_state(conn, invoice) == (4_000_00, "partial")
    make_payment(conn, invoice, 6_000_00, world["accountant_user_id"], "bkash", "BK-1")
    assert invoice_state(conn, invoice) == (10_000_00, "paid")


def test_overpayment_is_rejected_by_the_invoice_check(conn, world):
    """The trigger's new paid_amount would break CHECK (paid_amount <= total_amount), so the payment is undone."""
    invoice = make_invoice(conn, world["student_id"], world["semester_id"], 1_000_00)
    make_payment(conn, invoice, 900_00, world["accountant_user_id"])
    with pytest.raises(sqlite3.IntegrityError, match="chk_invoice_not_overpaid"):
        make_payment(conn, invoice, 200_00, world["accountant_user_id"])
    assert invoice_state(conn, invoice) == (900_00, "partial")
    assert count(conn, "payments", "invoice_id = ?", (invoice,)) == 1


# ---------------------------------------------------------------------------
# 5) audit logs
# ---------------------------------------------------------------------------
def audit_rows(conn, table: str, record_id: int) -> list[dict]:
    return fetch_all(conn, "SELECT * FROM audit_logs WHERE table_name = ? AND record_id = ? ORDER BY id",
                     (table, record_id))


def test_enrollment_changes_are_audited_with_the_actor(conn, world):
    with transaction(conn, actor_id=world["admin_user_id"]):
        enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    with transaction(conn, actor_id=world["student_user_id"]):
        conn.execute("UPDATE enrollments SET status = 'dropped', dropped_at = datetime('now') WHERE id = ?",
                     (enrollment,))
    with transaction(conn, actor_id=world["admin_user_id"]):
        conn.execute("DELETE FROM enrollments WHERE id = ?", (enrollment,))

    rows = audit_rows(conn, "enrollments", enrollment)
    assert [(r["action"], r["changed_by"]) for r in rows] == [
        ("INSERT", world["admin_user_id"]),
        ("UPDATE", world["student_user_id"]),
        ("DELETE", world["admin_user_id"]),
    ]
    insert, update, delete = rows
    assert insert["old_data"] is None and json.loads(insert["new_data"])["status"] == "enrolled"
    assert json.loads(update["old_data"])["status"] == "enrolled"
    assert json.loads(update["new_data"])["status"] == "dropped"
    assert json.loads(delete["old_data"])["student_id"] == world["student_id"] and delete["new_data"] is None


def test_one_update_writes_exactly_one_audit_row(conn, world):
    """
    Regression test (LEARNING_NOTES #3): the updated_at trigger makes a second
    UPDATE; that one only changes updated_at and must NOT be logged again.
    """
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    conn.execute("UPDATE enrollments SET total_marks = 71 WHERE id = ?", (enrollment,))
    assert [r["action"] for r in audit_rows(conn, "enrollments", enrollment)] == ["INSERT", "UPDATE"]


def test_timestamp_only_update_is_not_audited(conn, world):
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    conn.execute("UPDATE enrollments SET updated_at = ? WHERE id = ?", (OLD_TIME, enrollment))
    assert [r["action"] for r in audit_rows(conn, "enrollments", enrollment)] == ["INSERT"]


def test_payments_are_audited(conn, world):
    invoice = make_invoice(conn, world["student_id"], world["semester_id"], 5_000_00)
    with transaction(conn, actor_id=world["accountant_user_id"]):
        payment = make_payment(conn, invoice, 1_500_50, world["accountant_user_id"], "nagad", "NG-77")
    row = audit_rows(conn, "payments", payment)[0]
    assert (row["action"], row["changed_by"]) == ("INSERT", world["accountant_user_id"])
    data = json.loads(row["new_data"])          # json_object(...) text -> Python dict
    assert (data["id"], data["invoice_id"], data["amount"]) == (payment, invoice, 150050)
    assert (data["method"], data["transaction_ref"]) == ("nagad", "NG-77")


def test_actor_is_reset_for_every_transaction(conn, world):
    """transaction() without an actor writes NULL, so an old actor is never blamed for a new change."""
    with transaction(conn, actor_id=world["admin_user_id"]):
        pass
    with transaction(conn):
        enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    assert audit_rows(conn, "enrollments", enrollment)[0]["changed_by"] is None


# ---------------------------------------------------------------------------
# 6) no double-booking
# ---------------------------------------------------------------------------
@pytest.fixture
def booked(conn, world) -> dict:
    """The world offering has a class on Monday (1) 09:00-10:30 in the world room."""
    make_schedule(conn, world["offering_id"], world["room_id"], 1, "09:00", "10:30")
    other_course = make_course(conn, world["cse_id"])
    return {
        # same semester, different teacher
        "other_teachers_offering": make_offering(conn, other_course, world["semester_id"], world["other_teacher_id"]),
        # same semester, SAME teacher
        "same_teachers_offering": make_offering(conn, other_course, world["semester_id"], world["teacher_id"]),
    }


@pytest.mark.parametrize("start, end", [("09:00", "10:30"), ("10:00", "11:00"), ("08:00", "09:30"), ("09:30", "10:00")])
def test_room_conflict_is_rejected(conn, world, booked, start, end):
    """Same room, same day, overlapping time (exact, later, earlier, inside) -> rejected."""
    with pytest.raises(sqlite3.IntegrityError, match="room conflict"):
        make_schedule(conn, booked["other_teachers_offering"], world["room_id"], 1, start, end)


def test_back_to_back_classes_are_allowed(conn, world, booked):
    """09:00-10:30 and 10:30-12:00 only touch; they do not overlap."""
    make_schedule(conn, booked["other_teachers_offering"], world["room_id"], 1, "10:30", "12:00")
    make_schedule(conn, booked["other_teachers_offering"], world["room_id"], 1, "07:30", "09:00")


def test_same_time_on_another_day_or_room_is_allowed(conn, world, booked):
    make_schedule(conn, booked["other_teachers_offering"], world["room_id"], 2, "09:00", "10:30")
    make_schedule(conn, booked["other_teachers_offering"], make_room(conn), 1, "09:00", "10:30")


def test_rooms_are_reused_in_other_semesters(conn, world, booked):
    next_semester = make_semester(conn, "future")
    offering = make_offering(conn, world["course_id"], next_semester, world["other_teacher_id"])
    make_schedule(conn, offering, world["room_id"], 1, "09:00", "10:30")


def test_cancelled_offering_does_not_block_the_room(conn, world, booked):
    conn.execute("UPDATE course_offerings SET status = 'cancelled' WHERE id = ?", (world["offering_id"],))
    make_schedule(conn, booked["other_teachers_offering"], world["room_id"], 1, "09:00", "10:30")


def test_teacher_conflict_is_rejected(conn, world, booked):
    """The same teacher cannot teach two classes at once, even in different rooms."""
    with pytest.raises(sqlite3.IntegrityError, match="teacher conflict"):
        make_schedule(conn, booked["same_teachers_offering"], make_room(conn), 1, "10:00", "11:00")


def test_different_teachers_can_teach_at_the_same_time(conn, world, booked):
    make_schedule(conn, booked["other_teachers_offering"], make_room(conn), 1, "09:00", "10:30")
