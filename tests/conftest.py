"""
Shared pytest fixtures.

Every test gets its OWN fresh database FILE (not ":memory:"). Two reasons:
  1. Tests never see each other's rows, so the order they run in does not matter.
  2. A file can be opened by several connections at once. The concurrency
     tests need that; every ":memory:" connection would be a separate database.

Speed trick: building the schema (6 SQL files) takes about 0.15 s. We build
it ONCE per test run into a template file, and each test gets a copy of it.

Fixtures (ask for them by name as a test argument):
    db_path   path of this test's fresh database (schema only, no rows)
    conn      an open connection to it
    world     the standard small data set (see tests/factory.py -> build_world)
    client    a FastAPI TestClient that talks to this test's database
    auth      auth("student") -> HTTP headers with a valid token for that world user
    seeded_db_path  ONE database with the full demo seed, shared by the whole run (read-only use!)
"""

import os
import shutil
import tempfile
from pathlib import Path

# Point the app at a throw-away path BEFORE it is imported, so a test can never
# touch your real ucms.db. (app/config.py reads UCMS_DB_PATH once, at import.)
os.environ["UCMS_DB_PATH"] = str(Path(tempfile.gettempdir()) / "ucms_pytest_unused.db")
os.environ["JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.database import get_connection  # noqa: E402
from app.main import app  # noqa: E402
from scripts.init_db import init_database  # noqa: E402
from scripts.seed import seed_database  # noqa: E402
from tests.factory import auth_headers, build_world  # noqa: E402


@pytest.fixture(scope="session")
def schema_template(tmp_path_factory) -> Path:
    """Build the full schema once per test run."""
    path = tmp_path_factory.mktemp("template") / "schema.db"
    init_database(path, verbose=False)
    return path


@pytest.fixture
def db_path(schema_template: Path, tmp_path: Path, monkeypatch) -> Path:
    """
    A fresh copy of the empty schema for this one test.

    config.DB_PATH is patched, so everything that opens "the" database
    (the API's get_db(), services called without a path) uses this file.
    That is the same thing setting UCMS_DB_PATH does when the app starts.
    """
    path = tmp_path / "test.db"
    shutil.copyfile(schema_template, path)
    monkeypatch.setattr(config, "DB_PATH", path)
    return path


@pytest.fixture
def conn(db_path: Path):
    """An open connection (foreign keys ON) to this test's database."""
    connection = get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def world(conn) -> dict:
    """The standard small data set. Returns a dict of ids."""
    return build_world(conn)


@pytest.fixture
def client(db_path: Path, world: dict):
    """A TestClient for the real FastAPI app, using this test's database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(world: dict):
    """
    auth("admin" | "teacher" | "student" | "accountant") -> Authorization headers
    for that role's user in the world. auth("other_student") / auth("other_teacher") also work.
    """
    users = {
        "admin": (world["admin_user_id"], "admin"),
        "accountant": (world["accountant_user_id"], "accountant"),
        "teacher": (world["teacher_user_id"], "teacher"),
        "other_teacher": (world["other_teacher_user_id"], "teacher"),
        "student": (world["student_user_id"], "student"),
        "other_student": (world["other_student_user_id"], "student"),
    }

    def headers(who: str) -> dict:
        user_id, role = users[who]
        return auth_headers(user_id, role)

    return headers


@pytest.fixture(scope="session")
def seeded_db_path(tmp_path_factory) -> Path:
    """
    The full demo data set (about 7 seconds to build), made once and shared.
    Tests that use it must only READ, because other tests see the same file.
    """
    path = tmp_path_factory.mktemp("seeded") / "seeded.db"
    init_database(path, verbose=False)
    seed_database(path)
    return path
