"""
Billing services.

Services from the spec:
    #3 record_payment(invoice_id, amount, method, ref, actor_id)
    #8 generate_invoice(student_id, semester_id, actor_id)

All amounts here are INTEGER paisa.
"""

import sqlite3

from app.database import fetch_all, fetch_one, fetch_value, transaction
from app.errors import BusinessRuleError, not_found
from app.repositories import billing as billing_repo
from app.schemas.common import paisa_to_taka

INVOICE_DUE_DAYS = 75              # due date = semester start + 75 days
MIN_DAYS_TO_PAY = 14               # ...but never less than 14 days from today

# For each fee type take the DEPARTMENT row if one exists, otherwise the
# GLOBAL row (department_id IS NULL). Read the last condition as: "skip a
# global row when the same fee type also has a row for this department".
# late_fine is charged separately. admission is only charged once (see below).
APPLICABLE_FEES_SQL = """
SELECT f.id, f.fee_type, f.amount
FROM fee_structures f
WHERE f.semester_id = :semester_id
  AND (f.department_id = :department_id OR f.department_id IS NULL)
  AND f.fee_type <> 'late_fine'
  AND NOT (
        f.department_id IS NULL
        AND EXISTS (SELECT 1 FROM fee_structures o
                    WHERE o.semester_id = f.semester_id
                      AND o.fee_type = f.fee_type
                      AND o.department_id = :department_id)
  )
ORDER BY CASE f.fee_type WHEN 'admission' THEN 1 WHEN 'tuition' THEN 2 WHEN 'lab' THEN 3
                         WHEN 'exam' THEN 4 WHEN 'library' THEN 5 ELSE 6 END
"""


def record_payment(conn: sqlite3.Connection, invoice_id: int, amount_paisa: int, method: str,
                   transaction_ref: str | None, actor_id: int) -> dict:
    """
    SERVICE #3: record a payment, rejecting any amount above what is still due.

    The trigger trg_payment_update_invoice then updates the invoice's
    paid_amount and status inside the SAME transaction.

    Returns:
        {"payment": ..., "invoice": ...} after the change.
    """
    with transaction(conn, actor_id):
        invoice = fetch_one(conn, "SELECT id, total_amount, paid_amount FROM invoices WHERE id = ?", (invoice_id,))
        if invoice is None:
            raise not_found("Invoice", invoice_id)
        if amount_paisa <= 0:
            raise BusinessRuleError("Amount must be greater than zero", field="amount")

        due = invoice["total_amount"] - invoice["paid_amount"]
        if due == 0:
            raise BusinessRuleError("This invoice is already fully paid", field="amount")
        if amount_paisa > due:
            raise BusinessRuleError(
                f"Amount ৳{paisa_to_taka(amount_paisa)} exceeds the remaining due ৳{paisa_to_taka(due)}",
                field="amount",
            )
        if transaction_ref and fetch_value(conn, "SELECT 1 FROM payments WHERE transaction_ref = ?",
                                           (transaction_ref,)):
            raise BusinessRuleError("This transaction reference has already been used",
                                    status_code=409, field="transaction_ref")

        payment_id = billing_repo.insert_payment(conn, invoice_id, amount_paisa, method, transaction_ref, actor_id)
    return {"payment": billing_repo.get_payment(conn, payment_id), "invoice": billing_repo.get_invoice(conn, invoice_id)}


def create_invoice_inside_transaction(conn: sqlite3.Connection, student_id: int, semester_id: int) -> int:
    """
    The work of generate_invoice WITHOUT its own transaction, so the bulk
    version can create many invoices in ONE transaction.

    Returns:
        The new invoice id.
    """
    student = fetch_one(
        conn, "SELECT id, student_code, department_id, status FROM students WHERE id = ?", (student_id,)
    )
    if student is None:
        raise not_found("Student", student_id)
    semester = fetch_one(conn, "SELECT id, code, start_date FROM semesters WHERE id = ?", (semester_id,))
    if semester is None:
        raise not_found("Semester", semester_id)

    invoice_no = f"INV-{semester['code']}-{student['student_code']}"
    if fetch_value(conn, "SELECT 1 FROM invoices WHERE student_id = ? AND semester_id = ?", (student_id, semester_id)):
        raise BusinessRuleError(f"Invoice {invoice_no} already exists for this student and semester", status_code=409)

    fees = fetch_all(conn, APPLICABLE_FEES_SQL, {"semester_id": semester_id, "department_id": student["department_id"]})
    # The admission fee is only charged on a student's FIRST invoice
    has_earlier_invoice = fetch_value(conn, "SELECT 1 FROM invoices WHERE student_id = ?", (student_id,))
    if has_earlier_invoice:
        fees = [fee for fee in fees if fee["fee_type"] != "admission"]
    if not fees:
        raise BusinessRuleError(f"No fee structure is defined for semester {semester['code']}")

    # Due date: semester start + 75 days, but at least 14 days from today
    due_date = fetch_value(
        conn,
        "SELECT MAX(date(?, ?), date('now', ?))",
        (semester["start_date"], f"+{INVOICE_DUE_DAYS} days", f"+{MIN_DAYS_TO_PAY} days"),
    )
    total = sum(fee["amount"] for fee in fees)
    invoice_id = billing_repo.insert_invoice(conn, student_id, semester_id, invoice_no, total, due_date)
    for fee in fees:
        description = fee["fee_type"].replace("_", " ").capitalize() + " fee"
        billing_repo.insert_invoice_item(conn, invoice_id, fee["id"], description, fee["amount"])
    return invoice_id


def generate_invoice(conn: sqlite3.Connection, student_id: int, semester_id: int, actor_id: int) -> dict:
    """
    SERVICE #8: build an invoice from the fee structures of the semester.
    Department-specific rows override global rows. The invoice number is
    INV-{semester_code}-{student_code}.
    """
    with transaction(conn, actor_id):
        invoice_id = create_invoice_inside_transaction(conn, student_id, semester_id)
    return billing_repo.get_invoice(conn, invoice_id)


def generate_invoices_for_semester(conn: sqlite3.Connection, semester_id: int, actor_id: int) -> dict:
    """
    Bulk version: an invoice for every student who has a (non-dropped)
    enrollment in the semester and no invoice yet. All or nothing: one
    transaction for the whole batch.
    """
    with transaction(conn, actor_id):
        student_ids = [
            row["student_id"]
            for row in fetch_all(
                conn,
                """SELECT DISTINCT e.student_id
                   FROM enrollments e
                   JOIN course_offerings co ON co.id = e.offering_id
                   WHERE co.semester_id = ? AND e.status <> 'dropped'
                     AND NOT EXISTS (SELECT 1 FROM invoices i
                                     WHERE i.student_id = e.student_id AND i.semester_id = co.semester_id)
                   ORDER BY e.student_id""",
                (semester_id,),
            )
        ]
        created = [create_invoice_inside_transaction(conn, student_id, semester_id) for student_id in student_ids]
    return {"created": len(created), "invoice_ids": created}
