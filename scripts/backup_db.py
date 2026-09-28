"""
Make a safe copy of the live database.

Usage (from the project folder):
    python scripts/backup_db.py                 # -> backups/ucms_YYYYmmdd_HHMMSS.db
    python scripts/backup_db.py my_copy.db      # -> a file name of your choice

WHY NOT JUST COPY THE FILE?
In WAL mode, recent changes may still sit in ucms.db-wal and not yet in
ucms.db. Copying only ucms.db while the server runs can give you an old or
even broken copy. SQLite's "online backup API" (conn.backup) copies a
consistent snapshot, even while other connections are reading and writing.
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402
from app.database import get_connection  # noqa: E402


def backup_database(target: Path | str | None = None) -> Path:
    """
    Copy the database into `target` using the SQLite backup API.

    Args:
        target: destination file. Default: backups/ucms_<timestamp>.db

    Returns:
        The path of the backup file.

    Raises:
        FileNotFoundError: if there is no database to back up.
    """
    if not config.DB_PATH.exists():
        raise FileNotFoundError(f"No database at {config.DB_PATH}. Run scripts/init_db.py first.")

    if target is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = config.BACKUP_DIR / f"ucms_{stamp}.db"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    source_conn = get_connection(config.DB_PATH)
    target_conn = get_connection(target)
    try:
        # pages=0 means "copy everything in one step"
        source_conn.backup(target_conn, pages=0)
    finally:
        target_conn.close()
        source_conn.close()

    # The copy should be a plain single file, so switch it from WAL back to
    # the default journal mode (this merges its own -wal file into it).
    copy_conn = get_connection(target)
    try:
        copy_conn.execute("PRAGMA journal_mode = DELETE")
        result = copy_conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        copy_conn.close()

    if result != "ok":
        raise RuntimeError(f"Backup integrity check failed: {result}")
    return target


def main() -> int:
    """Command-line entry point. Returns the process exit code."""
    target = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        path = backup_database(target)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"ERROR: {error}")
        return 1
    size_kb = path.stat().st_size / 1024
    print(f"Backup written: {path}  ({size_kb:,.0f} KB, integrity_check = ok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
