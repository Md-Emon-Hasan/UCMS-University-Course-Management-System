"""
Service tests: the 10 business functions from the spec.

     #1 enroll_student            (+ every one of its 7 rejection reasons)
     #2 drop_enrollment
     #3 record_payment
     #4 calculate_final_marks
     #5 marks_to_gpa
     #6 finalize_grade
     #7 calculate_cgpa
     #8 generate_invoice
     #9 close_semester
    #10 refresh_department_performance

A rejected call must leave the database EXACTLY as it was. Many tests
check that by comparing a full dump of the database (every row as an
INSERT statement) from before and after the failed call.

(conn.total_changes cannot be used for this: it also counts rows that
were changed and then ROLLED BACK. See LEARNING_NOTES.md.)
"""

import pytest

from app.database import fetch_one, fetch_value
from app.errors import BusinessRuleError
from app.services.billing_service import generate_invoice, generate_invoices_for_semester, record_payment
from app.services.enrollment_service import (MAX_CREDITS_PER_SEMESTER, check_eligibility, drop_enrollment,
                                             enroll_student, list_eligibility)
from app.services.grading_service import calculate_cgpa, calculate_final_marks, finalize_grade, marks_to_gpa
from app.services.report_service import refresh_department_performance
from app.services.semester_service import activate_semester, close_semester
from tests.factory import (add_prerequisite, count, enrolled_count, make_assessments, make_course, make_enrollment,
                           make_fee, make_invoice, make_offering, make_passed_course, make_result, make_semester,
                           make_student)


def database_dump(conn) -> list[str]:
    """Every table and row of the database as SQL text (sqlite3's built-in iterdump)."""
    return list(conn.iterdump())


def assert_rejected(conn, call, message_part: str, status_code: int = 400) -> BusinessRuleError:
    """
    Run `call()`, expect a BusinessRuleError containing `message_part`,
    and check that NOTHING was written and no transaction was left open.
    """
    before = database_dump(conn)
    with pytest.raises(BusinessRuleError) as error:
        call()
    assert message_part in error.value.message
    assert error.value.status_code == status_code
    assert not conn.in_transaction, "the transaction must be rolled back"
    assert database_dump(conn) == before, "a rejected call must not change any row"
    return error.value


# ===========================================================================
# #5 marks_to_gpa
# ===========================================================================
@pytest.mark.parametrize("marks, expected", [
    (100, (4.00, "A+")), (80, (4.00, "A+")), (79.99, (3.75, "A")), (75, (3.75, "A")),
    (74.5, (3.50, "A-")), (70, (3.50, "A-")), (65, (3.25, "B+")), (60, (3.00, "B")),
    (55, (2.75, "B-")), (50, (2.50, "C+")), (45, (2.25, "C")), (40, (2.00, "D")),
    (39.99, (0.00, "F")), (0, (0.00, "F")),
])
def test_marks_to_gpa_bands(marks, expected):
    assert marks_to_gpa(marks) == expected


@pytest.mark.parametrize("marks", [-1, 100.01])
def test_marks_to_gpa_rejects_impossible_marks(marks):
    with pytest.raises(ValueError):
        marks_to_gpa(marks)


# ===========================================================================
# #4 calculate_final_marks   and   #6 finalize_grade
# ===========================================================================
@pytest.fixture
def graded(conn, world) -> int:
    """
    An enrollment with 3 of its 4 results entered (the assessments are
    quiz 20 max / 10%, assignment 20 / 20%, midterm 30 / 30%, final 40 / 40%):
        quiz        16 / 20 * 10 =  8
        assignment  20 / 20 * 20 = 20
        midterm     15 / 30 * 30 = 15
        final       (missing)    =  0
        total                      43  -> D (2.00), the 40-44 band
    """
    enrollment = make_enrollment(conn, world["student_id"], world["offering_id"])
    quiz, assignment, midterm, _final = world["assessment_ids"]
    for assessment, marks in ((quiz, 16), (assignment, 20), (midterm, 15)):
        make_result(conn, assessment, enrollment, marks, world["teacher_user_id"])
    return enrollment


def test_calculate_final_marks_is_weighted(conn, graded):
    assert calculate_final_marks(conn, graded) == 43.0


def test_calculate_final_marks_with_no_results_is_zero(conn, world):
    enrollment = make_enrollment(conn, world["other_student_id"], world["offering_id"])
    assert calculate_final_marks(conn, enrollment) == 0.0


def test_finalize_grade_saves_the_grade(conn, world, graded):
    result = finalize_grade(conn, graded, world["teacher_user_id"])
    assert result == {"enrollment_id": graded, "total_marks": 43.0, "grade_point": 2.0,
                      "letter_grade": "D", "status": "completed"}
    row = fetch_one(conn, "SELECT status, total_marks, grade_point, letter_grade FROM enrollments WHERE id = ?",
                    (graded,))
    assert dict(row) == {"status": "completed", "total_marks": 43.0, "grade_point": 2.0, "letter_grade": "D"}
    assert enrolled_count(conn, world["offering_id"]) == 0          # a completed row no longer holds a seat


def test_finalize_grade_needs_weights_of_100(conn, world, graded):
    conn.execute("DELETE FROM assessments WHERE id = ?", (world["assessment_ids"][3],))   # remove the 40% final
    assert_rejected(conn, lambda: finalize_grade(conn, graded, world["teacher_user_id"]), "add up to 60%")
    assert fetch_value(conn, "SELECT status FROM enrollments WHERE id = ?", (graded,)) == "enrolled"


def test_finalize_grade_only_once(conn, world, graded):
    finalize_grade(conn, graded, world["teacher_user_id"])
    assert_rejected(conn, lambda: finalize_grade(conn, graded, world["teacher_user_id"]),
                    "current status: completed")


# ===========================================================================
# #7 calculate_cgpa
# ===========================================================================
def test_cgpa_is_weighted_by_credits(conn, world):
    """(4.0 * 3 credits + 2.0 * 1.5 credits) / 4.5 credits = 15 / 4.5 = 3.33"""
    three_credit = make_course(conn, world["cse_id"], credits=3)
    lab = make_course(conn, world["cse_id"], credits=1.5)
    make_passed_course(conn, world["student_id"], three_credit, world["past_semester_id"], world["teacher_id"], 4.0)
    make_passed_course(conn, world["student_id"], lab, world["past_semester_id"], world["teacher_id"], 2.0)
    make_enrollment(conn, world["student_id"], world["offering_id"])          # 'enrolled': not counted yet
    assert calculate_cgpa(conn, world["student_id"]) == {"cgpa": 3.33, "credits_completed": 4.5,
                                                          "courses_completed": 2}


def test_cgpa_without_completed_courses_is_none(conn, world):
    assert calculate_cgpa(conn, world["student_id"])["cgpa"] is None


# ===========================================================================
# #1 enroll_student: the happy path
# ===========================================================================
def test_enroll_student_creates_the_enrollment(conn, world):
    enrollment = enroll_student(conn, world["student_id"], world["offering_id"], world["student_user_id"])
    assert (enrollment["status"], enrollment["course_code"]) == ("enrolled", fetch_value(
        conn, "SELECT code FROM courses WHERE id = ?", (world["course_id"],)))
    assert enrolled_count(conn, world["offering_id"]) == 1
    # the audit trigger recorded WHO did it (set by transaction(conn, actor_id))
    assert fetch_value(conn, "SELECT changed_by FROM audit_logs WHERE table_name = 'enrollments'") == \
        world["student_user_id"]


def test_enroll_again_after_drop_reuses_the_row(conn, world):
    """UNIQUE(student_id, offering_id) allows one row per pair, so the dropped row is switched back on."""
    first = enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"])
    drop_enrollment(conn, first["id"], world["admin_user_id"])
    again = enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"])
    assert again["id"] == first["id"]
    assert (again["status"], again["dropped_at"]) == ("enrolled", None)
    assert enrolled_count(conn, world["offering_id"]) == 1


def test_student_may_take_a_course_after_passing_its_prerequisite(conn, world):
    advanced = make_course(conn, world["cse_id"], level=2)
    add_prerequisite(conn, advanced, world["course_id"])
    make_passed_course(conn, world["student_id"], world["course_id"], world["past_semester_id"],
                       world["teacher_id"], grade_point=2.0)             # D = the lowest pass
    offering = make_offering(conn, advanced, world["semester_id"], world["teacher_id"])
    assert enroll_student(conn, world["student_id"], offering, world["admin_user_id"])["status"] == "enrolled"


def test_credit_limit_boundary_is_allowed(conn, world):
    """18 credits + 3 = exactly 21 is still allowed."""
    for _ in range(3):
        course = make_course(conn, world["cse_id"], credits=6)
        make_enrollment(conn, world["student_id"], make_offering(conn, course, world["semester_id"], world["teacher_id"]))
    enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"])


# ===========================================================================
# #1 enroll_student: the 7 rejection reasons (in the spec's order)
# ===========================================================================
def test_reject_1_student_not_active(conn, world):
    suspended = make_student(conn, world["cse_id"], status="suspended")
    assert_rejected(conn, lambda: enroll_student(conn, suspended["id"], world["offering_id"], world["admin_user_id"]),
                    "Student is not active (status: suspended)")


def test_reject_2_registration_window_closed(conn, world):
    for when in ("past", "future"):
        semester = make_semester(conn, when)
        offering = make_offering(conn, world["course_id"], semester, world["teacher_id"])
        assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], offering, world["admin_user_id"]),
                        "Registration for")


def test_reject_3_offering_not_open(conn, world):
    for status in ("closed", "cancelled"):
        offering = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], status=status)
        assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], offering, world["admin_user_id"]),
                        f"not open for enrollment (status: {status})")


def test_reject_4_already_enrolled_in_this_course(conn, world):
    """Already in section A, so section B of the same course is refused too."""
    enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"])
    section_b = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], section="B")
    for offering in (world["offering_id"], section_b):
        assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], offering, world["admin_user_id"]),
                        "Already enrolled in")


def test_reject_5_offering_full(conn, world):
    tiny = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=1)
    enroll_student(conn, world["other_student_id"], tiny, world["admin_user_id"])
    assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], tiny, world["admin_user_id"]),
                    "This offering is full (1/1)")


def test_reject_6_missing_prerequisite(conn, world):
    advanced = make_course(conn, world["cse_id"], level=2)
    add_prerequisite(conn, advanced, world["course_id"])
    offering = make_offering(conn, advanced, world["semester_id"], world["teacher_id"])
    enroll = lambda: enroll_student(conn, world["student_id"], offering, world["admin_user_id"])  # noqa: E731

    assert_rejected(conn, enroll, "Missing prerequisite(s)")                       # never took it
    make_passed_course(conn, world["student_id"], world["course_id"], world["past_semester_id"],
                       world["teacher_id"], grade_point=0.0)
    assert_rejected(conn, enroll, "Missing prerequisite(s)")                       # took it, but failed (F)


def test_reject_7_credit_limit(conn, world):
    """18 credits + 1.5 + 3 = 22.5 > 21."""
    for credits in (6, 6, 6, 1.5):
        course = make_course(conn, world["cse_id"], credits=credits)
        make_enrollment(conn, world["student_id"], make_offering(conn, course, world["semester_id"], world["teacher_id"]))
    assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"]),
                    f"Credit limit exceeded: 19.5 + 3 > {MAX_CREDITS_PER_SEMESTER} credits")


def test_checks_run_in_the_spec_order(conn, world):
    """A suspended student asking for a FULL offering gets reason #1 (not #5): the first failing check wins."""
    tiny = make_offering(conn, world["course_id"], world["semester_id"], world["teacher_id"], capacity=1)
    make_enrollment(conn, world["other_student_id"], tiny)
    suspended = make_student(conn, world["cse_id"], status="suspended")
    assert_rejected(conn, lambda: enroll_student(conn, suspended["id"], tiny, world["admin_user_id"]), "not active")


def test_unknown_student_or_offering_is_404(conn, world):
    assert_rejected(conn, lambda: enroll_student(conn, 9999, world["offering_id"], world["admin_user_id"]),
                    "Student 9999 not found", status_code=404)
    assert_rejected(conn, lambda: enroll_student(conn, world["student_id"], 9999, world["admin_user_id"]),
                    "Offering 9999 not found", status_code=404)


def test_eligibility_is_a_read_only_dry_run(conn, world):
    tiny = make_offering(conn, world["course_id"], world["semester_id"], world["other_teacher_id"], capacity=1,
                         section="B")
    make_enrollment(conn, world["other_student_id"], tiny)
    before = database_dump(conn)

    assert check_eligibility(conn, world["student_id"], world["offering_id"]) == (True, None)
    items = {item["section"]: item for item in list_eligibility(conn, world["student_id"], world["semester_id"])}
    assert items["A"]["eligible"] is True
    assert (items["B"]["eligible"], items["B"]["reason"]) == (False, "This offering is full (1/1)")
    assert database_dump(conn) == before


# ===========================================================================
# #2 drop_enrollment
# ===========================================================================
def test_drop_enrollment(conn, world):
    enrollment = enroll_student(conn, world["student_id"], world["offering_id"], world["admin_user_id"])
    dropped = drop_enrollment(conn, enrollment["id"], world["student_user_id"])
    assert dropped["status"] == "dropped" and dropped["dropped_at"] is not None
    assert enrolled_count(conn, world["offering_id"]) == 0


def test_drop_only_an_active_enrollment(conn, world):
    completed = make_enrollment(conn, world["student_id"], world["offering_id"], status="completed", grade_point=3.0)
    assert_rejected(conn, lambda: drop_enrollment(conn, completed, world["admin_user_id"]), "current status: completed")
    assert_rejected(conn, lambda: drop_enrollment(conn, 9999, world["admin_user_id"]), "not found", status_code=404)


# ===========================================================================
# #3 record_payment
# ===========================================================================
@pytest.fixture
def invoice(conn, world) -> int:
    return make_invoice(conn, world["student_id"], world["semester_id"], 10_000_00)        # ৳10,000.00


def test_record_payment_partial_then_full(conn, world, invoice):
    actor = world["accountant_user_id"]
    first = record_payment(conn, invoice, 2_500_50, "cash", None, actor)
    assert first["invoice"]["status"] == "partial"
    assert (first["invoice"]["paid_amount"], first["invoice"]["due_amount_taka"]) == (2_500_50, "7499.50")

    second = record_payment(conn, invoice, 7_499_50, "bkash", "BK-100", actor)
    assert (second["invoice"]["status"], second["invoice"]["due_amount"]) == ("paid", 0)
    assert second["payment"]["transaction_ref"] == "BK-100"


def test_record_payment_rejects_more_than_due(conn, world, invoice):
    error = assert_rejected(conn, lambda: record_payment(conn, invoice, 10_000_01, "cash", None,
                                                         world["accountant_user_id"]),
                            "exceeds the remaining due ৳10000.00")
    assert error.field == "amount"


def test_record_payment_on_paid_invoice(conn, world, invoice):
    record_payment(conn, invoice, 10_000_00, "cash", None, world["accountant_user_id"])
    assert_rejected(conn, lambda: record_payment(conn, invoice, 1, "cash", None, world["accountant_user_id"]),
                    "already fully paid")


def test_record_payment_reference_used_once(conn, world, invoice):
    record_payment(conn, invoice, 100_00, "card", "CARD-1", world["accountant_user_id"])
    assert_rejected(conn, lambda: record_payment(conn, invoice, 100_00, "card", "CARD-1", world["accountant_user_id"]),
                    "already been used", status_code=409)


def test_record_payment_zero_amount(conn, world, invoice):
    assert_rejected(conn, lambda: record_payment(conn, invoice, 0, "cash", None, world["accountant_user_id"]),
                    "greater than zero")


# ===========================================================================
# #8 generate_invoice
# ===========================================================================
@pytest.fixture
def fees(conn, world) -> None:
    """Price list of the active semester (amounts in paisa)."""
    semester = world["semester_id"]
    make_fee(conn, semester, "admission", 10_000_00)
    make_fee(conn, semester, "tuition", 50_000_00)                      # global
    make_fee(conn, semester, "tuition", 55_000_00, world["cse_id"])     # CSE overrides tuition
    make_fee(conn, semester, "lab", 5_000_00, world["cse_id"])          # CSE only
    make_fee(conn, semester, "exam", 3_000_00)
    make_fee(conn, semester, "late_fine", 500_00)                       # never part of a normal invoice


def test_generate_invoice_uses_department_overrides(conn, world, fees):
    invoice = generate_invoice(conn, world["student_id"], world["semester_id"], world["accountant_user_id"])
    lines = [(item["description"], item["amount"]) for item in invoice["items"]]
    assert lines == [("Admission fee", 10_000_00), ("Tuition fee", 55_000_00), ("Lab fee", 5_000_00),
                     ("Exam fee", 3_000_00)]
    assert invoice["total_amount"] == 73_000_00
    student_code = fetch_value(conn, "SELECT student_code FROM students WHERE id = ?", (world["student_id"],))
    semester_code = fetch_value(conn, "SELECT code FROM semesters WHERE id = ?", (world["semester_id"],))
    assert invoice["invoice_no"] == f"INV-{semester_code}-{student_code}"
    assert invoice["status"] == "unpaid"


def test_generate_invoice_for_another_department_uses_global_rows(conn, world, fees):
    eee_student = make_student(conn, world["eee_id"])
    invoice = generate_invoice(conn, eee_student["id"], world["semester_id"], world["accountant_user_id"])
    assert [item["description"] for item in invoice["items"]] == ["Admission fee", "Tuition fee", "Exam fee"]
    assert invoice["total_amount"] == 63_000_00


def test_admission_fee_only_on_the_first_invoice(conn, world, fees):
    make_invoice(conn, world["student_id"], world["past_semester_id"], 1_000_00)    # an older invoice exists
    invoice = generate_invoice(conn, world["student_id"], world["semester_id"], world["accountant_user_id"])
    assert "Admission fee" not in [item["description"] for item in invoice["items"]]


def test_generate_invoice_twice_is_409(conn, world, fees):
    generate_invoice(conn, world["student_id"], world["semester_id"], world["accountant_user_id"])
    assert_rejected(conn, lambda: generate_invoice(conn, world["student_id"], world["semester_id"],
                                                   world["accountant_user_id"]), "already exists", status_code=409)


def test_generate_invoice_without_fees(conn, world):
    assert_rejected(conn, lambda: generate_invoice(conn, world["student_id"], world["semester_id"],
                                                   world["accountant_user_id"]), "No fee structure")


def test_bulk_invoices_for_enrolled_students_only(conn, world, fees):
    make_enrollment(conn, world["student_id"], world["offering_id"])
    make_enrollment(conn, world["other_student_id"], world["offering_id"], status="dropped")
    result = generate_invoices_for_semester(conn, world["semester_id"], world["accountant_user_id"])
    assert result["created"] == 1
    assert count(conn, "invoices") == 1
    assert count(conn, "invoice_items") == 4


# ===========================================================================
# #9 close_semester   (+ activate_semester)
# ===========================================================================
def test_close_semester_finalizes_closes_and_switches(conn, world, graded):
    next_semester = make_semester(conn, "future")
    result = close_semester(conn, world["semester_id"], next_semester, world["admin_user_id"])
    assert result["grades_finalized"] == 1 and result["offerings_closed"] == 1
    assert fetch_value(conn, "SELECT letter_grade FROM enrollments WHERE id = ?", (graded,)) == "D"
    assert fetch_value(conn, "SELECT status FROM course_offerings WHERE id = ?", (world["offering_id"],)) == "closed"
    assert fetch_value(conn, "SELECT id FROM semesters WHERE is_active = 1") == next_semester


def test_close_semester_is_all_or_nothing(conn, world, graded):
    """A second offering has weights of only 50%, so NOTHING may change, not even the first offering's grade."""
    course = make_course(conn, world["cse_id"])
    broken = make_offering(conn, course, world["semester_id"], world["teacher_id"])
    make_assessments(conn, broken, [("final", 50, 50)])
    make_enrollment(conn, world["other_student_id"], broken)
    next_semester = make_semester(conn, "future")

    assert_rejected(conn, lambda: close_semester(conn, world["semester_id"], next_semester, world["admin_user_id"]),
                    "add up to 50%")
    assert fetch_value(conn, "SELECT status FROM enrollments WHERE id = ?", (graded,)) == "enrolled"
    assert fetch_value(conn, "SELECT id FROM semesters WHERE is_active = 1") == world["semester_id"]


def test_close_semester_needs_a_different_next_semester(conn, world):
    assert_rejected(conn, lambda: close_semester(conn, world["semester_id"], world["semester_id"],
                                                 world["admin_user_id"]), "must be different")


def test_activate_semester_keeps_exactly_one_active(conn, world):
    activate_semester(conn, world["past_semester_id"], world["admin_user_id"])
    assert fetch_value(conn, "SELECT group_concat(id) FROM semesters WHERE is_active = 1") == \
        str(world["past_semester_id"])


# ===========================================================================
# #10 refresh_department_performance
# ===========================================================================
def test_refresh_department_performance(conn, world):
    """CSE students: grades 4.0, 3.0 and 0.0 -> avg 2.33, pass rate 2 of 3 = 66.7%."""
    course2 = make_course(conn, world["cse_id"])
    make_passed_course(conn, world["student_id"], world["course_id"], world["past_semester_id"], world["teacher_id"], 4.0)
    make_passed_course(conn, world["student_id"], course2, world["past_semester_id"], world["teacher_id"], 3.0)
    make_passed_course(conn, world["other_student_id"], world["course_id"], world["past_semester_id"],
                       world["teacher_id"], 0.0)

    assert refresh_department_performance(conn, world["admin_user_id"]) == 1
    row = fetch_one(conn, "SELECT * FROM mv_department_performance")
    assert (row["department_id"], row["semester_id"]) == (world["cse_id"], world["past_semester_id"])
    assert (row["avg_gpa"], row["pass_rate"], row["total_students"]) == (2.33, 66.7, 2)

    # Running it again rebuilds the table (DELETE + INSERT), so there is no UNIQUE error and no duplicate
    assert refresh_department_performance(conn) == 1
