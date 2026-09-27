"""HTTP routes serving the contract in docs/api.md. Thin: all data comes from the repository."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.repository import Repository, ranked_overlaps
from app.samples import prepare_samples
from app.schemas import ErrorDetail, Health, Overlap, Project, Workspace, WorkspaceRequest
from app.submissions import SubmissionConflict, prepare_submission

router = APIRouter()


def get_repository(request: Request) -> Repository:
    """The repository `create_app` attached; tests replace this via dependency_overrides."""
    return request.app.state.repository


RepositoryDep = Annotated[Repository, Depends(get_repository)]


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@router.get("/projects", response_model=list[Project])
def list_projects(repository: RepositoryDep) -> list[Project]:
    return repository.list_projects()


@router.get("/overlaps", response_model=list[Overlap])
def list_overlaps(repository: RepositoryDep) -> list[Overlap]:
    # The contract promises rank 1 first; enforce it here rather than trust the source.
    return sorted(repository.list_overlaps(), key=lambda overlap: overlap.rank)


@router.get(
    "/overlaps/{overlap_id}",
    response_model=Overlap,
    responses={404: {"model": ErrorDetail}},
)
def get_overlap(overlap_id: str, repository: RepositoryDep) -> Overlap:
    overlap = repository.get_overlap(overlap_id)
    if overlap is None:
        raise HTTPException(status_code=404, detail=f"overlap {overlap_id} not found")
    return overlap


@router.post(
    "/workspace",
    response_model=Workspace,
    responses={409: {"model": ErrorDetail}},
)
def build_workspace(body: WorkspaceRequest, repository: RepositoryDep) -> Workspace:
    """The published plans, the sample submissions and the caller's own uploads, ranked together.

    Stores nothing: the uploads live in the caller's browser, which sends them again on every
    page load. They are checked against the published plans and the samples alike, so an
    upload repeating a sample is the same readable 409 as one repeating a published project.
    """
    published, stored = repository.published_plans()
    samples = prepare_samples(repository.sample_submissions(), published)
    try:
        uploaded = prepare_submission(body.projects, [*published, *samples])
    except SubmissionConflict as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return Workspace(
        projects=[*sorted(published, key=lambda p: p.project_id), *samples, *uploaded],
        overlaps=ranked_overlaps(stored, published, [*samples, *uploaded]),
    )
