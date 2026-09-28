"""Raw SQL for audit_logs (read-only here: only triggers ever write to it)."""

import json
import sqlite3

from app.database import where_clause
from app.pagination import paginate

AUDIT_SELECT = """
SELECT
    a.id, a.table_name, a.record_id, a.action, a.old_data, a.new_data,
    a.changed_by, u.email AS changed_by_email, a.changed_at
FROM audit_logs a
LEFT JOIN users u ON u.id = a.changed_by       -- LEFT: changed_by can be NULL
"""


def list_audit_logs(conn: sqlite3.Connection, list_args: dict, table_name: str | None = None,
                    action: str | None = None, record_id: int | None = None,
                    changed_by: int | None = None, date_from: str | None = None,
                    date_to: str | None = None) -> dict:
    """
    One page of audit rows, newest first. old_data/new_data are JSON text in
    the database; here we parse them into real objects for the client.
    """
    conditions, params = [], []
    for column, value in (("a.table_name", table_name), ("a.action", action),
                          ("a.record_id", record_id), ("a.changed_by", changed_by)):
        if value is not None and value != "":
            conditions.append(f"{column} = ?")
            params.append(value)
    if date_from:
        conditions.append("a.changed_at >= ?")
        params.append(f"{date_from} 00:00:00")
    if date_to:
        conditions.append("a.changed_at <= ?")
        params.append(f"{date_to} 23:59:59")
    if not list_args["sort"]:
        list_args = {**list_args, "sort": "id", "order": "desc"}
    page = paginate(
        conn, AUDIT_SELECT + where_clause(conditions), params, list_args,
        search_columns=["table_name", "changed_by_email", "new_data", "old_data"],
        sort_columns=["id", "table_name", "record_id", "action", "changed_at"],
        default_sort="id",
    )
    for row in page["items"]:
        row["old_data"] = json.loads(row["old_data"]) if row["old_data"] else None
        row["new_data"] = json.loads(row["new_data"]) if row["new_data"] else None
    return page
