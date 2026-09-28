"""
/api/audit-logs
    GET /api/audit-logs     (admin only)
"""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.pagination import list_params
from app.repositories.audit_logs import list_audit_logs
from app.security import require_role

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def audit_logs(
    list_args: dict = Depends(list_params),
    table_name: str | None = Query(None),
    action: str | None = Query(None, pattern="^(INSERT|UPDATE|DELETE)$"),
    record_id: int | None = Query(None),
    changed_by: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    user: dict = Depends(require_role("admin")),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paged audit history (written by triggers), with old/new data as JSON objects."""
    return list_audit_logs(
        conn, list_args, table_name, action, record_id, changed_by,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
