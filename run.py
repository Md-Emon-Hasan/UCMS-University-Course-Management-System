"""
Start UCMS with one command:

    python run.py

- If ucms.db does not exist yet (or is empty), it is created and filled with demo data first.
- Then the web server starts at http://localhost:8000 (API docs at /docs).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn  # noqa: E402

from app import config  # noqa: E402
from app.database import fetch_value, get_connection  # noqa: E402
from scripts.init_db import init_database, list_tables  # noqa: E402
from scripts.seed import DEMO_PASSWORD, seed_database  # noqa: E402


def ensure_database() -> None:
    """Create the schema and seed demo data if the database is missing or empty."""
    conn = get_connection()
    try:
        has_tables = bool(list_tables(conn))
        has_users = has_tables and fetch_value(conn, "SELECT COUNT(*) FROM users") > 0
    finally:
        conn.close()

    if not has_tables:
        print("Creating the database schema ...")
        init_database(config.DB_PATH, verbose=False)
    if not has_users:
        print("Seeding demo data (takes a few seconds) ...")
        seed_database(config.DB_PATH)


def main() -> None:
    """Prepare the database, then run the web server."""
    ensure_database()
    host_for_link = "localhost" if config.HOST in ("127.0.0.1", "0.0.0.0") else config.HOST
    print(f"\nUCMS is running at http://{host_for_link}:{config.PORT}   (API docs: /docs)")
    print(f"Demo logins (password {DEMO_PASSWORD}): admin@ucms.edu, teacher@ucms.edu, "
          "student@ucms.edu, accountant@ucms.edu\n")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
