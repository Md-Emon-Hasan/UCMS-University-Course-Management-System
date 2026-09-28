"""
Shared paging / search / sorting for every list endpoint.

Every list endpoint accepts:   ?page=1&limit=20&search=&sort=&order=asc
and returns:                   {"items": [...], "total": 57, "page": 1, "limit": 20, "pages": 3}

How it works: the repository writes a normal SELECT (the "base query"), and
we wrap it as a sub-query:

    SELECT * FROM ( <base query> ) AS t
    WHERE t.name LIKE ? OR t.code LIKE ?      -- search
    ORDER BY t.<sort> ASC                     -- sort (whitelisted!)
    LIMIT ? OFFSET ?                          -- one page

Wrapping lets us search and sort on computed columns too (like full_name),
because the sub-query gives every column a simple name.
"""

import math
import sqlite3

from fastapi import Query

from app.database import fetch_all, fetch_value


def list_params(
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    limit: int = Query(20, ge=1, le=200, description="Rows per page"),
    search: str = Query("", max_length=100, description="Text to search for"),
    sort: str = Query("", max_length=50, description="Column to sort by"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="asc or desc"),
) -> dict:
    """FastAPI dependency that collects the standard list parameters into one dict."""
    return {"page": page, "limit": limit, "search": search.strip(), "sort": sort, "order": order}


def paginate(
    conn: sqlite3.Connection,
    base_sql: str,
    params: list,
    list_args: dict,
    search_columns: list[str],
    sort_columns: list[str],
    default_sort: str = "id",
) -> dict:
    """
    Run one page of `base_sql` and count all matching rows.

    Args:
        base_sql: a SELECT whose result has an `id` column plus the search/sort columns.
        params: values for the ? placeholders inside base_sql (for filters).
        list_args: the dict from list_params().
        search_columns: columns that `search` looks in (LIKE %text%).
        sort_columns: columns the client MAY sort by.
        default_sort: used when the client asks for no sort, or an unknown one.

    DB LESSON: values can be ? parameters, but column NAMES cannot. So the sort
    column is checked against a whitelist. Putting the client's text straight
    into "ORDER BY ..." would allow SQL injection.
    """
    values = list(params)
    where = ""
    if list_args["search"] and search_columns:
        where = " WHERE " + " OR ".join(f"t.{column} LIKE ?" for column in search_columns)
        values += [f"%{list_args['search']}%"] * len(search_columns)

    sort = list_args["sort"] if list_args["sort"] in sort_columns else default_sort
    order = "DESC" if list_args["order"] == "desc" else "ASC"
    # Add id as a tie-breaker so rows with equal sort values keep a stable order between pages
    order_by = f"t.{sort} {order}" + ("" if sort == "id" else ", t.id")

    total = fetch_value(conn, f"SELECT COUNT(*) FROM ({base_sql}) AS t{where}", values)
    page, limit = list_args["page"], list_args["limit"]
    items = fetch_all(
        conn,
        f"SELECT * FROM ({base_sql}) AS t{where} ORDER BY {order_by} LIMIT ? OFFSET ?",
        values + [limit, (page - 1) * limit],
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, math.ceil(total / limit)),
    }
