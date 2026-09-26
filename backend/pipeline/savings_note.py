"""One-to-two-sentence plain-English note for a flagged pair, written by Snowflake Cortex.

The numbers are never the model's: overlap detection and the savings estimate stay
deterministic (pipeline/overlap.py, pipeline/savings.py). Cortex only rewrites those numbers as
prose. Whenever Snowflake is not configured, fails, or returns text we can't trust, the note
falls back to the estimate's own `savings_basis` and a WARNING says why.

This is meant for a batch step (once per pair at load time), not per API request: one LLM call
per request would make every page load wait on Snowflake.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# --- configuration (all optional: missing -> fallback, never a crash) ------------------------

ACCOUNT_URL_ENV = "SNOWFLAKE_ACCOUNT_URL"
TOKEN_ENV = "SNOWFLAKE_PAT"
MODEL_ENV = "SNOWFLAKE_CORTEX_MODEL"
# Widely available across Snowflake regions; override with SNOWFLAKE_CORTEX_MODEL.
DEFAULT_MODEL = "llama3.1-70b"

# Cortex REST API, OpenAI-compatible Chat Completions endpoint (non-streaming by default).
CHAT_COMPLETIONS_PATH = "/api/v2/cortex/v1/chat/completions"
HTTP_TIMEOUT_S = 20
MAX_COMPLETION_TOKENS = 150

# A one-to-two-sentence note comfortably fits; anything longer is the model rambling.
MAX_NOTE_CHARS = 400
# The only dollar figure a note may give is the savings estimate: never the project cost, which
# a model can easily present as the saving ("could save $23.8 million" when the estimate is
# $709,900). The estimate may be rounded to however many digits the note shows, but never
# further off than this share of it ("about $700,000" is fine, "$1 million" is not).
DOLLAR_TOLERANCE = 0.05


class CortexError(RuntimeError):
    """Snowflake Cortex could not produce a completion (HTTP error, timeout, odd response)."""


# Anything that turns a prompt into text. The real one is CortexClient; tests pass a fake.
CompletionClient = Callable[[str], str]


@dataclass(frozen=True)
class NoteInputs:
    """The deterministic facts about one flagged pair. The note is written from these only."""

    distance_mi: float
    time_gap_days: int
    est_savings_usd: int | None
    savings_basis: str
    project_a_name: str | None = None
    utility_a: str | None = None
    project_b_name: str | None = None
    utility_b: str | None = None


@dataclass(frozen=True)
class SavingsNote:
    """The note text plus the untouched inputs it was written from.

    `inputs` is the caller's object itself, so the numbers can't drift. `source` is "cortex"
    when the model's text passed the checks, "fallback" when `note` is `savings_basis`.
    """

    inputs: NoteInputs
    note: str
    source: str


# --- the Snowflake call (the only code that knows the endpoint and auth) --------------------


class CortexClient:
    """Calls Cortex Chat Completions over HTTPS with a programmatic access token (PAT)."""

    def __init__(
        self,
        account_url: str,
        token: str,
        model: str = DEFAULT_MODEL,
        *,
        session: requests.Session | None = None,
        timeout_s: float = HTTP_TIMEOUT_S,
    ) -> None:
        self.url = account_url.rstrip("/") + CHAT_COMPLETIONS_PATH
        self.model = model
        self._token = token
        self._session = session or requests.Session()
        self._timeout_s = timeout_s

    def __repr__(self) -> str:  # never show the token
        return f"CortexClient(url={self.url!r}, model={self.model!r})"

    def __call__(self, prompt: str) -> str:
        try:
            response = self._session.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": MAX_COMPLETION_TOKENS,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=self._timeout_s,
            )
        except requests.Timeout as exc:
            raise CortexError(f"timed out after {self._timeout_s}s") from exc
        except requests.RequestException as exc:
            raise CortexError(f"request failed: {type(exc).__name__}") from exc

        if response.status_code != 200:
            raise CortexError(f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CortexError("unexpected response shape (no choices[0].message.content)") from exc
        if not isinstance(content, str):
            raise CortexError(f"completion content is {type(content).__name__}, not text")
        return content


def cortex_client_from_env(environ: Mapping[str, str] | None = None) -> CortexClient | None:
    """A CortexClient from the environment, or None (with a warning) if it isn't configured."""
    env = os.environ if environ is None else environ
    account_url = (env.get(ACCOUNT_URL_ENV) or "").strip()
    token = (env.get(TOKEN_ENV) or "").strip()
    missing = [name for name, value in ((ACCOUNT_URL_ENV, account_url), (TOKEN_ENV, token))
               if not value]
    if missing:
        log.warning(
            "Snowflake Cortex not configured (%s not set); savings notes fall back to "
            "savings_basis",
            ", ".join(missing),
        )
        return None
    if not account_url.startswith("https://"):
        log.warning(
            "%s must start with https:// (got %r); savings notes fall back to savings_basis",
            ACCOUNT_URL_ENV,
            account_url,
        )
        return None
    model = (env.get(MODEL_ENV) or "").strip() or DEFAULT_MODEL
    return CortexClient(account_url, token, model)


# --- the note ----------------------------------------------------------------------------------


def write_savings_note(inputs: NoteInputs, client: CompletionClient | None) -> SavingsNote:
    """Ask `client` for a short note about `inputs`; fall back to `savings_basis` if it can't.

    Falls back (and logs a WARNING with the reason) when there is no client, the client
    raises, or the text is empty, too long, or quotes a dollar amount, distance or day count
    that disagrees with the inputs. Never raises for a Snowflake problem.
    """
    if client is None:
        return _fallback(inputs, "Snowflake Cortex is not configured")
    try:
        text = client(build_prompt(inputs))
    except Exception as exc:  # the note is optional; any failure must not break the load
        return _fallback(inputs, f"Cortex call failed: {type(exc).__name__}: {exc}")
    if not isinstance(text, str):
        return _fallback(inputs, f"Cortex returned {type(text).__name__}, not text")

    note = " ".join(text.split())  # collapse newlines/extra spaces
    problem = check_note(note, inputs)
    if problem:
        return _fallback(inputs, f"Cortex note rejected: {problem}")
    return SavingsNote(inputs, note, "cortex")


def build_prompt(inputs: NoteInputs) -> str:
    """The instruction plus every fact the model may use, and nothing else."""
    if inputs.est_savings_usd is None:
        estimate = "none (no project cost is known, so no dollar figure may be given)"
    else:
        estimate = f"${inputs.est_savings_usd:,}"
    facts = [
        f"- Project A: {_describe(inputs.project_a_name, inputs.utility_a)}",
        f"- Project B: {_describe(inputs.project_b_name, inputs.utility_b)}",
        f"- Distance between project centers: {inputs.distance_mi:g} miles",
        f"- Days between in-service dates: {inputs.time_gap_days}",
        f"- Estimated coordination savings: {estimate}",
        f"- How the estimate was made: {inputs.savings_basis}",
    ]
    return (
        "You write short notes for utility transmission planners. In one or two plain-English "
        "sentences (under 60 words), say why coordinating these two nearby transmission "
        "projects could save money. Use only the facts below. Do not invent, recompute or "
        "change any number; if you quote a number, copy it exactly. The only dollar amount you "
        "may write is the estimated coordination savings: do not repeat project costs. Give "
        "distance in miles and timing in days. Reply with the note only.\n"
        + "\n".join(facts)
    )


def check_note(note: str, inputs: NoteInputs) -> str | None:
    """Why `note` can't be shown for `inputs`, or None if it is fine.

    Strict on purpose: a wrongly rejected note just falls back to `savings_basis`, but a
    wrongly accepted one shows a judge a number we never computed.
    """
    if not note:
        return "empty text"
    if len(note) > MAX_NOTE_CHARS:
        return f"{len(note)} characters, over the {MAX_NOTE_CHARS} limit"

    for match in _MONEY_RE.finditer(note):
        sign, number, suffix = _money_parts(match)
        negative = sign or note[: match.start()].rstrip().endswith("-")  # "$-5" or "-$5"
        if negative or not _is_the_estimate(number, suffix, inputs.est_savings_usd):
            return f"dollar amount {match.group(0).strip()!r} is not the savings estimate"
    money_words = _MONEY_WORDS_RE.search(_MONEY_RE.sub(" ", note))
    if money_words:
        return f"money wording the check can't verify: {money_words.group(0)!r}"

    allowed_percents = {float(p) for p in _PERCENT_RE.findall(inputs.savings_basis)}
    for percent in _PERCENT_RE.findall(note):
        if float(percent) not in allowed_percents:
            return f"{percent}% is not in the estimate's basis"

    for miles in _MILES_RE.findall(note):
        if not _is_rounding_of(miles, inputs.distance_mi):
            return f"distance {miles} mi disagrees with {inputs.distance_mi:g} mi"

    for days in _DAYS_RE.findall(note):
        if int(days.replace(",", "")) != inputs.time_gap_days:
            return f"{days} days disagrees with {inputs.time_gap_days} days"

    unverifiable = _OTHER_UNITS_RE.search(note) or _WORDED_QUANTITY_RE.search(note)
    if unverifiable:
        return f"quantity the check can't verify: {unverifiable.group(0)!r}"
    return None


# --- helpers -----------------------------------------------------------------------------------

_NUMBER = r"(\d[\d,]*(?:\.\d+)?|\.\d+)"
_SUFFIX = r"(k|thousand|mm|m|million|bn|b|billion)"
# "$709,900", "US$0.7 million", "USD 700k", "$-5", and "5 million dollars", "700,000 USD".
_MONEY_RE = re.compile(
    rf"(?:US\$|\$|\bUSD)\s*(-?)\s*{_NUMBER}\s*{_SUFFIX}?\b"
    rf"|(-?){_NUMBER}\s*{_SUFFIX}?\s*(?:dollars?|USD)\b",
    re.IGNORECASE,
)
# Money a note might state without a figure the check can parse: other currencies, or
# "five million dollars". Anything left after the figures above are removed is rejected.
_MONEY_WORDS_RE = re.compile(
    r"[€£¥]|\b(?:dollars?|usd|euros?|thousands?|millions?|billions?)\b"
    r"|\b\d[\d,.]*\s*(?:k|mm|m|bn|b)\b",  # "23.8M", "750K" with no currency marker
    re.IGNORECASE,
)
_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)
_MILES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?(?:mi\b|miles?\b|mile\b)", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d[\d,]*)\s*(?:-\s*)?days?\b", re.IGNORECASE)
# Distances and gaps must be given in the units we check; anything else can't be verified.
_OTHER_UNITS_RE = re.compile(
    r"\d[\d,.]*\s*(?:-\s*)?(?:km|kilomet(?:er|re)s?|weeks?|months?|years?)\b", re.IGNORECASE
)
_WORDED_QUANTITY_RE = re.compile(
    r"\b(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a few|several"
    r"|a couple of|half an?|a dozen|dozens of|hundreds of"
    r"|(?:thir|four|fif|six|seven|eigh|nine)teen|(?:twen|thir|for|fif|six|seven|eigh|nine)ty)"
    r"(?:\s*-\s*|\s+)(?:miles?|days?|weeks?|months?|years?|km)\b",  # "five months", "two-month"
    re.IGNORECASE,
)


def _money_parts(match: re.Match[str]) -> tuple[str, str, str | None]:
    """(sign, number, suffix) from whichever of _MONEY_RE's two forms matched."""
    if match.group(2) is not None:
        return match.group(1), match.group(2), match.group(3)
    return match.group(4), match.group(5), match.group(6)


def _is_the_estimate(number: str, suffix: str | None, estimate: int | None) -> bool:
    """The written amount is `estimate`, rounded no coarser than the digits the note shows, and
    within DOLLAR_TOLERANCE of it: "$0.7 million" and "$710,000" for $709,900, not "$745,000"."""
    if estimate is None:
        return False
    scale = _MULTIPLIERS[suffix.lower()] if suffix else 1.0
    diff = abs(float(number.replace(",", "")) * scale - estimate)
    return diff <= _half_last_digit(number) * scale and diff <= DOLLAR_TOLERANCE * estimate


def _is_rounding_of(quoted: str, value: float) -> bool:
    """`quoted` is `value` rounded to the decimals it shows: "6" or "5.7" for 5.65, not "6.1"."""
    return abs(float(quoted) - value) <= _half_last_digit(quoted)


def _half_last_digit(number: str) -> float:
    """Half a unit in the last significant place of `number`: "5.7" -> 0.05, "710,000" -> 5000."""
    digits = number.replace(",", "")
    if "." in digits:
        return 0.5 * 10 ** -len(digits.split(".")[1]) + 1e-9
    trailing_zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
    return 0.5 * 10 ** trailing_zeros + 1e-9


def _describe(name: str | None, utility: str | None) -> str:
    if name and utility:
        return f"{name} ({utility})"
    return name or utility or "unnamed"


def _fallback(inputs: NoteInputs, reason: str) -> SavingsNote:
    log.warning("Savings note falling back to savings_basis: %s", reason)
    return SavingsNote(inputs, inputs.savings_basis, "fallback")
