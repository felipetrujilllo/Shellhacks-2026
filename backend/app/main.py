"""FastAPI application factory.

Run from backend/ (env vars from the repo-root .env):

    uvicorn app.main:app --reload --env-file ../.env
"""

from __future__ import annotations

from functools import cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, load_settings
from app.repository import PostgresRepository
from app.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="Relay API")
    app.state.repository = PostgresRepository(settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],  # POST: /submissions
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
