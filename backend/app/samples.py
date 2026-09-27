"""The standing sample submissions: one made-up utility's projects, served to every visitor as
if someone had already uploaded them.

SAMPLE DATA, NOT A REAL UTILITY'S PUBLIC FILING ("Tallapoosa Grid Partners", see the note at the
top of sample_submissions.csv and docs/api.md "Standing sample submissions"). Never loaded into
the database: the API merges them in as uploads on every request, through the same path as a
visitor's own (prepare_submission -> submitted_overlaps -> ranked_overlaps), so they come out
with SUB- ids, location_confidence 'low' and the frontend's "Uploaded" tag.

The CSV lives in backend/app/, not data/seed/: the deployed API is built from backend/ alone
(.do/app.yaml `source_dir: backend`), so a file outside it would not exist in production.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from itertools import dropwhile
from pathlib import Path

from pydantic import ValidationError

from app.schemas import Project, UploadedProject
from app.submissions import SubmissionConflict, prepare_submission

SAMPLE_SUBMISSIONS_CSV = Path(__file__).with_name("sample_submissions.csv")

# Lines starting with this before the header row are the file's note, not data.
COMMENT_PREFIX = "#"


class SampleDataError(RuntimeError):
    """The sample file is broken, or clashes with the published plans: our bug, never a 4xx."""


def load_sample_submissions(path: Path = SAMPLE_SUBMISSIONS_CSV) -> list[UploadedProject]:
    """Every row of the sample CSV as an upload (client id = the row's project_id).

    Fails loud on the first bad row, an unknown column, an empty file, or two rows that
    would clash as uploads (same utility + name, or same id).
    """
    lines = dropwhile(
        lambda line: line.startswith(COMMENT_PREFIX),
        path.read_text(encoding="utf-8").splitlines(),
    )
    reader = csv.DictReader(lines)
    samples = []
    for n, row in enumerate(reader, start=1):
        if n == 1:
            unknown = set(reader.fieldnames or ()) - set(UploadedProject.model_fields)
            if unknown:
                raise SampleDataError(f"{path.name}: unknown column(s) {sorted(unknown)}")
        try:
            samples.append(UploadedProject.model_validate(row))
        except ValidationError as err:
            raise SampleDataError(f"{path.name} data row {n}: {err}") from err
    if not samples:
        raise SampleDataError(f"{path.name} has no rows")
    prepare_samples(samples, [])  # the rows must not clash with each other
    return samples


def prepare_samples(
    samples: Sequence[UploadedProject], published: Sequence[Project]
) -> list[Project]:
    """The samples as served uploads (prepare_submission), checked against the published plans.

    A clash here is the sample file's fault, not the visitor's: it raises SampleDataError (a
    500), never the SubmissionConflict that routes turn into a 409.
    """
    try:
        return prepare_submission(samples, published)
    except SubmissionConflict as err:
        raise SampleDataError(f"sample submissions: {err}") from err
