"""HTTP routes serving the contract in docs/api.md. Thin: all data comes from the repository."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.repository import Repository
from app.schemas import ErrorDetail, Health, Overlap, Project

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
