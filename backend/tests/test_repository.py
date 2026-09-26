"""PostgresRepository's connection settings (the SQL itself needs a real database)."""

from app import repository
from app.repository import CONNECT_TIMEOUT_S, PostgresRepository


def test_connect_uses_a_timeout_so_an_unreachable_db_fails_fast(monkeypatch):
    calls = []
    monkeypatch.setattr(
        repository.psycopg, "connect", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    PostgresRepository("postgresql://localhost/never-connected")._connect()

    [(args, kwargs)] = calls
    assert args == ("postgresql://localhost/never-connected",)
    assert kwargs["connect_timeout"] == CONNECT_TIMEOUT_S
    assert 0 < CONNECT_TIMEOUT_S <= 10
