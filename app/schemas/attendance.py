"""Schemas for attendance."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import StrictModel

AttendanceStatus = Literal["present", "absent", "late", "excused"]


class AttendanceRecord(StrictModel):
    """One student's attendance for the chosen date."""
    enrollment_id: int
    status: AttendanceStatus
    remarks: str | None = Field(default=None, max_length=200)


class AttendanceBulk(StrictModel):
    """Body of POST /api/offerings/{id}/attendance: the whole roster for ONE date."""
    class_date: date
    records: list[AttendanceRecord] = Field(min_length=1, max_length=500)

    @field_validator("class_date")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        """Attendance cannot be taken for a future class."""
        if value > date.today():
            raise ValueError("Attendance cannot be recorded for a future date")
        return value
