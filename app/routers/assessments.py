"""
Assessments and marks:
    POST /api/assessments                      (admin, owning teacher)
    GET  /api/offerings/{id}/assessments       (admin, owning teacher)
    POST /api/assessments/{id}/results         (admin, owning teacher; bulk marks)
    GET  /api/offerings/{id}/gradebook         (admin, owning teacher; the whole grid)
"""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import fetch_all, get_db, transaction
from app.errors import BusinessRuleError, found_or_404
from app.repositories import assessments as repo
from app.schemas.assessment import AssessmentCreate, ResultsBulk
from app.security import ensure_teacher_owns_offering, require_role

router = APIRouter(tags=["assessments"])


@router.post("/assessments", status_code=201)
def create_assessment(body: AssessmentCreate, user: dict = Depends(require_role("admin", "teacher")),
                      conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Add an assessment. The weights of an offering may never add up to more than 100%."""
    ensure_teacher_owns_offering(conn, user, body.offering_id)
    with transaction(conn, user["id"]):
        used = repo.weight_total(conn, body.offering_id)
        if used + body.weight_percent > 100 + 1e-9:
            raise BusinessRuleError(
                f"Weights would add up to {used + body.weight_percent:g}% "
                f"(already used {used:g}%, only {100 - used:g}% left)",
                field="weight_percent",
            )
        assessment_id = repo.insert_assessment(conn, body.model_dump(mode="json"))
    return repo.get_assessment(conn, assessment_id)


@router.get("/offerings/{offering_id}/assessments")
def list_assessments(offering_id: int, user: dict = Depends(require_role("admin", "teacher")),
                     conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Assessments of an offering and the total weight used so far."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    items = repo.list_for_offering(conn, offering_id)
    return {"items": items, "weight_total": sum(a["weight_percent"] for a in items)}


@router.post("/assessments/{assessment_id}/results")
def save_results(assessment_id: int, body: ResultsBulk, user: dict = Depends(require_role("admin", "teacher")),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    Save the marks of many students for one assessment, all or nothing.
    We check "marks <= max_marks" here for a clear per-row message, and the
    trigger trg_validate_marks_* enforces it again inside the database.
    """
    assessment = found_or_404(repo.get_assessment(conn, assessment_id), "Assessment", assessment_id)
    ensure_teacher_owns_offering(conn, user, assessment["offering_id"])

    enrollments = {row["id"]: row["status"] for row in fetch_all(
        conn, "SELECT id, status FROM enrollments WHERE offering_id = ?", (assessment["offering_id"],))}
    for index, result in enumerate(body.results):
        field = f"results.{index}.marks_obtained"
        if result.enrollment_id not in enrollments:
            raise BusinessRuleError(f"Enrollment {result.enrollment_id} is not in this offering",
                                    field=f"results.{index}.enrollment_id")
        if enrollments[result.enrollment_id] != "enrolled":
            raise BusinessRuleError(
                f"Enrollment {result.enrollment_id} is {enrollments[result.enrollment_id]}; its marks are locked",
                field=field)
        if result.marks_obtained > assessment["max_marks"]:
            raise BusinessRuleError(f"Marks {result.marks_obtained:g} exceed max_marks {assessment['max_marks']:g}",
                                    field=field)

    with transaction(conn, user["id"]):
        saved = repo.upsert_results(conn, assessment_id, [r.model_dump() for r in body.results], user["id"])
    return {"assessment_id": assessment_id, "saved": saved}


@router.get("/offerings/{offering_id}/gradebook")
def gradebook(offering_id: int, user: dict = Depends(require_role("admin", "teacher")),
              conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Assessments (columns) x students (rows) with marks and a weighted total."""
    ensure_teacher_owns_offering(conn, user, offering_id)
    return {"offering_id": offering_id, **repo.get_gradebook(conn, offering_id)}
