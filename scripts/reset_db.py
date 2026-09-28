"""
Delete the database and build an empty one again.

Usage (from the project folder):
    python scripts/reset_db.py          # asks for confirmation
    python scripts/reset_db.py --yes    # no question (for scripts)

Note: in WAL mode SQLite uses 3 files: ucms.db, ucms.db-wal and ucms.db-shm.
All three must be removed, otherwise old data could come back from the -wal file.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402
from scripts.init_db import init_database, print_summary  # noqa: E402


def delete_database_files(db_path: Path) -> list[Path]:
    """
    Delete the database file and its WAL/SHM side files.

    Returns:
        The list of files that were actually deleted.
    """
    deleted = []
    for suffix in ("", "-wal", "-shm"):
        file = Path(str(db_path) + suffix)
        if file.exists():
            file.unlink()
            deleted.append(file)
    return deleted


def main() -> int:
    """Command-line entry point. Returns the process exit code."""
    db_path = config.DB_PATH

    if "--yes" not in sys.argv:
        answer = input(f"This will DELETE all data in {db_path.name}. Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            print("Cancelled. Nothing was changed.")
            return 1

    try:
        deleted = delete_database_files(db_path)
    except PermissionError:
        print("ERROR: the database file is in use. Stop the server (run.py) and try again.")
        return 1

    for file in deleted:
        print(f"Deleted  : {file.name}")

    init_database(db_path)
    print_summary(db_path)
    print("\nDatabase reset complete. Run `python scripts/seed.py` to add demo data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
