"""
Concurrency tests: many students clicking "Enroll" at the same moment.

THE PROBLEM (a "race condition")
    enroll_student() reads "0 of 1 seats taken", then inserts. If two
    requests both read BEFORE either one writes, both see a free seat.

THE FIX
    enroll_student() runs inside BEGIN IMMEDIATE, which takes SQLite's write
    lock BEFORE the first read. The second request waits (busy_timeout),
    then reads the NEW count and is rejected with a clean "full" message.

Each thread uses its OWN connection, like two separate web requests.
threading.Barrier makes all threads start at the same instant, so the race
is real and not an accident of timing.

The last tests show the locking rules themselves, without threads.
"""

import sqlite3
import threading

import pytest

from app.database import fetch_value, get_connection, transaction
from app.errors import BusinessRuleError
from app.services.enrollment_service import enroll_student
from tests.factory import count, enrolled_count, make_offering, make_student


def race(db_path, student_ids: list[int], offering_id: int, actor_id: int) -> dict[int, str]:
    """
    Let every student try to enroll at the same instant, each in its own thread
    with its own connection.

    Returns:
        {student_id: "ok"} or {student_id: "<error message>"} for every student.
    """
    results: dict[int, str] = {}
    barrier = threading.Barrier(len(student_ids))

    def try_to_enroll(student_id: int) -> None:
        own_conn = get_connection(db_path)            # like a separate web request
        try:
            barrier.wait()                            # everybody starts together
            enroll_student(own_conn, student_id, offering_id, actor_id)
            results[student_id] = "ok"
        except BusinessRuleError as error:
            results[student_id] = error.message
        except Exception as error:                    # anything else is a failure of the test
            results[student_id] = f"UNEXPECTED {type(error).__name__}: {error}"
        finally:
            own_conn.close()

    threads = [threading.Thread(target=try_to_enroll, args=(sid,)) for sid in student_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.mark.parametrize("attempt", range(5))       # repeat: a race bug does not show up every time
def test_two_students_one_seat_exactly_one_wins(db_path, conn, world, attempt):
    last_seat = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=1)

    results = race(db_path, [world["student_id"], world["other_student_id"]], last_seat, world["admin_user_id"])

    outcomes = list(results.values())
    assert outcomes.count("ok") == 1, results                             # exactly one winner ...
    assert outcomes.count("This offering is full (1/1)") == 1, results    # ... and one clean rejection
    assert enrolled_count(conn, last_seat) == 1
    assert count(conn, "enrollments", "offering_id = ?", (last_seat,)) == 1


def test_ten_students_three_seats(db_path, conn, world):
    offering = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=3)
    students = [make_student(conn, world["cse_id"])["id"] for _ in range(10)]

    results = race(db_path, students, offering, world["admin_user_id"])

    assert list(results.values()).count("ok") == 3, results
    assert all(message == "ok" or "full" in message for message in results.values()), results
    assert enrolled_count(conn, offering) == 3
    # the stored counter and a live COUNT agree, so no update was lost
    assert count(conn, "enrollments", "offering_id = ? AND status = 'enrolled'", (offering,)) == 3


# ---------------------------------------------------------------------------
# The locking rules behind it (no threads needed)
# ---------------------------------------------------------------------------
def test_begin_immediate_blocks_a_second_writer(db_path, conn, world):
    """While one connection holds the write lock, another cannot start writing."""
    impatient = get_connection(db_path)
    impatient.execute("PRAGMA busy_timeout = 100")       # wait only 0.1 s instead of 5 s
    try:
        with transaction(conn, world["admin_user_id"]):
            with pytest.raises(sqlite3.OperationalError, match="database is locked"):
                impatient.execute("BEGIN IMMEDIATE")
        # the first transaction has committed: now the second writer gets the lock
        impatient.execute("BEGIN IMMEDIATE")
        impatient.execute("ROLLBACK")
    finally:
        impatient.close()


def test_readers_are_not_blocked_and_see_only_committed_data(db_path, conn, world):
    """
    WAL mode: a reader keeps working while a writer holds the lock, and it
    sees the last COMMITTED data, never a half-finished transaction.
    """
    reader = get_connection(db_path)
    try:
        with transaction(conn, world["admin_user_id"]):
            conn.execute("UPDATE courses SET title = 'Uncommitted title' WHERE id = ?", (world["course_id"],))
            seen = fetch_value(reader, "SELECT title FROM courses WHERE id = ?", (world["course_id"],))
            assert seen != "Uncommitted title"
        assert fetch_value(reader, "SELECT title FROM courses WHERE id = ?", (world["course_id"],)) == \
            "Uncommitted title"
    finally:
        reader.close()


def test_deferred_begin_fails_after_a_stale_read(db_path, conn, world):
    """
    Why plain BEGIN is not enough: A reads, B writes and commits, then A
    tries to write based on its OLD read. SQLite refuses at once with
    "database is locked" (busy_timeout does not help here). The data stays
    correct, but the user would get an error instead of a clear message.
    BEGIN IMMEDIATE avoids this situation completely.
    """
    other = get_connection(db_path)
    try:
        conn.execute("BEGIN")                                        # deferred: no lock yet
        seats = fetch_value(conn, "SELECT enrolled_count FROM course_offerings WHERE id = ?", (world["offering_id"],))
        assert seats == 0

        with transaction(other, world["admin_user_id"]):            # someone else enrolls meanwhile
            other.execute("INSERT INTO enrollments (student_id, offering_id) VALUES (?, ?)",
                          (world["other_student_id"], world["offering_id"]))

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            conn.execute("INSERT INTO enrollments (student_id, offering_id) VALUES (?, ?)",
                         (world["student_id"], world["offering_id"]))
        conn.execute("ROLLBACK")
    finally:
        other.close()
