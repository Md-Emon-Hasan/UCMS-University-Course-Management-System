"""Schemas for course offerings and their weekly schedules."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import StrictModel, TimeText

OfferingStatus = Literal["open", "closed", "cancelled"]


class OfferingCreate(StrictModel):
    """Body of POST /api/offerings."""
    course_id: int
    semester_id: int
    teacher_id: int
    section: str = Field(pattern=r"^[A-Z]{1,3}$", examples=["A"])
    capacity: int = Field(gt=0, le=500)
    status: OfferingStatus = "open"


class OfferingUpdate(StrictModel):
    """Body of PATCH /api/offerings/{id}."""
    teacher_id: int | None = None
    section: str | None = Field(default=None, pattern=r"^[A-Z]{1,3}$")
    capacity: int | None = Field(default=None, gt=0, le=500)
    status: OfferingStatus | None = None


class ScheduleCreate(StrictModel):
    """Body of POST /api/offerings/{id}/schedules. day_of_week: 0 = Sunday ... 6 = Saturday."""
    room_id: int
    day_of_week: int = Field(ge=0, le=6)
    start_time: TimeText
    end_time: TimeText

    @model_validator(mode="after")
    def end_after_start(self) -> "ScheduleCreate":
        """Same rule as CHECK (end_time > start_time)."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
