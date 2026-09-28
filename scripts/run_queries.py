"""
Run the practice queries in queries/*.sql and print each result as a table.

Usage (from the project folder):
    python scripts/run_queries.py                         # all 6 files
    python scripts/run_queries.py queries/05_window.sql   # one file
    python scripts/run_queries.py --rows 30               # show up to 30 rows per query

Why this script? Windows usually has no `sqlite3` command-line tool.
This gives you a one-command way to run and study every query.
(DB Browser for SQLite, https://sqlitebrowser.org, is a nice GUI alternative.)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection  # noqa: E402


def split_statements(sql_text: str) -> list[tuple[str, str]]:
    """
    Split a .sql file into (title, statement) pairs.

    sqlite3.complete_statement() tells us when the text collected so far
    ends with a full statement, which is safer than splitting on every ';'.
    The title is the nearest '-- Qnn.' comment line above the statement.
    """
    statements, buffer, title = [], [], "(untitled)"
    for line in sql_text.splitlines():
        stripped = line.strip()
        # A title looks like "-- Q12. ..." (Q followed by a digit)
        if stripped.startswith("-- Q") and stripped[4:5].isdigit():
            title = stripped[3:]
        buffer.append(line)
        text = "\n".join(buffer)
        if sqlite3.complete_statement(text):
            # Keep only real SQL (skip buffers that are only comments)
            code = "\n".join(l for l in buffer if l.strip() and not l.strip().startswith("--"))
            if code.strip():
                statements.append((title, text))
            buffer = []
    return statements


def format_table(columns: list[str], rows: list[tuple], max_rows: int) -> str:
    """Draw rows as a simple text table, cutting long cells."""
    shown = [["" if v is None else str(v)[:40] for v in row] for row in rows[:max_rows]]
    widths = [max([len(c)] + [len(r[i]) for r in shown]) for i, c in enumerate(columns)]
    line = "  ".join("-" * w for w in widths)
    out = ["  ".join(c.ljust(w) for c, w in zip(columns, widths)), line]
    out += ["  ".join(v.ljust(w) for v, w in zip(r, widths)) for r in shown]
    if len(rows) > max_rows:
        out.append(f"... ({len(rows) - max_rows} more rows)")
    return "\n".join(out)


def run_file(conn: sqlite3.Connection, path: Path, max_rows: int) -> tuple[int, int]:
    """Run every statement in one file. Returns (ok_count, error_count)."""
    ok, errors = 0, 0
    print(f"\n{'=' * 78}\n{path.name}\n{'=' * 78}")
    for title, statement in split_statements(path.read_text(encoding="utf-8")):
        print(f"\n>> {title}")
        try:
            cursor = conn.execute(statement)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            print(format_table(columns, [tuple(r) for r in rows], max_rows) if rows else "(no rows)")
            print(f"[{len(rows)} rows]")
            ok += 1
        except sqlite3.Error as error:
            print(f"ERROR: {error}")
            errors += 1
    return ok, errors


def main() -> int:
    """Command-line entry point. Returns the process exit code (1 if any query failed)."""
    parser = argparse.ArgumentParser(description="Run the UCMS practice queries.")
    parser.add_argument("files", nargs="*", help="query files (default: all queries/*.sql)")
    parser.add_argument("--rows", type=int, default=10, help="max rows to print per query")
    args = parser.parse_args()

    files = [Path(f) for f in args.files] or sorted((PROJECT_ROOT / "queries").glob("*.sql"))
    conn = get_connection()
    total_ok, total_errors = 0, 0
    try:
        for path in files:
            ok, errors = run_file(conn, path, args.rows)
            total_ok += ok
            total_errors += errors
    finally:
        conn.close()

    print(f"\nSummary: {total_ok} statements ran, {total_errors} errors.")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
