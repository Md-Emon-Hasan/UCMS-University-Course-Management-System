"""
Application settings.

All settings come from environment variables. For convenience we also read a
`.env` file in the project folder (see `.env.example`). We use a tiny
hand-written loader instead of an extra library, so there is nothing magic here.
"""

import os
from pathlib import Path

# Project root folder = the folder that contains `app/`, `sql/`, `scripts/` ...
BASE_DIR: Path = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    """
    Read simple KEY=VALUE lines from a .env file into os.environ.

    Real environment variables always win (we use setdefault), so you can
    still override anything from the command line.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


load_env_file(BASE_DIR / ".env")


def resolve_path(value: str) -> Path:
    """Turn a relative path from the settings into an absolute path inside BASE_DIR."""
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


# ---- Database ----
DB_PATH: Path = resolve_path(os.getenv("UCMS_DB_PATH", "ucms.db"))
SQL_DIR: Path = BASE_DIR / "sql"
BACKUP_DIR: Path = BASE_DIR / "backups"

# ---- Auth ----
JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

# ---- Web server ----
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
FRONTEND_DIR: Path = BASE_DIR / "frontend"
