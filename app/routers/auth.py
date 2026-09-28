"""
/api/auth: login and "who am I".
    POST /api/auth/login
    GET  /api/auth/me
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db, transaction
from app.repositories.users import get_user_by_email, update_last_login
from app.schemas.auth import LoginRequest
from app.security import create_access_token, get_current_user, load_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Check email + password and return a JWT.
    Wrong email and wrong password give the SAME message, so an attacker cannot
    find out which emails exist.
    """
    user = get_user_by_email(conn, body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="This account is disabled. Please contact the admin.")

    with transaction(conn, actor_id=user["id"]):
        update_last_login(conn, user["id"])

    return {
        "access_token": create_access_token(user["id"], user["role"]),
        "token_type": "bearer",
        "role": user["role"],
        "user": load_user(conn, user["id"]),
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    """The logged-in user, with teacher_id / student_id / department_id if they have one."""
    return user
