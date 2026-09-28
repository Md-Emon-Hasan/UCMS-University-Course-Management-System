"""Raw SQL for announcements."""

import sqlite3

from app.database import execute, fetch_one, where_clause
from app.pagination import paginate

ANNOUNCEMENT_SELECT = """
SELECT
    a.id, a.title, a.body, a.posted_by, u.email AS posted_by_email,
    a.target_role, a.target_department_id, d.code AS target_department_code,
    a.published_at, a.expires_at,
    (a.expires_at IS NOT NULL AND a.expires_at < datetime('now')) AS is_expired,
    a.created_at
FROM announcements a
JOIN users u ON u.id = a.posted_by
LEFT JOIN departments d ON d.id = a.target_department_id
"""


def list_announcements(conn: sqlite3.Connection, list_args: dict, user: dict,
                       include_expired: bool = False) -> dict:
    """
    Announcements the user may see, newest first.
    Admins see everything. Others only see announcements that are
      * for everyone or for their role,
      * for every department or for their own department,
      * already published and not expired.
    Note the "IS NULL OR ..." pattern: NULL means "no restriction".
    """
    conditions, params = [], []
    if user["role"] != "admin":
        conditions += [
            "(a.target_role IS NULL OR a.target_role = ?)",
            "(a.target_department_id IS NULL OR a.target_department_id = ?)",
            "a.published_at <= datetime('now')",
        ]
        params += [user["role"], user["department_id"]]
        include_expired = False
    if not include_expired:
        conditions.append("(a.expires_at IS NULL OR a.expires_at > datetime('now'))")
    if not list_args["sort"]:
        list_args = {**list_args, "sort": "published_at", "order": "desc"}
    return paginate(
        conn, ANNOUNCEMENT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["title", "body"],
        sort_columns=["id", "title", "published_at", "expires_at", "target_role"],
        default_sort="published_at",
    )


def get_announcement(conn: sqlite3.Connection, announcement_id: int) -> dict | None:
    """One announcement."""
    return fetch_one(conn, ANNOUNCEMENT_SELECT + " WHERE a.id = ?", (announcement_id,))


def insert_announcement(conn: sqlite3.Connection, data: dict, posted_by: int) -> int:
    """Create an announcement (published now) and return its id."""
    expires_at = f"{data['expires_on']} 23:59:59" if data.get("expires_on") else None
    return execute(
        conn,
        """INSERT INTO announcements (title, body, posted_by, target_role, target_department_id, expires_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["title"], data["body"], posted_by, data.get("target_role"),
         data.get("target_department_id"), expires_at),
    )
