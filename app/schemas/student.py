"""Schemas for students and their 1:1 profile."""

from datetime import date
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import Name, Password, Phone, StrictModel

StudentStatus = Literal["active", "suspended", "graduated", "dropped_out"]
Gender = Literal["male", "female", "other"]
BloodGroup = Literal["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]


class ProfileCreate(StrictModel):
    """Step 2 of the "new student" form: personal and guardian details."""
    date_of_birth: date
    gender: Gender
    blood_group: BloodGroup | None = None
    address_line: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=60)
    postal_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    guardian_name: Name
    guardian_phone: Phone
    guardian_relation: str = Field(min_length=2, max_length=40)

    @field_validator("date_of_birth")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        """A birth date cannot be in the future."""
        if value >= date.today():
            raise ValueError("Date of birth must be in the past")
        return value


class ProfileUpdate(StrictModel):
    """Profile fields for PATCH (all optional)."""
    date_of_birth: date | None = None
    gender: Gender | None = None
    blood_group: BloodGroup | None = None
    address_line: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=60)
    postal_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    guardian_name: Name | None = None
    guardian_phone: Phone | None = None
    guardian_relation: str | None = Field(default=None, min_length=2, max_length=40)


class StudentCreate(StrictModel):
    """Body of POST /api/students: account (step 1) + profile (step 2) in ONE request."""
    email: EmailStr
    password: Password
    department_id: int
    student_code: str = Field(pattern=r"^[A-Z0-9-]{4,20}$", examples=["CSE26061"])
    first_name: Name
    last_name: Name
    admission_date: date
    status: StudentStatus = "active"
    profile: ProfileCreate


class StudentUpdate(StrictModel):
    """Body of PATCH /api/students/{id}."""
    department_id: int | None = None
    first_name: Name | None = None
    last_name: Name | None = None
    admission_date: date | None = None
    status: StudentStatus | None = None
    is_active: bool | None = None
    profile: ProfileUpdate | None = None
