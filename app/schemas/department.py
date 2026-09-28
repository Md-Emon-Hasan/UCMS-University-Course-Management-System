"""Schemas for departments."""

from pydantic import Field

from app.schemas.common import StrictModel


class DepartmentCreate(StrictModel):
    """Body of POST /api/departments."""
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(pattern=r"^[A-Z]{2,6}$", examples=["CSE"])
    head_teacher_id: int | None = None
    is_active: bool = True


class DepartmentUpdate(StrictModel):
    """Body of PATCH /api/departments/{id}. Only the fields you send are changed."""
    name: str | None = Field(default=None, min_length=2, max_length=100)
    code: str | None = Field(default=None, pattern=r"^[A-Z]{2,6}$")
    head_teacher_id: int | None = None
    is_active: bool | None = None
