"""Settings come from the environment and fail loud when DATABASE_URL is missing."""

import importlib

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import ConfigError, Settings, load_settings

ENV = {"DATABASE_URL": "postgresql://localhost/tsdb", "FRONTEND_ORIGIN": "http://x.test"}


def test_load_settings_reads_env_var_names_from_env_example():
    assert load_settings(ENV) == Settings(
        database_url=ENV["DATABASE_URL"], frontend_origin=ENV["FRONTEND_ORIGIN"]
    )


def test_load_settings_defaults_to_process_environment(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    assert load_settings().database_url == ENV["DATABASE_URL"]


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_database_url_raises_clear_error(value):
    env = {**ENV, "DATABASE_URL": value} if value is not None else {
        k: v for k, v in ENV.items() if k != "DATABASE_URL"
    }
    with pytest.raises(ConfigError, match="DATABASE_URL is not set"):
        load_settings(env)


def test_missing_frontend_origin_raises_clear_error():
    with pytest.raises(ConfigError, match="FRONTEND_ORIGIN is not set"):
        load_settings({"DATABASE_URL": ENV["DATABASE_URL"]})


def test_create_app_without_database_url_fails_at_startup(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGIN", ENV["FRONTEND_ORIGIN"])
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        main.create_app()


def test_importing_main_does_not_need_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert importlib.reload(main).create_app is not None


def test_module_level_app_uses_env_frontend_origin(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    main._default_app.cache_clear()
    try:
        response = TestClient(main.app).get("/health", headers={"Origin": ENV["FRONTEND_ORIGIN"]})
    finally:
        main._default_app.cache_clear()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ENV["FRONTEND_ORIGIN"]
