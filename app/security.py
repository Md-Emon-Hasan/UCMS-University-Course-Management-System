"""
Authentication (who are you?) and authorization (what may you do?).

- Passwords are stored as bcrypt hashes, never as plain text.
- After login the client gets a JWT (JSON Web Token), valid for 8 hours.
  It sends it back on every request:  Authorization: Bearer <token>
- require_role("admin", ...) is a FastAPI dependency that returns 403 if
  the logged-in user has a different role.
- The ensure_* helpers check OWNERSHIP ("a student may only see their own
  data"), which a role check alone cannot do.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app import config
from app.database import fetch_one, fetch_value, get_db

# bcrypt is deliberately slow, which makes guessing passwords expensive
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# auto_error=False: we raise our own 401 message instead of FastAPI's default 403
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """Return the bcrypt hash of a password."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a password against its stored hash."""
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    """
    Create a signed JWT. The payload is readable by anyone, but it cannot be
    changed without the secret key, because the signature would no longer match.
    """
    expires = datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "role": role, "exp": expires}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------
# One query loads the user plus their teacher/student profile (if any).
# LEFT JOIN: an admin has neither, so those columns come back as NULL.
CURRENT_USER_SQL = """
SELECT
    u.id, u.email, u.role, u.is_active, u.last_login_at,
    t.id AS teacher_id,
    s.id AS student_id,
    COALESCE(t.first_name || ' ' || t.last_name, s.first_name || ' ' || s.last_name) AS full_name,
    COALESCE(t.department_id, s.department_id) AS department_id
FROM users u
LEFT JOIN teachers t ON t.user_id = u.id
LEFT JOIN students s ON s.user_id = u.id
WHERE u.id = ?
"""


def load_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    """Load a user with profile ids. Admins/accountants get a name made from their email."""
    user = fetch_one(conn, CURRENT_USER_SQL, (user_id,))
    if user and not user["full_name"]:
        local_part = user["email"].split("@")[0]
        user["full_name"] = local_part.replace(".", " ").title()
    return user


def unauthorized(message: str) -> HTTPException:
    """Build a 401 error. The WWW-Authenticate header tells clients to use a Bearer token."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """
    FastAPI dependency: read the Bearer token, verify it, and load the user.
    Raises 401 if the token is missing, invalid or expired, or the user is disabled.
    """
    if credentials is None:
        raise unauthorized("Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized("Invalid or expired token")

    user = load_user(conn, user_id)
    if user is None or not user["is_active"]:
        raise unauthorized("User not found or disabled")
    return user


def require_role(*roles: str) -> Callable[..., dict]:
    """
    Build a dependency that only lets the given roles through.

        @router.post("/departments")
        def create(user: dict = Depends(require_role("admin"))): ...
    """
    def check_role(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"This action is only allowed for: {', '.join(roles)}")
        return user
    return check_role


# ---------------------------------------------------------------------------
# Ownership checks (admin may always pass)
# ---------------------------------------------------------------------------
def forbidden(message: str) -> HTTPException:
    """Build a 403 error."""
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def ensure_self_student(user: dict, student_id: int) -> None:
    """Admin, or the student whose data it is. Anyone else gets 403."""
    if user["role"] == "admin":
        return
    if user["role"] == "student" and user["student_id"] == student_id:
        return
    raise forbidden("You can only access your own student records")


def ensure_self_teacher(user: dict, teacher_id: int) -> None:
    """Admin, or the teacher themself."""
    if user["role"] == "admin":
        return
    if user["role"] == "teacher" and user["teacher_id"] == teacher_id:
        return
    raise forbidden("You can only access your own teacher records")


def ensure_teacher_owns_offering(conn: sqlite3.Connection, user: dict, offering_id: int) -> None:
    """Admin, or the teacher assigned to this offering. Raises 404 if the offering does not exist."""
    owner_id = fetch_value(conn, "SELECT teacher_id FROM course_offerings WHERE id = ?", (offering_id,))
    if owner_id is None:
        raise HTTPException(status_code=404, detail=f"Offering {offering_id} not found")
    if user["role"] == "admin":
        return
    if user["role"] == "teacher" and user["teacher_id"] == owner_id:
        return
    raise forbidden("You can only manage your own offerings")
