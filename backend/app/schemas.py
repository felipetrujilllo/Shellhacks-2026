"""API contract: the JSON shapes every layer shares (see docs/api.md).

Field names match the `projects` / `project_overlaps` tables in db/schema.sql and the seed CSV
read by pipeline/load.py, so a row flows from CSV to database to API to frontend under one
vocabulary.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

# The overlap engine's radius; project_overlaps bounds distance_mi the same way.
from pipeline.overlap import OVERLAP_RADIUS_MI

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class Project(BaseModel):
    """One utility's planned transmission project — one row of `projects_seed.csv`.

    Only the center is required to locate a project; either endpoint may be unmatched.
    """

    project_id: str = Field(min_length=1)
    utility: str = Field(min_length=1)
    state: str = Field(min_length=1)
    project_name: str = Field(min_length=1)

    name_a: str | None = None
    lat_a: Latitude | None = None
    lon_a: Longitude | None = None
    name_b: str | None = None
    lat_b: Latitude | None = None
    lon_b: Longitude | None = None

    lat_center: Latitude
    lon_center: Longitude

    in_service_date: date
    # Whole dollars; null where the utility redacts the figure (all of Georgia Power).
    est_cost_usd: int | None = Field(default=None, ge=0)
    location_confidence: Literal["confirmed", "low"] = "confirmed"

    @field_validator("*", mode="before")
    @classmethod
    def blank_is_missing(cls, value, info: ValidationInfo):
        """A CSV leaves unmatched fields as empty strings; treat those as absent.

        Absent optional fields fall back to their default; absent required ones are rejected.
        """
        if isinstance(value, str) and not value.strip():
            field = cls.model_fields[info.field_name]
            return None if field.is_required() else field.get_default()
        return value

    @field_validator("in_service_date", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        """Only YYYY-MM-DD; pydantic alone would also take Unix timestamps."""
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value.strip())
        raise ValueError("in_service_date must be an ISO date (YYYY-MM-DD)")


class Overlap(BaseModel):
    """One flagged cross-utility pair, ranked for the 'top coordination opportunities' list.

    `score`, `distance_mi` and `time_gap_days` mean exactly what the overlap engine
    (pipeline/overlap.py) computes; `rank` is the 1-based position by descending score.
    """

    overlap_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    distance_mi: float = Field(ge=0, le=OVERLAP_RADIUS_MI)
    time_gap_days: int = Field(ge=0)
    project_a: Project
    project_b: Project


class Health(BaseModel):
    """Body of GET /health."""

    status: Literal["ok"]


class ErrorDetail(BaseModel):
    """Body of a 404 — FastAPI's default HTTPException shape."""

    detail: str
