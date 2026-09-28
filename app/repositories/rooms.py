"""Raw SQL for rooms."""

import sqlite3

from app.database import execute, fetch_one, update_by_id, where_clause
from app.pagination import paginate

ROOM_SELECT = """
SELECT
    r.id, r.building, r.room_number, r.capacity, r.room_type,
    -- weekly classes booked in this room in the active semester
    (SELECT COUNT(*) FROM class_schedules cs
       JOIN course_offerings co ON co.id = cs.offering_id
       JOIN semesters sem ON sem.id = co.semester_id
      WHERE cs.room_id = r.id AND sem.is_active = 1) AS weekly_classes,
    r.created_at, r.updated_at
FROM rooms r
"""


def list_rooms(conn: sqlite3.Connection, list_args: dict, room_type: str | None = None,
               min_capacity: int | None = None) -> dict:
    """One page of rooms, with optional type and minimum-capacity filters."""
    conditions, params = [], []
    if room_type:
        conditions.append("r.room_type = ?")
        params.append(room_type)
    if min_capacity is not None:
        conditions.append("r.capacity >= ?")
        params.append(min_capacity)
    return paginate(
        conn, ROOM_SELECT + where_clause(conditions), params, list_args,
        search_columns=["building", "room_number"],
        sort_columns=["id", "building", "room_number", "capacity", "room_type", "weekly_classes"],
        default_sort="building",
    )


def get_room(conn: sqlite3.Connection, room_id: int) -> dict | None:
    """One room."""
    return fetch_one(conn, ROOM_SELECT + " WHERE r.id = ?", (room_id,))


def insert_room(conn: sqlite3.Connection, data: dict) -> int:
    """Create a room and return its id."""
    return execute(
        conn,
        "INSERT INTO rooms (building, room_number, capacity, room_type) VALUES (?, ?, ?, ?)",
        (data["building"], data["room_number"], data["capacity"], data["room_type"]),
    )


def update_room(conn: sqlite3.Connection, room_id: int, changes: dict) -> int:
    """Change some columns of a room."""
    return update_by_id(conn, "rooms", room_id, changes)
