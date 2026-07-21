"""Trader Memory Core — thesis CRUD and index management.

Provides atomic read/write operations for thesis YAML files and the
_index.json summary.  All writes use tempfile + os.replace for safety.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator, FormatChecker

logger = logging.getLogger(__name__)

# -- Constants ----------------------------------------------------------------

_STATUS_ORDER = [
    "IDEA",
    "ENTRY_READY",
    "ACTIVE",
    "PARTIALLY_CLOSED",
    "CLOSED",
    "INVALIDATED",
]
_TERMINAL_STATUSES = {"CLOSED", "INVALIDATED"}  # PARTIALLY_CLOSED is non-terminal

# Used by attach_position() (equity): (re)writing position incl.
# shares_remaining == shares is only coherent before the position is
# opened or while it is fully open. On PARTIALLY_CLOSED it would violate
# 0 < shares_remaining < shares, on CLOSED it would violate
# shares_remaining == 0, and either would clobber the trim ledger
# relationship — reject those (and terminal INVALIDATED) explicitly.
# ACTIVE is safe to re-attach for equity: attach_position() only ever
# rewrites shares/shares_remaining/position_value/risk_dollars, none of
# which encode a directional sign.
_ATTACH_ALLOWED = {"IDEA", "ENTRY_READY", "ACTIVE"}

# Futures-only, deliberately STRICTER than _ATTACH_ALLOWED above (P1-1,
# user independent review, money-critical): re-attaching on ACTIVE would
# silently overwrite the ENTIRE position dict of an already-open futures
# position, INCLUDING `direction`. A LONG position re-attached with a
# SHORT SIZED report would flip `_sign()` for every subsequent P&L
# computation — a real loss would compute as a fabricated profit and vice
# versa, with no error raised anywhere. Equity attach_position() has no
# such sign-flip risk (see _ATTACH_ALLOWED above), so this guard is
# futures-specific. Correcting an already-open futures position (wrong
# contracts/multiplier/direction) is out of scope for this PR — that needs
# a dedicated history-preserving "amend" operation, not a re-attach.
_ATTACH_FUTURES_ALLOWED = {"IDEA", "ENTRY_READY"}


def _parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 / RFC 3339 string into an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_TYPE_ABBR = {
    "dividend_income": "div",
    "growth_momentum": "grw",
    "mean_reversion": "rev",
    "earnings_drift": "ern",
    "pivot_breakout": "pvt",
}

_VALID_THESIS_TYPES = set(_TYPE_ABBR.keys())

INDEX_FILE = "_index.json"

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "thesis.schema.json"
_SCHEMA: dict | None = None
_VALID_EXIT_REASONS = {"stop_hit", "target_hit", "time_stop", "invalidated", "manual"}

_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _check_datetime(value):
    """Validate RFC 3339 date-time strings (T separator + timezone required)."""
    if not isinstance(value, str):
        return True  # null handled by type validation, not format
    # RFC 3339 requires 'T' separator, not space
    if " " in value:
        raise ValueError(f"date-time must use 'T' separator: {value}")
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"Invalid date-time: {value}")
    # RFC 3339 requires timezone offset
    if dt.tzinfo is None:
        raise ValueError(f"date-time must include timezone offset: {value}")
    return True


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@_FORMAT_CHECKER.checks("date", raises=ValueError)
def _check_date(value):
    """Validate YYYY-MM-DD date strings with strict zero-padding."""
    if not isinstance(value, str):
        return True  # null handled by type validation, not format
    if not _DATE_RE.match(value):
        raise ValueError(f"date must be YYYY-MM-DD (zero-padded): {value}")
    date.fromisoformat(value)
    return True


# -- Helpers ------------------------------------------------------------------


def _is_futures(thesis: dict) -> bool:
    """Money-safety dispatch key. A thesis is futures-backed iff its
    position carries asset_type="futures" (set by attach_futures_position()
    / a direct open_position(contracts=...)) or quantity_unit="contracts".

    This — together with `_sign` — is the money-math logic shared between
    the equity and futures code paths in close()/terminate()/trim()/
    open_position()/_validate_thesis(). Do NOT "consolidate" the futures
    and equity branches of those functions into one shared execution path
    in a future refactor: the whole point of the dispatch-at-entry pattern
    is that a futures thesis can never reach the legacy no-position
    per-unit P&L branches (which ignore multiplier/direction entirely and
    would silently compute a plausible-looking but wrong dollar amount).

    `_sum_realized()` is ALSO called from both paths, but is a deliberate,
    safe exception to the above: it only sums already-computed
    `realized_pnl` ledger values (`sum(e["realized_pnl"] for e in history
    if "realized_pnl" in e)`) and contains no multiplier/per-unit math of
    its own, so it has no silent-wrong-P&L path to reopen — the actual
    dollar computation happens entirely inside `_finalize_outcome()` /
    `_finalize_futures_outcome()` before `_sum_realized()` ever runs.
    """
    pos = thesis.get("position") or {}
    return pos.get("asset_type") == "futures" or pos.get("quantity_unit") == "contracts"


def _sign(direction: str) -> int:
    """LONG=+1, SHORT=-1 for futures P&L (`(exit-entry)*multiplier*qty*sign`).
    Futures-only — equity has no direction concept and stays long-only."""
    if direction == "LONG":
        return 1
    if direction == "SHORT":
        return -1
    raise ValueError(f"Invalid futures direction: {direction!r}, expected 'LONG' or 'SHORT'")


# Sanity cap on any futures contract count (P1-B, user re-review). Same
# VALUE as futures-position-sizer's CONTRACTS_SANITY_MAX
# (skills/futures-position-sizer/scripts/futures_sizing.py) — duplicated
# here as a local constant rather than importing across skill boundaries
# (each skill in this repo is independently packaged/distributed; see
# CLAUDE.md's per-skill packaging model). Beyond closing the same
# "economically-absurd input" hole that module documents, this cap is
# also what lets _valid_positive_int()/_valid_nonneg_int() below refuse a
# huge Python int (arbitrary-precision — e.g. a bare 400-digit JSON
# integer) via a plain int-int comparison, WITHOUT ever calling
# math.isfinite()/float() on it: both raise OverflowError for an int
# larger than a float can represent (~1.8e308), which would otherwise
# escape as an uncaught crash instead of a clean ValueError/
# ArgumentTypeError.
_MAX_CONTRACTS = 10**12

# Sanity cap on equity shares (Issue #254, pre-existing money-critical
# gap — same value as _MAX_CONTRACTS above, but a SEPARATE local
# constant: equity has no natural economic upper bound the way a
# contract count does (fractional shares, penny stocks), so this is
# purely an absurd-input sanity bound, not an economic constraint. It
# exists to reject a "400-digit JSON value" class of input and a
# finite-but-absurd value like 1e300 before a thesis can ever become
# ACTIVE-then-uncloseable (shares that overflow every downstream P&L
# computation with no way to close the position). Deliberately not
# reused as _MAX_CONTRACTS to keep the equity and futures sanity bounds
# independently tunable even though they start at the same value.
_MAX_SHARES = 10**12


def _valid_finite_positive(value: Any) -> float | None:
    """A usable positive number from untrusted input: finite, non-bool,
    strictly > 0. `isinstance(True, int)` is `True` in Python, so bool
    must be excluded explicitly or a boolean would silently pass as
    0.0/1.0 (bool-exclude -> isfinite -> range, in that order — same
    guard as futures_sizing.py's `_valid_finite_positive`).

    P1-B (user re-review): a huge Python int (e.g. a bare 400-digit JSON
    integer with no decimal point — `multiplier` has no fixed sanity cap
    of its own, unlike contracts/quantity, so this can't just bound-check
    like _valid_positive_int() below) raises OverflowError from
    math.isfinite() rather than comparing as "not finite" — caught
    explicitly here and treated as invalid input (None), never an
    uncaught crash.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value) or value <= 0:
            return None
        return float(value)
    except OverflowError:
        return None


def _valid_finite_nonneg(value: Any) -> float | None:
    """Like `_valid_finite_positive` above, but allows exactly 0 (Issue
    #254): `position.shares_remaining == 0` is a legitimate, common state
    for any CLOSED equity thesis (see `test_closed_shares_remaining_zero_
    passes_schema`) — unlike `shares` itself, this field's floor is >= 0,
    not > 0. Same bool-exclude -> isfinite -> range chain, huge-int-safe
    (`OverflowError` caught) — the float analog of `_valid_nonneg_int`
    vs. `_valid_positive_int` below."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value) or value < 0:
            return None
        return float(value)
    except OverflowError:
        return None


def _valid_positive_int(value: Any) -> int | None:
    """A usable positive, WHOLE-NUMBER count from untrusted input (P1-4,
    user independent review): futures contracts trade in whole units only
    (no fractional contracts on CME/ICE/etc.), so this is stricter than
    `_valid_finite_positive` above. Same bool-exclude -> isfinite chain,
    plus an integral check before truncating to `int`: `contracts=1.5`
    must be rejected outright, never silently floored to 1.

    P1-B (user re-review): int and float are handled SEPARATELY. A
    Python `int` is arbitrary-precision and is compared directly against
    _MAX_CONTRACTS with plain int-int comparison — never passed through
    math.isfinite()/float(), both of which raise OverflowError (not
    "returns False") for an int too large to represent as a float. A
    `float` input is still safe to run through isfinite() on its own
    (IEEE 754 doubles overflow to inf at PARSE time, well before this
    function ever sees them), so it keeps the original
    isfinite -> is_integer -> range chain.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 1 <= value <= _MAX_CONTRACTS:
            return value
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if not value.is_integer():
            return None
        int_value = int(value)
        if not (1 <= int_value <= _MAX_CONTRACTS):
            return None
        return int_value
    return None


def _valid_nonneg_int(value: Any) -> int | None:
    """A usable non-negative WHOLE-NUMBER count (P1 addendum, user
    re-review): like `_valid_positive_int` but allows exactly 0 —
    `quantity_remaining` is legitimately 0 once a futures position is
    fully closed, unlike `quantity`/`quantity_sold`, which are always
    strictly positive. Same int/float split and _MAX_CONTRACTS cap as
    `_valid_positive_int` (P1-B) — see its docstring for the
    OverflowError rationale."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 0 <= value <= _MAX_CONTRACTS:
            return value
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if not value.is_integer():
            return None
        int_value = int(value)
        if not (0 <= int_value <= _MAX_CONTRACTS):
            return None
        return int_value
    return None


def _validate_expected_price_match(
    field_name: str, expected: Any, report_value: Any, tolerance: float = 0.01
) -> None:
    """Validate an --expected-entry/--expected-stop value against the
    corresponding field of an untrusted futures-position-sizer report
    (P1-C, user re-review, money-critical). Fixes a fail-open hole in the
    previous inline check (`if expected is not None and report_value is
    not None: if abs(report_value - expected) > tolerance: raise`):

      - expected=nan: comparisons against nan are ALWAYS False, so
        `abs(report_value - nan) > tolerance` never fires — ANY
        report_value silently "matches" a NaN expectation.
      - expected given but report_value missing/None: the `and`
        short-circuits to False and NO check runs at all — an
        unverifiable expectation was silently treated as a pass instead
        of a failure.

    Contract:
      1. expected is None -> no check (caller didn't ask to verify).
      2. expected is given -> must itself be finite, non-bool, and
         strictly positive (rejects bool/string/nan/+-inf/0/negative).
      3. Once expected is given, report_value becomes MANDATORY — missing/
         null/bool/string/dict/list/non-finite/0/negative on the report
         side is rejected; an unverifiable expectation is a failure, not
         a silent pass.
      4. Both valid -> abs(report_value - expected) computed.
      5. > tolerance -> mismatch, rejected.
      6. Every rejection names the field (`field_name`) and the
         offending value.
      7. Must be called BEFORE the thesis is loaded/mutated/saved — see
         its call site in attach_futures_position(), which runs this
         ahead of _load_thesis() so a rejection never touches state.
    """
    if expected is None:
        return
    valid_expected = _valid_finite_positive(expected)
    if valid_expected is None:
        raise ValueError(
            f"expected_{field_name} must be a finite positive number, got {expected!r}"
        )
    valid_report_value = _valid_finite_positive(report_value)
    if valid_report_value is None:
        raise ValueError(
            f"Futures position report {field_name} is invalid or missing "
            f"(required to verify against expected_{field_name}={valid_expected}): "
            f"{report_value!r}"
        )
    if abs(valid_report_value - valid_expected) > tolerance:
        raise ValueError(
            f"{field_name.capitalize()} price mismatch: thesis expects "
            f"{valid_expected}, report has {valid_report_value}"
        )


def _contains_non_finite(value: Any) -> bool:
    """Iteratively (not recursively — see contrarian-setup-gate's
    run_contrarian_setup_gate.py::_contains_non_finite for the full
    RecursionError rationale) scan a JSON-parsed structure for any
    non-finite float (inf/-inf/nan) anywhere, at any depth."""
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, float):
            if not math.isfinite(current):
                return True
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


def _load_untrusted_json(path: str) -> tuple[Any | None, str | None]:
    """Read and parse an untrusted JSON file. Returns (data, None) on
    success, or (None, tag) on failure — tag is one of "unreadable"
    (missing / permission-denied / not valid UTF-8), "parse_error", or
    "non_finite" (valid JSON but contains inf/-inf/nan somewhere).

    Same three-class loader vocabulary as contrarian-setup-gate's
    load_json_file / futures_sizing.py's normalize_gate_report — reused
    verbatim, no new tags, so attach_futures_position() reports failures
    in the same idiom the rest of the Shapiro pipeline already uses.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, "unreadable"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, "parse_error"
    except RecursionError:
        return None, "parse_error"
    if _contains_non_finite(data):
        return None, "non_finite"
    return data, None


def _get_schema() -> dict:
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


def _validate_futures_position_fields(position: dict) -> None:
    """Defense-in-depth, status-agnostic field validator for a futures
    position (P1/P2 addendum, user re-review — "root-cause" fix at the
    common _save_thesis() chokepoint). Called from _validate_thesis() for
    EVERY save of a futures thesis, regardless of which function produced
    it: attach_futures_position() / open_position(contracts=...) / trim()
    / close() / terminate() already validate their own inputs before
    calling _save_thesis(), so this is redundant-but-harmless for them —
    but it is the ONLY thing standing between update() (or any other
    future function that loads-mutates-saves a thesis) and a malformed
    position landing on disk.

    Verified empirically that the JSON Schema alone is NOT sufficient: a
    `{"type": "number", "exclusiveMinimum": 0}` field does not reject
    nan/inf — nan/inf compare False against both `<=` and `>` checks, so
    jsonschema's exclusiveMinimum silently lets them through (Draft7Validator
    confirmed: multiplier=nan and multiplier=inf both produce zero schema
    errors). This closes that hole in Python.

    Does NOT duplicate the status-specific quantity_remaining invariants
    already enforced in _validate_thesis() below (ACTIVE ⇒ ==quantity,
    CLOSED ⇒ ==0, PARTIALLY_CLOSED ⇒ strictly between) — this is a
    weaker, universal sanity bound (0 <= quantity_remaining <= quantity)
    that holds regardless of status, layered underneath those.

    Raises ValueError on the first invalid field (never returns a reason
    code) — a single non-finite or malformed field blocks the WHOLE save,
    preserving _save_thesis()'s validate-then-write contract (validation
    always runs before _atomic_write_yaml, so a raise here leaves the
    on-disk file byte-for-byte untouched).
    """
    multiplier = position.get("multiplier")
    if _valid_finite_positive(multiplier) is None:
        raise ValueError(
            f"futures thesis position.multiplier is invalid: {multiplier!r} "
            "(must be a finite positive number)"
        )
    quantity = position.get("quantity")
    valid_quantity = _valid_positive_int(quantity)
    if valid_quantity is None:
        raise ValueError(
            f"futures thesis position.quantity is invalid: {quantity!r} "
            "(must be a positive whole number)"
        )
    quantity_remaining = position.get("quantity_remaining")
    valid_remaining = _valid_nonneg_int(quantity_remaining)
    if valid_remaining is None:
        raise ValueError(
            f"futures thesis position.quantity_remaining is invalid: "
            f"{quantity_remaining!r} (must be a non-negative whole number)"
        )
    if valid_remaining > valid_quantity:
        raise ValueError(
            f"futures thesis position.quantity_remaining ({valid_remaining}) "
            f"must be <= quantity ({valid_quantity})"
        )
    direction = position.get("direction")
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"futures thesis position.direction is invalid: {direction!r}")
    contract_spec = position.get("contract_spec")
    currency = contract_spec.get("currency") if isinstance(contract_spec, dict) else None
    if currency != "USD":
        raise ValueError(
            f"futures thesis position.contract_spec.currency is invalid: "
            f"{currency!r} (must be 'USD')"
        )


def _validate_equity_position_fields(position: dict) -> None:
    """Defense-in-depth, status-agnostic field validator for an equity
    position (Issue #254, pre-existing money-critical gap — symmetric
    with `_validate_futures_position_fields()` above). Called from
    `_validate_thesis()` for EVERY save of a thesis that has a
    shares-shaped position, regardless of which function produced it:
    `open_position(shares=...)` / `attach_position()` / `trim()` never
    validated `shares` at all before this fix (`shares=10**400` crashed
    `close()` with an uncaught `OverflowError`; `shares=inf` silently
    persisted `pnl_dollars: inf`) — this is the ONE chokepoint that closes
    every write path, including `attach_position()`'s untouched-by-this-
    PR plain `json.load()` of the position-sizer report (it flows through
    here for free, since attach also ends in `_save_thesis()`) and any
    future `update()`-style load-mutate-save path.

    Uses `_valid_finite_positive()` for `shares` (fractional shares are
    legitimate — unlike futures contracts, this does NOT integer-
    truncate) and `_valid_finite_nonneg()` for `shares_remaining` (which
    legitimately reaches exactly 0 once CLOSED — using
    `_valid_finite_positive` there would reject every closed equity
    thesis).

    Placement note: called from `_validate_thesis()` AFTER the JSON
    Schema check. The schema's own `exclusiveMinimum: 0` on `shares`
    already rejects 0/negative with `"Schema validation failed"` — this
    function only needs to catch what the schema can't express: nan/inf
    (schema's `exclusiveMinimum` does not reject either, verified
    empirically for the analogous futures field) and the sanity cap.

    Raises ValueError on the first invalid field, before any state
    mutation elsewhere in `_save_thesis()`'s validate-then-write contract
    (validation always runs before `_atomic_write_yaml`, so a raise here
    leaves the on-disk file byte-for-byte untouched).
    """
    shares = position.get("shares")
    valid_shares = _valid_finite_positive(shares)
    if valid_shares is None:
        raise ValueError(
            f"equity thesis position.shares is invalid: {shares!r} "
            "(must be a finite positive number)"
        )
    if valid_shares > _MAX_SHARES:
        raise ValueError(
            f"equity thesis position.shares ({valid_shares}) exceeds the "
            f"maximum sanity bound ({_MAX_SHARES})"
        )

    shares_remaining = position.get("shares_remaining")
    if shares_remaining is not None:
        valid_remaining = _valid_finite_nonneg(shares_remaining)
        if valid_remaining is None:
            raise ValueError(
                f"equity thesis position.shares_remaining is invalid: "
                f"{shares_remaining!r} (must be a finite non-negative number)"
            )
        if valid_remaining > _MAX_SHARES:
            raise ValueError(
                f"equity thesis position.shares_remaining ({valid_remaining}) "
                f"exceeds the maximum sanity bound ({_MAX_SHARES})"
            )
        if valid_remaining > valid_shares:
            raise ValueError(
                f"equity thesis position.shares_remaining ({valid_remaining}) "
                f"must be <= shares ({valid_shares})"
            )


def _validate_thesis(thesis: dict) -> None:
    """JSON Schema + business invariants. Called by _save_thesis()."""
    schema = _get_schema()
    validator = Draft7Validator(schema, format_checker=_FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(thesis), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"Schema validation failed: {errors[0].message}")

    status = thesis.get("status")

    position = thesis.get("position") or {}

    if _is_futures(thesis):
        _validate_futures_position_fields(position)
    elif position and position.get("shares") is not None:
        # Issue #254: the equity analog of the futures branch above — any
        # thesis with a shares-shaped position gets the same
        # status-agnostic field validation, regardless of write path.
        _validate_equity_position_fields(position)

    if status == "ACTIVE":
        entry = thesis.get("entry", {})
        if entry.get("actual_price") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_price")
        if entry.get("actual_date") is None:
            raise ValueError("ACTIVE thesis requires entry.actual_date")
        if _is_futures(thesis):
            # No legacy data exists for futures (new feature) — require both
            # fields explicitly rather than fall through as a silent no-op.
            qty = position.get("quantity")
            qty_rem = position.get("quantity_remaining")
            if qty is None or qty_rem is None:
                raise ValueError(
                    "ACTIVE futures thesis requires position.quantity and quantity_remaining"
                )
            if qty_rem != qty:
                raise ValueError(
                    f"ACTIVE futures thesis: quantity_remaining ({qty_rem}) "
                    f"must equal quantity ({qty})"
                )
        else:
            # Legacy-lenient: pre-PR-80B ACTIVE files may lack shares_remaining
            # (runtime defaults it to shares). Only enforce when present.
            rem = position.get("shares_remaining")
            sh = position.get("shares")
            if rem is not None and sh is not None and rem != sh:
                raise ValueError(
                    f"ACTIVE thesis: shares_remaining ({rem}) must equal shares ({sh})"
                )

    if status == "PARTIALLY_CLOSED":
        # PR-80B-only status — NO legacy leniency: a PARTIALLY_CLOSED record
        # must be fully specified. Branches on asset_type (D2 non-negotiable,
        # see _is_futures docstring) — the equity branch below is
        # byte-for-byte the pre-futures behavior; do not merge the branches.
        entry = thesis.get("entry", {})
        if entry.get("actual_price") is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires entry.actual_price")
        if entry.get("actual_date") is None:
            raise ValueError("PARTIALLY_CLOSED thesis requires entry.actual_date")
        if not thesis.get("position"):
            raise ValueError("PARTIALLY_CLOSED thesis requires a position")
        if _is_futures(thesis):
            qty = position.get("quantity")
            qty_rem = position.get("quantity_remaining")
            if qty is None:
                raise ValueError("PARTIALLY_CLOSED futures thesis requires position.quantity")
            if qty_rem is None:
                raise ValueError(
                    "PARTIALLY_CLOSED futures thesis requires position.quantity_remaining"
                )
            if not (0 < qty_rem < qty):
                raise ValueError(
                    f"PARTIALLY_CLOSED futures thesis requires 0 < quantity_remaining "
                    f"({qty_rem}) < quantity ({qty})"
                )
        else:
            sh = position.get("shares")
            rem = position.get("shares_remaining")
            if sh is None:
                raise ValueError("PARTIALLY_CLOSED thesis requires position.shares")
            if rem is None:
                raise ValueError("PARTIALLY_CLOSED thesis requires position.shares_remaining")
            if not (0 < rem < sh):
                raise ValueError(
                    f"PARTIALLY_CLOSED thesis requires 0 < shares_remaining ({rem}) < shares ({sh})"
                )

    if status == "CLOSED":
        exit_data = thesis.get("exit", {})
        if exit_data.get("actual_price") is None:
            raise ValueError("CLOSED thesis requires exit.actual_price")
        if exit_data.get("actual_date") is None:
            raise ValueError("CLOSED thesis requires exit.actual_date")
        exit_reason = exit_data.get("exit_reason")
        if exit_reason not in _VALID_EXIT_REASONS:
            raise ValueError(f"Invalid exit_reason: {exit_reason}")
        entry_date = thesis.get("entry", {}).get("actual_date")
        exit_date = exit_data.get("actual_date")
        if entry_date and exit_date and _parse_dt(exit_date) < _parse_dt(entry_date):
            raise ValueError("exit.actual_date must be >= entry.actual_date")
        if _is_futures(thesis):
            # Explicit futures invariant (not a shares_remaining fallthrough
            # no-op): only enforce when quantity_remaining is present.
            qty_rem = position.get("quantity_remaining")
            if qty_rem is not None and qty_rem != 0:
                raise ValueError(
                    f"CLOSED futures thesis requires quantity_remaining == 0, got {qty_rem}"
                )
            rem = None
        else:
            # Legacy-lenient: only enforce when shares_remaining is present.
            rem = position.get("shares_remaining")
        if rem is not None and rem != 0:
            raise ValueError(f"CLOSED thesis requires shares_remaining == 0, got {rem}")

    if status == "INVALIDATED":
        exit_data = thesis.get("exit", {})
        exit_reason = exit_data.get("exit_reason")
        if exit_reason is not None and exit_reason != "invalidated":
            raise ValueError(
                f"INVALIDATED thesis must have exit_reason='invalidated', got '{exit_reason}'"
            )
        entry_date = thesis.get("entry", {}).get("actual_date")
        exit_date = exit_data.get("actual_date")
        if entry_date and exit_date and _parse_dt(exit_date) < _parse_dt(entry_date):
            raise ValueError("exit.actual_date must be >= entry.actual_date")

    # -- status_history monotonic check --
    history = thesis.get("status_history", [])
    for i in range(1, len(history)):
        prev_at = history[i - 1].get("at", "")
        curr_at = history[i].get("at", "")
        if prev_at and curr_at and _parse_dt(curr_at) < _parse_dt(prev_at):
            raise ValueError(
                f"status_history[{i}].at ({curr_at}) is before "
                f"status_history[{i - 1}].at ({prev_at})"
            )
    if history and history[-1]["status"] != thesis["status"]:
        raise ValueError(
            f"status_history[-1].status ({history[-1]['status']}) "
            f"!= thesis.status ({thesis['status']})"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _coerce_dt(value: str | None) -> str | None:
    """Normalize a CLI date arg to an RFC 3339 date-time string.

    ``status_history.at`` / ``entry.actual_date`` are schema ``date-time``
    (``_check_datetime`` requires a 'T' separator + timezone). A bare
    ``YYYY-MM-DD`` is widened to midnight UTC — the same idiom register()
    applies to ``_source_date``. A value that already contains 'T' (a full
    timestamp) is returned unchanged; ``None`` stays ``None``.
    """
    if value is None:
        return None
    if "T" in value:
        return value
    return f"{value}T00:00:00+00:00"


def _generate_thesis_id(ticker: str, thesis_type: str, date_str: str) -> str:
    """Generate a thesis ID with a 4-char hash suffix for uniqueness."""
    abbr = _TYPE_ABBR.get(thesis_type)
    if abbr is None:
        raise ValueError(
            f"Unknown thesis_type: {thesis_type}. Must be one of {sorted(_VALID_THESIS_TYPES)}"
        )
    salt = uuid.uuid4().hex[:8]
    hash4 = hashlib.sha256(f"{ticker}_{thesis_type}_{date_str}_{salt}".encode()).hexdigest()[:4]
    return f"th_{ticker.lower()}_{abbr}_{date_str}_{hash4}"


def _compute_origin_fingerprint(thesis_data: dict) -> str:
    """Compute a deterministic fingerprint for deduplication."""
    parts = [
        thesis_data.get("ticker", ""),
        thesis_data.get("thesis_type", ""),
        thesis_data.get("thesis_statement", ""),
        thesis_data.get("_source_date", ""),
    ]
    origin = thesis_data.get("origin", {})
    parts.append(origin.get("skill", ""))
    # output_file excluded from fingerprint (path-dependent, not content-dependent)
    raw = origin.get("raw_provenance", {})
    if raw:
        parts.append(json.dumps(raw, sort_keys=True, default=str))
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _find_by_fingerprint(state_dir: Path, fingerprint: str) -> str | None:
    """Find thesis ID by fingerprint. Index first, always YAML fallback."""
    index = _load_index(state_dir)
    for tid, entry in index.get("theses", {}).items():
        if entry.get("origin_fingerprint") == fingerprint:
            return tid
    # Always fall back to YAML scan (index may be partial)
    for yaml_path in state_dir.glob("th_*.yaml"):
        try:
            thesis = yaml.safe_load(yaml_path.read_text())
            if thesis and thesis.get("origin_fingerprint") == fingerprint:
                return thesis["thesis_id"]
        except (OSError, yaml.YAMLError, KeyError):
            continue
    return None


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write YAML atomically using tempfile + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using tempfile + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_index(state_dir: Path) -> dict:
    """Load _index.json or return empty index."""
    idx_path = state_dir / INDEX_FILE
    if idx_path.exists():
        with open(idx_path) as f:
            return json.load(f)
    return {"version": 1, "theses": {}}


def _save_index(state_dir: Path, index: dict) -> None:
    """Save _index.json atomically."""
    _atomic_write_json(state_dir / INDEX_FILE, index)


def _load_thesis(state_dir: Path, thesis_id: str) -> dict:
    """Load a thesis YAML file."""
    path = state_dir / f"{thesis_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Thesis not found: {thesis_id}")
    with open(path) as f:
        return yaml.safe_load(f)


def _save_thesis(state_dir: Path, thesis: dict) -> None:
    """Validate and save a thesis YAML file atomically."""
    _validate_thesis(thesis)
    path = state_dir / f"{thesis['thesis_id']}.yaml"
    _atomic_write_yaml(path, thesis)


def _default_thesis() -> dict:
    """Return a thesis template with all fields set to defaults."""
    return {
        "thesis_id": None,
        "ticker": None,
        "created_at": None,
        "updated_at": None,
        "thesis_type": None,
        "setup_type": None,
        "catalyst": None,
        "status": "IDEA",
        "status_history": [],
        "thesis_statement": None,
        "mechanism_tag": None,
        "evidence": [],
        "kill_criteria": [],
        "confidence": None,
        "confidence_score": None,
        "origin_fingerprint": None,
        "entry": {
            "target_price": None,
            "conditions": [],
            "actual_price": None,
            "actual_date": None,
        },
        "exit": {
            "stop_loss": None,
            "stop_loss_pct": None,
            "take_profit": None,
            "take_profit_rr": None,
            "time_stop_days": None,
            "actual_price": None,
            "actual_date": None,
            "exit_reason": None,
        },
        "position": None,
        "market_context": None,
        "monitoring": {
            "review_interval_days": 30,
            "next_review_date": None,
            "last_review_date": None,
            "review_status": "OK",
            "triggers_config": [],
            "alerts": [],
        },
        "origin": {
            "skill": None,
            "output_file": None,
            "screening_grade": None,
            "screening_score": None,
            "raw_provenance": {},
        },
        "linked_reports": [],
        "outcome": {
            "pnl_dollars": None,
            "pnl_pct": None,
            "holding_days": None,
            "mae_pct": None,
            "mfe_pct": None,
            "mae_mfe_source": None,
            "lessons_learned": None,
        },
    }


def _project_index_fields(thesis: dict) -> dict:
    """Project thesis fields into the lightweight index representation."""
    created_date = thesis["created_at"][:10] if thesis["created_at"] else None
    updated_at = thesis.get("updated_at") or thesis["created_at"]
    updated_date = updated_at[:10] if updated_at else None
    return {
        "ticker": thesis["ticker"],
        "status": thesis["status"],
        "thesis_type": thesis["thesis_type"],
        "created_at": created_date,
        "updated_at": updated_date,
        "next_review_date": thesis.get("monitoring", {}).get("next_review_date"),
        "review_status": thesis.get("monitoring", {}).get("review_status", "OK"),
        "origin_fingerprint": thesis.get("origin_fingerprint"),
    }


def _update_index_entry(index: dict, thesis: dict) -> None:
    """Update the index entry for a thesis."""
    tid = thesis["thesis_id"]
    index["theses"][tid] = _project_index_fields(thesis)


# -- Public API ---------------------------------------------------------------


def _build_thesis_for_registration(thesis_data: dict) -> dict:
    """Build and validate the full thesis object without writing it."""
    required = ["ticker", "thesis_type", "thesis_statement"]
    for field in required:
        if not thesis_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    if thesis_data["thesis_type"] not in _VALID_THESIS_TYPES:
        raise ValueError(
            f"Invalid thesis_type: {thesis_data['thesis_type']}. "
            f"Must be one of {sorted(_VALID_THESIS_TYPES)}"
        )

    # Validate origin sub-fields (clear error messages before schema check)
    origin = thesis_data.get("origin", {})
    if not origin.get("skill"):
        raise ValueError("Missing required field: origin.skill")
    if not origin.get("output_file"):
        raise ValueError("Missing required field: origin.output_file")

    # Build thesis from template + provided data
    fingerprint = _compute_origin_fingerprint(thesis_data)

    thesis = _default_thesis()
    now = _now_iso()

    # Use source date if provided (e.g., report's as_of), else today
    source_date = thesis_data.get("_source_date")  # "YYYY-MM-DD" or None
    if source_date:
        date_str = source_date.replace("-", "")
        created_at = f"{source_date}T00:00:00+00:00"
        source_base = created_at  # status_history and next_review use source date
    else:
        date_str = _today_str()
        created_at = now
        source_base = now
    thesis_id = _generate_thesis_id(thesis_data["ticker"], thesis_data["thesis_type"], date_str)

    thesis["thesis_id"] = thesis_id
    thesis["ticker"] = thesis_data["ticker"].upper()
    thesis["created_at"] = created_at
    thesis["updated_at"] = now
    thesis["thesis_type"] = thesis_data["thesis_type"]
    thesis["origin_fingerprint"] = fingerprint
    thesis["status"] = "IDEA"
    thesis["status_history"] = [
        {
            "status": "IDEA",
            "at": source_base,
            "reason": thesis_data.get("_register_reason", "registered"),
        }
    ]

    # Copy optional fields
    for key in [
        "setup_type",
        "catalyst",
        "thesis_statement",
        "mechanism_tag",
        "evidence",
        "kill_criteria",
        "confidence",
        "confidence_score",
    ]:
        if key in thesis_data:
            thesis[key] = thesis_data[key]

    # Copy nested objects
    if "entry" in thesis_data:
        thesis["entry"].update(thesis_data["entry"])
    if "exit" in thesis_data:
        thesis["exit"].update(thesis_data["exit"])
    if "market_context" in thesis_data:
        thesis["market_context"] = thesis_data["market_context"]
    if "monitoring" in thesis_data:
        thesis["monitoring"].update(thesis_data["monitoring"])
    if "origin" in thesis_data:
        thesis["origin"].update(thesis_data["origin"])

    # Set next_review_date based on source date (not wall-clock)
    interval = thesis["monitoring"].get("review_interval_days", 30)
    base_dt = datetime.fromisoformat(source_base)
    next_review = (base_dt + timedelta(days=interval)).strftime("%Y-%m-%d")
    thesis["monitoring"]["next_review_date"] = next_review

    # Validate complete thesis BEFORE idempotency check —
    # invalid input must fail even if fingerprint matches an existing thesis.
    _validate_thesis(thesis)
    return thesis


def register(state_dir: Path, thesis_data: dict) -> str:
    """Register a new thesis from provided data.

    Args:
        state_dir: Path to state/theses/ directory.
        thesis_data: Partial thesis dict with at least ticker, thesis_type,
                     thesis_statement, and origin fields.

    Returns:
        The generated thesis_id.

    Raises:
        ValueError: If required fields are missing or thesis_type is invalid.
    """
    # Build and validate before any idempotency or persistence checks.
    thesis = _build_thesis_for_registration(thesis_data)
    fingerprint = thesis["origin_fingerprint"]
    state_dir.mkdir(parents=True, exist_ok=True)

    # Idempotency: check fingerprint after validation passes
    existing_tid = _find_by_fingerprint(state_dir, fingerprint)
    if existing_tid:
        logger.info(
            "Idempotent register: %s already exists for fingerprint %s",
            existing_tid,
            fingerprint[:8],
        )
        return existing_tid

    # Persist
    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Registered thesis %s for %s", thesis["thesis_id"], thesis["ticker"])
    return thesis["thesis_id"]


def get(state_dir: Path, thesis_id: str) -> dict:
    """Load a thesis by ID.

    Raises:
        FileNotFoundError: If thesis does not exist.
    """
    return _load_thesis(state_dir, thesis_id)


def query(
    state_dir: Path,
    *,
    ticker: str | None = None,
    status: str | None = None,
    thesis_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Query theses by filter criteria using the index.

    Args:
        state_dir: Path to state/theses/ directory.
        ticker: Filter by ticker symbol.
        status: Filter by status.
        thesis_type: Filter by thesis type.
        date_from: Filter by created_at >= date_from (YYYY-MM-DD).
        date_to: Filter by created_at <= date_to (YYYY-MM-DD).

    Returns list of matching index entries (lightweight, not full thesis).
    """
    index = _load_index(state_dir)
    results = []
    for tid, entry in index.get("theses", {}).items():
        if ticker and entry.get("ticker", "").upper() != ticker.upper():
            continue
        if status and entry.get("status") != status:
            continue
        if thesis_type and entry.get("thesis_type") != thesis_type:
            continue
        created = entry.get("created_at", "")
        if date_from and created < date_from:
            continue
        if date_to and created > date_to:
            continue
        results.append({"thesis_id": tid, **entry})
    return results


def update(state_dir: Path, thesis_id: str, fields: dict) -> dict:
    """Partial update of a thesis.

    Args:
        state_dir: Path to state/theses/ directory.
        thesis_id: Thesis to update.
        fields: Dict of fields to update (shallow merge for top-level,
                deep merge for nested dicts like entry, exit, monitoring).

    Returns:
        The updated thesis dict.

    Raises:
        ValueError: If a protected field is targeted, or `fields["position"]`
            would touch a futures position (see below).
    """
    thesis = _load_thesis(state_dir, thesis_id)
    now = _now_iso()

    # P1 addendum (user re-review, money-critical): "position" is in
    # neither _protected nor _nested_keys below, so without this guard
    # update() would do a raw, UNVALIDATED replace of thesis["position"] —
    # bypassing attach_futures_position()'s direction/multiplier/currency/
    # integer-contracts validation AND the _ATTACH_FUTURES_ALLOWED
    # ACTIVE-reattach guard entirely. Concretely: open a LONG futures
    # position, then update(id, {"position": {**pos, "direction": "SHORT"}})
    # would silently flip every subsequent P&L's sign with zero error
    # (the P1-1 sign-flip bug, reopened through a different API). Blocked
    # in BOTH directions: (a) the thesis is ALREADY futures (any position
    # field write is un-auditable outside the dedicated lifecycle
    # functions), or (b) the incoming value ITSELF looks futures-shaped
    # (asset_type="futures"/quantity_unit="contracts") — closes the
    # "inject a fresh futures position via update() on a non-futures
    # thesis" path too, which _is_futures(thesis) alone (checked on the
    # PRE-merge thesis) would miss. Equity position updates are entirely
    # unaffected (out of scope) — this only fires for futures on either
    # side of the check.
    if "position" in fields:
        incoming = fields["position"]
        incoming_is_futures_shaped = isinstance(incoming, dict) and (
            incoming.get("asset_type") == "futures" or incoming.get("quantity_unit") == "contracts"
        )
        if _is_futures(thesis) or incoming_is_futures_shaped:
            raise ValueError(
                "update() cannot modify position on a futures thesis (or set a "
                "futures-shaped one) — use attach_futures_position() / "
                "open_position(contracts=...) / trim() / close() / terminate() "
                "instead; direct position writes bypass currency/multiplier/"
                "direction/quantity validation"
            )

    # Deep merge nested dicts
    _protected = frozenset(
        {
            "thesis_id",
            "created_at",
            "status",
            "status_history",
            "ticker",
            "thesis_type",
            "origin_fingerprint",
        }
    )
    _nested_keys = {"entry", "exit", "monitoring", "market_context", "origin", "outcome"}
    for key, value in fields.items():
        if key in _protected:
            raise ValueError(f"Cannot update protected field: {key}")
        if key in _nested_keys and isinstance(value, dict) and isinstance(thesis.get(key), dict):
            thesis[key].update(value)
        else:
            thesis[key] = value

    thesis["updated_at"] = now
    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    return thesis


def transition(
    state_dir: Path,
    thesis_id: str,
    new_status: str,
    reason: str,
    event_date: str | None = None,
) -> dict:
    """Transition thesis to a new status.

    Only allows IDEA → ENTRY_READY. All terminal statuses (ACTIVE, CLOSED,
    INVALIDATED) are blocked — use open_position(), close(), or terminate().

    Args:
        event_date: Optional ISO/date string for status_history.at (for
            backfilling existing broker positions). Defaults to now. Mirrors
            open_position(); a bare YYYY-MM-DD is widened to midnight UTC so a
            later backdated open_position() stays monotonic.

    Raises:
        ValueError: If the transition is invalid.
    """
    thesis = _load_thesis(state_dir, thesis_id)
    current = thesis["status"]

    if current in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot transition from terminal status {current}")

    if new_status == "ACTIVE":
        raise ValueError(
            "Use open_position() to transition to ACTIVE — "
            "it requires actual_price and actual_date."
        )

    if new_status == "PARTIALLY_CLOSED":
        raise ValueError(
            "Use trim() to reach PARTIALLY_CLOSED — it requires shares_sold, price, and date."
        )

    if new_status in _TERMINAL_STATUSES:
        raise ValueError(
            f"Cannot transition to terminal status {new_status} via transition(). "
            "Use close() for CLOSED or terminate() for INVALIDATED."
        )

    # Forward-only check (only IDEA → ENTRY_READY remains)
    current_idx = _STATUS_ORDER.index(current)
    try:
        new_idx = _STATUS_ORDER.index(new_status)
    except ValueError:
        raise ValueError(f"Invalid status: {new_status}")
    if new_idx <= current_idx:
        raise ValueError(f"Cannot transition backward from {current} to {new_status}")

    now = _now_iso()
    history_at = _coerce_dt(event_date) or now
    thesis["status"] = new_status
    thesis["status_history"].append({"status": new_status, "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Transitioned %s: %s → %s (%s)", thesis_id, current, new_status, reason)
    return thesis


def attach_position(
    state_dir: Path,
    thesis_id: str,
    position_report_path: str,
    expected_entry: float | None = None,
    expected_stop: float | None = None,
) -> dict:
    """Attach position-sizer output to an existing thesis.

    Validates:
      1. Report mode must be "shares" (budget mode has no shares/value/risk).
      2. If expected_entry is provided, must match report's entry_price.
      3. If expected_stop is provided, must match report's stop_price.

    Raises:
        ValueError: If validation fails.
        FileNotFoundError: If report or thesis doesn't exist.
    """
    report_path = Path(position_report_path)
    if not report_path.exists():
        raise FileNotFoundError(f"Position report not found: {position_report_path}")

    with open(report_path) as f:
        report = json.load(f)

    # Validate mode
    mode = report.get("mode")
    if mode != "shares":
        raise ValueError(
            f"Position report mode is '{mode}', expected 'shares'. "
            "Budget mode does not produce shares/value/risk fields."
        )

    # Validate expected entry/stop
    params = report.get("parameters", {})
    if expected_entry is not None:
        actual_entry = params.get("entry_price")
        if actual_entry is not None and abs(actual_entry - expected_entry) > 0.01:
            raise ValueError(
                f"Entry price mismatch: thesis expects {expected_entry}, report has {actual_entry}"
            )
    if expected_stop is not None:
        actual_stop = params.get("stop_price")
        if actual_stop is not None and abs(actual_stop - expected_stop) > 0.01:
            raise ValueError(
                f"Stop price mismatch: thesis expects {expected_stop}, report has {actual_stop}"
            )

    thesis = _load_thesis(state_dir, thesis_id)

    # Cross-attach guard (P1 addendum, user re-review, money-critical, same
    # root cause as the update() P1 fix): the status guard below only
    # blocks re-attaching on the WRONG STATUS — it says nothing about
    # whether a position of the OPPOSITE asset type is already attached.
    # IDEA/ENTRY_READY are in BOTH _ATTACH_ALLOWED and
    # _ATTACH_FUTURES_ALLOWED, so without this check, calling
    # attach_position() on a thesis that already has a futures position
    # (attach_futures_position() doesn't advance status) silently replaces
    # the ENTIRE position dict with an equity shares dict — direction/
    # multiplier/quantity/contract_spec vanish, _is_futures(thesis)
    # flips to False, and open_position()/close()/trim() then dispatch
    # into the legacy EQUITY per-unit path for what was a futures trade
    # (wrong sign, wrong magnitude, no error anywhere — confirmed
    # reproducible before this fix). Symmetric guard in
    # attach_futures_position() below.
    if _is_futures(thesis):
        raise ValueError(
            "attach_position() cannot attach an equity position to a thesis "
            "that already has a futures position — use attach_futures_position() "
            "instead, or register a fresh thesis"
        )

    # attach_position() (re)writes position incl. shares_remaining == shares
    # — see the module-level _ATTACH_ALLOWED docstring for why this status
    # guard exists.
    if thesis["status"] not in _ATTACH_ALLOWED:
        raise ValueError(
            f"attach_position() not allowed for status {thesis['status']}; "
            f"only {sorted(_ATTACH_ALLOWED)} (would corrupt shares_remaining)"
        )

    # Determine sizing method from whichever calculation was actually used
    sizing_method = None
    calcs = report.get("calculations", {})
    for method_key in ("fixed_fractional", "atr_based", "kelly"):
        if calcs.get(method_key) is not None:
            sizing_method = calcs[method_key].get("method", method_key)
            break

    thesis["position"] = {
        "shares": report.get("final_recommended_shares"),
        "shares_remaining": report.get("final_recommended_shares"),
        "position_value": report.get("final_position_value"),
        "risk_dollars": report.get("final_risk_dollars"),
        "risk_pct_of_account": report.get("final_risk_pct"),
        "account_type": None,
        "sizing_method": sizing_method,
        "raw_source": {
            "skill": "position-sizer",
            "file": str(position_report_path),
            "fields": {
                "final_recommended_shares": report.get("final_recommended_shares"),
                "final_position_value": report.get("final_position_value"),
                "final_risk_dollars": report.get("final_risk_dollars"),
            },
        },
    }
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Attached position to %s: %s shares", thesis_id, thesis["position"]["shares"])
    return thesis


def attach_futures_position(
    state_dir: Path,
    thesis_id: str,
    position_report_path: str,
    expected_entry: float | None = None,
    expected_stop: float | None = None,
) -> dict:
    """Attach a futures-position-sizer SIZED report to an existing thesis.

    Futures analog of attach_position() (D6/D2) — deliberately NOT shared
    code: the report shape and validated fields are entirely different
    (no "mode" field; "direction" / "contracts" / "contract_spec.multiplier"
    instead of "final_recommended_shares"). Loads the report through the
    same hardened three-class loader vocabulary as contrarian-setup-gate /
    futures_sizing.py (unreadable / parse_error / non_finite — reused
    verbatim, no new tags).

    Validates:
      1. sizing_status == "SIZED" (rejects NO_TRADE and, incidentally, an
         equity position-sizer report, which has no sizing_status field).
      2. direction in {LONG, SHORT}.
      3. contracts is a positive whole number (P1-4: no fractional
         contracts).
      4. contract_spec.multiplier is a finite, non-bool, strictly-positive
         number.
      5. contract_spec.currency is present, a non-empty string, and equal
         to "USD" — no fallback to any other field (P1-2 / P1-addendum-3:
         this skill has no FX conversion — a non-USD contract's P&L would
         silently be computed in the WRONG currency's magnitude; fail
         closed instead).
      6. If expected_entry/expected_stop given, must match the report's
         top-level entry/stop (same 0.01 tolerance as attach_position()).
      7. _ATTACH_FUTURES_ALLOWED status guard — IDEA/ENTRY_READY ONLY
         (P1-1: stricter than equity's _ATTACH_ALLOWED, which also allows
         ACTIVE). Re-attaching on ACTIVE would silently overwrite the
         entire position dict incl. `direction` of an already-open
         futures position — a sign-flip that corrupts every subsequent
         P&L computation with no error raised. See
         _ATTACH_FUTURES_ALLOWED's module-level docstring.
      8. Cross-attach guard (P1 addendum, user re-review): rejects a
         thesis that already has an EQUITY position attached (same root
         cause and symmetric fix as attach_position()'s cross-attach
         guard above — IDEA/ENTRY_READY are in both status allow-sets, so
         the status guard alone can't stop an equity position from being
         silently overwritten by a futures one, dropping shares/
         shares_remaining/position_value/risk_dollars with no error).

    Raises:
        ValueError: If validation fails.
        FileNotFoundError: If the report path itself does not exist.
    """
    report_path = Path(position_report_path)
    if not report_path.exists():
        raise FileNotFoundError(f"Position report not found: {position_report_path}")

    data, load_error = _load_untrusted_json(str(report_path))
    if load_error is not None:
        raise ValueError(f"Futures position report {load_error}: {position_report_path}")
    if not isinstance(data, dict):
        raise ValueError(f"Futures position report is not a JSON object: {position_report_path}")
    report = data

    sizing_status = report.get("sizing_status")
    if sizing_status != "SIZED":
        raise ValueError(
            f"Futures position report sizing_status is {sizing_status!r}, expected 'SIZED' "
            f"(no_trade_reason={report.get('no_trade_reason')!r})"
        )

    direction = report.get("direction")
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"Futures position report has invalid direction: {direction!r}")

    contracts = _valid_positive_int(report.get("contracts"))
    if contracts is None:
        raise ValueError(
            f"Futures position report has invalid contracts: {report.get('contracts')!r} "
            "(must be a positive whole number of contracts)"
        )

    contract_spec = report.get("contract_spec")
    if not isinstance(contract_spec, dict):
        raise ValueError("Futures position report is missing contract_spec")
    multiplier = _valid_finite_positive(contract_spec.get("multiplier"))
    if multiplier is None:
        raise ValueError(
            f"Futures position report has invalid contract_spec.multiplier: "
            f"{contract_spec.get('multiplier')!r} (must be a finite positive number)"
        )

    # P1-2 / P1-addendum-3 (user independent review, money-critical): this
    # skill has no FX conversion anywhere in the futures P&L path
    # (_finalize_futures_outcome computes (exit-entry)*multiplier*qty*sign
    # with no fx_rate term). A non-USD contract (e.g. FESX/EUR) would
    # silently produce a P&L figure in the wrong currency's magnitude —
    # fail closed instead of computing a plausible-looking but wrong
    # dollar amount. contract_spec.currency is the SOLE source of truth —
    # NO fallback to a top-level report.currency (a prior revision of this
    # check had one; a user re-review correctly flagged it as a second,
    # unnecessary trust boundary that could be used to smuggle a currency
    # claim past the authoritative contract_spec). Missing, empty,
    # non-string, and non-"USD" values are ALL rejected explicitly (not
    # just "!= 'USD'"), so a falsy-but-truthy-looking edge case can't slip
    # through by accident.
    report_currency = contract_spec.get("currency")
    if not isinstance(report_currency, str) or not report_currency:
        raise ValueError(
            "Futures position report is missing contract_spec.currency (must be 'USD')"
        )
    if report_currency != "USD":
        raise ValueError(
            f"non-USD futures not supported (currency={report_currency!r}): P&L "
            "would not be FX-converted; only USD-denominated contracts are accepted"
        )

    # Validate expected entry/stop against the report (P1-C, user
    # re-review: _validate_expected_price_match() closes the fail-open
    # holes the previous inline check had — see its docstring). Runs
    # before _load_thesis(), so a rejection never touches thesis state.
    _validate_expected_price_match("entry", expected_entry, report.get("entry"))
    _validate_expected_price_match("stop", expected_stop, report.get("stop"))

    thesis = _load_thesis(state_dir, thesis_id)

    # Cross-attach guard (P1 addendum, user re-review, money-critical) —
    # symmetric with attach_position()'s guard above. IDEA/ENTRY_READY are
    # in both _ATTACH_ALLOWED and _ATTACH_FUTURES_ALLOWED, so without
    # this, attach_futures_position() could silently overwrite an
    # already-attached EQUITY position (dropping shares/shares_remaining/
    # position_value/risk_dollars with no error, and no way to recover
    # the sizing data). Checked directly on position.shares rather than
    # via _is_futures(), which only recognizes the futures shape — an
    # equity position never sets asset_type/quantity_unit at all, so
    # _is_futures() would return False for it either way.
    existing_position = thesis.get("position") or {}
    if existing_position.get("shares") is not None:
        raise ValueError(
            "attach_futures_position() cannot attach a futures position to a "
            "thesis that already has an equity position — use attach_position() "
            "instead, or register a fresh thesis"
        )

    # _ATTACH_FUTURES_ALLOWED status guard — IDEA/ENTRY_READY ONLY (P1-1,
    # deliberately stricter than equity's _ATTACH_ALLOWED which also
    # permits ACTIVE): see _ATTACH_FUTURES_ALLOWED's module-level
    # docstring for the sign-flip risk this closes.
    if thesis["status"] not in _ATTACH_FUTURES_ALLOWED:
        raise ValueError(
            f"attach_futures_position() not allowed for status {thesis['status']}; "
            f"only {sorted(_ATTACH_FUTURES_ALLOWED)} (ACTIVE would silently overwrite "
            "the position incl. direction — sign-flip risk)"
        )

    thesis["position"] = {
        "asset_type": "futures",
        "quantity": contracts,
        "quantity_remaining": contracts,
        "quantity_unit": "contracts",
        "multiplier": multiplier,
        "contract_symbol": report.get("symbol"),
        "direction": direction,
        "contract_spec": dict(contract_spec),
        "risk_per_contract_usd": report.get("risk_per_contract_usd"),
        "total_risk_usd": report.get("total_risk_usd"),
        "risk_pct_of_account": report.get("risk_pct_of_account"),
        "raw_source": {
            "skill": "futures-position-sizer",
            "file": str(position_report_path),
            "fields": {
                "contracts": contracts,
                "total_risk_usd": report.get("total_risk_usd"),
                "risk_per_contract_usd": report.get("risk_per_contract_usd"),
            },
        },
    }
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Attached futures position to %s: %s %s contracts (%s, mult=%s)",
        thesis_id,
        contracts,
        thesis["position"]["contract_symbol"],
        direction,
        multiplier,
    )
    return thesis


def link_report(state_dir: Path, thesis_id: str, skill: str, file: str, date: str) -> dict:
    """Add a linked report to the thesis."""
    thesis = _load_thesis(state_dir, thesis_id)
    thesis["linked_reports"].append({"skill": skill, "file": file, "date": date})
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    return thesis


def _sum_realized(history: list[dict]) -> float:
    """Σ realized_pnl over status_history ledger entries (trims + final leg)."""
    return sum(e["realized_pnl"] for e in history if "realized_pnl" in e)


def _finalize_outcome(
    thesis: dict,
    *,
    exit_price: float,
    exit_date: str,
    history_at: str,
    status: str,
    reason: str,
    append_entry: bool,
) -> None:
    """Roll up the cumulative realized outcome for a position-backed thesis.

    Single owner of the final-leg status_history ledger append. Callers:
      - close() / terminate(): append_entry=True (this appends the one final
        ledger entry for the still-open remainder).
      - trim() full close-out: append_entry=False (trim already appended the
        final ledger entry; here we only sum + finalize).

    Precondition: thesis has a position with shares (legacy / no-position
    theses keep their pre-PR-80B code path in the caller and never reach here).

    Output-side finiteness (Issue #254, pre-existing money-critical gap —
    same "guard the OUTPUT, not just the input" principle and the same
    two-layer arithmetic/finiteness pattern as `_finalize_futures_outcome()`):
    every value computed here (proceeds, realized_pnl,
    cumulative pnl_dollars via `_sum_realized()`, pnl_pct) is computed
    into a LOCAL variable and validated finite BEFORE any mutation of
    `thesis`/`position`/`status_history`. Validation is TWO layers, both
    required:

      1. `try/except OverflowError` around the arithmetic itself. A huge
         Python int operand (e.g. a disk-corrupted `shares: 10**400` that
         bypassed `_validate_thesis()` at write time — see D1's
         `_validate_equity_position_fields()`, which only runs on
         `_save_thesis()`, not on read) makes `round(10**400 * 1.5, 2)`
         raise `OverflowError` from *inside* the multiplication —
         `math.isfinite()` is never reached. Verified empirically.
      2. `math.isfinite()` on the result, for the case where the
         arithmetic itself succeeds but produces `inf`/`nan` (e.g.
         `shares = float("inf")`, which multiplies cleanly to `inf`
         without raising).

    Both layers apply to `math.isfinite()` itself too, not just the
    preceding arithmetic — `_sum_realized()` over an all-Python-int
    ledger can return a huge *int* result (no float ever entered the
    computation, so `round()` doesn't raise), and `math.isfinite()` on
    THAT huge int raises OverflowError in turn. Each finiteness check
    below therefore lives inside the same `try` as the value it checks.
    """
    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")
    position = thesis["position"]
    original = position["shares"]
    remaining = position.get("shares_remaining", original)

    new_entry = None
    if append_entry:
        try:
            leg_proceeds = round(exit_price * remaining, 2)
            leg_realized = round((exit_price - entry_price) * remaining, 2)
            leg_finite = math.isfinite(leg_proceeds) and math.isfinite(leg_realized)
        except OverflowError as exc:
            raise ValueError(
                "computed proceeds/realized_pnl overflowed (exit_price="
                f"{exit_price}, shares={remaining}) — operands too large"
            ) from exc
        if not leg_finite:
            raise ValueError(
                f"computed proceeds/realized_pnl is not finite ({leg_proceeds}, {leg_realized})"
            )
        new_entry = {
            "status": status,
            "at": history_at,
            "reason": reason,
            "shares_sold": remaining,
            "price": exit_price,
            "proceeds": leg_proceeds,
            "realized_pnl": leg_realized,
        }

    # Cumulative pnl_dollars computed WITHOUT mutating status_history yet
    # — _sum_realized() runs over the existing ledger plus the
    # not-yet-appended new_entry, so a non-finite/overflowing cumulative
    # result still rejects cleanly before any state changes.
    history_for_sum = thesis["status_history"] + ([new_entry] if new_entry else [])
    try:
        pnl_dollars = round(_sum_realized(history_for_sum), 2)
        pnl_dollars_finite = math.isfinite(pnl_dollars)
    except OverflowError as exc:
        raise ValueError(
            "computed cumulative pnl_dollars overflowed — the position's "
            "realized P&L ledger contains an operand too large"
        ) from exc
    if not pnl_dollars_finite:
        raise ValueError(f"computed cumulative pnl_dollars is not finite ({pnl_dollars})")

    pnl_pct = None
    if entry_price and original:
        try:
            pnl_pct = round(pnl_dollars / (entry_price * original) * 100, 2)
            pnl_pct_finite = math.isfinite(pnl_pct)
        except OverflowError as exc:
            raise ValueError(
                "computed pnl_pct overflowed — the notional denominator (entry * shares) overflowed"
            ) from exc
        if not pnl_pct_finite:
            raise ValueError(f"computed pnl_pct is not finite ({pnl_pct})")

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(exit_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass

    # All computed values validated finite — now, and only now, mutate.
    if new_entry is not None:
        thesis["status_history"].append(new_entry)
    position["shares_remaining"] = 0
    thesis["status"] = status
    thesis["outcome"]["pnl_dollars"] = pnl_dollars
    thesis["outcome"]["pnl_pct"] = pnl_pct
    thesis["outcome"]["holding_days"] = holding_days


def _finalize_futures_outcome(
    thesis: dict,
    *,
    exit_price: float,
    exit_date: str,
    history_at: str,
    status: str,
    reason: str,
    append_entry: bool,
) -> None:
    """Futures analog of _finalize_outcome() — deliberately NOT shared code
    (D2/D4 non-negotiable, see _is_futures docstring): the multiplier and
    direction sign must never leak into the equity per-unit path, and the
    equity per-unit path must never be reachable from a futures thesis.

    realized_pnl = round((exit_price - entry_price) * multiplier * qty * sign, 2)
    sign: LONG=+1, SHORT=-1 (see _sign()).

    Precondition: thesis["position"] has quantity/multiplier/direction set
    (attach_futures_position() or a direct open_position(contracts=...)
    always sets all three together).

    Output-side finiteness (P1 addendum, user re-review, teaching 10b —
    guard the OUTPUT, not just the input): every value computed here
    (realized_pnl, proceeds, cumulative pnl_dollars, pnl_pct) is computed
    into a LOCAL variable and validated with math.isfinite() BEFORE any
    mutation of thesis/position/status_history. The checks are two-layered:
    arithmetic and math.isfinite() both live inside try/except OverflowError
    for disk-corrupted huge ints, while the explicit finiteness branch still
    rejects ordinary float inf/nan results.
    """
    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")
    position = thesis["position"]
    original = position["quantity"]
    remaining = position.get("quantity_remaining", original)
    multiplier = position["multiplier"]
    sign = _sign(position["direction"])

    new_entry = None
    if append_entry:
        try:
            leg_proceeds = round(exit_price * multiplier * remaining, 2)
            leg_realized = round((exit_price - entry_price) * multiplier * remaining * sign, 2)
            leg_finite = math.isfinite(leg_proceeds) and math.isfinite(leg_realized)
        except OverflowError as exc:
            raise ValueError(
                "computed proceeds/realized_pnl overflowed (exit_price="
                f"{exit_price}, multiplier={multiplier}, quantity={remaining}) — "
                "operands too large"
            ) from exc
        if not leg_finite:
            raise ValueError(
                "computed proceeds/realized_pnl is not finite (exit_price="
                f"{exit_price}, multiplier={multiplier}, quantity={remaining}) — "
                "operands are individually finite but their product overflowed"
            )
        new_entry = {
            "status": status,
            "at": history_at,
            "reason": reason,
            "quantity_sold": remaining,
            "price": exit_price,
            "proceeds": leg_proceeds,
            "realized_pnl": leg_realized,
        }

    # Cumulative pnl_dollars/pct computed WITHOUT mutating status_history
    # yet — _sum_realized() runs over the existing ledger plus the
    # not-yet-appended new_entry, so a non-finite cumulative result still
    # rejects cleanly before any state changes.
    history_for_sum = thesis["status_history"] + ([new_entry] if new_entry else [])
    try:
        pnl_dollars = round(_sum_realized(history_for_sum), 2)
        pnl_dollars_finite = math.isfinite(pnl_dollars)
    except OverflowError as exc:
        raise ValueError(
            "computed cumulative pnl_dollars overflowed — the position's "
            "realized P&L ledger contains an operand too large"
        ) from exc
    if not pnl_dollars_finite:
        raise ValueError(
            f"computed cumulative pnl_dollars is not finite ({pnl_dollars}) — "
            "the position's realized P&L ledger overflowed"
        )

    pnl_pct = None
    if entry_price and original:
        # % basis: notional value (entry * multiplier * original contracts),
        # the direct futures analog of equity's entry*shares denominator —
        # a descriptive metric only; pnl_dollars above is the money-critical
        # exact figure and is never derived from this percentage.
        try:
            pnl_pct = round(pnl_dollars / (entry_price * multiplier * original) * 100, 2)
            pnl_pct_finite = math.isfinite(pnl_pct)
        except OverflowError as exc:
            raise ValueError(
                "computed pnl_pct overflowed — the notional denominator "
                "(entry * multiplier * quantity) contains an operand too large"
            ) from exc
        if not pnl_pct_finite:
            raise ValueError(
                f"computed pnl_pct is not finite ({pnl_pct}) — the notional "
                "denominator (entry * multiplier * quantity) overflowed"
            )

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(exit_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass

    # All computed values validated finite — now, and only now, mutate.
    if new_entry is not None:
        thesis["status_history"].append(new_entry)
    position["quantity_remaining"] = 0
    thesis["status"] = status
    thesis["outcome"]["pnl_dollars"] = pnl_dollars
    thesis["outcome"]["pnl_pct"] = pnl_pct
    thesis["outcome"]["holding_days"] = holding_days


def close(
    state_dir: Path,
    thesis_id: str,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None = None,
) -> dict:
    """Close an ACTIVE or PARTIALLY_CLOSED thesis and compute outcome.

    With a position: outcome is the cumulative realized P&L (Σ trim
    realized_pnl + this final leg). With no position: the pre-PR-80B
    single-leg behaviour is kept verbatim.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to close.
        exit_reason: One of stop_hit, target_hit, time_stop, invalidated, manual.
        actual_price: Exit price.
        actual_date: Exit date (ISO format).
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ACTIVE/PARTIALLY_CLOSED or entry missing.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must NEVER reach the legacy no-position
    # branch below, which ignores multiplier/direction entirely.
    if _is_futures(thesis):
        return _close_futures(state_dir, thesis, exit_reason, actual_price, actual_date, event_date)

    if thesis["status"] not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only close ACTIVE or PARTIALLY_CLOSED thesis, current status: {thesis['status']}"
        )

    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")

    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    # Set exit data
    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    now = _now_iso()
    history_at = event_date or now
    position = thesis.get("position")

    if position and position.get("shares"):
        # Cumulative path (single-owner ledger append in _finalize_outcome).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="CLOSED",
            reason=f"closed: {exit_reason}",
            append_entry=True,
        )
    else:
        # Legacy no-position path — pre-PR-80B behaviour, byte-identical.
        pnl_dollars = actual_price - entry_price
        pnl_pct = ((actual_price - entry_price) / entry_price) * 100 if entry_price else None
        holding_days = None
        if entry_date:
            try:
                holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
            except (ValueError, TypeError):
                pass
        thesis["outcome"]["pnl_dollars"] = (
            round(pnl_dollars, 2) if pnl_dollars is not None else None
        )
        thesis["outcome"]["pnl_pct"] = round(pnl_pct, 2) if pnl_pct is not None else None
        thesis["outcome"]["holding_days"] = holding_days
        thesis["status"] = "CLOSED"
        thesis["status_history"].append(
            {"status": "CLOSED", "at": history_at, "reason": f"closed: {exit_reason}"}
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Closed %s: %s, P&L=%.2f%%",
        thesis_id,
        exit_reason,
        thesis["outcome"].get("pnl_pct") or 0,
    )
    return thesis


def _close_futures(
    state_dir: Path,
    thesis: dict,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None,
) -> dict:
    """Futures analog of close() — deliberately NOT shared code (D2/D4
    non-negotiable, see _is_futures docstring): a futures thesis must
    never reach close()'s legacy no-position per-unit branch, which
    ignores multiplier/direction and would silently compute a
    plausible-looking but wrong dollar amount.

    Unlike close(), there is no no-position fallback here — a thesis that
    dispatches into this function (_is_futures() is True) always has an
    attached futures position with a quantity.
    """
    if thesis["status"] not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only close ACTIVE or PARTIALLY_CLOSED thesis, current status: {thesis['status']}"
        )

    # P1-3 (user independent review, money-critical): validated before any
    # mutation, before _save_thesis() — a NaN/Infinity exit price would
    # otherwise persist into outcome.pnl_dollars.
    if _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "close() requires a finite positive actual_price for a futures "
            f"thesis, got {actual_price!r}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("quantity") is None:
        raise ValueError("Cannot close futures thesis: position.quantity is not set")

    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    now = _now_iso()
    history_at = event_date or now

    _finalize_futures_outcome(
        thesis,
        exit_price=actual_price,
        exit_date=actual_date,
        history_at=history_at,
        status="CLOSED",
        reason=f"closed: {exit_reason}",
        append_entry=True,
    )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Closed %s: %s, P&L=%.2f",
        thesis["thesis_id"],
        exit_reason,
        thesis["outcome"].get("pnl_dollars") or 0,
    )
    return thesis


def trim(
    state_dir: Path,
    thesis_id: str,
    shares_sold: float,
    price: float,
    date: str,
    reason: str = "position trimmed",
    exit_reason: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Partially close (trim) an ACTIVE / PARTIALLY_CLOSED position.

    Records a status_history ledger entry (shares_sold / price / proceeds /
    realized_pnl) and decrements position.shares_remaining. If the trim sells
    the entire remaining quantity it becomes a full close-out (status CLOSED,
    exit fields set, cumulative outcome).

    Args:
        shares_sold: Quantity sold in this trim (0 < shares_sold <= remaining).
        price: Trim execution price.
        date: Trim execution date (YYYY-MM-DD or ISO).
        exit_reason: Only used when this trim fully closes the position
            (default "manual"); ∈ stop_hit/target_hit/time_stop/invalidated/manual.
        event_date: Overrides the ledger timestamp (else --date is used).

    Raises:
        ValueError: On bad status / missing entry / no position / bad qty.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must never reach the equity per-unit
    # math below.
    if _is_futures(thesis):
        return _trim_futures(
            state_dir, thesis, shares_sold, price, date, reason, exit_reason, event_date
        )

    status = thesis["status"]
    if status not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only trim ACTIVE or PARTIALLY_CLOSED thesis, current status: {status}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot trim thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("shares") is None:
        raise ValueError("trim requires a recorded position — run open-position --shares first")

    original = position["shares"]
    remaining = position.get("shares_remaining", original)  # legacy default
    if not (0 < shares_sold <= remaining):
        raise ValueError(
            f"shares_sold ({shares_sold}) must be > 0 and <= shares_remaining ({remaining})"
        )
    # Note: this range check is comparison-based, not arithmetic — a
    # huge/nan/inf shares_sold is already rejected here (comparisons
    # never raise OverflowError in Python, unlike the multiplication/
    # subtraction below), so no separate input-side guard is needed.

    # Output-side finiteness (Issue #254, pre-existing money-critical gap
    # — see _finalize_outcome()'s docstring for the two-layer rationale:
    # try/except OverflowError for arithmetic that can raise mid-
    # computation on a disk-corrupted huge `shares_remaining` — e.g. a
    # thesis that bypassed _validate_thesis()'s write-time D1 chokepoint
    # — PLUS math.isfinite() for a clean-but-inf/nan result). Both layers
    # apply before any state mutation below.
    try:
        realized = round((price - entry_price) * shares_sold, 2)
        proceeds = round(price * shares_sold, 2)
        # Round to kill float-subtraction noise (7.86 - 4.00 == 3.86000…3),
        # then epsilon-snap a ~0 remainder to an exact 0.0 (→ full close-out).
        new_remaining = round(remaining - shares_sold, 8)
        trim_finite = (
            math.isfinite(realized) and math.isfinite(proceeds) and math.isfinite(new_remaining)
        )
    except OverflowError as exc:
        raise ValueError(
            f"computed realized_pnl/proceeds/shares_remaining overflowed (price={price}, "
            f"shares_sold={shares_sold}) — operands too large"
        ) from exc
    if not trim_finite:
        raise ValueError(
            "computed realized_pnl/proceeds/shares_remaining is not finite "
            f"({realized}, {proceeds}, {new_remaining})"
        )
    if abs(new_remaining) < 1e-9:
        new_remaining = 0.0

    now = _now_iso()
    history_at = _coerce_dt(event_date) or _coerce_dt(date)
    full_close = new_remaining == 0
    new_status = "CLOSED" if full_close else "PARTIALLY_CLOSED"

    # trim() owns its ledger append (exactly one entry per trim).
    thesis["status_history"].append(
        {
            "status": new_status,
            "at": history_at,
            "reason": reason,
            "shares_sold": shares_sold,
            "price": price,
            "proceeds": proceeds,
            "realized_pnl": realized,
        }
    )
    position["shares_remaining"] = new_remaining

    if full_close:
        exit_date = _coerce_dt(date)
        thesis["exit"]["actual_price"] = price
        thesis["exit"]["actual_date"] = exit_date
        thesis["exit"]["exit_reason"] = exit_reason or "manual"
        thesis["status"] = "CLOSED"
        # Ledger entry already appended above → append_entry=False (sum only).
        _finalize_outcome(
            thesis,
            exit_price=price,
            exit_date=exit_date,
            history_at=history_at,
            status="CLOSED",
            reason=reason,
            append_entry=False,
        )
    else:
        thesis["status"] = "PARTIALLY_CLOSED"

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Trimmed %s: sold %s @ %.4f → %s remaining, status %s",
        thesis_id,
        shares_sold,
        price,
        new_remaining,
        thesis["status"],
    )
    return thesis


def _trim_futures(
    state_dir: Path,
    thesis: dict,
    contracts_sold: float,
    price: float,
    date: str,
    reason: str,
    exit_reason: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of trim() — deliberately NOT shared code (D2/D4
    non-negotiable, see _is_futures docstring): realized_pnl here always
    includes multiplier * sign, unlike the equity per-unit formula above.
    """
    status = thesis["status"]
    if status not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only trim ACTIVE or PARTIALLY_CLOSED thesis, current status: {status}"
        )

    # P1-3 (user independent review, money-critical): validated before any
    # mutation, before _save_thesis().
    if _valid_finite_positive(price) is None:
        raise ValueError(
            f"trim() requires a finite positive price for a futures thesis, got {price!r}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot trim thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("quantity") is None:
        raise ValueError(
            "trim requires a recorded futures position — run "
            "open-position --contracts or attach-futures-position first"
        )

    original = position["quantity"]
    remaining = position.get("quantity_remaining", original)
    # P1-4: contracts_sold must be a whole number (no fractional contracts).
    valid_contracts_sold = _valid_positive_int(contracts_sold)
    if valid_contracts_sold is None:
        raise ValueError(
            f"contracts_sold must be a positive whole number of contracts, got {contracts_sold!r}"
        )
    if not (0 < valid_contracts_sold <= remaining):
        raise ValueError(
            f"contracts_sold ({valid_contracts_sold}) must be > 0 and <= "
            f"quantity_remaining ({remaining})"
        )

    multiplier = position["multiplier"]
    sign = _sign(position["direction"])
    # P1 addendum-1 (user re-review, teaching 10b — guard the OUTPUT, not
    # just the input): individually-finite operands (e.g. multiplier=1e308)
    # can still overflow their PRODUCT to inf, while a disk-corrupted huge
    # int can raise OverflowError before math.isfinite() is reached. Both
    # cases are validated before any mutation below.
    try:
        realized = round((price - entry_price) * multiplier * valid_contracts_sold * sign, 2)
        proceeds = round(price * multiplier * valid_contracts_sold, 2)
        trim_finite = math.isfinite(realized) and math.isfinite(proceeds)
    except OverflowError as exc:
        raise ValueError(
            "computed realized_pnl/proceeds overflowed (price="
            f"{price}, multiplier={multiplier}, contracts_sold={valid_contracts_sold}) — "
            "operands too large"
        ) from exc
    if not trim_finite:
        raise ValueError(
            "computed realized_pnl/proceeds is not finite (price="
            f"{price}, multiplier={multiplier}, contracts_sold={valid_contracts_sold}) — "
            "operands are individually finite but their product overflowed"
        )
    # Round to kill float-subtraction noise, then epsilon-snap a ~0
    # remainder to an exact 0 (→ full close-out) — same as equity trim().
    # (Both operands are exact ints post-P1-4, so this is now a no-op
    # safety net rather than a load-bearing rounding step, but kept for
    # symmetry with equity trim() and defense-in-depth.)
    new_remaining = round(remaining - valid_contracts_sold, 8)
    if abs(new_remaining) < 1e-9:
        new_remaining = 0
    # P1 addendum-4 (canonical int storage): quantity_remaining must never
    # be a float like 2.0 — validated + coerced to int here even though,
    # with whole-number contracts throughout, this should always already
    # be an exact integer.
    valid_new_remaining = _valid_nonneg_int(new_remaining)
    if valid_new_remaining is None:
        raise ValueError(
            f"computed quantity_remaining is not a valid non-negative integer "
            f"({new_remaining!r}) — this should be unreachable with whole-number "
            "contracts"
        )
    new_remaining = valid_new_remaining

    now = _now_iso()
    history_at = _coerce_dt(event_date) or _coerce_dt(date)
    full_close = new_remaining == 0
    new_status = "CLOSED" if full_close else "PARTIALLY_CLOSED"

    # _trim_futures() owns its ledger append (exactly one entry per trim).
    thesis["status_history"].append(
        {
            "status": new_status,
            "at": history_at,
            "reason": reason,
            "quantity_sold": valid_contracts_sold,
            "price": price,
            "proceeds": proceeds,
            "realized_pnl": realized,
        }
    )
    position["quantity_remaining"] = new_remaining

    if full_close:
        exit_date = _coerce_dt(date)
        thesis["exit"]["actual_price"] = price
        thesis["exit"]["actual_date"] = exit_date
        thesis["exit"]["exit_reason"] = exit_reason or "manual"
        thesis["status"] = "CLOSED"
        # Ledger entry already appended above → append_entry=False (sum only).
        _finalize_futures_outcome(
            thesis,
            exit_price=price,
            exit_date=exit_date,
            history_at=history_at,
            status="CLOSED",
            reason=reason,
            append_entry=False,
        )
    else:
        thesis["status"] = "PARTIALLY_CLOSED"

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Trimmed %s: sold %s contracts @ %.4f → %s remaining, status %s",
        thesis["thesis_id"],
        valid_contracts_sold,
        price,
        new_remaining,
        thesis["status"],
    )
    return thesis


def open_position(
    state_dir: Path,
    thesis_id: str,
    actual_price: float,
    actual_date: str,
    reason: str = "position opened",
    shares: float | None = None,
    event_date: str | None = None,
    contracts: float | None = None,
    multiplier: float | None = None,
    direction: str | None = None,
    contract_symbol: str | None = None,
    contract_currency: str | None = None,
) -> dict:
    """Transition thesis from ENTRY_READY to ACTIVE with entry data.

    This is the only way to reach ACTIVE status. transition() blocks ACTIVE.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to activate.
        actual_price: Entry price.
        actual_date: Entry date (ISO format).
        reason: Transition reason.
        shares: Optional share count to record (equity).
        event_date: Optional ISO timestamp for status_history.at (for backfilling).
        contracts: Optional contract count to record (futures; P2-1). If a
            futures position was already attached via
            attach_futures_position(), leave this None — the attached
            quantity is used. If given, this is a "direct open" that
            populates position from scratch and REQUIRES multiplier,
            direction, AND contract_currency too.
        multiplier: Futures contract multiplier — required with `contracts`
            on a direct open (no attached position).
        direction: "LONG" | "SHORT" — required with `contracts` on a direct
            open (no attached position).
        contract_symbol: Optional futures contract symbol (e.g. "ES").
        contract_currency: Required with `contracts` on a direct open
            (P1-addendum-2, user re-review): a direct open with no
            attach_futures_position() handoff has no contract_spec at all,
            so — unlike the attach path — there is no currency to
            validate unless the caller supplies one explicitly. Must be
            exactly "USD" (this skill has no FX conversion); a direct
            open with no currency, or a non-USD currency, is rejected
            rather than silently treated as USD.

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ENTRY_READY.
    """
    # P3-2: providing both is never meaningful (one silently overrides or
    # gets ignored depending on dispatch order) — fail loud instead of
    # silently picking one.
    if shares is not None and contracts is not None:
        raise ValueError(
            "open_position() got both shares and contracts; provide either "
            "--shares (equity) or --contracts (futures), not both"
        )

    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring). `contracts is not None` covers a direct futures open with
    # no prior attach; `_is_futures(thesis)` covers open_position() called
    # after attach_futures_position() already populated position. The
    # existing equity `shares=` branch below is untouched.
    if contracts is not None or _is_futures(thesis):
        return _open_futures_position(
            state_dir,
            thesis,
            actual_price,
            actual_date,
            reason=reason,
            contracts=contracts,
            multiplier=multiplier,
            direction=direction,
            contract_symbol=contract_symbol,
            contract_currency=contract_currency,
            event_date=event_date,
        )

    if thesis["status"] != "ENTRY_READY":
        raise ValueError(f"open_position() requires ENTRY_READY status, got {thesis['status']}")

    now = _now_iso()
    thesis["entry"]["actual_price"] = actual_price
    thesis["entry"]["actual_date"] = actual_date
    if shares is not None:
        if thesis["position"] is None:
            thesis["position"] = {}
        thesis["position"]["shares"] = shares
    # A PR-80B-era ACTIVE thesis carries shares_remaining explicitly (== the
    # full opened quantity). Covers both --shares here and an earlier
    # attach_position()-populated position; legacy (no shares) stays absent.
    pos = thesis.get("position")
    if pos and pos.get("shares") is not None and pos.get("shares_remaining") is None:
        pos["shares_remaining"] = pos["shares"]

    history_at = event_date or now
    thesis["status"] = "ACTIVE"
    thesis["status_history"].append({"status": "ACTIVE", "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Opened position %s at %.2f", thesis_id, actual_price)
    return thesis


def _open_futures_position(
    state_dir: Path,
    thesis: dict,
    actual_price: float,
    actual_date: str,
    *,
    reason: str,
    contracts: float | None,
    multiplier: float | None,
    direction: str | None,
    contract_symbol: str | None,
    contract_currency: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of open_position()'s equity shares= branch —
    deliberately NOT shared code (D2/D4 non-negotiable, see _is_futures
    docstring). Two entry paths:

      1. attach_futures_position() already populated position (asset_type,
         quantity, multiplier, direction, contract_spec incl. currency,
         ...) — `contracts` here is None and this only transitions status
         + sets entry data. Currency was already validated as "USD" by
         attach_futures_position() itself.
      2. Direct open (no prior attach): `contracts`/`multiplier`/`direction`/
         `contract_currency` are supplied here and this populates position
         from scratch (P2-3c: `open-position --contracts` without
         attach-futures-position first). Unlike path 1, there is no
         contract_spec at all here, so currency must be validated
         explicitly (P1-addendum-2, user re-review) — a direct open with
         no contract_currency, or a non-USD one, is a fail-closed reject,
         not a silent USD assumption.
    """
    if thesis["status"] != "ENTRY_READY":
        raise ValueError(f"open_position() requires ENTRY_READY status, got {thesis['status']}")

    # P1-3 (user independent review, money-critical): validated BEFORE any
    # mutation of `pos`/`thesis` below, so a rejected call leaves the
    # in-memory thesis untouched and _save_thesis() is never reached — a
    # NaN/Infinity actual_price would otherwise persist into entry data and
    # NaN-poison every downstream P&L computation for this thesis.
    if _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "open_position() requires a finite positive actual_price for a "
            f"futures thesis, got {actual_price!r}"
        )

    pos = dict(thesis.get("position") or {})

    if contracts is not None:
        if multiplier is None or direction is None:
            raise ValueError(
                "open_position(contracts=...) requires multiplier and direction "
                "when no futures position is already attached"
            )
        # P1-addendum-2 (user re-review): a direct open has no attached
        # contract_spec, so currency must be supplied and validated here —
        # never silently assumed to be USD. Same rejection rules as
        # attach_futures_position(): missing/empty/non-string/non-USD are
        # ALL rejected explicitly.
        if not isinstance(contract_currency, str) or not contract_currency:
            raise ValueError(
                "open_position(contracts=...) requires contract_currency "
                "when no futures position is already attached (must be 'USD')"
            )
        if contract_currency != "USD":
            raise ValueError(
                f"non-USD futures not supported (currency={contract_currency!r}): "
                "P&L would not be FX-converted; only USD-denominated contracts "
                "are accepted"
            )
        # Symmetric with attach_futures_position()'s handoff validation
        # (P2/P1-4): bool-exclude -> isfinite -> integral -> range, with a
        # futures-specific error message rather than relying on the
        # generic schema failure surfaced later at _save_thesis() time.
        # Contracts must be a whole number (P1-4) — no fractional
        # contracts.
        valid_contracts = _valid_positive_int(contracts)
        if valid_contracts is None:
            raise ValueError(
                "open_position(contracts=...) requires a positive whole "
                f"number of contracts, got {contracts!r}"
            )
        valid_multiplier = _valid_finite_positive(multiplier)
        if valid_multiplier is None:
            raise ValueError(
                "open_position(contracts=...) requires a finite positive "
                f"multiplier, got {multiplier!r}"
            )
        _sign(direction)  # raises ValueError for anything other than LONG/SHORT
        pos["asset_type"] = "futures"
        pos["quantity_unit"] = "contracts"
        pos["quantity"] = valid_contracts
        pos["multiplier"] = valid_multiplier
        pos["direction"] = direction
        # Stored in contract_spec.currency for audit consistency with the
        # attach path (contract_spec.currency is the single field any
        # future code checks for currency — see attach_futures_position()).
        spec = dict(pos.get("contract_spec") or {})
        spec["currency"] = contract_currency
        pos["contract_spec"] = spec
        if contract_symbol is not None:
            pos["contract_symbol"] = contract_symbol

    if pos.get("quantity") is None:
        raise ValueError(
            "open_position() for a futures thesis requires position.quantity — "
            "attach a SIZED report via attach-futures-position, or pass contracts="
        )

    pos["quantity_remaining"] = pos["quantity"]
    thesis["position"] = pos

    now = _now_iso()
    thesis["entry"]["actual_price"] = actual_price
    thesis["entry"]["actual_date"] = actual_date

    history_at = event_date or now
    thesis["status"] = "ACTIVE"
    thesis["status_history"].append({"status": "ACTIVE", "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Opened futures position %s at %.2f (%s contracts)",
        thesis["thesis_id"],
        actual_price,
        pos["quantity"],
    )
    return thesis


def terminate(
    state_dir: Path,
    thesis_id: str,
    terminal_status: str,
    exit_reason: str,
    actual_price: float | None = None,
    actual_date: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Move thesis to a terminal state (CLOSED or INVALIDATED).

    For CLOSED: delegates to close() which requires actual_price/date.
    For INVALIDATED: actual_price/date are optional. If ACTIVE with price,
    computes P&L. Partial outcome (no P&L) is allowed.

    Args:
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Raises:
        ValueError: If terminal_status is invalid or thesis is already terminal.
    """
    if terminal_status == "CLOSED":
        if actual_price is None or actual_date is None:
            raise ValueError("CLOSED requires actual_price and actual_date")
        return close(
            state_dir, thesis_id, exit_reason, actual_price, actual_date, event_date=event_date
        )

    if terminal_status != "INVALIDATED":
        raise ValueError(f"terminal_status must be CLOSED or INVALIDATED, got {terminal_status}")

    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must never reach the legacy per-unit
    # partial-outcome branch below, which ignores multiplier/direction.
    if _is_futures(thesis):
        return _terminate_futures(
            state_dir, thesis, exit_reason, actual_price, actual_date, event_date
        )

    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot terminate: already in terminal status {thesis['status']}")

    now = _now_iso()

    # Set exit data if provided
    if actual_price is not None:
        thesis["exit"]["actual_price"] = actual_price
    if actual_date is not None:
        thesis["exit"]["actual_date"] = actual_date
    # exit_reason enum: use "invalidated"; user's reason goes in status_history
    thesis["exit"]["exit_reason"] = "invalidated"

    entry_price = thesis["entry"].get("actual_price")
    history_at = event_date or now
    position = thesis.get("position")

    if (
        position
        and position.get("shares")
        and actual_price is not None
        and actual_date is not None
        and entry_price
    ):
        # Cumulative path: single-owner ledger append + roll-up. For a no-trim
        # ACTIVE thesis (shares_remaining == shares) this yields the same
        # pnl_dollars/pct as the legacy block below; for a PARTIALLY_CLOSED
        # thesis it correctly sums prior trims (no double-count).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="INVALIDATED",
            reason=f"invalidated: {exit_reason}",
            append_entry=True,
        )
    else:
        # Pre-PR-80B partial-outcome path — verbatim (covers no-price
        # terminate INVALIDATED, incl. position-attached but no exit price).
        #
        # Output-side finiteness (Issue #254, pre-existing money-critical
        # gap — same two-layer rationale as _finalize_outcome()'s
        # docstring): pnl_dollars/pnl_pct are computed into LOCAL
        # variables and validated (try/except OverflowError for
        # mid-arithmetic overflow on a disk-corrupted huge `shares`, then
        # math.isfinite() for a clean-but-inf/nan result) BEFORE any
        # mutation of thesis["outcome"]. compute_outcome mirrors the
        # original `if entry_price and actual_price:` gate exactly, so a
        # thesis with no price data is untouched exactly as before.
        pnl_pct = None
        pnl_dollars = None
        holding_days = None
        compute_outcome = bool(entry_price and actual_price)
        if compute_outcome:
            try:
                pnl_pct_raw = ((actual_price - entry_price) / entry_price) * 100
                pnl_dollars_raw = actual_price - entry_price
                if thesis.get("position") and thesis["position"].get("shares"):
                    pnl_dollars_raw *= thesis["position"]["shares"]
                pnl_pct = round(pnl_pct_raw, 2)
                pnl_dollars = round(pnl_dollars_raw, 2)
                outcome_finite = math.isfinite(pnl_pct) and math.isfinite(pnl_dollars)
            except OverflowError as exc:
                raise ValueError(
                    "computed pnl_dollars/pnl_pct overflowed (actual_price="
                    f"{actual_price}, entry_price={entry_price}) — operands too large"
                ) from exc
            if not outcome_finite:
                raise ValueError(
                    f"computed pnl_dollars/pnl_pct is not finite ({pnl_dollars}, {pnl_pct})"
                )

            entry_date = thesis["entry"].get("actual_date")
            if entry_date and actual_date:
                try:
                    holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
                except (ValueError, TypeError):
                    pass

        # All computed values validated finite — now, and only now, mutate.
        if compute_outcome:
            thesis["outcome"]["pnl_pct"] = pnl_pct
            thesis["outcome"]["pnl_dollars"] = pnl_dollars
            if holding_days is not None:
                thesis["outcome"]["holding_days"] = holding_days

        thesis["status"] = "INVALIDATED"
        thesis["status_history"].append(
            {
                "status": "INVALIDATED",
                "at": history_at,
                "reason": f"invalidated: {exit_reason}",
            }
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Terminated %s → INVALIDATED: %s", thesis_id, exit_reason)
    return thesis


def _terminate_futures(
    state_dir: Path,
    thesis: dict,
    exit_reason: str,
    actual_price: float | None,
    actual_date: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of terminate()'s INVALIDATED branch — deliberately
    NOT shared code (D2/D4 non-negotiable, see _is_futures docstring):
    must never reach the legacy per-unit no-position INVALIDATED branch
    above, which ignores multiplier/direction entirely.

    Unlike the equity legacy branch, when a full P&L cannot be computed
    (missing price/quantity) this NEVER falls back to a partial per-unit
    calculation — it simply records the INVALIDATED transition with no
    P&L, avoiding any multiplier-ignorant dollar figure.
    """
    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot terminate: already in terminal status {thesis['status']}")

    # P1-3 (user independent review, money-critical): actual_price is
    # OPTIONAL for INVALIDATED (unlike close()'s required actual_price),
    # so only validate when given — but validated before any mutation,
    # before _save_thesis().
    if actual_price is not None and _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "terminate() requires a finite positive actual_price for a futures "
            f"thesis when provided, got {actual_price!r}"
        )

    now = _now_iso()

    if actual_price is not None:
        thesis["exit"]["actual_price"] = actual_price
    if actual_date is not None:
        thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = "invalidated"

    entry_price = thesis["entry"].get("actual_price")
    history_at = event_date or now
    position = thesis.get("position")

    if (
        position
        and position.get("quantity")
        and actual_price is not None
        and actual_date is not None
        and entry_price
    ):
        _finalize_futures_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="INVALIDATED",
            reason=f"invalidated: {exit_reason}",
            append_entry=True,
        )
    else:
        # No P&L computed — plain INVALIDATED transition (see docstring:
        # never a multiplier-ignorant partial calculation).
        thesis["status"] = "INVALIDATED"
        thesis["status_history"].append(
            {
                "status": "INVALIDATED",
                "at": history_at,
                "reason": f"invalidated: {exit_reason}",
            }
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Terminated %s → INVALIDATED: %s", thesis["thesis_id"], exit_reason)
    return thesis


def mark_reviewed(
    state_dir: Path,
    thesis_id: str,
    *,
    review_date: str,
    outcome: str = "OK",
    notes: str | None = None,
) -> dict:
    """Record a review and advance next_review_date.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to review.
        review_date: Date of review (YYYY-MM-DD).
        outcome: One of "OK", "WARN", "REVIEW".
        notes: Optional review notes (appended to alerts).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is in terminal status or outcome is invalid.
    """
    valid_outcomes = {"OK", "WARN", "REVIEW"}
    if outcome not in valid_outcomes:
        raise ValueError(f"outcome must be one of {valid_outcomes}, got {outcome}")

    thesis = _load_thesis(state_dir, thesis_id)

    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot review terminal thesis ({thesis['status']})")

    interval = thesis["monitoring"].get("review_interval_days", 30)
    review_dt = datetime.fromisoformat(f"{review_date}T00:00:00+00:00")
    next_review = (review_dt + timedelta(days=interval)).strftime("%Y-%m-%d")

    thesis["monitoring"]["last_review_date"] = review_date
    thesis["monitoring"]["next_review_date"] = next_review
    thesis["monitoring"]["review_status"] = outcome

    if notes:
        thesis["monitoring"]["alerts"].append(f"[{review_date}] {outcome}: {notes}")

    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Reviewed %s: %s → next %s", thesis_id, outcome, next_review)
    return thesis


def list_active(state_dir: Path) -> list[dict]:
    """List all ACTIVE theses from the index."""
    return query(state_dir, status="ACTIVE")


def list_review_due(state_dir: Path, as_of: str) -> list[dict]:
    """List theses with next_review_date <= as_of.

    Args:
        state_dir: Path to state/theses/.
        as_of: Date string (YYYY-MM-DD) for comparison.

    Returns:
        List of index entries for theses due for review.
    """
    as_of_date = date.fromisoformat(as_of)
    index = _load_index(state_dir)
    results = []
    for tid, entry in index.get("theses", {}).items():
        if entry.get("status") in _TERMINAL_STATUSES:
            continue
        nrd = entry.get("next_review_date")
        if nrd:
            try:
                if date.fromisoformat(nrd) <= as_of_date:
                    results.append({"thesis_id": tid, **entry})
            except ValueError:
                logger.warning("Skipping unparsable next_review_date for %s: %s", tid, nrd)
    return results


# -- Recovery tools -----------------------------------------------------------


def rebuild_index(state_dir: Path) -> dict:
    """Rebuild _index.json from valid th_*.yaml files.

    Skips files that fail schema or business invariant validation.

    Returns:
        The rebuilt index dict.
    """
    index = {"version": 1, "theses": {}}
    for yaml_path in sorted(state_dir.glob("th_*.yaml")):
        try:
            thesis = yaml.safe_load(yaml_path.read_text())
            if thesis and "thesis_id" in thesis:
                _validate_thesis(thesis)
                _update_index_entry(index, thesis)
        except Exception as e:
            logger.warning("Skipping invalid file %s: %s", yaml_path.name, e)
            continue

    _save_index(state_dir, index)
    logger.info("Rebuilt index: %d theses", len(index["theses"]))
    return index


def validate_state(state_dir: Path) -> dict:
    """Check file ⇔ index consistency and schema validity.

    Returns:
        {"ok": bool, "missing_in_index": [...], "orphaned_in_index": [...],
         "field_mismatches": [...], "schema_errors": [...]}
    """
    index = _load_index(state_dir)
    index_ids = set(index.get("theses", {}).keys())
    file_ids = set()

    for yaml_path in state_dir.glob("th_*.yaml"):
        stem = yaml_path.stem
        file_ids.add(stem)

    missing_in_index = file_ids - index_ids
    orphaned_in_index = index_ids - file_ids

    field_mismatches = []
    schema_errors = []
    for tid in file_ids & index_ids:
        try:
            thesis = _load_thesis(state_dir, tid)
        except Exception:
            field_mismatches.append({"thesis_id": tid, "error": "failed to load"})
            continue

        try:
            _validate_thesis(thesis)
        except (ValueError, Exception) as e:
            schema_errors.append({"thesis_id": tid, "error": str(e)})
            continue

        idx_entry = index["theses"][tid]
        expected = _project_index_fields(thesis)
        for field, exp_val in expected.items():
            if idx_entry.get(field) != exp_val:
                field_mismatches.append(
                    {
                        "thesis_id": tid,
                        "field": field,
                        "file_value": exp_val,
                        "index_value": idx_entry.get(field),
                    }
                )

    ok = (
        not missing_in_index
        and not orphaned_in_index
        and not field_mismatches
        and not schema_errors
    )
    return {
        "ok": ok,
        "missing_in_index": sorted(missing_in_index),
        "orphaned_in_index": sorted(orphaned_in_index),
        "field_mismatches": field_mismatches,
        "schema_errors": schema_errors,
    }


# -- CLI entry point ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (0 ok, non-zero error).

    Extracted from the former ``if __name__ == "__main__"`` block (behavior of
    the pre-existing subcommands is unchanged) so the lifecycle subcommands are
    unit-testable via ``main([...])``.
    """
    import argparse

    def _strict_finite_float(value: str) -> float:
        """Argparse type= for --actual-price/--price (P1-3, user
        independent review, money-critical): a finite float. Plain
        `type=float` accepts "inf"/"-inf"/"nan" as valid Python float
        literals — a NaN/Infinity price would otherwise persist into
        thesis state and NaN-poison every downstream P&L computation.
        Modeled on futures-position-sizer's strict_positive_float /
        _strict_float_type, but deliberately does NOT also require > 0
        here (unlike that helper): this flag is shared between the equity
        and futures CLI paths, and a $0 equity exit price is a legitimate
        real-world value (e.g. a delisted/bankrupt position) — an actual
        downstream consumer test (drawdown-circuit-breaker) exercises
        exactly this. The futures-only finite-AND-positive constraint is
        enforced separately at the Python level by _valid_finite_positive()
        inside _open_futures_position()/_close_futures()/_trim_futures()/
        _terminate_futures() — this CLI guard only needs to close the
        nan/inf hole, not re-litigate positivity for a shared flag."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        return parsed

    def _strict_positive_int(value: str) -> int:
        """Argparse type= for --contracts/--contracts-sold (P1-4, user
        independent review): an exact positive whole number. Parses via
        int(), never float() (same reasoning as futures_sizing.py's
        strict_nonneg_int: float64 loses precision above 2**53, and a
        fractional string like "1.5" must be rejected outright — futures
        trade in whole contracts only, never silently truncated).

        P1-B (user re-review): also enforces the same _MAX_CONTRACTS
        sanity cap as _valid_positive_int()/_valid_nonneg_int() (the
        Python API side). Python's int() parses a 400-digit string with
        no error at all (arbitrary precision) — without this bound, such
        a value would reach the business logic layer as a "successfully
        parsed" CLI arg and only be rejected several calls later, deep
        inside open_position(). Caught here instead as an
        argparse.ArgumentTypeError (exit 2, a usage error) — consistent
        with every other malformed-input case this parser already
        rejects at the CLI boundary."""
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{value!r} must be a whole number of contracts"
            ) from exc
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        if parsed > _MAX_CONTRACTS:
            raise argparse.ArgumentTypeError(
                f"{value!r} exceeds the maximum contract count ({_MAX_CONTRACTS})"
            )
        return parsed

    def _strict_positive_finite_float(value: str) -> float:
        """Argparse type= for attach-futures-position's --expected-entry/
        --expected-stop ONLY (P1-C, user re-review) — a dedicated,
        futures-specific parser, distinct from _strict_finite_float above
        (which deliberately allows 0/negative for the shared --actual-price/
        --price flags — see its docstring). An expected futures price is
        never legitimately 0 or negative, so this rejects those too,
        matching _validate_expected_price_match()'s own finite-AND-positive
        requirement on the Python side. Does NOT touch attach-position's
        (equity) --expected-entry/--expected-stop, which keep the original
        plain type=float behavior — cross-attach and price-fail-open fixes
        in this PR are scoped to futures only."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        return parsed

    def _strict_shares(value: str) -> float:
        """Argparse type= for --shares (open-position) / --shares-sold
        (trim) ONLY (Issue #254, pre-existing money-critical gap) — a
        dedicated, equity-specific parser, per-domain like
        _strict_positive_int above (NOT a cap bolted onto the shared
        _strict_positive_finite_float, which is documented as
        futures-only and would conflate two independently-tunable sanity
        domains — see _is_futures()'s module docstring on why futures/
        equity code paths must not be merged).

        Parses via float() (never int()) since equity shares are
        legitimately fractional (7.86, matching a real IBKR/Robinhood
        fill) — unlike futures contracts, this does NOT truncate to a
        whole number. Rejects nan/inf/non-numeric (argparse.
        ArgumentTypeError, exit 2, no traceback) and enforces the same
        _MAX_SHARES sanity cap as _valid_finite_positive()'s callers on
        the Python API side, for the same reason _strict_positive_int
        enforces _MAX_CONTRACTS: a 400+-digit CLI string would otherwise
        reach the business logic layer as a "successfully parsed" value
        and only be rejected several calls later, deep inside
        open_position()/trim(). Note the mechanism differs from the
        contracts case: float("1" + "0"*400) returns inf cleanly (no
        exception — string-to-float parsing saturates rather than
        raising OverflowError, unlike int-to-float conversion), so this
        is caught by the isfinite() check below, not a try/except."""
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(f"{value!r} is not a valid number") from exc
        if not math.isfinite(parsed):
            raise argparse.ArgumentTypeError(f"{value!r} must be finite (not inf/-inf/nan)")
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{value!r} must be greater than 0")
        if parsed > _MAX_SHARES:
            raise argparse.ArgumentTypeError(
                f"{value!r} exceeds the maximum share count ({_MAX_SHARES})"
            )
        return parsed

    parser = argparse.ArgumentParser(description="Trader Memory Core — thesis store CLI")
    parser.add_argument("--state-dir", default="state/theses", help="Path to thesis state dir")
    sub = parser.add_subparsers(dest="command")

    # list
    list_p = sub.add_parser("list", help="List theses")
    list_p.add_argument("--ticker", help="Filter by ticker")
    list_p.add_argument("--status", help="Filter by status")
    list_p.add_argument("--type", dest="thesis_type", help="Filter by thesis type")
    list_p.add_argument("--date-from", help="Filter by created_at >= YYYY-MM-DD")
    list_p.add_argument("--date-to", help="Filter by created_at <= YYYY-MM-DD")

    # get
    get_p = sub.add_parser("get", help="Get thesis by ID")
    get_p.add_argument("thesis_id", help="Thesis ID")

    # review-due
    review_p = sub.add_parser("review-due", help="List theses due for review")
    review_p.add_argument("--as-of", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # rebuild-index
    sub.add_parser("rebuild-index", help="Rebuild _index.json from YAML files")

    # doctor
    sub.add_parser("doctor", help="Validate file/index consistency")

    # mark-reviewed
    mr_p = sub.add_parser("mark-reviewed", help="Record a review")
    mr_p.add_argument("thesis_id", help="Thesis ID")
    mr_p.add_argument("--review-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    mr_p.add_argument("--outcome", default="OK", choices=["OK", "WARN", "REVIEW"])
    mr_p.add_argument("--notes", default=None)

    # transition (IDEA → ENTRY_READY); --event-date backdates the history stamp
    tr_p = sub.add_parser("transition", help="Transition thesis status (e.g. ENTRY_READY)")
    tr_p.add_argument("thesis_id", help="Thesis ID")
    tr_p.add_argument("new_status", help="Target status (e.g. ENTRY_READY)")
    tr_p.add_argument("--reason", required=True, help="Reason for the transition")
    tr_p.add_argument("--event-date", default=None, help="Backdate status_history.at (YYYY-MM-DD)")

    # open-position (ENTRY_READY → ACTIVE)
    op_p = sub.add_parser("open-position", help="Open a position (→ ACTIVE)")
    op_p.add_argument("thesis_id", help="Thesis ID")
    op_p.add_argument(
        "--actual-price", type=_strict_finite_float, required=True, help="Entry price"
    )
    op_p.add_argument("--actual-date", required=True, help="Entry date (YYYY-MM-DD or ISO)")
    op_p.add_argument(
        "--shares", type=_strict_shares, default=None, help="Share count (fractional ok)"
    )
    op_p.add_argument(
        "--contracts", type=_strict_positive_int, default=None, help="Contract count (futures)"
    )
    op_p.add_argument(
        "--multiplier",
        type=float,
        default=None,
        help="Futures contract multiplier (required with --contracts if no futures "
        "position is already attached)",
    )
    op_p.add_argument(
        "--direction",
        choices=["LONG", "SHORT"],
        default=None,
        help="Futures direction (required with --contracts if no futures position "
        "is already attached)",
    )
    op_p.add_argument("--contract-symbol", default=None, help="Futures contract symbol, e.g. ES")
    op_p.add_argument(
        "--contract-currency",
        default=None,
        help="Futures contract currency (required with --contracts if no futures "
        "position is already attached; USD only)",
    )
    op_p.add_argument("--reason", default="position opened", help="Transition reason")
    op_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # attach-position (position-sizer report)
    ap_p = sub.add_parser("attach-position", help="Attach a position-sizer report")
    ap_p.add_argument("thesis_id", help="Thesis ID")
    ap_p.add_argument("--report", required=True, help="Path to position-sizer JSON report")
    ap_p.add_argument("--expected-entry", type=float, default=None, help="Expected entry price")
    ap_p.add_argument("--expected-stop", type=float, default=None, help="Expected stop price")

    # attach-futures-position (futures-position-sizer SIZED report)
    afp_p = sub.add_parser(
        "attach-futures-position", help="Attach a futures-position-sizer SIZED report"
    )
    afp_p.add_argument("thesis_id", help="Thesis ID")
    afp_p.add_argument(
        "--report", required=True, help="Path to futures-position-sizer SIZED JSON report"
    )
    afp_p.add_argument(
        "--expected-entry",
        type=_strict_positive_finite_float,
        default=None,
        help="Expected entry price",
    )
    afp_p.add_argument(
        "--expected-stop",
        type=_strict_positive_finite_float,
        default=None,
        help="Expected stop price",
    )

    # close (ACTIVE → CLOSED)
    cl_p = sub.add_parser("close", help="Close an ACTIVE thesis")
    cl_p.add_argument("thesis_id", help="Thesis ID")
    cl_p.add_argument(
        "--exit-reason",
        required=True,
        choices=["stop_hit", "target_hit", "time_stop", "invalidated", "manual"],
    )
    cl_p.add_argument("--actual-price", type=_strict_finite_float, required=True, help="Exit price")
    cl_p.add_argument("--actual-date", required=True, help="Exit date (YYYY-MM-DD or ISO)")
    cl_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    # trim (partial close: ACTIVE/PARTIALLY_CLOSED → PARTIALLY_CLOSED or CLOSED)
    tr2_p = sub.add_parser("trim", help="Partially close (trim) a position")
    tr2_p.add_argument("thesis_id", help="Thesis ID")
    tr2_p.add_argument(
        "--shares-sold", type=_strict_shares, default=None, help="Quantity sold (equity)"
    )
    tr2_p.add_argument(
        "--contracts-sold",
        type=_strict_positive_int,
        default=None,
        help="Quantity sold (futures)",
    )
    tr2_p.add_argument(
        "--price", type=_strict_finite_float, required=True, help="Trim execution price"
    )
    tr2_p.add_argument("--date", required=True, help="Trim date (YYYY-MM-DD or ISO)")
    tr2_p.add_argument("--reason", default="position trimmed", help="Trim reason")
    tr2_p.add_argument(
        "--exit-reason",
        default=None,
        choices=["stop_hit", "target_hit", "time_stop", "invalidated", "manual"],
        help="Only used if the trim fully closes the position (default manual)",
    )
    tr2_p.add_argument("--event-date", default=None, help="Override ledger timestamp")

    # terminate (→ CLOSED or INVALIDATED)
    tm_p = sub.add_parser("terminate", help="Move thesis to a terminal state")
    tm_p.add_argument("thesis_id", help="Thesis ID")
    tm_p.add_argument("--terminal-status", required=True, choices=["CLOSED", "INVALIDATED"])
    tm_p.add_argument("--exit-reason", required=True, help="Reason for termination")
    tm_p.add_argument(
        "--actual-price", type=_strict_finite_float, default=None, help="Exit price (optional)"
    )
    tm_p.add_argument("--actual-date", default=None, help="Exit date (optional)")
    tm_p.add_argument("--event-date", default=None, help="Backdate status_history.at")

    args = parser.parse_args(argv)
    state_dir = Path(args.state_dir)

    if args.command == "list":
        results = query(
            state_dir,
            ticker=args.ticker,
            status=args.status,
            thesis_type=args.thesis_type,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print(json.dumps(results, indent=2))
    elif args.command == "get":
        thesis = get(state_dir, args.thesis_id)
        print(yaml.dump(thesis, default_flow_style=False, sort_keys=False))
    elif args.command == "review-due":
        results = list_review_due(state_dir, args.as_of)
        print(json.dumps(results, indent=2))
    elif args.command == "rebuild-index":
        idx = rebuild_index(state_dir)
        print(f"Rebuilt index: {len(idx['theses'])} theses")
    elif args.command == "doctor":
        result = validate_state(state_dir)
        print(json.dumps(result, indent=2))
    elif args.command == "mark-reviewed":
        t = mark_reviewed(
            state_dir,
            args.thesis_id,
            review_date=args.review_date,
            outcome=args.outcome,
            notes=args.notes,
        )
        print(
            f"Reviewed {args.thesis_id}: {args.outcome}, next review: "
            f"{t['monitoring']['next_review_date']}"
        )
    elif args.command == "transition":
        t = transition(
            state_dir,
            args.thesis_id,
            args.new_status,
            args.reason,
            event_date=_coerce_dt(args.event_date),
        )
        print(f"{args.thesis_id} → {t['status']}")
    elif args.command == "open-position":
        # P3-2: same guard as open_position() itself (defense in depth at
        # the CLI boundary, symmetric with trim's "exactly one of" check).
        if args.shares is not None and args.contracts is not None:
            raise ValueError(
                "open-position got both --shares and --contracts; provide "
                "either --shares (equity) or --contracts (futures), not both"
            )
        t = open_position(
            state_dir,
            args.thesis_id,
            args.actual_price,
            _coerce_dt(args.actual_date),
            reason=args.reason,
            shares=args.shares,
            event_date=_coerce_dt(args.event_date),
            contracts=args.contracts,
            multiplier=args.multiplier,
            direction=args.direction,
            contract_symbol=args.contract_symbol,
            contract_currency=args.contract_currency,
        )
        pos = t.get("position") or {}
        if pos.get("quantity_unit") == "contracts":
            print(
                f"{args.thesis_id} → {t['status']} @ {args.actual_price} "
                f"x {pos.get('quantity')} contracts"
            )
        else:
            print(f"{args.thesis_id} → {t['status']} @ {args.actual_price} x {args.shares}")
    elif args.command == "attach-position":
        t = attach_position(
            state_dir,
            args.thesis_id,
            args.report,
            expected_entry=args.expected_entry,
            expected_stop=args.expected_stop,
        )
        print(f"Attached position to {args.thesis_id}: {t['position']['shares']} shares")
    elif args.command == "attach-futures-position":
        t = attach_futures_position(
            state_dir,
            args.thesis_id,
            args.report,
            expected_entry=args.expected_entry,
            expected_stop=args.expected_stop,
        )
        pos = t["position"]
        print(
            f"Attached futures position to {args.thesis_id}: "
            f"{pos['quantity']} contracts ({pos['direction']})"
        )
    elif args.command == "close":
        t = close(
            state_dir,
            args.thesis_id,
            args.exit_reason,
            args.actual_price,
            _coerce_dt(args.actual_date),
            event_date=_coerce_dt(args.event_date),
        )
        out = t.get("outcome") or {}
        print(
            f"{args.thesis_id} → {t['status']} ({args.exit_reason}), pnl={out.get('pnl_dollars')}"
        )
    elif args.command == "trim":
        if (args.shares_sold is None) == (args.contracts_sold is None):
            raise ValueError(
                "trim requires exactly one of --shares-sold (equity) or --contracts-sold (futures)"
            )
        quantity = args.shares_sold if args.shares_sold is not None else args.contracts_sold
        t = trim(
            state_dir,
            args.thesis_id,
            quantity,
            args.price,
            _coerce_dt(args.date),
            reason=args.reason,
            exit_reason=args.exit_reason,
            event_date=_coerce_dt(args.event_date),
        )
        pos = t.get("position") or {}
        if args.contracts_sold is not None:
            rem = pos.get("quantity_remaining")
            unit = "contracts"
        else:
            rem = pos.get("shares_remaining")
            unit = "shares"
        print(
            f"{args.thesis_id} → {t['status']} "
            f"(sold {quantity} {unit} @ {args.price}, remaining {rem})"
        )
    elif args.command == "terminate":
        t = terminate(
            state_dir,
            args.thesis_id,
            args.terminal_status,
            args.exit_reason,
            actual_price=args.actual_price,
            actual_date=_coerce_dt(args.actual_date),
            event_date=_coerce_dt(args.event_date),
        )
        print(f"{args.thesis_id} → {t['status']} ({args.exit_reason})")
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
