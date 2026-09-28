"""Schemas for assessments and their results (marks)."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel

AssessmentType = Literal["quiz", "assignment", "midterm", "final", "project"]


class AssessmentCreate(StrictModel):
    """Body of POST /api/assessments."""
    offering_id: int
    title: str = Field(min_length=2, max_length=80)
    type: AssessmentType
    max_marks: float = Field(gt=0, le=1000)
    weight_percent: float = Field(gt=0, le=100)
    due_date: date


class ResultIn(StrictModel):
    """Marks of one student in one assessment."""
    enrollment_id: int
    marks_obtained: float = Field(ge=0)


class ResultsBulk(StrictModel):
    """Body of POST /api/assessments/{id}/results. All rows are saved together, or none."""
    results: list[ResultIn] = Field(min_length=1, max_length=500)
