"""
Create a fresh ucms.db from the SQL files in the `sql/` folder.

Usage (from the project folder):
    python scripts/init_db.py

What it does:
    1. Refuses to touch a database that already has tables (use reset_db.py).
    2. Turns on WAL mode.
    3. Runs every sql/*.sql file in name order (01_..., 02_..., ...).
    4. Runs PRAGMA foreign_key_check to prove the data is consistent.
    5. Prints every table with its row count, plus the number of core tables.
"""

import sys
from pathlib import Path

# Allow "python scripts/init_db.py": put the project root on the import path
# so that "from app import ..." works.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402
from app.database import enable_wal, fetch_all, get_connection, run_sql_file  # noqa: E402

# Tables that are NOT part of the 21 core tables of the spec.
HELPER_TABLE_PREFIXES = ("sqlite_", "_", "mv_")


def list_tables(conn) -> list[str]:
    """Return the names of all tables in the database, sorted."""
    rows = fetch_all(conn, "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    return [row["name"] for row in rows]


def count_core_tables(table_names: list[str]) -> int:
    """Count tables that belong to the spec (skip sqlite_*, _helper and mv_ tables)."""
    return sum(1 for name in table_names if not name.startswith(HELPER_TABLE_PREFIXES))


def init_database(db_path: Path | str | None = None, verbose: bool = True) -> Path:
    """
    Build the full schema into a NEW database file.

    Args:
        db_path: where to create the database (default: config.DB_PATH).
        verbose: print progress messages.

    Returns:
        The path of the created database.

    Raises:
        RuntimeError: if the database already has tables, or the FK check fails.
    """
    path = Path(db_path or config.DB_PATH)
    conn = get_connection(path)
    try:
        if list_tables(conn):
            raise RuntimeError(
                f"{path.name} already has tables. Run `python scripts/reset_db.py` to start over."
            )

        mode = enable_wal(conn)
        if verbose:
            print(f"Database : {path}")
            print(f"Journal  : {mode}")

        sql_files = sorted(config.SQL_DIR.glob("*.sql"))
        for sql_file in sql_files:
            if verbose:
                print(f"Running  : sql/{sql_file.name}")
            run_sql_file(conn, sql_file)

        # executescript() may leave FKs in any state, so switch them back on to be safe
        conn.execute("PRAGMA foreign_keys = ON")

        # DB LESSON: foreign_key_check returns one row per broken reference.
        # An empty result means every FK in the database is satisfied.
        problems = fetch_all(conn, "PRAGMA foreign_key_check")
        if problems:
            raise RuntimeError(f"Foreign key check failed: {problems}")
    finally:
        conn.close()
    return path


def print_summary(db_path: Path | str | None = None) -> None:
    """Print each table with its row count, and prove the circular FK exists."""
    conn = get_connection(db_path)
    try:
        tables = list_tables(conn)
        print("\nTables:")
        for name in tables:
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            marker = "   (helper)" if name.startswith(HELPER_TABLE_PREFIXES) else ""
            print(f"  {name:<28} {count:>7} rows{marker}")

        print(f"\nCore tables: {count_core_tables(tables)} (expected 21)")

        # Count the other schema objects. Automatic indexes (made by UNIQUE /
        # PRIMARY KEY) are named sqlite_autoindex_..., so we skip those.
        for object_type, label in (("view", "Views"), ("trigger", "Triggers"), ("index", "Indexes")):
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
                (object_type,),
            ).fetchone()[0]
            print(f"{label + ':':<13}{count}")

        # Show that the rebuild really added departments.head_teacher_id -> teachers(id)
        fk_rows = fetch_all(conn, "PRAGMA foreign_key_list('departments')")
        for fk in fk_rows:
            print(
                f"Circular FK: departments.{fk['from']} -> {fk['table']}({fk['to']}) "
                f"ON DELETE {fk['on_delete']}"
            )
    finally:
        conn.close()


def main() -> int:
    """Command-line entry point. Returns the process exit code."""
    try:
        path = init_database()
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 1
    print_summary(path)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
