#!/usr/bin/env python3
"""
Contrarian Setup Gate -- pure synthesis logic.

The center of Jason Shapiro's contrarian pipeline: this module normalizes
the three upstream verdicts (crowding / news-failure / price-action) into
one fail-closed `NormalizedInput` per step, then combines them through an
explicit, exhaustively-tested precedence state machine into one actionable
`setup_status`.

This module is PURE: no file I/O, no network, no environment reads. The CLI
(`run_contrarian_setup_gate.py`) owns file loading -- unreadable /
parse_error / non_finite are CLI-level `load_error` tags detected before
this module ever sees the data (non_finite: PR #249 user-review round 3,
a whole-file recursive scan for any non-finite float anywhere, closing off
the only route by which a raw non-finite value could otherwise reach the
CLI's `allow_nan=False` JSON writer via an audit-echo field) -- and passes
either the parsed JSON or one of those tags into the `normalize_*`
functions below, which detect the remaining classes (malformed / stale /
symbol_mismatch / direction_mismatch / schema_unsupported / unknown_verdict
/ unknown_confidence / unknown_reason / invalid_stop_reference) themselves.

State machine precedence (plan Issue #241 §3.3, v4 -- SEQUENTIAL
pipeline-order evaluation, PR #249 user-review P1-3):

  Each step is evaluated in strict pipeline order -- crowding, then news,
  then price-action -- and each step FULLY SETTLES (reaches a
  determination) before the next step's file is even consulted for a
  decision. This is deliberate, not an optimization: an earlier step's
  definitive verdict must never be softened by a LATER step's problem
  (corruption, staleness, its own insufficiency, ...). The v3 design
  aggregated "any provided INVALID" and "any NOT_CONFIRMED" ACROSS both
  downstream steps before deciding which rule fired first; that let a
  later step's file corruption soften an earlier step's definitive
  NOT_CONFIRMED rejection back up to a mere INSUFFICIENT_EVIDENCE -- the
  same class of softening bug already fixed twice elsewhere in this gate
  (the loader path and the consistency path), now caught a third time in
  cross-step aggregation by an independent user review of PR #249.

  1. Crowding: INVALID/INSUFFICIENT -> INSUFFICIENT_EVIDENCE;
     NOT_CONFIRMED (classification NEUTRAL) -> REJECTED; CONFIRMED ->
     continue to step 2. (Crowding has no PENDING state -- the detector
     report is always required.)
  2. News, if provided (state != PENDING): INVALID -> INSUFFICIENT_EVIDENCE;
     NOT_CONFIRMED -> REJECTED; INSUFFICIENT -> INSUFFICIENT_EVIDENCE;
     CONFIRMED -> continue to step 3. If news is PENDING, price-action is
     still evaluated next under the out-of-order rule (step 3).
  3. Price-action, if provided: the same four-way settlement as step 2.
     Out-of-order use (price-action provided while news is still PENDING):
     price-action is STILL fully evaluated here -- INVALID/NOT_CONFIRMED/
     INSUFFICIENT still resolve to their normal outcomes -- but a CONFIRMED
     price-action caps the final status at CROWDED with warning
     `out_of_order_price_action` rather than advancing to READY_FOR_PLAN,
     since news was never actually confirmed.
  4. Progressive from the confirmed prefix: crowding only -> CROWDED;
     crowding+news -> WATCHING_PRICE; crowding+news+price-action ->
     READY_FOR_PLAN (direction, gate_confidence, entry_trigger,
     invalidation_level populated).

  Pipeline order therefore REFINES the issue's original "any explicit
  NOT_CONFIRMED rejects" framing: a later step's NOT_CONFIRMED can still
  be masked by an EARLIER step's own settlement (e.g. news=INSUFFICIENT
  settles before price-action=NOT_CONFIRMED is ever looked at, giving
  INSUFFICIENT_EVIDENCE, not REJECTED) -- each later step's validity is
  premised on the earlier ones already having passed, mirroring how
  technical-analyst itself refuses to run its own confirmation pass on a
  NEUTRAL (unconfirmed) detector.

Cross-input consistency (symbol_mismatch / direction_mismatch /
schema_unsupported) is PER-INPUT INVALID (v3): a failure marks the
exhibiting input INVALID with a named reason and flows into the rules
above exactly like a loader failure -- never a global override that could
soften crowding's own conclusion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "1.0"
SKILL_NAME = "contrarian-setup-gate"

STATE_CONFIRMED = "CONFIRMED"
STATE_NOT_CONFIRMED = "NOT_CONFIRMED"
STATE_INSUFFICIENT = "INSUFFICIENT"
STATE_PENDING = "PENDING"
STATE_INVALID = "INVALID"

STEP_CROWDING = "crowding"
STEP_NEWS = "news_failure"
STEP_PRICE = "price_action"

# CROWDED_LONG means the crowd is long -> fade SHORT. CROWDED_SHORT means
# the crowd is short -> fade LONG. NEUTRAL is not one of these keys (it
# maps to NOT_CONFIRMED, not a fade direction).
FADE_DIRECTION = {"CROWDED_LONG": "SHORT", "CROWDED_SHORT": "LONG"}

NEWS_VERDICTS = {"CONFIRMED", "NOT_CONFIRMED", "INSUFFICIENT_EVIDENCE"}
PRICE_VERDICTS = {"CONFIRMED", "NOT_CONFIRMED", "INSUFFICIENT_DATA"}

# LOW is a reserved token both upstreams document but never actually emit
# (technical-analyst's compute_confidence(): "LOW is reserved, never
# emitted"). Accepted here for forward-compatibility, ranked weakest.
# Anything else (non-string, or a string outside this set) is INVALID
# `<input>_unknown_confidence` -- never silently passed through (PR #249
# user-review P1-2: an unvalidated "BANANA" used to reach gate_confidence
# verbatim).
VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}
CONFIDENCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# "Near stale" fires when age is within this many days of the configured
# max age (and not already over it, which is INVALID `<input>_json_stale`).
NEAR_STALE_WINDOW_DAYS = 2

# Maps TA's short verdict_reason token (plan §2 output contract) back to
# the `checks` dict key that carries its `week_of`, for entry_trigger.
CHECK_REASON_TO_KEY = {
    "key_reversal": "weekly_key_reversal",
    "failed_extreme": "failed_extreme",
    "failed_breakout": "failed_breakout",
}

# The exhaustive set of verdict_reason tokens technical-analyst can emit
# for a CONFIRMED verdict (weekly_price_action.CHECK_REASON_MAP's values,
# verified against the merged source). Derived from CHECK_REASON_TO_KEY's
# keys so the two can never drift apart within this module; a cross-skill
# consistency test in test_gate_logic.py additionally pins this against
# TA's own source, so upstream drift there is caught, not silently
# trusted (PR #249 user-review round 2, P1-A). Unlike news's verdict_reason
# (display-only, open-ended vocabulary, never allowlisted -- see
# references/gate-decision-table.md), price-action's CONFIRMED
# verdict_reason feeds directly into `entry_trigger`, part of the
# actionable READY_FOR_PLAN output -- so it IS allowlisted here.
PRICE_ACTION_CONFIRMED_REASONS = frozenset(CHECK_REASON_TO_KEY)

REQUIRED_REPORT_KEYS = ("symbol", "direction", "verdict", "confidence")


@dataclass(frozen=True)
class NormalizedInput:
    """One step's normalized, fail-closed state.

    `kind` selects which fields `to_audit_dict()` surfaces, matching the
    `inputs.<step>` block shape in the output contract (plan §2). `reason`
    is populated for INVALID (a gate-side validation failure, named token)
    and for NOT_CONFIRMED/INSUFFICIENT derived from an upstream verdict
    (the upstream's own `verdict_reason`, when present -- more informative
    than a generic token).
    """

    kind: str
    state: str
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    classification: str | None = None
    direction: str | None = None  # crowding only: fade direction SHORT/LONG
    verdict: str | None = None
    confidence: str | None = None
    verdict_reason: str | None = None
    stop_reference: float | None = None
    entry_trigger: str | None = None
    data_date: str | None = None
    as_of: str | None = None
    age_days: int | None = None
    report_path: str | None = None

    def to_audit_dict(self) -> dict[str, Any]:
        if self.kind == STEP_CROWDING:
            return {
                "state": self.state,
                "classification": self.classification,
                "data_date": self.data_date,
                "age_days": self.age_days,
                "report_path": self.report_path,
            }
        if self.kind == STEP_NEWS:
            return {
                "state": self.state,
                "verdict": self.verdict,
                "confidence": self.confidence,
                "verdict_reason": self.verdict_reason,
                "as_of": self.as_of,
                "age_days": self.age_days,
                "report_path": self.report_path,
            }
        return {  # STEP_PRICE
            "state": self.state,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "verdict_reason": self.verdict_reason,
            "stop_reference": self.stop_reference,
            "as_of": self.as_of,
            "age_days": self.age_days,
            "report_path": self.report_path,
        }


def pending_input(kind: str) -> NormalizedInput:
    """The normalized state for a step whose report file was not provided."""
    return NormalizedInput(kind=kind, state=STATE_PENDING)


# --- Shared helpers --------------------------------------------------------


def _is_supported_schema(value: Any) -> bool:
    """Accept schema major version "1" (e.g. "1.0", "1.4"); reject anything
    else, including missing/non-string/other-major values (fail closed)."""
    if not isinstance(value, str) or not value:
        return False
    return value.split(".", 1)[0] == "1"


def _parse_as_of_date(as_of: str) -> date:
    return datetime.strptime(as_of, "%Y-%m-%d").date()


def _resolve_vintage(raw_value: Any, as_of_dt: date, max_age_days: int) -> tuple[str, int | None]:
    """Resolve a report's vintage string (detector `data_date` or
    news/price `run_context.as_of`) against `as_of_dt`.

    Returns (status, age_days) where status is one of "missing" (None/""),
    "invalid" (not a string, or unparsable), "future" (dated after
    as_of_dt), "stale" (older than max_age_days), or "ok". Mirrors the
    proven guard sequence in technical-analyst's
    resolve_direction_from_detector() and news-reaction-failure-analyzer's
    counterpart: type guard before slicing, no as_of-for-data_date
    fallback, age computed only once the value is known-good.
    """
    if raw_value is None or raw_value == "":
        return "missing", None
    if not isinstance(raw_value, str):
        return "invalid", None
    try:
        value_dt = datetime.strptime(raw_value[:10], "%Y-%m-%d").date()
    except ValueError:
        return "invalid", None
    age_days = (as_of_dt - value_dt).days
    if age_days < 0:
        return "future", age_days
    if age_days > max_age_days:
        return "stale", age_days
    return "ok", age_days


def _near_stale(age_days: int, max_age_days: int) -> bool:
    return (max_age_days - age_days) <= NEAR_STALE_WINDOW_DAYS


def _valid_stop_reference(value: Any) -> float | None:
    """A usable stop_reference: a finite, positive, non-bool number.
    `isinstance(True, int)` is True in Python, so bool must be excluded
    explicitly, or a boolean would silently pass as 0.0/1.0. Non-finite
    values (inf/-inf/NaN -- all of which `json.loads` accepts as literal
    tokens even though they aren't standard JSON) are rejected here too:
    a non-finite stop_reference used to flow straight through to
    READY_FOR_PLAN's `invalidation_level` and produce non-standard JSON
    output (PR #249 user-review round 2, P1-B)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _resolve_stop_reference(raw_data: dict[str, Any]) -> tuple[float | None, str | None]:
    """handoff.price_action.stop_reference, falling back to top-level
    swing_levels.stop_reference when handoff provides no value at all
    (plan §3.1). Returns (value, error): error is `None` on success,
    `"missing"` when neither source provided any non-null value, or
    `"invalid"` when a source provided an explicit but unusable value
    (wrong type, bool, non-finite, zero, or negative) -- an explicit
    garbage value is a real report bug and must not be silently masked
    by falling through to the other source."""
    handoff = raw_data.get("handoff")
    if isinstance(handoff, dict):
        price_action = handoff.get("price_action")
        if isinstance(price_action, dict):
            raw_value = price_action.get("stop_reference")
            if raw_value is not None:
                value = _valid_stop_reference(raw_value)
                return (value, None) if value is not None else (None, "invalid")

    swing_levels = raw_data.get("swing_levels")
    if isinstance(swing_levels, dict):
        raw_value = swing_levels.get("stop_reference")
        if raw_value is not None:
            value = _valid_stop_reference(raw_value)
            return (value, None) if value is not None else (None, "invalid")

    return None, "missing"


def _build_entry_trigger(raw_data: dict[str, Any], verdict_reason: Any) -> str | None:
    """Factual echo of the TA confirming signal: `verdict_reason` plus the
    matching check's `week_of`, when both are resolvable. Never raises on
    an unexpected shape -- degrades to a shorter echo, or None."""
    if not isinstance(verdict_reason, str) or not verdict_reason:
        return None
    week_of = None
    checks = raw_data.get("checks")
    if isinstance(checks, dict):
        check_key = CHECK_REASON_TO_KEY.get(verdict_reason)
        if check_key:
            check = checks.get(check_key)
            if isinstance(check, dict):
                candidate = check.get("week_of")
                if isinstance(candidate, str) and candidate:
                    week_of = candidate
    if week_of:
        return f"price-action confirmation: {verdict_reason} at week_of={week_of}"
    return f"price-action confirmation: {verdict_reason}"


# --- Per-step normalization -------------------------------------------------


def normalize_crowding(
    raw_data: Any,
    load_error: str | None,
    *,
    symbol: str,
    as_of: str,
    max_age_days: int,
    report_path: str | None = None,
) -> NormalizedInput:
    """Normalize a cot-contrarian-detector report for `symbol`.

    CROWDED_LONG/CROWDED_SHORT -> CONFIRMED (direction = fade side).
    NEUTRAL -> NOT_CONFIRMED (measurably not crowded, an explicit
    negative -- not an insufficiency). Symbol absent from markets[] or
    present in skipped[] -> INSUFFICIENT (detector_missing_symbol).
    Everything else fails closed to INVALID with a named reason.
    """
    kind = STEP_CROWDING
    if load_error == "unreadable":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason="detector_unreadable", report_path=report_path
        )
    if load_error == "parse_error":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason="detector_parse_error", report_path=report_path
        )
    if load_error == "non_finite":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason="detector_non_finite", report_path=report_path
        )
    if not isinstance(raw_data, dict):
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason="detector_malformed", report_path=report_path
        )

    if not _is_supported_schema(raw_data.get("schema_version")):
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_schema_unsupported",
            report_path=report_path,
        )

    run_context = raw_data.get("run_context")
    run_context = run_context if isinstance(run_context, dict) else {}
    markets_raw = raw_data.get("markets")
    markets = markets_raw if isinstance(markets_raw, list) else []
    skipped_raw = raw_data.get("skipped")
    skipped_list = skipped_raw if isinstance(skipped_raw, list) else []
    # Only string symbols are ever eligible to match --symbol (itself a
    # string); filtering here also avoids ever trying to add an unhashable
    # value (a list/dict "symbol" in an untrusted skip-entry) to this set,
    # which would crash the set comprehension itself (PR #249 P1-1).
    skipped_symbols = {
        s.get("symbol")
        for s in skipped_list
        if isinstance(s, dict) and isinstance(s.get("symbol"), str)
    }

    # Duplicate symbol rows in markets[] -> first match wins (the `next()`
    # pattern the detector itself uses; plan §3.2 v2 P2-7).
    market_row = next(
        (m for m in markets if isinstance(m, dict) and m.get("symbol") == symbol), None
    )
    if market_row is None or symbol in skipped_symbols:
        return NormalizedInput(
            kind=kind,
            state=STATE_INSUFFICIENT,
            reason="detector_missing_symbol",
            report_path=report_path,
        )

    data_date = run_context.get("data_date")
    as_of_dt = _parse_as_of_date(as_of)
    status, age_days = _resolve_vintage(data_date, as_of_dt, max_age_days)
    if status == "missing":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_missing_data_date",
            report_path=report_path,
        )
    if status == "invalid":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_invalid_data_date",
            report_path=report_path,
        )
    if status == "future":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_future_data_date",
            data_date=data_date,
            age_days=age_days,
            report_path=report_path,
        )
    if status == "stale":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_json_stale",
            data_date=data_date,
            age_days=age_days,
            report_path=report_path,
        )

    assert age_days is not None  # status == "ok" always sets age_days
    warnings: list[str] = []
    if _near_stale(age_days, max_age_days):
        warnings.append("detector_near_stale")
    row_data_date = market_row.get("data_date")
    if isinstance(row_data_date, str) and row_data_date and row_data_date != data_date:
        warnings.append("detector_data_date_divergence")

    classification = market_row.get("classification")
    if classification == "NEUTRAL":
        return NormalizedInput(
            kind=kind,
            state=STATE_NOT_CONFIRMED,
            reason="detector_not_crowded",
            classification=classification,
            data_date=data_date,
            age_days=age_days,
            warnings=tuple(warnings),
            report_path=report_path,
        )
    # Type guard BEFORE the allowlist membership check: `in`/`not in` on a
    # dict requires the operand to be hashable, so an unhashable
    # classification (e.g. a JSON list) would otherwise crash this line
    # with TypeError instead of failing closed (PR #249 P1-1).
    if not isinstance(classification, str) or classification not in FADE_DIRECTION:
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason="detector_unknown_classification",
            classification=classification,
            data_date=data_date,
            age_days=age_days,
            warnings=tuple(warnings),
            report_path=report_path,
        )
    return NormalizedInput(
        kind=kind,
        state=STATE_CONFIRMED,
        classification=classification,
        direction=FADE_DIRECTION[classification],
        data_date=data_date,
        age_days=age_days,
        warnings=tuple(warnings),
        report_path=report_path,
    )


def _normalize_downstream_report(
    raw_data: Any,
    load_error: str | None,
    *,
    kind: str,
    symbol: str,
    as_of: str,
    max_age_days: int,
    detector: NormalizedInput,
    report_path: str | None,
    valid_verdicts: set[str],
    verdict_to_state: dict[str, str],
    prefix: str,
) -> NormalizedInput:
    """Shared normalization body for news-failure and price-action reports
    (both share the same top-level shape: symbol/direction/verdict/
    confidence/verdict_reason/run_context.as_of). Only price-action needs
    the extra stop_reference/entry_trigger handling, layered on by its own
    wrapper below."""
    if load_error == "unreadable":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_unreadable", report_path=report_path
        )
    if load_error == "parse_error":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_parse_error", report_path=report_path
        )
    if load_error == "non_finite":
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_non_finite", report_path=report_path
        )
    if not isinstance(raw_data, dict):
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_malformed", report_path=report_path
        )
    if any(key not in raw_data for key in REQUIRED_REPORT_KEYS):
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_malformed", report_path=report_path
        )

    report_symbol = raw_data.get("symbol")
    if (
        not isinstance(report_symbol, str)
        or report_symbol.strip().upper() != symbol.strip().upper()
    ):
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_symbol_mismatch",
            report_path=report_path,
        )

    return _validated_report_input(
        raw_data,
        kind=kind,
        as_of=as_of,
        max_age_days=max_age_days,
        detector=detector,
        report_path=report_path,
        valid_verdicts=valid_verdicts,
        verdict_to_state=verdict_to_state,
        prefix=prefix,
    )


def _validated_report_input(
    raw_data: dict[str, Any],
    *,
    kind: str,
    as_of: str,
    max_age_days: int,
    detector: NormalizedInput,
    report_path: str | None,
    valid_verdicts: set[str],
    verdict_to_state: dict[str, str],
    prefix: str,
) -> NormalizedInput:
    run_context = raw_data.get("run_context")
    run_context = run_context if isinstance(run_context, dict) else {}

    schema_source = run_context if prefix == "price_action" else raw_data
    if not _is_supported_schema(schema_source.get("schema_version")):
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_schema_unsupported",
            report_path=report_path,
        )

    report_direction = raw_data.get("direction")
    if report_direction is None:
        # The report's own direction resolution failed upstream (e.g.
        # NRF's no_direction_provided early exit) -- this is that input's
        # own fail-closed insufficiency, not a mismatch against the
        # detector. Comparing None != detector.classification below would
        # otherwise always be truthy and misreport this as
        # `<prefix>_direction_mismatch` (P3-1).
        fallback_reason = raw_data.get("verdict_reason")
        if isinstance(fallback_reason, str) and fallback_reason:
            return NormalizedInput(
                kind=kind,
                state=STATE_INSUFFICIENT,
                reason=fallback_reason,
                verdict=raw_data.get("verdict"),
                confidence=raw_data.get("confidence"),
                verdict_reason=fallback_reason,
                report_path=report_path,
            )
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_malformed", report_path=report_path
        )
    if not isinstance(report_direction, str):
        # A non-null, non-string direction (a JSON list/dict/number/bool)
        # is malformed input, not a legitimate mismatch to report against
        # the detector's classification (PR #249 P1-1: every enum-shaped
        # field must be type-validated before it participates in any
        # comparison or membership check).
        return NormalizedInput(
            kind=kind, state=STATE_INVALID, reason=f"{prefix}_malformed", report_path=report_path
        )
    if detector.state == STATE_CONFIRMED and report_direction != detector.classification:
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_direction_mismatch",
            report_path=report_path,
        )

    as_of_value = run_context.get("as_of")
    as_of_dt = _parse_as_of_date(as_of)
    status, age_days = _resolve_vintage(as_of_value, as_of_dt, max_age_days)
    if status == "missing":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_missing_as_of",
            report_path=report_path,
        )
    if status == "invalid":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_invalid_as_of",
            report_path=report_path,
        )
    if status == "future":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_future_as_of",
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )
    if status == "stale":
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_json_stale",
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )

    assert age_days is not None
    warnings: list[str] = []
    if _near_stale(age_days, max_age_days):
        warnings.append(f"{prefix}_near_stale")

    verdict = raw_data.get("verdict")
    verdict_reason = raw_data.get("verdict_reason")
    confidence = raw_data.get("confidence")

    # Type guard BEFORE the allowlist membership check: `verdict not in
    # valid_verdicts` requires verdict to be hashable, so an unhashable
    # verdict (e.g. a JSON list) would otherwise crash with TypeError
    # instead of failing closed (PR #249 P1-1, the reported repro). A
    # non-string verdict is malformed input; a string outside the
    # allowlist is an unknown (but well-typed) verdict -- two distinct,
    # named reasons.
    if not isinstance(verdict, str):
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_malformed",
            verdict=verdict,
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )
    if verdict not in valid_verdicts:
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_unknown_verdict",
            verdict=verdict,
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )

    # Same two-step guard for confidence (PR #249 P1-1/P1-2): an unhashable
    # confidence would otherwise crash `CONFIDENCE_RANK.get(...)` deep
    # inside gate_confidence computation, and an unvalidated string (e.g.
    # "BANANA") would otherwise pass straight through to the output
    # contract's HIGH|MEDIUM|LOW|null field.
    if not isinstance(confidence, str):
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_malformed",
            verdict=verdict,
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )
    if confidence not in VALID_CONFIDENCES:
        return NormalizedInput(
            kind=kind,
            state=STATE_INVALID,
            reason=f"{prefix}_unknown_confidence",
            verdict=verdict,
            confidence=confidence,
            as_of=as_of_value,
            age_days=age_days,
            report_path=report_path,
        )

    state = verdict_to_state[verdict]
    if state == STATE_CONFIRMED and prefix == "price_action":
        # verdict_reason feeds entry_trigger, part of the actionable
        # READY_FOR_PLAN output -- unlike the display-only fallback below
        # (used for NOT_CONFIRMED/INSUFFICIENT and for news generally),
        # it is validated type-first, then against TA's own contract
        # (PR #249 user-review round 2, P1-A).
        if not isinstance(verdict_reason, str) or not verdict_reason:
            return NormalizedInput(
                kind=kind,
                state=STATE_INVALID,
                reason="price_action_malformed",
                verdict=verdict,
                confidence=confidence,
                as_of=as_of_value,
                age_days=age_days,
                warnings=tuple(warnings),
                report_path=report_path,
            )
        if verdict_reason not in PRICE_ACTION_CONFIRMED_REASONS:
            return NormalizedInput(
                kind=kind,
                state=STATE_INVALID,
                reason="price_action_unknown_reason",
                verdict=verdict,
                confidence=confidence,
                verdict_reason=verdict_reason,
                as_of=as_of_value,
                age_days=age_days,
                warnings=tuple(warnings),
                report_path=report_path,
            )

        stop_reference, stop_error = _resolve_stop_reference(raw_data)
        if stop_error is not None:
            reason = (
                "price_action_missing_stop_reference"
                if stop_error == "missing"
                else "price_action_invalid_stop_reference"
            )
            return NormalizedInput(
                kind=kind,
                state=STATE_INVALID,
                reason=reason,
                verdict=verdict,
                confidence=confidence,
                verdict_reason=verdict_reason,
                as_of=as_of_value,
                age_days=age_days,
                warnings=tuple(warnings),
                report_path=report_path,
            )
        return NormalizedInput(
            kind=kind,
            state=STATE_CONFIRMED,
            verdict=verdict,
            confidence=confidence,
            verdict_reason=verdict_reason,
            stop_reference=stop_reference,
            entry_trigger=_build_entry_trigger(raw_data, verdict_reason),
            as_of=as_of_value,
            age_days=age_days,
            warnings=tuple(warnings),
            report_path=report_path,
        )

    reason = (
        verdict_reason
        if isinstance(verdict_reason, str) and verdict_reason
        else f"{prefix}_{state.lower()}"
    )
    return NormalizedInput(
        kind=kind,
        state=state,
        reason=reason if state != STATE_CONFIRMED else None,
        verdict=verdict,
        confidence=confidence,
        verdict_reason=verdict_reason,
        as_of=as_of_value,
        age_days=age_days,
        warnings=tuple(warnings),
        report_path=report_path,
    )


def normalize_news(
    raw_data: Any,
    load_error: str | None,
    *,
    symbol: str,
    as_of: str,
    max_age_days: int,
    detector: NormalizedInput,
    report_path: str | None = None,
) -> NormalizedInput:
    """Normalize a news-reaction-failure-analyzer report for `symbol`."""
    return _normalize_downstream_report(
        raw_data,
        load_error,
        kind=STEP_NEWS,
        symbol=symbol,
        as_of=as_of,
        max_age_days=max_age_days,
        detector=detector,
        report_path=report_path,
        valid_verdicts=NEWS_VERDICTS,
        verdict_to_state={
            "CONFIRMED": STATE_CONFIRMED,
            "NOT_CONFIRMED": STATE_NOT_CONFIRMED,
            "INSUFFICIENT_EVIDENCE": STATE_INSUFFICIENT,
        },
        prefix="news",
    )


def normalize_price_action(
    raw_data: Any,
    load_error: str | None,
    *,
    symbol: str,
    as_of: str,
    max_age_days: int,
    detector: NormalizedInput,
    report_path: str | None = None,
) -> NormalizedInput:
    """Normalize a technical-analyst contrarian-confirmation report for
    `symbol`. schema_version is read from `run_context.schema_version`
    (TA carries no top-level key -- reading top-level here would silently
    disable the check; plan §3.2 v2 P1-3)."""
    return _normalize_downstream_report(
        raw_data,
        load_error,
        kind=STEP_PRICE,
        symbol=symbol,
        as_of=as_of,
        max_age_days=max_age_days,
        detector=detector,
        report_path=report_path,
        valid_verdicts=PRICE_VERDICTS,
        verdict_to_state={
            "CONFIRMED": STATE_CONFIRMED,
            "NOT_CONFIRMED": STATE_NOT_CONFIRMED,
            "INSUFFICIENT_DATA": STATE_INSUFFICIENT,
        },
        prefix="price_action",
    )


# --- State machine -----------------------------------------------------


def decide_setup_status(
    crowding: NormalizedInput, news: NormalizedInput, price: NormalizedInput
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Apply the SEQUENTIAL precedence rules (module docstring, v4) to the
    three normalized inputs. Returns (setup_status, missing_confirmations,
    extra_warnings) -- `extra_warnings` holds machine-level warnings (only
    `out_of_order_price_action` today); per-input warnings are merged by
    the caller (`build_gate_result`).

    Each step fully settles -- reaches a determination -- before the next
    step's state is even inspected. This is what makes the "earlier
    definitive verdicts are never softened by later problems" property
    structural rather than something a rule-ordering audit has to keep
    re-proving (PR #249 P1-3)."""
    missing: list[dict[str, Any]] = []
    extra_warnings: list[str] = []

    # Step 1: crowding, evaluated first and exclusively.
    if crowding.state in (STATE_INVALID, STATE_INSUFFICIENT):
        missing.append({"step": STEP_CROWDING, "state": crowding.state, "reason": crowding.reason})
        return "INSUFFICIENT_EVIDENCE", missing, extra_warnings
    if crowding.state == STATE_NOT_CONFIRMED:
        missing.append(
            {
                "step": STEP_CROWDING,
                "state": STATE_NOT_CONFIRMED,
                "reason": crowding.reason or "detector_not_crowded",
            }
        )
        return "REJECTED", missing, extra_warnings
    # Crowding is CONFIRMED from here.

    def _settle(step: str, inp: NormalizedInput) -> tuple[str, list[dict[str, Any]]] | None:
        """Settle one downstream step (news or price-action) against its
        own four-way outcome. Returns (status, missing_entries) when the
        step is definitive, or None when it's CONFIRMED (continue to the
        next step) -- PENDING is handled separately by each call site
        since its meaning differs between news (step 2) and price-action
        (step 3, where it never blocks)."""
        if inp.state == STATE_INVALID:
            return "INSUFFICIENT_EVIDENCE", [
                {"step": step, "state": inp.state, "reason": inp.reason}
            ]
        if inp.state == STATE_NOT_CONFIRMED:
            return "REJECTED", [{"step": step, "state": inp.state, "reason": inp.reason}]
        if inp.state == STATE_INSUFFICIENT:
            return "INSUFFICIENT_EVIDENCE", [
                {"step": step, "state": inp.state, "reason": inp.reason}
            ]
        return None

    # Step 2: news. Fully settles before price-action is ever consulted --
    # unless news itself is PENDING, in which case price-action is still
    # evaluated next (out-of-order use, handled inside the PENDING branch).
    if news.state != STATE_PENDING:
        settled = _settle(STEP_NEWS, news)
        if settled is not None:
            status, entries = settled
            missing.extend(entries)
            return status, missing, extra_warnings
        # news.state == CONFIRMED. Step 3: price-action.
        if price.state == STATE_PENDING:
            missing.append({"step": STEP_PRICE, "state": STATE_PENDING, "reason": "pending_step"})
            return "WATCHING_PRICE", missing, extra_warnings
        settled = _settle(STEP_PRICE, price)
        if settled is not None:
            status, entries = settled
            missing.extend(entries)
            return status, missing, extra_warnings
        # price.state == CONFIRMED: all three confirmed.
        return "READY_FOR_PLAN", missing, extra_warnings

    # news.state == PENDING: out-of-order use. Price-action is still fully
    # evaluated -- INVALID/NOT_CONFIRMED/INSUFFICIENT resolve normally; a
    # CONFIRMED price-action caps the status at CROWDED with a warning
    # (news was never actually confirmed, so this can't advance further).
    missing.append({"step": STEP_NEWS, "state": STATE_PENDING, "reason": "pending_step"})
    settled = _settle(STEP_PRICE, price)
    if settled is not None:
        status, entries = settled
        missing.extend(entries)
        return status, missing, extra_warnings
    if price.state == STATE_CONFIRMED:
        extra_warnings.append("out_of_order_price_action")
        return "CROWDED", missing, extra_warnings
    # price.state == PENDING too: crowding only.
    missing.append({"step": STEP_PRICE, "state": STATE_PENDING, "reason": "pending_step"})
    return "CROWDED", missing, extra_warnings


def _weakest_confidence(a: str | None, b: str | None) -> str | None:
    values = [v for v in (a, b) if v is not None]
    if not values:
        return None
    return min(values, key=lambda v: CONFIDENCE_RANK.get(v, 0))


def build_gate_result(
    *,
    symbol: str,
    crowding: NormalizedInput,
    news: NormalizedInput,
    price: NormalizedInput,
    max_detector_age_days: int,
    max_report_age_days: int,
    as_of: str,
) -> dict[str, Any]:
    """Compose the full output contract (plan §2) from three normalized
    inputs. Pure: no I/O, deterministic given its inputs."""
    setup_status, missing_confirmations, extra_warnings = decide_setup_status(crowding, news, price)

    direction = crowding.direction if crowding.state == STATE_CONFIRMED else None

    gate_confidence: str | None = None
    entry_trigger: str | None = None
    invalidation_level: float | None = None
    if setup_status == "READY_FOR_PLAN":
        gate_confidence = _weakest_confidence(news.confidence, price.confidence)
        entry_trigger = price.entry_trigger
        invalidation_level = price.stop_reference
        # Defensive invariant (PR #249 user-review round 2, P1-A/P1-B):
        # normalize_price_action's CONFIRMED path is the actual enforcer
        # -- it never returns CONFIRMED without a validated entry_trigger
        # and a finite positive stop_reference -- but this assert exists
        # as a second, independent guard against a future regression that
        # could let READY_FOR_PLAN slip out without both being usable.
        assert isinstance(entry_trigger, str) and entry_trigger, (
            "invariant violated: READY_FOR_PLAN requires a non-empty entry_trigger"
        )
        assert (
            isinstance(invalidation_level, (int, float))
            and not isinstance(invalidation_level, bool)
            and math.isfinite(invalidation_level)
            and invalidation_level > 0
        ), "invariant violated: READY_FOR_PLAN requires a finite, positive invalidation_level"

    warnings = list(extra_warnings)
    warnings.extend(crowding.warnings)
    warnings.extend(news.warnings)
    warnings.extend(price.warnings)
    if setup_status == "READY_FOR_PLAN":
        if price.confidence == "MEDIUM":
            warnings.append("price_action_confidence_medium")
        if news.confidence == "MEDIUM":
            warnings.append("news_confidence_medium")

    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "setup_status": setup_status,
        "direction": direction,
        "gate_confidence": gate_confidence,
        "entry_trigger": entry_trigger,
        "invalidation_level": invalidation_level,
        "missing_confirmations": missing_confirmations,
        "warnings": warnings,
        "inputs": {
            STEP_CROWDING: crowding.to_audit_dict(),
            STEP_NEWS: news.to_audit_dict(),
            STEP_PRICE: price.to_audit_dict(),
        },
        "run_context": {
            "symbol": symbol,
            "as_of": as_of,
            "max_detector_age_days": max_detector_age_days,
            "max_report_age_days": max_report_age_days,
            "schema_version": SCHEMA_VERSION,
            "skill": SKILL_NAME,
        },
    }
