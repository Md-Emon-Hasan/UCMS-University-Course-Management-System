"""Schemas for enrollments."""

from app.schemas.common import StrictModel


class EnrollRequest(StrictModel):
    """
    Body of POST /api/enrollments.
    A student enrolls themself, so student_id is ignored for them.
    An admin must say which student to enroll.
    """
    offering_id: int
    student_id: int | None = None
