"""
Errors and how they are turned into JSON responses.

Every error the API returns looks like this:
    {"detail": "Human readable message", "errors": {"field_name": "message"}}
`errors` is only present when the problem belongs to a specific form field,
so the frontend can show it right under that input.
"""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("ucms")


class BusinessRuleError(Exception):
    """
    A business rule was broken, for example "Offering is full (40/40)".

    Args:
        message: text shown to the user.
        status_code: HTTP status (400 = bad request, 404 = not found, 409 = conflict).
        field: optional form field the error belongs to.
    """

    def __init__(self, message: str, status_code: int = 400, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.field = field


def not_found(entity: str, entity_id: object) -> BusinessRuleError:
    """Shortcut: raise not_found("Student", 5) -> 404 "Student 5 not found"."""
    return BusinessRuleError(f"{entity} {entity_id} not found", status_code=404)


def found_or_404(row: dict | None, entity: str, entity_id: object) -> dict:
    """Return the row, or raise 404 if the lookup found nothing."""
    if row is None:
        raise not_found(entity, entity_id)
    return row


# ---------------------------------------------------------------------------
# Friendly messages for database constraint errors.
# SQLite messages look like "UNIQUE constraint failed: users.email" or
# "CHECK constraint failed: chk_offering_not_over_capacity". We look for a
# known piece of text and replace it with (field, friendly message).
# ---------------------------------------------------------------------------
FRIENDLY_CONSTRAINT_MESSAGES: dict[str, tuple[str | None, str]] = {
    "users.email": ("email", "This email is already registered"),
    "departments.name": ("name", "A department with this name already exists"),
    "departments.code": ("code", "A department with this code already exists"),
    "teachers.employee_code": ("employee_code", "This employee code is already used"),
    "students.student_code": ("student_code", "This student code is already used"),
    "courses.code": ("code", "A course with this code already exists"),
    "semesters.code": ("code", "A semester with this code already exists"),
    "semesters.is_active": (None, "Another semester is already active"),
    "rooms.building, rooms.room_number": ("room_number", "This room number already exists in that building"),
    "course_offerings.course_id, course_offerings.semester_id, course_offerings.section":
        ("section", "This section already exists for the course in this semester"),
    "course_prerequisites.course_id, course_prerequisites.prerequisite_course_id":
        ("prerequisite_course_ids", "This prerequisite is already linked"),
    "invoices.student_id, invoices.semester_id": (None, "This student already has an invoice for this semester"),
    "invoices.invoice_no": (None, "This invoice number already exists"),
    "payments.transaction_ref": ("transaction_ref", "This transaction reference has already been used"),
    "fee_structures.semester_id": ("fee_type", "This fee type is already defined for that semester and department"),
    "attendance.enrollment_id, attendance.class_date": ("class_date", "Attendance for this date already exists"),
    "chk_offering_not_over_capacity": ("capacity", "Capacity cannot be lower than the number of enrolled students"),
    "chk_invoice_not_overpaid": ("amount", "Payment is larger than the amount still due"),
    "chk_prereq_not_self": ("prerequisite_course_ids", "A course cannot be its own prerequisite"),
    "chk_dropped_has_date": (None, "A dropped enrollment needs a drop date"),
}


def friendly_integrity_message(error: sqlite3.IntegrityError) -> tuple[str | None, str]:
    """Turn a raw SQLite constraint error into (field, message) for the user."""
    text = str(error)
    for key, (field, message) in FRIENDLY_CONSTRAINT_MESSAGES.items():
        if key in text:
            return field, message
    if text.startswith("FOREIGN KEY"):
        return None, "A referenced record does not exist, or this record is still in use elsewhere"
    if text.startswith("CHECK constraint failed"):
        return None, "Invalid value: " + text.split(": ", 1)[-1]
    if text.startswith("NOT NULL constraint failed"):
        column = text.split(": ", 1)[-1].split(".")[-1]
        return column, f"{column} is required"
    # Messages from our triggers (RAISE(ABORT, '...')) are already readable
    return None, text


def error_body(message: str, field: str | None = None) -> dict:
    """Build the standard error JSON body."""
    body: dict = {"detail": message}
    if field:
        body["errors"] = {field: message}
    return body


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
async def business_rule_handler(request: Request, exc: BusinessRuleError) -> JSONResponse:
    """BusinessRuleError -> its own status code (400/404/409)."""
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.message, exc.field))


async def integrity_error_handler(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
    """A database constraint or trigger rejected the data -> 409 Conflict."""
    field, message = friendly_integrity_message(exc)
    return JSONResponse(status_code=409, content=error_body(message, field))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Pydantic validation failed -> 422 with one message per field, e.g.
        {"detail": "Please fix the highlighted fields", "errors": {"capacity": "Input should be greater than 0"}}
    """
    errors: dict[str, str] = {}
    for err in exc.errors():
        parts = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        field = ".".join(parts) or "request"
        message = err["msg"].removeprefix("Value error, ")
        errors.setdefault(field, message)
    return JSONResponse(status_code=422, content={"detail": "Please fix the highlighted fields", "errors": errors})


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything else is a bug: log the details, but show only a generic message."""
    logger.exception("Unexpected error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all handlers to the FastAPI app (called from main.py)."""
    app.add_exception_handler(BusinessRuleError, business_rule_handler)
    app.add_exception_handler(sqlite3.IntegrityError, integrity_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
