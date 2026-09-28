"""Schemas for announcements."""

from datetime import date

from pydantic import Field, field_validator

from app.schemas.common import Role, StrictModel


class AnnouncementCreate(StrictModel):
    """
    Body of POST /api/announcements.
    target_role / target_department_id = null means "everyone".
    expires_on: the announcement is hidden after the end of this day.
    """
    title: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=3, max_length=5000)
    target_role: Role | None = None
    target_department_id: int | None = None
    expires_on: date | None = None

    @field_validator("expires_on")
    @classmethod
    def not_in_past(cls, value: date | None) -> date | None:
        """An announcement that has already expired makes no sense."""
        if value is not None and value < date.today():
            raise ValueError("expires_on cannot be in the past")
        return value
