"""
Billing (money in requests is TAKA; in the database and responses it is INTEGER paisa + *_taka text):
    GET  /api/fee-structures        (admin, accountant)
    POST /api/fee-structures        (admin, accountant)
    POST /api/invoices/generate     (admin, accountant)
    GET  /api/invoices              (admin, accountant)
    GET  /api/invoices/{id}         (admin, accountant, or the student it belongs to)
    POST /api/payments              (admin, accountant)
    GET  /api/payments              (admin, accountant)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import found_or_404
from app.pagination import list_params
from app.repositories import billing as repo
from app.repositories.departments import get_department
from app.repositories.semesters import get_semester
from app.schemas.billing import FeeStructureCreate, InvoiceGenerate, PaymentCreate
from app.schemas.common import taka_to_paisa
from app.security import ensure_self_student, get_current_user, require_role
from app.services.billing_service import generate_invoice, generate_invoices_for_semester, record_payment

router = APIRouter(tags=["billing"])
MONEY_ROLES = ("admin", "accountant")


# ---------------------------------------------------------------------------
# Fee structures
# ---------------------------------------------------------------------------
@router.get("/fee-structures")
def list_fee_structures(
    list_args: dict = Depends(list_params),
    semester_id: int | None = Query(None),
    department_id: int | None = Query(None),
    user: dict = Depends(require_role(*MONEY_ROLES)),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged price list."""
    return repo.list_fee_structures(conn, list_args, semester_id, department_id)


@router.post("/fee-structures", status_code=201)
def create_fee_structure(body: FeeStructureCreate, user: dict = Depends(require_role(*MONEY_ROLES)),
                         conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Add a fee row. department_id = null applies to every department."""
    found_or_404(get_semester(conn, body.semester_id), "Semester", body.semester_id)
    if body.department_id is not None:
        found_or_404(get_department(conn, body.department_id), "Department", body.department_id)
    with transaction(conn, user["id"]):
        fee_id = repo.insert_fee_structure(conn, body.semester_id, body.department_id, body.fee_type,
                                           taka_to_paisa(body.amount))
    return repo.get_fee_structure(conn, fee_id)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
@router.post("/invoices/generate", status_code=201)
def generate(body: InvoiceGenerate, user: dict = Depends(require_role(*MONEY_ROLES)),
             conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One invoice (with student_id), or all missing invoices of the semester (without it)."""
    if body.student_id is not None:
        return {"created": 1, "invoice": generate_invoice(conn, body.student_id, body.semester_id, user["id"])}
    return generate_invoices_for_semester(conn, body.semester_id, user["id"])


@router.get("/invoices")
def list_invoices(
    list_args: dict = Depends(list_params),
    semester_id: int | None = Query(None),
    student_id: int | None = Query(None),
    department_id: int | None = Query(None),
    status: str | None = Query(None, pattern="^(unpaid|partial|paid|overdue)$"),
    user: dict = Depends(require_role(*MONEY_ROLES)),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged invoices, filterable by semester, student, department and (effective) status."""
    return repo.list_invoices(conn, list_args, semester_id, student_id, status, department_id)


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user: dict = Depends(get_current_user),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One invoice with items and payments. A student may open only their own."""
    invoice = found_or_404(repo.get_invoice(conn, invoice_id), "Invoice", invoice_id)
    if user["role"] not in MONEY_ROLES:
        ensure_self_student(user, invoice["student_id"])
    return invoice


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@router.post("/payments", status_code=201)
def create_payment(body: PaymentCreate, user: dict = Depends(require_role(*MONEY_ROLES)),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Record a payment. Anything above the remaining due is rejected."""
    return record_payment(conn, body.invoice_id, taka_to_paisa(body.amount), body.method,
                          body.transaction_ref, user["id"])


@router.get("/payments")
def list_payments(
    list_args: dict = Depends(list_params),
    semester_id: int | None = Query(None),
    method: str | None = Query(None),
    invoice_id: int | None = Query(None),
    user: dict = Depends(require_role(*MONEY_ROLES)),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged payments, newest first."""
    return repo.list_payments(conn, list_args, semester_id, method, invoice_id)
