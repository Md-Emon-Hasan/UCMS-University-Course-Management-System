"""Schemas for fee structures, invoices and payments. Amounts are sent in TAKA."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import PositiveTaka, StrictModel, Taka

FeeType = Literal["tuition", "admission", "lab", "library", "exam", "late_fine"]
PaymentMethod = Literal["cash", "bank", "bkash", "nagad", "card"]


class FeeStructureCreate(StrictModel):
    """Body of POST /api/fee-structures. department_id = null means "all departments"."""
    semester_id: int
    department_id: int | None = None
    fee_type: FeeType
    amount: Taka


class InvoiceGenerate(StrictModel):
    """
    Body of POST /api/invoices/generate.
    With student_id: one invoice. Without it: invoices for every student
    enrolled in that semester who does not have one yet.
    """
    semester_id: int
    student_id: int | None = None


class PaymentCreate(StrictModel):
    """Body of POST /api/payments."""
    invoice_id: int
    amount: PositiveTaka
    method: PaymentMethod
    transaction_ref: str | None = Field(default=None, min_length=3, max_length=50)

    @model_validator(mode="after")
    def reference_for_non_cash(self) -> "PaymentCreate":
        """Every method except cash leaves a transaction id, so require it."""
        if self.method != "cash" and not self.transaction_ref:
            raise ValueError("transaction_ref is required for non-cash payments")
        return self
