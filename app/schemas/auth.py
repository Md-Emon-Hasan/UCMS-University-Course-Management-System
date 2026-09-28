"""Schemas for login."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """
    Email + password. The email is a plain string here (not EmailStr): a
    login form should just say "wrong email or password", without hints.
    """
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)
