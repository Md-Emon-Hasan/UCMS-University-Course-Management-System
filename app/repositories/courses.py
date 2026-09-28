"""Raw SQL for courses and course_prerequisites (a SELF many-to-many)."""

import sqlite3

from app.database import execute, fetch_all, fetch_one, fetch_value, update_by_id, where_clause
from app.pagination import paginate

COURSE_SELECT = """
SELECT
    c.id, c.department_id, d.code AS department_code,
    c.code, c.title, c.description, c.credits, c.level, c.is_active,
    (SELECT COUNT(*) FROM course_prerequisites cp WHERE cp.course_id = c.id) AS prerequisite_count,
    (SELECT group_concat(p.code, ', ')
       FROM course_prerequisites cp JOIN courses p ON p.id = cp.prerequisite_course_id
      WHERE cp.course_id = c.id)                                            AS prerequisite_codes,
    c.created_at, c.updated_at
FROM courses c
JOIN departments d ON d.id = c.department_id
"""


def list_courses(conn: sqlite3.Connection, list_args: dict, department_id: int | None = None,
                 level: int | None = None, is_active: bool | None = None) -> dict:
    """One page of courses, with optional department, level and active filters."""
    conditions, params = [], []
    if department_id is not None:
        conditions.append("c.department_id = ?")
        params.append(department_id)
    if level is not None:
        conditions.append("c.level = ?")
        params.append(level)
    if is_active is not None:
        conditions.append("c.is_active = ?")
        params.append(1 if is_active else 0)
    return paginate(
        conn, COURSE_SELECT + where_clause(conditions), params, list_args,
        search_columns=["code", "title"],
        sort_columns=["id", "code", "title", "credits", "level", "department_code", "prerequisite_count"],
        default_sort="code",
    )


def get_course(conn: sqlite3.Connection, course_id: int) -> dict | None:
    """One course with its DIRECT prerequisites listed."""
    course = fetch_one(conn, COURSE_SELECT + " WHERE c.id = ?", (course_id,))
    if course is None:
        return None
    course["prerequisites"] = fetch_all(
        conn,
        """SELECT p.id, p.code, p.title, p.level, p.credits
           FROM course_prerequisites cp
           JOIN courses p ON p.id = cp.prerequisite_course_id
           WHERE cp.course_id = ?
           ORDER BY p.code""",
        (course_id,),
    )
    return course


def insert_course(conn: sqlite3.Connection, data: dict) -> int:
    """Create a course and return its id."""
    return execute(
        conn,
        """INSERT INTO courses (department_id, code, title, description, credits, level, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data["department_id"], data["code"], data["title"], data.get("description"),
         data["credits"], data["level"], data.get("is_active", True)),
    )


def update_course(conn: sqlite3.Connection, course_id: int, changes: dict) -> int:
    """Change some columns of a course."""
    return update_by_id(conn, "courses", course_id, changes)


# DB LESSON: a RECURSIVE CTE walks down the prerequisite links as deep as they go.
# "Is `target` somewhere below `start`?" means: follow start -> its prerequisites
# -> their prerequisites ... and see whether target appears.
REACHABLE_SQL = """
WITH RECURSIVE below(course_id) AS (
    SELECT prerequisite_course_id FROM course_prerequisites WHERE course_id = :start
    UNION
    SELECT cp.prerequisite_course_id
    FROM course_prerequisites cp
    JOIN below b ON cp.course_id = b.course_id
)
SELECT 1 FROM below WHERE course_id = :target LIMIT 1
"""


def would_create_cycle(conn: sqlite3.Connection, course_id: int, prerequisite_id: int) -> bool:
    """
    Adding "course needs prerequisite" makes a cycle if the course is already
    (directly or indirectly) a prerequisite OF that prerequisite.
    Example: CSE201 needs CSE101. Making CSE101 need CSE201 would be a loop.
    """
    if course_id == prerequisite_id:
        return True
    found = fetch_value(conn, REACHABLE_SQL, {"start": prerequisite_id, "target": course_id})
    return found is not None


def replace_prerequisites(conn: sqlite3.Connection, course_id: int, prerequisite_ids: list[int]) -> None:
    """Delete the old links and insert the new ones (the caller wraps this in a transaction)."""
    conn.execute("DELETE FROM course_prerequisites WHERE course_id = ?", (course_id,))
    for prerequisite_id in prerequisite_ids:
        conn.execute(
            "INSERT INTO course_prerequisites (course_id, prerequisite_course_id) VALUES (?, ?)",
            (course_id, prerequisite_id),
        )


# Every edge of the prerequisite tree below one course, with its depth.
# parent_id is the course that NEEDS the prerequisite (id).
TREE_SQL = """
WITH RECURSIVE tree(parent_id, id, depth) AS (
    SELECT course_id, prerequisite_course_id, 1
    FROM course_prerequisites
    WHERE course_id = ?
    UNION
    SELECT cp.course_id, cp.prerequisite_course_id, t.depth + 1
    FROM course_prerequisites cp
    JOIN tree t ON cp.course_id = t.id
    WHERE t.depth < 10                      -- safety stop
)
SELECT t.parent_id, t.id, t.depth, c.code, c.title, c.level, c.credits
FROM tree t
JOIN courses c ON c.id = t.id
ORDER BY t.depth, c.code
"""


def get_prerequisite_tree(conn: sqlite3.Connection, course_id: int) -> list[dict]:
    """All prerequisite links below a course, found with a recursive CTE."""
    return fetch_all(conn, TREE_SQL, (course_id,))


def get_required_by(conn: sqlite3.Connection, course_id: int) -> list[dict]:
    """Courses that list this course as a DIRECT prerequisite (the other direction of the self N:M)."""
    return fetch_all(
        conn,
        """SELECT c.id, c.code, c.title, c.level
           FROM course_prerequisites cp
           JOIN courses c ON c.id = cp.course_id
           WHERE cp.prerequisite_course_id = ?
           ORDER BY c.code""",
        (course_id,),
    )
