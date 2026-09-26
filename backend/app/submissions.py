"""Projects uploaded by utilities outside the published plans (POST /submissions).

Pure functions, no database: `prepare_submission` turns an upload into rows the repository can
store, and `submitted_overlaps` finds the pairs those rows form, using the same engine the batch
load runs (pipeline/overlap.py), so an uploaded pair is scored exactly like a published one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

from app.schemas import Project
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import Project as EngineProject
from pipeline.overlap import detect_overlaps

# Server-assigned ids, so a submitted project or pair is recognisable anywhere (the frontend
# tags pairs whose id starts with SUBMITTED_OVERLAP_PREFIX). Published ids never use them.
SUBMITTED_ID_PREFIX = "SUB-"
SUBMITTED_OVERLAP_PREFIX = "SUB:"

# Uploaded coordinates are the submitter's own; nothing has matched them against OSM.
SUBMITTED_CONFIDENCE = "low"


class SubmissionConflict(ValueError):
    """The upload repeats a project that already exists; nothing from it is stored."""


def _fold(text: str) -> str:
    """Case- and spacing-blind key: "georgia  POWER " and "Georgia Power" are one utility."""
    return " ".join(text.split()).casefold()


def prepare_submission(
    submitted: Sequence[Project], existing: Sequence[Project], *, batch_id: str | None = None
) -> list[Project]:
    """Validate an upload against what is already stored and give it server ids.

    - The client's `project_id` is only its own reference; every project gets
      SUB-<batch>-<n> instead.
    - A utility that matches an existing one ignoring case and spacing takes the existing
      spelling. The engine compares utilities exactly, so without this "georgia power" would
      be flagged as overlapping Georgia Power.
    - Every project is marked location_confidence 'low' (SUBMITTED_CONFIDENCE).
    - The same utility + project name (ignoring case) may not already exist or appear twice
      in the upload: raises SubmissionConflict, and the caller stores nothing.
    """
    batch = batch_id or uuid4().hex[:8]
    utilities = {_fold(p.utility): p.utility for p in existing}
    stored = {(_fold(p.utility), _fold(p.project_name)) for p in existing}
    seen: set[tuple[str, str]] = set()

    prepared = []
    for n, project in enumerate(submitted, start=1):
        key = (_fold(project.utility), _fold(project.project_name))
        label = f"project {n} ({project.project_name.strip()!r} by {project.utility.strip()!r})"
        if key in stored:
            raise SubmissionConflict(f"{label} already exists")
        if key in seen:
            raise SubmissionConflict(f"{label} appears twice in this upload")
        seen.add(key)
        prepared.append(
            project.model_copy(
                update={
                    "project_id": f"{SUBMITTED_ID_PREFIX}{batch}-{n}",
                    "utility": utilities.setdefault(key[0], project.utility.strip()),
                    "project_name": project.project_name.strip(),
                    "location_confidence": SUBMITTED_CONFIDENCE,
                }
            )
        )
    return prepared


def _engine_project(project: Project) -> EngineProject:
    return EngineProject(
        project_id=project.project_id,
        utility=project.utility,
        lat_center=project.lat_center,
        lon_center=project.lon_center,
        in_service_date=project.in_service_date,
    )


def submitted_overlaps(
    published: Sequence[Project], submitted: Sequence[Project]
) -> list[EngineOverlap]:
    """Every flagged pair with at least one submitted project, id SUB:<a>|<b>.

    Published-only pairs are left out: those are already stored in project_overlaps.
    """
    submitted_ids = {p.project_id for p in submitted}
    if not submitted_ids:
        return []
    found = detect_overlaps(_engine_project(p) for p in [*published, *submitted])
    return [
        replace(o, overlap_id=f"{SUBMITTED_OVERLAP_PREFIX}{o.project_id_a}|{o.project_id_b}")
        for o in found
        if o.project_id_a in submitted_ids or o.project_id_b in submitted_ids
    ]
