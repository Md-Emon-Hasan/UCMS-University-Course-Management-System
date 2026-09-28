"""Schemas for teachers."""

from datetime import date
from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.common import Name, Password, Phone, StrictModel

Designation = Literal["lecturer", "assistant_professor", "associate_professor", "professor"]
TeacherStatus = Literal["active", "on_leave", "resigned"]


class TeacherCreate(StrictModel):
    """Body of POST /api/teachers. Creates the login account AND the teacher row together."""
    email: EmailStr
    password: Password
    department_id: int
    employee_code: str = Field(pattern=r"^[A-Z0-9-]{3,20}$", examples=["EMP031"])
    first_name: Name
    last_name: Name
    phone: Phone | None = None
    designation: Designation
    hired_at: date
    status: TeacherStatus = "active"


class TeacherUpdate(StrictModel):
    """Body of PATCH /api/teachers/{id}. is_active switches the login account on or off."""
    department_id: int | None = None
    first_name: Name | None = None
    last_name: Name | None = None
    phone: Phone | None = None
    designation: Designation | None = None
    hired_at: date | None = None
    status: TeacherStatus | None = None
    is_active: bool | None = None
