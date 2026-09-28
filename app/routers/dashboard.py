"""
/api/dashboard: role-aware numbers for the home page.
    GET /api/dashboard/stats
"""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import get_db
from app.repositories.announcements import list_announcements
from app.security import get_current_user
from app.services.report_service import dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """4 stat cards + 2 charts (trend line, distribution bar) + the 5 latest announcements."""
    data = dashboard_stats(conn, user)
    latest = list_announcements(conn, {"page": 1, "limit": 5, "search": "", "sort": "", "order": "desc"}, user)
    data["announcements"] = latest["items"]
    return data
