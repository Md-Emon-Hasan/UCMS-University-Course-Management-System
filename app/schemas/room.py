"""Schemas for rooms."""

from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel

RoomType = Literal["lecture", "lab", "seminar"]


class RoomCreate(StrictModel):
    """Body of POST /api/rooms."""
    building: str = Field(min_length=1, max_length=80)
    room_number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(gt=0, le=1000)
    room_type: RoomType


class RoomUpdate(StrictModel):
    """Body of PATCH /api/rooms/{id}."""
    building: str | None = Field(default=None, min_length=1, max_length=80)
    room_number: str | None = Field(default=None, min_length=1, max_length=20)
    capacity: int | None = Field(default=None, gt=0, le=1000)
    room_type: RoomType | None = None
