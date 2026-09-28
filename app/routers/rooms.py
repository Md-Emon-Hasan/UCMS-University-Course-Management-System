"""
/api/rooms
    GET   /api/rooms          (any logged-in user)
    POST  /api/rooms          (admin)
    GET   /api/rooms/{id}     (any logged-in user)
    PATCH /api/rooms/{id}     (admin)
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.database import get_db, transaction
from app.errors import found_or_404
from app.pagination import list_params
from app.repositories import rooms as repo
from app.schemas.room import RoomCreate, RoomUpdate
from app.security import get_current_user, require_role

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("")
def list_rooms(
    list_args: dict = Depends(list_params),
    room_type: str | None = Query(None),
    min_capacity: int | None = Query(None, ge=1),
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged list of rooms with this semester's weekly bookings."""
    return repo.list_rooms(conn, list_args, room_type, min_capacity)


@router.post("", status_code=201)
def create_room(body: RoomCreate, user: dict = Depends(require_role("admin")),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Add a room (building + room_number must be unique)."""
    with transaction(conn, user["id"]):
        room_id = repo.insert_room(conn, body.model_dump(mode="json"))
    return repo.get_room(conn, room_id)


@router.get("/{room_id}")
def get_room(room_id: int, user: dict = Depends(get_current_user),
             conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """One room."""
    return found_or_404(repo.get_room(conn, room_id), "Room", room_id)


@router.patch("/{room_id}")
def update_room(room_id: int, body: RoomUpdate, user: dict = Depends(require_role("admin")),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Change room fields."""
    found_or_404(repo.get_room(conn, room_id), "Room", room_id)
    with transaction(conn, user["id"]):
        repo.update_room(conn, room_id, body.model_dump(mode="json", exclude_unset=True))
    return repo.get_room(conn, room_id)
