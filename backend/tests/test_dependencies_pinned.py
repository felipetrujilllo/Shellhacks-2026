"""Guards for #31: every direct backend dependency is pinned to an exact version.

requirements.txt installs `.`, so pyproject.toml is the only place versions live. An unpinned
entry means every DigitalOcean rebuild and CI run resolves the newest release, and a breaking
FastAPI/pydantic release could take the live site down with no code change.

The installed-version test also catches drift the other way: a pin bumped in pyproject but
not installed (or a venv upgraded by hand) means the suite isn't running against what
production will install. Fix it with `pip install -e ".[dev]"`.

`packaging` is not a declared dependency; it is always present here because pytest depends
on it.
"""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def load_direct_requirements() -> list[str]:
    """Runtime dependencies plus the `dev` extra, as written in pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        project = tomllib.load(f)["project"]
    return [*project["dependencies"], *project["optional-dependencies"]["dev"]]


def exact_pin(spec: str) -> str | None:
    """Return the pinned version if `spec` is exactly one `==X.Y.Z` pin, else None.

    Rejects bare names, ranges (>=, ~=, <), arbitrary equality (===), wildcards (==1.*),
    multiple specifiers, and anything that doesn't parse as a requirement.
    """
    try:
        req = Requirement(spec)
    except InvalidRequirement:
        return None
    specifiers = list(req.specifier)
    if len(specifiers) != 1:
        return None
    (only,) = specifiers
    if only.operator != "==" or "*" in only.version:
        return None
    return only.version


def test_pyproject_lists_the_expected_dependency_groups():
    names = {Requirement(spec).name for spec in load_direct_requirements()}
    # Guards the parse itself: an empty list would make the pin checks below vacuous.
    assert {"fastapi", "uvicorn", "pydantic", "psycopg", "pytest", "ruff"} <= names


@pytest.mark.parametrize("spec", load_direct_requirements())
def test_every_direct_dependency_is_exactly_pinned(spec):
    assert exact_pin(spec) is not None, (
        f"{spec!r} in backend/pyproject.toml is not an exact `name==version` pin"
    )


@pytest.mark.parametrize("spec", load_direct_requirements())
def test_installed_version_matches_the_pin(spec):
    req = Requirement(spec)
    try:
        installed = version(req.name)
    except PackageNotFoundError:
        pytest.fail(f'{req.name} is pinned but not installed; run pip install -e ".[dev]"')
    assert installed == exact_pin(spec), (
        f"{req.name} {installed} is installed but pyproject pins {spec!r}; "
        'run pip install -e ".[dev]" (or update the pin after re-running the Checks)'
    )


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("fastapi==0.141.1", "0.141.1"),
        ("uvicorn[standard]==0.54.0", "0.54.0"),
        ("psycopg[binary] == 3.3.6", "3.3.6"),
    ],
)
def test_exact_pin_accepts_exact_pins_with_or_without_extras(spec, expected):
    assert exact_pin(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "fastapi",
        "uvicorn[standard]",
        "fastapi>=0.141.1",
        "fastapi~=0.141",
        "fastapi<1",
        "fastapi!=0.141.1",
        "fastapi===0.141.1",
        "fastapi==0.*",
        "fastapi==0.141.*",
        "fastapi==0.141.1,<1",
        "fastapi>=0.1,==0.141.1",
        "not a requirement ==",
    ],
)
def test_exact_pin_rejects_anything_but_a_single_exact_pin(spec):
    assert exact_pin(spec) is None
