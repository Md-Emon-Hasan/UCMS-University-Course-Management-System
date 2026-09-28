"""Schemas for courses and prerequisites."""

from pydantic import Field

from app.schemas.common import StrictModel


class CourseCreate(StrictModel):
    """Body of POST /api/courses."""
    department_id: int
    code: str = Field(pattern=r"^[A-Z]{2,6}[0-9]{3}$", examples=["CSE404"])
    title: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    credits: float = Field(gt=0, le=6)          # same rule as CHECK (credits > 0 AND credits <= 6)
    level: int = Field(ge=1, le=4)              # same rule as CHECK (level BETWEEN 1 AND 4)
    is_active: bool = True


class CourseUpdate(StrictModel):
    """Body of PATCH /api/courses/{id}."""
    department_id: int | None = None
    code: str | None = Field(default=None, pattern=r"^[A-Z]{2,6}[0-9]{3}$")
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    credits: float | None = Field(default=None, gt=0, le=6)
    level: int | None = Field(default=None, ge=1, le=4)
    is_active: bool | None = None


class PrerequisitesSet(StrictModel):
    """
    Body of POST /api/courses/{id}/prerequisites.
    The list REPLACES the course's prerequisites (an empty list removes them all).
    """
    prerequisite_course_ids: list[int] = Field(max_length=10)
