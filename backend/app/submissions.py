"""Projects a visitor uploaded, scored against the published plans on the fly (POST /workspace).

Pure functions, no database, nothing stored: uploads live in the visitor's own browser, which
sends them with every POST /workspace. `prepare_submission` validates them and gives them
their served ids, and `submitted_overlaps` finds the pairs they form, using the same engine the
batch load runs (pipeline/overlap.py), so an uploaded pair is scored exactly like a published one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.schemas import Project
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import Project as EngineProject
from pipeline.overlap import detect_overlaps

# Served ids, so an uploaded project or pair is recognisable anywhere (the frontend tags pairs
# whose id starts with SUBMITTED_OVERLAP_PREFIX). Published ids never use them.
SUBMITTED_ID_PREFIX = "SUB-"
SUBMITTED_OVERLAP_PREFIX = "SUB:"

# Uploaded coordinates are the uploader's own; nothing has matched them against OSM.
SUBMITTED_CONFIDENCE = "low"


class SubmissionConflict(ValueError):
    """The upload repeats a project that already exists, or repeats itself; -> 409."""


def _fold(text: str) -> str:
    """Case- and spacing-blind key: "georgia  POWER " and "Georgia Power" are one utility."""
    return " ".join(text.split()).casefold()


def submitted_id(client_id: str) -> str:
    """The served id of an upload: stable, because the browser keeps its client id for good."""
    return f"{SUBMITTED_ID_PREFIX}{client_id}"


def prepare_submission(submitted: Sequence[Project], existing: Sequence[Project]) -> list[Project]:
    """Validate an upload against the published plans and give it its served ids.

    - Each project's `project_id` is the id the browser gave it once, at import time (its
      shape is checked at the boundary, schemas.UPLOAD_ID_PATTERN); it is served as
      SUB-<client id>, so the same upload gets the same ids on every call.
    - A utility that matches an existing one ignoring case and spacing takes the existing
      spelling. The engine compares utilities exactly, so without this "georgia power" would
      be flagged as overlapping Georgia Power.
    - Every project is marked location_confidence 'low' (SUBMITTED_CONFIDENCE).
    - The same utility + project name (ignoring case) may not already exist or appear twice
      in the upload, and no client id may appear twice: raises SubmissionConflict.
    """
    utilities = {_fold(p.utility): p.utility for p in existing}
    stored = {(_fold(p.utility), _fold(p.project_name)) for p in existing}
    seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()

    prepared = []
    for n, project in enumerate(submitted, start=1):
        key = (_fold(project.utility), _fold(project.project_name))
        label = f"project {n} ({project.project_name.strip()!r} by {project.utility.strip()!r})"
        if key in stored:
            raise SubmissionConflict(f"{label} already exists")
        if key in seen:
            raise SubmissionConflict(f"{label} appears twice in this upload")
        if project.project_id in seen_ids:
            raise SubmissionConflict(f"{label} reuses the id {project.project_id!r}")
        seen.add(key)
        seen_ids.add(project.project_id)
        # A plain Project again (the request's id pattern only applies to client ids).
        prepared.append(
            Project.model_validate(
                {
                    **project.model_dump(),
                    "project_id": submitted_id(project.project_id),
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
