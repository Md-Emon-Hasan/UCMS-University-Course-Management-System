"""Schemas for semesters."""

from datetime import date

from pydantic import Field, model_validator

from app.schemas.common import StrictModel


class SemesterCreate(StrictModel):
    """
    Body of POST /api/semesters.
    The date rules repeat the table's CHECK constraints, so the user gets a
    clear per-field message instead of a raw database error.
    """
    name: str = Field(min_length=2, max_length=60, examples=["Fall 2026"])
    code: str = Field(pattern=r"^[A-Z]{3}[0-9]{2}$", examples=["FAL26"])
    start_date: date
    end_date: date
    registration_start: date
    registration_end: date

    @model_validator(mode="after")
    def check_dates(self) -> "SemesterCreate":
        """end_date > start_date and registration_end > registration_start."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.registration_end <= self.registration_start:
            raise ValueError("registration_end must be after registration_start")
        return self


class SemesterClose(StrictModel):
    """Body of POST /api/semesters/{id}/close."""
    next_semester_id: int
