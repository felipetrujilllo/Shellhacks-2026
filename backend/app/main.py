"""FastAPI application factory.

Run from backend/ (env vars from the repo-root .env):

    uvicorn app.main:app --reload --env-file ../.env
"""

from __future__ import annotations

import logging
from functools import cache

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.repository import PostgresRepository
from app.routes import router

logger = logging.getLogger(__name__)

# docs/api.md promises exactly this body; the cause goes to the server log, never the client.
DATABASE_UNAVAILABLE = "database unavailable"


def database_unavailable(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
    """The database could not be reached (down, restarting, network blip): 503, not a bare 500.

    Only OperationalError: a query bug (ProgrammingError, e.g. a missing table) stays a 500.
    """
    logger.warning("%s %s: database unavailable: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": DATABASE_UNAVAILABLE})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="Relay API")
    app.add_exception_handler(psycopg.OperationalError, database_unavailable)
    app.state.repository = PostgresRepository(settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],  # POST: /workspace
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


@cache
def _default_app() -> FastAPI:
    return create_app()


def __getattr__(name: str):
    # `app` is built on first access (by uvicorn), so importing this module never needs
    # DATABASE_URL — tests build their own app via create_app(settings).
    if name == "app":
        return _default_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
