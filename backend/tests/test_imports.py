"""Guards the scaffold: Python version, local packages, and runtime deps all import."""

import importlib
import sys

import pytest

RUNTIME_DEPS = ["fastapi", "uvicorn", "pydantic", "psycopg", "httpx", "pdfplumber", "requests"]


def test_python_is_at_least_3_11():
    assert sys.version_info >= (3, 11)


@pytest.mark.parametrize("package", ["app", "pipeline"])
def test_local_packages_import(package):
    assert importlib.import_module(package) is not None


@pytest.mark.parametrize("module", RUNTIME_DEPS)
def test_runtime_dependency_imports(module):
    assert importlib.import_module(module) is not None


def test_psycopg_binary_backend_available():
    # psycopg[binary] ships the compiled implementation; plain psycopg would need libpq.
    import psycopg

    assert psycopg.pq.__impl__ in {"binary", "c"}
