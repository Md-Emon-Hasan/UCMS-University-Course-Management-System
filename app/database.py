"""
Database helpers: connections, PRAGMAs, transactions and small query helpers.

Everything in the project talks to SQLite through the functions in this file.
We use ONLY Python's built-in `sqlite3` module (no ORM), so you can always see
the exact SQL that runs.

Main ideas (see LEARNING_NOTES.md for the long version):

1. `PRAGMA foreign_keys = ON` must be set on EVERY new connection.
   SQLite turns foreign keys OFF by default, for backward compatibility.
2. `isolation_level=None` puts the Python driver in "autocommit" mode.
   The driver then never starts transactions behind our back, and we write
   BEGIN / COMMIT / ROLLBACK ourselves.
3. `BEGIN IMMEDIATE` takes SQLite's write lock at the START of the transaction.
   This is how we replace `SELECT ... FOR UPDATE`, which SQLite does not have.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app import config


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Open a new SQLite connection with all our standard settings.

    Args:
        db_path: path of the database file. Defaults to config.DB_PATH.

    Returns:
        A ready-to-use sqlite3.Connection.
    """
    path = str(db_path or config.DB_PATH)

    conn = sqlite3.connect(
        path,
        isolation_level=None,      # we manage transactions manually
        check_same_thread=False,   # FastAPI may use the connection from a worker thread
        timeout=5,                 # seconds to wait if the database is locked
    )

    # Rows behave like dicts: row["email"] instead of row[1]
    conn.row_factory = sqlite3.Row

    # DB LESSON: foreign keys are OFF by default in SQLite.
    # This setting is per-connection, so we must run it every time.
    conn.execute("PRAGMA foreign_keys = ON")

    # DB LESSON: if another connection holds the write lock, wait up to
    # 5000 ms instead of failing immediately with "database is locked".
    conn.execute("PRAGMA busy_timeout = 5000")

    return conn


def enable_wal(conn: sqlite3.Connection) -> str:
    """
    Switch the database file to WAL (Write-Ahead Logging) mode.

    WAL lets readers keep reading while one writer writes. Unlike foreign_keys,
    this setting is stored IN the database file, so running it once at
    startup is enough.

    Returns:
        The journal mode SQLite reports back (should be "wal").
    """
    row = conn.execute("PRAGMA journal_mode = WAL").fetchone()
    return row[0]


def get_db() -> Iterator[sqlite3.Connection]:
    """
    FastAPI dependency: open one connection per request and always close it.

    Usage in a router:
        def my_endpoint(conn = Depends(get_db)): ...
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def set_actor(conn: sqlite3.Connection, user_id: int | None) -> None:
    """
    Remember which user is making the current change, for the audit triggers.

    The audit triggers read `(SELECT user_id FROM _audit_actor WHERE id = 1)`.

    DB LESSON: the spec wanted a TEMP table, but a normal trigger cannot see
    TEMP tables (SQLite looks for `main._audit_actor` and fails). So we use a
    normal one-row table. This is still safe: SQLite allows only ONE writer at
    a time, and we always write the actor inside our own write transaction.
    No other connection can change it until we COMMIT.
    """
    conn.execute(
        """
        INSERT INTO _audit_actor (id, user_id) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET user_id = excluded.user_id
        """,
        (user_id,),
    )


@contextmanager
def transaction(conn: sqlite3.Connection, actor_id: int | None = None) -> Iterator[sqlite3.Connection]:
    """
    Run a block of code inside one write transaction.

        with transaction(conn, actor_id=current_user_id):
            conn.execute("UPDATE ...")
            conn.execute("INSERT ...")

    - Starts with BEGIN IMMEDIATE, which takes the write lock right away.
    - Writes the actor into _audit_actor so the audit triggers know who did it.
    - Runs COMMIT if the block finishes normally.
    - Runs ROLLBACK if ANY exception happens, then re-raises the error.

    DB LESSON: plain `BEGIN` (deferred) only takes the write lock at the
    first write. Two transactions could both read "1 seat left", then both
    try to write. `BEGIN IMMEDIATE` makes the second one wait instead.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Always set the actor (even to NULL) so an old value is never reused.
        set_actor(conn, actor_id)
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# Small query helpers (they keep router/repository code short)
# ---------------------------------------------------------------------------

def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert one sqlite3.Row into a normal dict (or None)."""
    return dict(row) if row is not None else None


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple | list | dict = ()) -> dict[str, Any] | None:
    """Run a SELECT and return the first row as a dict, or None if there is no row."""
    return row_to_dict(conn.execute(sql, params).fetchone())


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple | list | dict = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return all rows as a list of dicts."""
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_value(conn: sqlite3.Connection, sql: str, params: tuple | list | dict = ()) -> Any:
    """Run a SELECT that returns one value (for example COUNT(*)) and return it."""
    row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def execute(conn: sqlite3.Connection, sql: str, params: tuple | list | dict = ()) -> int:
    """
    Run an INSERT/UPDATE/DELETE.

    Returns:
        For INSERT: the new row id (cursor.lastrowid).
        For UPDATE/DELETE: the number of changed rows.
    """
    cursor = conn.execute(sql, params)
    if sql.lstrip().upper().startswith("INSERT"):
        return cursor.lastrowid
    return cursor.rowcount


def where_clause(conditions: list[str]) -> str:
    """
    Join filter conditions into a WHERE clause.
        []                            -> ""
        ["a = ?", "b = ?"]            -> " WHERE a = ? AND b = ?"
    The conditions contain only ? placeholders; the values travel separately.
    """
    return (" WHERE " + " AND ".join(conditions)) if conditions else ""


def update_by_id(conn: sqlite3.Connection, table: str, row_id: int, changes: dict[str, Any],
                 id_column: str = "id") -> int:
    """
    Build and run:  UPDATE <table> SET col1 = ?, col2 = ? WHERE id = ?

    Only the VALUES are user input, and they go in as ? parameters. The table
    and column names come from our own code (Pydantic field names), never from
    the request, because names cannot be passed as ? parameters.

    Returns:
        The number of updated rows (0 if `changes` is empty or the id does not exist).
    """
    if not changes:
        return 0
    set_clause = ", ".join(f"{column} = ?" for column in changes)
    sql = f"UPDATE {table} SET {set_clause} WHERE {id_column} = ?"
    return conn.execute(sql, [*changes.values(), row_id]).rowcount


def run_sql_file(conn: sqlite3.Connection, path: str | Path) -> None:
    """
    Run a whole .sql file (many statements) with executescript().

    Note: executescript() first COMMITs any open transaction, then runs the
    file exactly as written. The file itself decides about BEGIN/COMMIT.
    """
    sql_text = Path(path).read_text(encoding="utf-8")
    conn.executescript(sql_text)
