"""Raw SQL for fee_structures, invoices, invoice_items and payments. All amounts are INTEGER paisa."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, where_clause
from app.pagination import paginate
from app.schemas.common import add_taka_fields

# ---------------------------------------------------------------------------
# Fee structures
# ---------------------------------------------------------------------------
FEE_SELECT = """
SELECT
    f.id, f.semester_id, sem.code AS semester_code, f.department_id,
    COALESCE(d.code, 'ALL') AS department_code, f.fee_type, f.amount,
    f.created_at, f.updated_at
FROM fee_structures f
JOIN semesters sem ON sem.id = f.semester_id
LEFT JOIN departments d ON d.id = f.department_id     -- LEFT: NULL department = all departments
"""


def list_fee_structures(conn: sqlite3.Connection, list_args: dict, semester_id: int | None = None,
                        department_id: int | None = None) -> dict:
    """One page of fee rows."""
    conditions, params = [], []
    if semester_id is not None:
        conditions.append("f.semester_id = ?")
        params.append(semester_id)
    if department_id is not None:
        conditions.append("f.department_id = ?")
        params.append(department_id)
    page = paginate(
        conn, FEE_SELECT + where_clause(conditions), params, list_args,
        search_columns=["fee_type", "department_code", "semester_code"],
        sort_columns=["id", "semester_code", "department_code", "fee_type", "amount"],
        default_sort="id",
    )
    for row in page["items"]:
        add_taka_fields(row, "amount")
    return page


def get_fee_structure(conn: sqlite3.Connection, fee_id: int) -> dict | None:
    """One fee row."""
    row = fetch_one(conn, FEE_SELECT + " WHERE f.id = ?", (fee_id,))
    return add_taka_fields(row, "amount") if row else None


def insert_fee_structure(conn: sqlite3.Connection, semester_id: int, department_id: int | None,
                         fee_type: str, amount_paisa: int) -> int:
    """Create a fee row and return its id."""
    return execute(
        conn,
        "INSERT INTO fee_structures (semester_id, department_id, fee_type, amount) VALUES (?, ?, ?, ?)",
        (semester_id, department_id, fee_type, amount_paisa),
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
INVOICE_SELECT = """
SELECT
    i.id, i.invoice_no, i.student_id, s.student_code,
    s.first_name || ' ' || s.last_name AS student_name, s.department_id,
    i.semester_id, sem.code AS semester_code,
    i.total_amount, i.paid_amount, i.total_amount - i.paid_amount AS due_amount,
    i.issued_at, i.due_date,
    -- the stored status, but an unpaid/partial invoice past its due date shows as overdue
    CASE WHEN i.paid_amount < i.total_amount AND i.due_date < date('now')
         THEN 'overdue' ELSE i.status END AS status,
    (SELECT COUNT(*) FROM payments p WHERE p.invoice_id = i.id) AS payment_count,
    i.created_at, i.updated_at
FROM invoices i
JOIN students  s   ON s.id   = i.student_id
JOIN semesters sem ON sem.id = i.semester_id
"""
INVOICE_MONEY = ("total_amount", "paid_amount", "due_amount")


def list_invoices(conn: sqlite3.Connection, list_args: dict, semester_id: int | None = None,
                  student_id: int | None = None, status: str | None = None,
                  department_id: int | None = None) -> dict:
    """One page of invoices. The status filter works on the effective status (overdue included)."""
    conditions, params = [], []
    if semester_id is not None:
        conditions.append("i.semester_id = ?")
        params.append(semester_id)
    if student_id is not None:
        conditions.append("i.student_id = ?")
        params.append(student_id)
    if department_id is not None:
        conditions.append("s.department_id = ?")
        params.append(department_id)
    base = INVOICE_SELECT + where_clause(conditions)
    if status:
        # status is a computed column, so filter it one level up
        base = f"SELECT * FROM ({base}) WHERE status = ?"
        params.append(status)
    page = paginate(
        conn, base, params, list_args,
        search_columns=["invoice_no", "student_code", "student_name"],
        sort_columns=["id", "invoice_no", "student_code", "student_name", "semester_code", "total_amount",
                      "paid_amount", "due_amount", "due_date", "status"],
        default_sort="id",
    )
    for row in page["items"]:
        add_taka_fields(row, *INVOICE_MONEY)
    return page


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    """One invoice with its items and payments."""
    invoice = fetch_one(conn, INVOICE_SELECT + " WHERE i.id = ?", (invoice_id,))
    if invoice is None:
        return None
    add_taka_fields(invoice, *INVOICE_MONEY)
    invoice["items"] = [
        add_taka_fields(item, "amount")
        for item in fetch_all(
            conn,
            """SELECT ii.id, ii.fee_structure_id, ii.description, ii.amount
               FROM invoice_items ii WHERE ii.invoice_id = ? ORDER BY ii.id""",
            (invoice_id,),
        )
    ]
    invoice["payments"] = [
        add_taka_fields(payment, "amount")
        for payment in fetch_all(
            conn,
            """SELECT p.id, p.amount, p.method, p.transaction_ref, p.paid_at, u.email AS received_by_email
               FROM payments p JOIN users u ON u.id = p.received_by
               WHERE p.invoice_id = ? ORDER BY p.paid_at, p.id""",
            (invoice_id,),
        )
    ]
    return invoice


def insert_invoice(conn: sqlite3.Connection, student_id: int, semester_id: int, invoice_no: str,
                   total_paisa: int, due_date: str) -> int:
    """Create the invoice header (issued now) and return its id."""
    return execute(
        conn,
        """INSERT INTO invoices (student_id, semester_id, invoice_no, total_amount, issued_at, due_date)
           VALUES (?, ?, ?, ?, datetime('now'), ?)""",
        (student_id, semester_id, invoice_no, total_paisa, due_date),
    )


def insert_invoice_item(conn: sqlite3.Connection, invoice_id: int, fee_structure_id: int | None,
                        description: str, amount_paisa: int) -> int:
    """Add one line to an invoice."""
    return execute(
        conn,
        "INSERT INTO invoice_items (invoice_id, fee_structure_id, description, amount) VALUES (?, ?, ?, ?)",
        (invoice_id, fee_structure_id, description, amount_paisa),
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
PAYMENT_SELECT = """
SELECT
    p.id, p.invoice_id, i.invoice_no, i.student_id, s.student_code,
    s.first_name || ' ' || s.last_name AS student_name, i.semester_id, sem.code AS semester_code,
    p.amount, p.method, p.transaction_ref, p.paid_at, p.received_by, u.email AS received_by_email,
    p.created_at
FROM payments p
JOIN invoices  i   ON i.id   = p.invoice_id
JOIN students  s   ON s.id   = i.student_id
JOIN semesters sem ON sem.id = i.semester_id
JOIN users     u   ON u.id   = p.received_by
"""


def list_payments(conn: sqlite3.Connection, list_args: dict, semester_id: int | None = None,
                  method: str | None = None, invoice_id: int | None = None) -> dict:
    """One page of payments (newest first by default)."""
    conditions, params = [], []
    for column, value in (("i.semester_id", semester_id), ("p.method", method), ("p.invoice_id", invoice_id)):
        if value is not None and value != "":
            conditions.append(f"{column} = ?")
            params.append(value)
    if not list_args["sort"]:
        list_args = {**list_args, "sort": "paid_at", "order": "desc"}
    page = paginate(
        conn, PAYMENT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["invoice_no", "student_code", "student_name", "transaction_ref"],
        sort_columns=["id", "paid_at", "amount", "method", "invoice_no", "student_code"],
        default_sort="paid_at",
    )
    for row in page["items"]:
        add_taka_fields(row, "amount")
    return page


def get_payment(conn: sqlite3.Connection, payment_id: int) -> dict | None:
    """One payment."""
    row = fetch_one(conn, PAYMENT_SELECT + " WHERE p.id = ?", (payment_id,))
    return add_taka_fields(row, "amount") if row else None


def insert_payment(conn: sqlite3.Connection, invoice_id: int, amount_paisa: int, method: str,
                   transaction_ref: str | None, received_by: int) -> int:
    """
    Record a payment. trg_payment_update_invoice then recomputes the invoice's
    paid_amount and status, and trg_audit_payments_ins writes the audit row.
    """
    return execute(
        conn,
        "INSERT INTO payments (invoice_id, amount, method, transaction_ref, received_by) VALUES (?, ?, ?, ?, ?)",
        (invoice_id, amount_paisa, method, transaction_ref, received_by),
    )
