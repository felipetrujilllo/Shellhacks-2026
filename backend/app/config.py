"""Runtime settings, read once from the environment (names match `.env.example`)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """A required setting is missing; the app refuses to start rather than guess."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    frontend_origin: str


def _required(environ: Mapping[str, str], name: str, hint: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise ConfigError(f"{name} is not set: {hint} (see .env.example)")
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build settings from `environ` (defaults to the process environment)."""
    env = os.environ if environ is None else environ
    return Settings(
        database_url=_required(env, "DATABASE_URL", "set it to the Postgres connection string"),
        frontend_origin=_required(
            env, "FRONTEND_ORIGIN", "set it to the frontend's origin, the only one CORS allows"
        ),
    )
