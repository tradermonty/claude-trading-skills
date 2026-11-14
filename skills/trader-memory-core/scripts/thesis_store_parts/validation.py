# thesis_store part: Field validators, equity/futures position validation, and the schema
# check behind validate_thesis().
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import json
    import math
    import re
    from pathlib import Path
    from typing import Any

    import thesis_store
    from jsonschema import Draft7Validator

    _FORMAT_CHECKER = thesis_store._FORMAT_CHECKER
    _SCHEMA_PATH = thesis_store._SCHEMA_PATH
    _VALID_EXIT_REASONS = thesis_store._VALID_EXIT_REASONS
    _parse_dt = thesis_store._parse_dt


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


def _valid_finite_number(value: Any) -> float | None:
    """Return a finite numeric value as float, or ``None`` when invalid.

    Equity ``actual_price`` fields intentionally use a finite-only
    contract: zero can represent a delisted stock, and negative values
    are not excluded by the storage contract. Bool is excluded explicitly
    because it is an ``int`` subclass. A Python integer too large for a
    float raises ``OverflowError`` from ``math.isfinite()``; treat that as
    invalid input rather than allowing it to escape from a public API.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value):
            return None
        return float(value)
    except OverflowError:
        return None


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


def _require_long_equity_direction(value: Any, *, normalize: bool = False) -> None:
    """Equity sign is fixed LONG; normalize ingress, never persisted schema data."""
    if value is None:
        return
    if normalize and isinstance(value, str):
        value = value.strip().upper()
    if not isinstance(value, str) or value != "LONG":
        raise ValueError(
            "Equity accounting is long-only; unsupported direction. "
            "For futures use attach_futures_position() or open_position(contracts=...)."
        )


def _validate_equity_initial_stop(entry: Any, stop: Any) -> None:
    """Check a supplied initial pair, not an ACTIVE long's trailing stop."""
    if entry is None or stop is None:
        return
    valid_entry = _valid_finite_number(entry)
    valid_stop = _valid_finite_number(stop)
    if valid_entry is None or valid_stop is None:
        raise ValueError(
            "Equity accounting is long-only; initial entry/stop must be finite numbers"
        )
    # Preserve #257's finite nonpositive-price compatibility. A positive
    # initial stop above a positive fill describes unsupported short geometry.
    if valid_entry > 0 and valid_stop > valid_entry:
        raise ValueError("Equity accounting is long-only; an initial stop cannot exceed entry")


def _has_unsupported_equity_short(thesis: dict) -> bool:
    """Identify explicit short intent in the side enum or legacy manual labels."""
    position = thesis.get("position")
    if isinstance(position, dict) and _is_futures(thesis):
        return False
    values = [position.get("direction")] if isinstance(position, dict) else []
    origin = thesis.get("origin")
    if isinstance(origin, dict) and origin.get("skill") == "manual":
        raw = origin.get("raw_provenance")
        if isinstance(raw, dict):
            values.append(raw.get("direction"))
    return any(isinstance(value, str) and _is_short_label(value) for value in values)


_SHORT_WORDS = frozenset({"SHORT", "SHORTED", "SHORTING", "SELLSHORT"})


def _is_short_label(value: str) -> bool:
    """Classify a free-text legacy side label.

    A SHORT word ("Short position", "short sale", "Short.") or a bare "SELL"
    means short, mirroring how "Long position" / "BUY" stay long. SELL inside
    a longer label ("Sell to close", "Long (sell calls)") describes an exit or
    an overlay on a long, so it is not treated as short intent.
    """
    words = re.findall(r"[A-Z]+", value.upper())
    return words == ["SELL"] or not _SHORT_WORDS.isdisjoint(words)


def _validate_equity_long_only(thesis: dict) -> None:
    """Reject explicit legacy short intent before accounting/review or saving."""
    position = thesis.get("position")
    if position is not None and not isinstance(position, dict):
        raise ValueError("Equity accounting is long-only; position must be a mapping")
    if _is_futures(thesis):
        return
    _require_long_equity_direction((position or {}).get("direction"))
    # Historical raw_provenance was free text (e.g. BUY / Long position).
    # New ingress remains strict; only explicit short labels are refused here.
    if _has_unsupported_equity_short(thesis):
        raise ValueError("Equity accounting is long-only; unsupported short direction")


def _validate_equity_actual_prices(thesis: dict, *, allow_legacy_short: bool = False) -> None:
    """Reject unsupported side and invalid prices before save or lifecycle math."""
    if not allow_legacy_short:
        _validate_equity_long_only(thesis)
    for section_name in ("entry", "exit"):
        section = thesis.get(section_name)
        if not isinstance(section, dict):
            continue
        actual_price = section.get("actual_price")
        if actual_price is not None and _valid_finite_number(actual_price) is None:
            raise ValueError(
                f"equity thesis {section_name}.actual_price is invalid: "
                f"{actual_price!r} (must be a finite number)"
            )


def _validate_thesis(thesis: dict, *, allow_legacy_short: bool = False) -> None:
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
    else:
        # Issue #257: JSON Schema's number type accepts NaN/Infinity in
        # Python. Check both equity price fields at the common save
        # chokepoint so update() and future load-mutate-save paths cannot
        # persist a thesis that later becomes uncloseable.
        _validate_equity_actual_prices(thesis, allow_legacy_short=allow_legacy_short)
        if position and position.get("shares") is not None:
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


def validate_thesis(thesis: dict) -> None:
    """Supported validation API: check schema and business invariants.

    Return None on success without modifying the input or persisted state.

    Raises:
        ValueError: If schema validation or a business invariant fails.
    """
    _validate_thesis(thesis)
