"""Guards for #8: the DigitalOcean App Platform spec must match the code it deploys.

These tests exist because nothing else notices when the spec and the app drift apart — a
renamed route, a new required setting or a moved build output only shows up as a failed
deploy (or worse, a green deploy serving a broken app). So each test resolves something out
of the spec and then checks it against the real thing: the FastAPI routes, load_settings(),
package.json, the git remote, CLAUDE.md.

yaml comes from uvicorn[standard], already a runtime dependency — no new package for tests.
"""

import importlib
import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings, load_settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / ".do" / "app.yaml"
SPEC_REL = ".do/app.yaml"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
README = REPO_ROOT / "README.md"

# Files DigitalOcean's Python buildpack looks for to recognize a Python component.
PYTHON_BUILDPACK_MARKERS = ("requirements.txt", "Pipfile", "setup.py")

SETTINGS = Settings(
    database_url="postgresql://localhost/never-connected", frontend_origin="http://x.test"
)


def load_spec() -> dict:
    assert SPEC_PATH.is_file(), f"{SPEC_REL} is missing: the app spec must be in the repo"
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def spec() -> dict:
    return load_spec()


@pytest.fixture(scope="module")
def api(spec) -> dict:
    """The one backend service component."""
    services = spec["services"]
    assert len(services) == 1, "expected exactly one service (the FastAPI backend)"
    return services[0]


@pytest.fixture(scope="module")
def web(spec) -> dict:
    """The one frontend static-site component."""
    sites = spec["static_sites"]
    assert len(sites) == 1, "expected exactly one static site (the Vite frontend)"
    return sites[0]


def env_map(component: dict) -> dict[str, dict]:
    envs = component.get("envs", [])
    keys = [entry["key"] for entry in envs]
    assert len(keys) == len(set(keys)), f"duplicate env keys in {component['name']}: {keys}"
    return {entry["key"]: entry for entry in envs}


def rule_for(spec: dict, component_name: str) -> dict:
    matching = [
        rule for rule in spec["ingress"]["rules"] if rule["component"]["name"] == component_name
    ]
    assert len(matching) == 1, f"expected one ingress rule for {component_name}"
    return matching[0]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def required_settings_names() -> list[str]:
    """Names load_settings() actually refuses to start without, discovered by asking it.

    Feeding it an empty environment and adding whatever it complains about is the only way
    to learn this without restating config.py's source in the test.
    """
    env: dict[str, str] = {}
    names: list[str] = []
    for _ in range(20):
        try:
            load_settings(env)
        except ConfigError as error:
            match = re.match(r"([A-Z0-9_]+) is not set", str(error))
            assert match, f"ConfigError no longer names the missing var: {error}"
            name = match.group(1)
            assert name not in env, f"load_settings() keeps rejecting {name}"
            names.append(name)
            env[name] = "placeholder"
        else:
            return names
    raise AssertionError("load_settings() requires more than 20 settings; something is wrong")


# --- the spec itself ------------------------------------------------------------------


def test_spec_is_version_controlled(spec):
    assert git("check-ignore", "-q", SPEC_REL).returncode == 1, (
        f"{SPEC_REL} must not be gitignored — the spec is the source of truth, not the console"
    )
    tracked_or_new = git("ls-files", "--cached", "--others", "--exclude-standard").stdout
    assert SPEC_REL in tracked_or_new.splitlines()


def test_spec_describes_both_components(api, web):
    assert api["name"] and web["name"]
    assert api["source_dir"] == "backend"
    assert web["source_dir"] == "frontend"
    for component in (api, web):
        source = REPO_ROOT / component["source_dir"]
        assert source.is_dir(), f"source_dir {component['source_dir']} does not exist"


def test_both_components_deploy_from_the_branch_claude_md_calls_demo_safe(api, web):
    text = CLAUDE_MD.read_text(encoding="utf-8")
    match = re.search(r"`([A-Za-z0-9._/-]+)` is the stable, demo-safe branch", text)
    assert match, "CLAUDE.md ## Branches no longer names the demo-safe branch"
    demo_branch = match.group(1)
    for component in (api, web):
        assert component["git"]["branch"] == demo_branch, (
            f"{component['name']} deploys from {component['git']['branch']!r}, but CLAUDE.md "
            f"says {demo_branch!r} is the demo-safe branch"
        )


def owner_repo(url: str) -> str | None:
    """`owner/repo` out of an https or ssh GitHub URL, with or without .git."""
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?\s*$", url.strip())
    return match.group(1) if match else None


def test_clone_url_matches_this_checkout(api, web):
    remote = git("remote", "get-url", "origin")
    if remote.returncode != 0:
        pytest.skip("no git remote named origin in this checkout")
    expected = owner_repo(remote.stdout)
    assert expected, f"could not read owner/repo out of {remote.stdout.strip()!r}"
    for component in (api, web):
        assert owner_repo(component["git"]["repo_clone_url"]) == expected


def test_clone_url_is_anonymous_https(api, web):
    """App Platform clones this with no credentials, which only works over https against a
    public repo. An ssh URL (git@github.com:...) would need a deploy key the spec doesn't
    have, and the build would fail at the clone step before anything useful happens."""
    for component in (api, web):
        url = component["git"]["repo_clone_url"]
        assert url.startswith("https://"), f"{component['name']} clones {url!r}, not https"
        assert "@" not in url, f"{component['name']} clone URL carries credentials: {url!r}"


def test_spec_holds_no_credentials():
    text = SPEC_PATH.read_text(encoding="utf-8")
    for token in ("postgres://", "postgresql://", "sslmode", "tsdb.cloud"):
        assert token not in text, f"{SPEC_REL} looks like it contains a connection string"


# --- backend component ---------------------------------------------------------------


def test_backend_source_dir_is_detectable_by_the_python_buildpack(api):
    source = REPO_ROOT / api["source_dir"]
    found = [name for name in PYTHON_BUILDPACK_MARKERS if (source / name).is_file()]
    assert found, (
        f"the buildpack needs one of {PYTHON_BUILDPACK_MARKERS} in {api['source_dir']}/; "
        "pyproject.toml alone is not detected"
    )


def test_requirements_txt_defers_to_pyproject_instead_of_duplicating_it():
    lines = [
        line.strip()
        for line in (REPO_ROOT / "backend" / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines == ["."], (
        "requirements.txt must install the local project ('.') so pyproject.toml stays the "
        f"only dependency list; found {lines}"
    )


def test_backend_run_command_binds_all_interfaces_and_the_platform_port(api):
    argv = shlex.split(api["run_command"])
    assert argv[0] == "uvicorn"
    assert "--host" in argv and argv[argv.index("--host") + 1] == "0.0.0.0", (
        "App Platform routes to the container from outside, so uvicorn must not bind localhost"
    )
    assert "--port" in argv and argv[argv.index("--port") + 1] == "$PORT", (
        "the port is assigned by the platform; hardcoding it breaks routing"
    )
    assert str(api["http_port"]) == "8080", "App Platform sets $PORT from http_port"


def test_backend_run_command_imports_an_asgi_app_that_exists(api, monkeypatch):
    target = shlex.split(api["run_command"])[1]
    module_name, sep, attr = target.partition(":")
    assert sep, f"run_command target {target!r} is not module:attribute"

    # The module builds the app lazily from the environment, so give it one.
    monkeypatch.setenv("DATABASE_URL", SETTINGS.database_url)
    monkeypatch.setenv("FRONTEND_ORIGIN", SETTINGS.frontend_origin)
    module = importlib.import_module(module_name)
    cache = getattr(module, "_default_app", None)
    if cache is not None:
        cache.cache_clear()
    try:
        asgi_app = getattr(module, attr)
        assert isinstance(asgi_app, FastAPI), f"{target} is not an ASGI app: {asgi_app!r}"
    finally:
        if cache is not None:
            cache.cache_clear()


def test_health_check_path_is_really_served(api):
    http_path = api["health_check"]["http_path"]
    response = TestClient(create_app(SETTINGS)).get(http_path)
    assert response.status_code == 200, (
        f"health_check.http_path {http_path!r} is not a route the app serves; the platform "
        "would restart the container forever"
    )
    assert response.json() == {"status": "ok"}


def test_backend_envs_are_exactly_the_settings_the_app_requires(api):
    required = set(required_settings_names())
    provided = set(env_map(api))
    assert required <= provided, (
        f"load_settings() requires {sorted(required - provided)}, which the spec never sets — "
        "the service would crash on boot"
    )
    assert provided <= required, (
        f"the spec sets {sorted(provided - required)} for the backend, which app/config.py "
        "does not read"
    )


def test_database_url_is_a_secret_with_no_value_in_the_repo(api):
    entry = env_map(api)["DATABASE_URL"]
    assert entry["type"] == "SECRET", "DATABASE_URL must be encrypted at rest by the platform"
    assert not entry.get("value"), (
        "DATABASE_URL must have no value here: the Tiger Data credential is set in the "
        "DigitalOcean console, never committed"
    )
    assert entry["scope"] == "RUN_TIME"


def test_no_env_value_hardcodes_a_url(api, web):
    for component in (api, web):
        for key, entry in env_map(component).items():
            value = entry.get("value")
            if not value:
                continue
            assert re.fullmatch(r"\$\{[A-Za-z0-9_.]+\}(/[A-Za-z0-9_./-]*)?", value), (
                f"{component['name']}.{key} = {value!r} should be a bindable platform "
                "variable, not a literal URL"
            )
            for literal in ("http://", "https://", "localhost", "ondigitalocean.app"):
                assert literal not in value, f"{component['name']}.{key} hardcodes {literal}"


# --- URL wiring between the two components -------------------------------------------


def test_frontend_origin_binds_to_the_app_url_which_the_static_site_owns(spec, api, web):
    assert env_map(api)["FRONTEND_ORIGIN"]["value"] == "${APP_URL}"
    assert rule_for(spec, web["name"])["match"]["path"]["prefix"] == "/", (
        "FRONTEND_ORIGIN = ${APP_URL} only holds while the static site is served at the "
        "app root; move it and the CORS origin stops matching the browser's"
    )


def test_frontend_api_url_binds_to_the_backend_component(api, web):
    entry = env_map(web)["VITE_API_URL"]
    expected = "${" + api["name"] + ".PUBLIC_URL}"
    assert entry["value"] == expected, (
        "VITE_API_URL must be derived from the backend component's public URL, not written out"
    )
    assert entry["scope"] == "BUILD_TIME", (
        "Vite inlines import.meta.env.VITE_* at build time; a RUN_TIME value never reaches "
        "the browser and frontend/src/api.ts would throw"
    )


def test_api_prefix_is_stripped_because_the_app_serves_routes_at_the_root(spec, api):
    rule = rule_for(spec, api["name"])
    prefix = rule["match"]["path"]["prefix"]
    assert prefix.startswith("/") and prefix != "/"
    assert not rule["component"].get("preserve_path_prefix", False), (
        f"the app serves /health, not {prefix}/health, so the prefix must be trimmed"
    )
    client = TestClient(create_app(SETTINGS))
    served = api["health_check"]["http_path"]
    assert client.get(served).status_code == 200
    assert client.get(f"{prefix}{served}").status_code == 404, (
        f"the app answers {prefix}{served}, so preserve_path_prefix should be revisited"
    )


def test_api_rule_is_matched_before_the_catch_all_root(spec, api, web):
    prefixes = [rule["match"]["path"]["prefix"] for rule in spec["ingress"]["rules"]]
    names = [rule["component"]["name"] for rule in spec["ingress"]["rules"]]
    assert names.index(api["name"]) < names.index(web["name"]), (
        f"the / rule shadows the API prefix; rules are {list(zip(names, prefixes, strict=True))}"
    )


# --- frontend component --------------------------------------------------------------


def test_frontend_build_command_is_a_script_package_json_defines(web):
    argv = shlex.split(web["build_command"])
    assert argv[:2] == ["npm", "run"], f"unexpected build command {web['build_command']!r}"
    scripts = json.loads(
        (REPO_ROOT / web["source_dir"] / "package.json").read_text(encoding="utf-8")
    )["scripts"]
    assert argv[2] in scripts, f"{web['source_dir']}/package.json has no {argv[2]!r} script"


def test_frontend_output_dir_matches_what_vite_actually_writes(web):
    vite_config = (REPO_ROOT / web["source_dir"] / "vite.config.ts").read_text(encoding="utf-8")
    custom = re.search(r"outDir\s*:\s*['\"]([^'\"]+)['\"]", vite_config)
    expected = custom.group(1) if custom else "dist"
    assert web["output_dir"] == expected, (
        f"output_dir is {web['output_dir']!r} but Vite writes to {expected!r}; the platform "
        "would publish an empty site"
    )
    built = REPO_ROOT / web["source_dir"] / web["output_dir"] / "index.html"
    if not built.is_file():
        pytest.skip(f"run `npm run build` in {web['source_dir']} to check the real output")
    assert built.stat().st_size > 0


# --- the procedure a human follows ---------------------------------------------------


def test_readme_documents_the_deploy_and_every_secret_it_needs(api, web):
    readme = README.read_text(encoding="utf-8")
    assert SPEC_REL in readme, f"README must point at {SPEC_REL}"
    for component in (api, web):
        for key, entry in env_map(component).items():
            if entry.get("type") == "SECRET":
                assert key in readme, (
                    f"{key} is a secret with no value in the spec, so README must say where "
                    "a human sets it"
                )

def test_readme_does_not_document_a_doctl_flag_that_does_not_exist():
    """`doctl apps update` takes --spec only; it has no --env. The README used to tell a
    teammate to pass the DATABASE_URL secret that way, which fails with `unknown flag: --env`
    at exactly the step where the deploy needs its credential. Verified against
    `doctl apps update --help` (1.175.0): --format, --no-header, --spec, --update-sources,
    --wait. The prose sentence saying the flag does not exist is allowed; an invocation is not.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    offenders = []
    for lineno, line in enumerate(readme.splitlines(), start=1):
        stripped = line.strip()
        is_invocation = stripped.startswith("doctl ") or stripped.startswith("--env")
        if is_invocation and "--env" in stripped:
            offenders.append(f"{lineno}: {stripped}")
    assert not offenders, (
        "README documents `--env` as a doctl argument, but no doctl apps command accepts it: "
        + "; ".join(offenders)
    )
