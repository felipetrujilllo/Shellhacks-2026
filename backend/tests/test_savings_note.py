"""The Snowflake savings note (pipeline/savings_note.py): Cortex writes text, never numbers.

Every test here runs without a Snowflake key: the model is a fake callable, and CortexClient is
driven through a fake HTTP session. The single live test at the bottom is opt-in.
"""

import logging
import os
from dataclasses import replace
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

from pipeline.overlap import Overlap
from pipeline.savings import estimate_savings
from pipeline.savings_note import (
    ACCOUNT_URL_ENV,
    CHAT_COMPLETIONS_PATH,
    DEFAULT_MODEL,
    MAX_NOTE_CHARS,
    MODEL_ENV,
    TOKEN_ENV,
    CortexClient,
    CortexError,
    NoteInputs,
    SavingsNote,
    cortex_client_from_env,
    write_savings_note,
)

LOGGER = "pipeline.savings_note"
DESC = "Dominion Energy South Carolina"
GPC = "Georgia Power"
DESC_3_COST = 23_787_423
FAKE_TOKEN = "not-a-real-token-" + "x" * 8
FAKE_URL = "https://example-account.snowflakecomputing.com"


def desc_vs_gpc_inputs(cost: int | None = DESC_3_COST) -> NoteInputs:
    """A realistic pair: the numbers come from the real deterministic estimate."""
    overlap = Overlap("OVL_1", "DESC_3", "GPC_2", 5.65, 152, 0.5)
    estimate = estimate_savings(overlap, cost, None, utility_a=DESC, utility_b=GPC)
    return NoteInputs(
        distance_mi=overlap.distance_mi,
        time_gap_days=overlap.time_gap_days,
        est_savings_usd=estimate.est_savings_usd,
        savings_basis=estimate.savings_basis,
        project_a_name="Jasper – Yemassee 230 kV",
        utility_a=DESC,
        project_b_name="Bainbridge – Hopeful 115 kV",
        utility_b=GPC,
    )


class FakeModel:
    """Stands in for Cortex: records the prompt and returns canned text (or raises)."""

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def good_note(inputs: NoteInputs) -> str:
    return (
        f"These projects are {inputs.distance_mi:g} miles apart and finish "
        f"{inputs.time_gap_days} days apart, so sharing crews and equipment could save "
        f"about ${inputs.est_savings_usd:,}."
    )


def fallback_warnings(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == LOGGER and r.levelno >= logging.WARNING
    ]


# --- mocked client: the note is used and the numbers never change ---------------------------


def test_mocked_cortex_note_is_used_and_numbers_are_untouched(caplog):
    inputs = desc_vs_gpc_inputs()
    before = replace(inputs)
    model = FakeModel(good_note(inputs))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, model)

    assert isinstance(result, SavingsNote)
    assert result.source == "cortex"
    assert result.note == good_note(inputs)
    assert result.inputs is inputs
    assert result.inputs == before
    assert (result.inputs.distance_mi, result.inputs.time_gap_days) == (5.65, 152)
    assert result.inputs.est_savings_usd == before.est_savings_usd
    assert result.inputs.savings_basis == before.savings_basis
    assert fallback_warnings(caplog) == []


def test_prompt_hands_the_model_the_deterministic_numbers():
    inputs = desc_vs_gpc_inputs()
    model = FakeModel(good_note(inputs))

    write_savings_note(inputs, model)

    (prompt,) = model.prompts
    assert "5.65 miles" in prompt
    assert "152" in prompt
    assert f"${inputs.est_savings_usd:,}" in prompt
    assert inputs.savings_basis in prompt
    assert "Jasper – Yemassee 230 kV" in prompt


def test_prompt_says_there_is_no_dollar_figure_when_no_cost_is_known():
    inputs = desc_vs_gpc_inputs(cost=None)
    model = FakeModel("Neither project has a published cost, so no savings figure is given.")

    result = write_savings_note(inputs, model)

    assert "no dollar figure" in model.prompts[0]
    assert result.source == "cortex"
    assert result.inputs.est_savings_usd is None


def test_whitespace_in_the_model_text_is_collapsed():
    inputs = desc_vs_gpc_inputs()
    model = FakeModel("  Sharing crews could help.\n\nThey are 5.65 miles apart.  ")

    result = write_savings_note(inputs, model)

    assert result.note == "Sharing crews could help. They are 5.65 miles apart."


@pytest.mark.parametrize(
    "note",
    [
        "Coordinating could save about $1.2 million.",  # rounded estimate
        "Coordinating could save roughly $1,187,000.",  # exact estimate
        "Coordinating could save about $1,190,000.",  # rounded to the nearest $10,000
        "Coordinating could save about 1.2 million dollars.",  # estimate in words-and-digits
        "They sit 6 miles apart, so crews could be shared.",  # distance rounded to a mile
        "They sit 5.7 miles apart, 152 days between in-service dates.",  # one decimal
        "Sharing 5% of mobilization is the assumption.",  # a percentage from the basis
        # Numbers in project names must not trip the checks.
        "Coordinating the Jasper-Yemassee 230 kV #2 and 115kV lines could save $1,187,000.",
    ],
)
def test_honest_rounding_is_accepted(note):
    inputs = NoteInputs(
        distance_mi=5.65,
        time_gap_days=152,
        est_savings_usd=1_187_000,
        savings_basis="Assumed shared mobilization of 5% of project A's $23,787,423 cost.",
    )

    result = write_savings_note(inputs, FakeModel(note))

    assert result.source == "cortex"
    assert result.note == note


# --- bad model output: fall back to savings_basis, loudly -----------------------------------


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("", "empty"),
        ("   \n  ", "empty"),
        ("Sharing crews helps. " * 40, "limit"),
        ("Coordinating could save $5,000,000.", "dollar amount"),
        ("Coordinating could save about $3 million.", "dollar amount"),
        # The project cost is in the basis, but a note must never show it: a model can present
        # it as the saving, ~33x the real $709,900 estimate.
        ("The $23,787,423 project could share mobilization.", "dollar amount"),
        ("Coordinating could save about $23.8 million.", "dollar amount"),
        # Rounded further than the digits shown, or more than 5% off, is not the estimate.
        ("Coordinating could save about $745,000.", "dollar amount"),
        ("Coordinating could save about $1 million.", "dollar amount"),
        ("Coordinating could save about $0.8 million.", "dollar amount"),
        # Money written without a leading "$" is still checked, or rejected when it can't be.
        ("Coordinating could save 5 million dollars.", "dollar amount"),
        ("Coordinating could save USD 5,000,000.", "dollar amount"),
        ("Coordinating could save 5,000,000 USD.", "dollar amount"),
        ("Coordinating could save $-709,900.", "dollar amount"),
        ("Coordinating could save $.5 million.", "dollar amount"),
        ("Coordinating could save €709,900.", "money wording"),
        ("Coordinating could save five million dollars.", "money wording"),
        ("Coordinating could save 99% of costs.", "99%"),
        ("The projects are 12 miles apart.", "distance"),
        ("The projects are 6.1 miles apart.", "distance"),  # 6.1 is no rounding of 5.65
        ("They finish 400 days apart.", "days"),
        ("They finish about 5 months apart.", "can't verify"),
        ("They finish two years apart.", "can't verify"),
        ("They finish five months apart.", "can't verify"),
        ("The projects are 9 km apart.", "can't verify"),
        # Found by the second gate: hyphenated and larger worded quantities, plural money
        # words, a leading minus, bare magnitudes, other currency words.
        ("They have a two-month gap.", "can't verify"),
        ("It is a six-mile hop.", "can't verify"),
        ("They are fifteen miles apart.", "can't verify"),
        ("They finish ninety days apart.", "can't verify"),
        ("Coordinating could save millions.", "money wording"),
        ("Coordinating could save hundreds of thousands.", "money wording"),
        ("Coordinating could save -$709,900.", "dollar amount"),
        ("Coordinating could save 23.8M.", "money wording"),
        ("Coordinating could save 750K.", "money wording"),
        ("Coordinating could save 709,900 euros.", "money wording"),
    ],
)
def test_bad_model_text_falls_back_to_savings_basis_with_a_warning(caplog, reply, reason):
    inputs = desc_vs_gpc_inputs()
    before = replace(inputs)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, FakeModel(reply))

    assert result.source == "fallback"
    assert result.note == inputs.savings_basis
    assert result.inputs == before
    (warning,) = fallback_warnings(caplog)
    assert "rejected" in warning and reason in warning


@pytest.mark.parametrize("reply", [None, 42, b"bytes are not text"])
def test_a_client_that_returns_something_other_than_text_falls_back(caplog, reply):
    inputs = desc_vs_gpc_inputs()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, FakeModel(reply))

    assert (result.source, result.note) == ("fallback", inputs.savings_basis)
    (warning,) = fallback_warnings(caplog)
    assert "not text" in warning


def test_the_prompt_forbids_repeating_the_project_cost():
    model = FakeModel(good_note(desc_vs_gpc_inputs()))
    write_savings_note(desc_vs_gpc_inputs(), model)
    assert "do not repeat project costs" in model.prompts[0]


def test_overlong_limit_is_the_documented_one():
    inputs = desc_vs_gpc_inputs()
    assert write_savings_note(inputs, FakeModel("a" * MAX_NOTE_CHARS)).source == "cortex"
    assert write_savings_note(inputs, FakeModel("a" * (MAX_NOTE_CHARS + 1))).source == "fallback"


def test_any_dollar_figure_is_rejected_when_there_is_no_estimate(caplog):
    inputs = desc_vs_gpc_inputs(cost=None)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, FakeModel("This could save around $250,000."))

    assert result.source == "fallback"
    assert result.note == inputs.savings_basis
    assert result.inputs.est_savings_usd is None
    assert "dollar amount" in fallback_warnings(caplog)[0]


# --- no key or an error: fall back to savings_basis, loudly ---------------------------------


def test_no_client_falls_back_to_savings_basis_with_a_warning(caplog):
    inputs = desc_vs_gpc_inputs()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, None)

    assert result == SavingsNote(inputs, inputs.savings_basis, "fallback")
    (warning,) = fallback_warnings(caplog)
    assert "not configured" in warning


@pytest.mark.parametrize(
    "error",
    [
        CortexError("HTTP 503: service unavailable"),
        CortexError("timed out after 20s"),
        RuntimeError("something unexpected"),
    ],
)
def test_client_error_falls_back_to_savings_basis_with_a_warning(caplog, error):
    inputs = desc_vs_gpc_inputs()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = write_savings_note(inputs, FakeModel(error=error))

    assert result.source == "fallback"
    assert result.note == inputs.savings_basis
    (warning,) = fallback_warnings(caplog)
    assert "Cortex call failed" in warning and str(error) in warning


def test_missing_env_gives_no_client_and_a_warning_naming_the_variable(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        client = cortex_client_from_env({ACCOUNT_URL_ENV: FAKE_URL})

    assert client is None
    (warning,) = fallback_warnings(caplog)
    assert TOKEN_ENV in warning


def test_empty_env_gives_no_client(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert cortex_client_from_env({ACCOUNT_URL_ENV: " ", TOKEN_ENV: ""}) is None
    (warning,) = fallback_warnings(caplog)
    assert ACCOUNT_URL_ENV in warning and TOKEN_ENV in warning


def test_non_https_account_url_gives_no_client(caplog):
    env = {ACCOUNT_URL_ENV: "example-account.snowflakecomputing.com", TOKEN_ENV: FAKE_TOKEN}

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert cortex_client_from_env(env) is None

    assert "https://" in fallback_warnings(caplog)[0]
    assert FAKE_TOKEN not in caplog.text


def test_configured_env_builds_a_client_with_default_or_chosen_model():
    env = {ACCOUNT_URL_ENV: FAKE_URL + "/", TOKEN_ENV: FAKE_TOKEN}

    client = cortex_client_from_env(env)
    assert client.url == FAKE_URL + CHAT_COMPLETIONS_PATH
    assert client.model == DEFAULT_MODEL

    chosen = cortex_client_from_env({**env, MODEL_ENV: "mistral-large2"})
    assert chosen.model == "mistral-large2"
    assert FAKE_TOKEN not in repr(chosen)


# --- CortexClient against a fake HTTP session (no network) ----------------------------------


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response


def completion(content) -> dict:
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}


def test_cortex_client_posts_the_prompt_with_bearer_auth_and_a_timeout():
    session = FakeSession(FakeResponse(200, completion("A short note.")))
    client = CortexClient(FAKE_URL, FAKE_TOKEN, "llama3.1-70b", session=session, timeout_s=7)

    assert client("the prompt") == "A short note."

    (call,) = session.calls
    assert call["url"] == FAKE_URL + "/api/v2/cortex/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert call["headers"]["X-Snowflake-Authorization-Token-Type"] == "PROGRAMMATIC_ACCESS_TOKEN"
    assert call["timeout"] == 7
    assert call["json"]["model"] == "llama3.1-70b"
    assert call["json"]["messages"] == [{"role": "user", "content": "the prompt"}]
    assert call["json"]["stream"] is False


@pytest.mark.parametrize(
    ("session", "message"),
    [
        (FakeSession(FakeResponse(401, text="unauthorized")), "HTTP 401"),
        (FakeSession(error=requests.Timeout("read timed out")), "timed out"),
        (FakeSession(error=requests.ConnectionError("no route")), "request failed"),
        (FakeSession(FakeResponse(200, ValueError("not json"))), "unexpected response shape"),
        (FakeSession(FakeResponse(200, {"choices": []})), "unexpected response shape"),
        (FakeSession(FakeResponse(200, completion(None))), "not text"),
    ],
)
def test_cortex_client_raises_cortex_error_on_failure(session, message):
    client = CortexClient(FAKE_URL, FAKE_TOKEN, session=session)

    with pytest.raises(CortexError, match=message):
        client("the prompt")


def test_http_failure_through_the_real_client_falls_back_without_logging_the_token(caplog):
    inputs = desc_vs_gpc_inputs()
    session = FakeSession(FakeResponse(500, text="internal error"))
    client = CortexClient(FAKE_URL, FAKE_TOKEN, session=session)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        result = write_savings_note(inputs, client)

    assert result.source == "fallback"
    assert result.note == inputs.savings_basis
    assert "HTTP 500" in fallback_warnings(caplog)[0]
    assert FAKE_TOKEN not in caplog.text


# --- the one opt-in live test -----------------------------------------------------------------

# Costs Snowflake credits, so it needs an explicit opt-in on top of the keys:
#   SNOWFLAKE_LIVE_TEST=1 .venv/bin/python -m pytest tests/test_savings_note.py -k live
# Keys come from the shell or the repo-root .env (read here, not loaded into os.environ).
REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


def _live_env() -> dict[str, str]:
    file_env = dotenv_values(REPO_ENV, encoding="utf-8") if REPO_ENV.is_file() else {}
    return {**{k: v for k, v in file_env.items() if v}, **os.environ}


@pytest.mark.skipif(
    os.environ.get("SNOWFLAKE_LIVE_TEST") != "1",
    reason="live Snowflake test is opt-in: set SNOWFLAKE_LIVE_TEST=1 and the Snowflake keys",
)
def test_live_cortex_writes_a_note_that_passes_the_checks():
    client = cortex_client_from_env(_live_env())
    assert client is not None, f"set {ACCOUNT_URL_ENV} and {TOKEN_ENV} for the live test"
    inputs = desc_vs_gpc_inputs()

    result = write_savings_note(inputs, client)

    assert result.source == "cortex", "live Cortex call fell back; see the warning in the log"
    assert result.inputs is inputs
    assert 0 < len(result.note) <= MAX_NOTE_CHARS
