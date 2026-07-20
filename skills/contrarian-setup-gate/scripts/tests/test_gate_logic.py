"""Tests for gate_logic.py -- the pure contrarian-setup-gate synthesis core.

Section 1 is the exhaustive state-machine matrix (plan Issue #241 §6's DoD:
"every verdict combination"), parametrized over all 125 reachable
combinations of normalized states, checked against an independent oracle
that encodes the precedence rules directly from the spec (not by calling
into decide_setup_status -- a matrix test that only re-derives the
implementation proves nothing). Section 2 pins the named precedence
combinations from the plan explicitly, for documentation and regression
value. Later sections cover normalization from real-schema fixtures,
consistency checks, staleness, warnings, and gate_confidence/entry_trigger.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_logic as gl  # noqa: E402

SYMBOL = "B6"
AS_OF = "2026-07-15"


# --- Section 1: exhaustive state-machine matrix -----------------------------

C_LABELS = ("CONF_L", "CONF_S", "NOT_CONF", "INSUFF", "INVALID")
NP_LABELS = ("CONF", "NOT_CONF", "INSUFF", "PENDING", "INVALID")


def _crowding(label: str) -> gl.NormalizedInput:
    if label == "CONF_L":
        return gl.NormalizedInput(
            kind=gl.STEP_CROWDING,
            state=gl.STATE_CONFIRMED,
            classification="CROWDED_LONG",
            direction="SHORT",
        )
    if label == "CONF_S":
        return gl.NormalizedInput(
            kind=gl.STEP_CROWDING,
            state=gl.STATE_CONFIRMED,
            classification="CROWDED_SHORT",
            direction="LONG",
        )
    if label == "NOT_CONF":
        return gl.NormalizedInput(
            kind=gl.STEP_CROWDING, state=gl.STATE_NOT_CONFIRMED, reason="detector_not_crowded"
        )
    if label == "INSUFF":
        return gl.NormalizedInput(
            kind=gl.STEP_CROWDING, state=gl.STATE_INSUFFICIENT, reason="detector_missing_symbol"
        )
    if label == "INVALID":
        return gl.NormalizedInput(
            kind=gl.STEP_CROWDING, state=gl.STATE_INVALID, reason="detector_json_stale"
        )
    raise AssertionError(label)


def _downstream(kind: str, label: str, prefix: str) -> gl.NormalizedInput:
    if label == "CONF":
        if kind == gl.STEP_PRICE:
            # A CONFIRMED price-action step must carry a validated
            # entry_trigger and stop_reference -- build_gate_result's
            # READY_FOR_PLAN invariant assert enforces this even for this
            # status-transition-only matrix (PR #249 user-review round 2).
            return gl.NormalizedInput(
                kind=kind,
                state=gl.STATE_CONFIRMED,
                confidence="HIGH",
                entry_trigger="price-action confirmation: key_reversal at week_of=2026-07-06",
                stop_reference=1.372,
            )
        return gl.NormalizedInput(kind=kind, state=gl.STATE_CONFIRMED, confidence="HIGH")
    if label == "NOT_CONF":
        return gl.NormalizedInput(
            kind=kind, state=gl.STATE_NOT_CONFIRMED, reason=f"{prefix}_not_confirmed"
        )
    if label == "INSUFF":
        return gl.NormalizedInput(
            kind=kind, state=gl.STATE_INSUFFICIENT, reason=f"{prefix}_insufficient"
        )
    if label == "PENDING":
        return gl.pending_input(kind)
    if label == "INVALID":
        return gl.NormalizedInput(kind=kind, state=gl.STATE_INVALID, reason=f"{prefix}_unreadable")
    raise AssertionError(label)


def _news(label: str) -> gl.NormalizedInput:
    return _downstream(gl.STEP_NEWS, label, "news")


def _price(label: str) -> gl.NormalizedInput:
    return _downstream(gl.STEP_PRICE, label, "price_action")


def _oracle_status(c: str, n: str, p: str) -> str:
    """Independent re-statement of plan §3.3's v4 SEQUENTIAL precedence
    (PR #249 P1-3), deliberately NOT derived from gate_logic's own code.
    Each step fully settles before the next is even looked at -- news
    settles before price-action is inspected at all, so a later step's
    problem can never soften an earlier step's definitive verdict."""
    if c in ("INVALID", "INSUFF"):
        return "INSUFFICIENT_EVIDENCE"
    if c == "NOT_CONF":
        return "REJECTED"
    # c in (CONF_L, CONF_S) from here. Step 2: news settles first, on its
    # own, without even looking at p yet.
    if n == "INVALID":
        return "INSUFFICIENT_EVIDENCE"
    if n == "NOT_CONF":
        return "REJECTED"
    if n == "INSUFF":
        return "INSUFFICIENT_EVIDENCE"
    if n == "PENDING":
        # Step 3, out-of-order: p is still fully evaluated on its own.
        if p == "INVALID":
            return "INSUFFICIENT_EVIDENCE"
        if p == "NOT_CONF":
            return "REJECTED"
        if p == "INSUFF":
            return "INSUFFICIENT_EVIDENCE"
        if p == "CONF":
            return "CROWDED"  # out-of-order cap + warning
        return "CROWDED"  # p == PENDING too: crowding only
    # n == CONF. Step 3: price-action, evaluated on its own.
    if p == "INVALID":
        return "INSUFFICIENT_EVIDENCE"
    if p == "NOT_CONF":
        return "REJECTED"
    if p == "INSUFF":
        return "INSUFFICIENT_EVIDENCE"
    if p == "PENDING":
        return "WATCHING_PRICE"
    return "READY_FOR_PLAN"  # p == CONF: all three confirmed


@pytest.mark.parametrize("c_label", C_LABELS)
@pytest.mark.parametrize("n_label", NP_LABELS)
@pytest.mark.parametrize("p_label", NP_LABELS)
def test_state_machine_matrix(c_label: str, n_label: str, p_label: str) -> None:
    crowding = _crowding(c_label)
    news = _news(n_label)
    price = _price(p_label)

    expected_status = _oracle_status(c_label, n_label, p_label)
    status, _missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == expected_status, (c_label, n_label, p_label)

    # direction: populated iff crowding is CONFIRMED, regardless of the
    # overall status (plan §2: "null unless crowding usable & confirmed").
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    if c_label == "CONF_L":
        assert result["direction"] == "SHORT"
    elif c_label == "CONF_S":
        assert result["direction"] == "LONG"
    else:
        assert result["direction"] is None

    # gate_confidence/entry_trigger/invalidation_level: only at READY_FOR_PLAN.
    if expected_status != "READY_FOR_PLAN":
        assert result["gate_confidence"] is None
        assert result["entry_trigger"] is None
        assert result["invalidation_level"] is None


# --- Section 2: named precedence pins (plan §3.3, §6) -----------------------


def test_pin_not_confirmed_beats_downstream_unreadable_invalid() -> None:
    """C=NOT_CONFIRMED + N=INVALID(unreadable) -> REJECTED (P1-1): crowding's
    own conclusion is never softened by a corrupted downstream file."""
    crowding = _crowding("NOT_CONF")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_INVALID, reason="news_unreadable")
    price = gl.pending_input(gl.STEP_PRICE)
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"
    assert missing == [
        {"step": "crowding", "state": "NOT_CONFIRMED", "reason": "detector_not_crowded"}
    ]


def test_pin_not_confirmed_beats_downstream_symbol_mismatch_invalid() -> None:
    """C=NOT_CONFIRMED + N=INVALID(symbol_mismatch) -> REJECTED: per-input
    INVALID from a consistency failure is never a global override that
    could soften crowding's own conclusion (round-2 P1, v3)."""
    crowding = _crowding("NOT_CONF")
    news = gl.NormalizedInput(
        kind=gl.STEP_NEWS, state=gl.STATE_INVALID, reason="news_symbol_mismatch"
    )
    price = gl.pending_input(gl.STEP_PRICE)
    status, _missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"


def test_pin_not_confirmed_beats_price_not_confirmed() -> None:
    """C=NOT_CONFIRMED + P=NOT_CONFIRMED -> REJECTED (crowding still the
    exclusive rejector; missing_confirmations names crowding, not price)."""
    crowding = _crowding("NOT_CONF")
    news = gl.pending_input(gl.STEP_NEWS)
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE, state=gl.STATE_NOT_CONFIRMED, reason="no_reversal_evidence"
    )
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"
    assert missing == [
        {"step": "crowding", "state": "NOT_CONFIRMED", "reason": "detector_not_crowded"}
    ]


def test_pin_crowding_invalid_beats_downstream_not_confirmed() -> None:
    """C=INVALID + N=NOT_CONFIRMED -> INSUFFICIENT_EVIDENCE (rule 1 first)."""
    crowding = _crowding("INVALID")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_NOT_CONFIRMED, reason="x")
    price = gl.pending_input(gl.STEP_PRICE)
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "INSUFFICIENT_EVIDENCE"
    assert missing == [{"step": "crowding", "state": "INVALID", "reason": "detector_json_stale"}]


def test_pin_crowding_insufficient_beats_downstream_not_confirmed() -> None:
    """C=INSUFFICIENT + N=NOT_CONFIRMED -> INSUFFICIENT_EVIDENCE."""
    crowding = _crowding("INSUFF")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_NOT_CONFIRMED, reason="x")
    price = gl.pending_input(gl.STEP_PRICE)
    status, _missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "INSUFFICIENT_EVIDENCE"


def test_pin_news_invalid_settles_before_price_is_ever_consulted() -> None:
    """C=CONFIRMED + N=INVALID + P=NOT_CONFIRMED -> INSUFFICIENT_EVIDENCE:
    news (step 2) settles as INVALID and returns immediately -- price
    (step 3) is never even inspected, so its NOT_CONFIRMED plays no part
    (v4 sequential model, PR #249 P1-3)."""
    crowding = _crowding("CONF_S")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_INVALID, reason="news_parse_error")
    price = gl.NormalizedInput(kind=gl.STEP_PRICE, state=gl.STATE_NOT_CONFIRMED, reason="x")
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "INSUFFICIENT_EVIDENCE"
    # Only the deciding (INVALID) step is named -- price was never reached.
    assert missing == [{"step": "news_failure", "state": "INVALID", "reason": "news_parse_error"}]


def test_pin_news_not_confirmed_settles_before_price_is_ever_consulted() -> None:
    """C=CONFIRMED + N=NOT_CONFIRMED + P=INSUFFICIENT -> REJECTED: news
    settles as NOT_CONFIRMED and returns immediately -- price's own
    INSUFFICIENT state is never reached (v4 sequential model)."""
    crowding = _crowding("CONF_L")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_NOT_CONFIRMED, reason="x")
    price = gl.NormalizedInput(kind=gl.STEP_PRICE, state=gl.STATE_INSUFFICIENT, reason="y")
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"
    assert missing == [{"step": "news_failure", "state": "NOT_CONFIRMED", "reason": "x"}]


def test_pin_news_not_confirmed_beats_price_invalid_p1_3_repro() -> None:
    """THE USER'S PR #249 P1-3 REPRO: C=CONFIRMED + N=NOT_CONFIRMED +
    P=INVALID(unreadable/binary) -> REJECTED, not INSUFFICIENT_EVIDENCE.
    Before the v4 fix, the v3 aggregate rule ("any provided INVALID
    across N/P" checked before "any NOT_CONFIRMED across N/P") let a
    LATER step's file corruption soften an EARLIER step's definitive
    rejection. News settling first structurally prevents that: price is
    never even inspected once news has already rejected."""
    crowding = _crowding("CONF_S")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_NOT_CONFIRMED, reason="no_reversal")
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE, state=gl.STATE_INVALID, reason="price_action_unreadable"
    )
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"
    assert missing == [{"step": "news_failure", "state": "NOT_CONFIRMED", "reason": "no_reversal"}]


def test_pin_news_insufficient_beats_price_not_confirmed_symmetric_case() -> None:
    """Symmetric to the P1-3 repro: C=CONFIRMED + N=INSUFFICIENT +
    P=NOT_CONFIRMED -> INSUFFICIENT_EVIDENCE, not REJECTED. News settles
    first as INSUFFICIENT (a run that tried and could not judge never
    advances); price's own NOT_CONFIRMED is never reached to reject."""
    crowding = _crowding("CONF_L")
    news = gl.NormalizedInput(
        kind=gl.STEP_NEWS, state=gl.STATE_INSUFFICIENT, reason="no_usable_events"
    )
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE, state=gl.STATE_NOT_CONFIRMED, reason="no_reversal"
    )
    status, missing, _warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "INSUFFICIENT_EVIDENCE"
    assert missing == [
        {"step": "news_failure", "state": "INSUFFICIENT", "reason": "no_usable_events"}
    ]


def test_pin_out_of_order_price_without_news_caps_at_crowded() -> None:
    crowding = _crowding("CONF_S")
    news = gl.pending_input(gl.STEP_NEWS)
    price = gl.NormalizedInput(kind=gl.STEP_PRICE, state=gl.STATE_CONFIRMED, confidence="HIGH")
    status, missing, warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "CROWDED"
    assert "out_of_order_price_action" in warnings
    assert {"step": "news_failure", "state": "PENDING", "reason": "pending_step"} in missing


def test_pin_out_of_order_price_not_confirmed_without_news_still_rejects() -> None:
    """A NOT_CONFIRMED price verdict still REJECTs even when news is
    PENDING (out-of-order use) -- rule 3 runs before rule 5's capping."""
    crowding = _crowding("CONF_S")
    news = gl.pending_input(gl.STEP_NEWS)
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE, state=gl.STATE_NOT_CONFIRMED, reason="no_reversal_evidence"
    )
    status, _missing, warnings = gl.decide_setup_status(crowding, news, price)
    assert status == "REJECTED"
    assert "out_of_order_price_action" not in warnings


# --- Section 3: normalize_crowding from real-schema fixtures ---------------


def detector_fixture(
    *,
    symbol: str = SYMBOL,
    classification: str = "CROWDED_SHORT",
    data_date: str = "2026-07-07",
    run_context_data_date: str | None = "2026-07-07",
    schema_version: str = "1.0",
    skipped: list | None = None,
    extra_market_fields: dict | None = None,
) -> dict:
    """Mirrors the real cot-contrarian-detector output shape (verified
    against reports/cot_crowding_2026-07-12.json, regenerated live)."""
    market_row = {
        "symbol": symbol,
        "status": "ok",
        "name": f"{symbol} Futures",
        "data_date": data_date,
        "classification": classification,
        "cot_index_3y": 7.2,
        "net_position": -87903,
    }
    if extra_market_fields:
        market_row.update(extra_market_fields)
    return {
        "schema_version": schema_version,
        "skill": "cot-contrarian-detector",
        "run_context": {
            "schema_version": schema_version,
            "skill": "cot-contrarian-detector",
            "as_of": "2026-07-12",
            "data_date": run_context_data_date,
        },
        "markets": [market_row],
        "skipped": skipped or [],
    }


def test_normalize_crowding_confirmed_crowded_short() -> None:
    data = detector_fixture(classification="CROWDED_SHORT")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_CONFIRMED
    assert result.classification == "CROWDED_SHORT"
    assert result.direction == "LONG"
    assert result.age_days == 8


def test_normalize_crowding_confirmed_crowded_long() -> None:
    data = detector_fixture(symbol="BT", classification="CROWDED_LONG")
    result = gl.normalize_crowding(data, None, symbol="BT", as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_CONFIRMED
    assert result.direction == "SHORT"


def test_normalize_crowding_neutral_is_not_confirmed() -> None:
    data = detector_fixture(classification="NEUTRAL")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_NOT_CONFIRMED
    assert result.reason == "detector_not_crowded"


def test_normalize_crowding_symbol_absent_is_insufficient() -> None:
    data = detector_fixture(symbol="ZZ")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "detector_missing_symbol"


def test_normalize_crowding_symbol_in_skipped_is_insufficient() -> None:
    data = detector_fixture()
    data["skipped"] = [{"symbol": SYMBOL, "reason": "no data returned by API"}]
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "detector_missing_symbol"


def test_normalize_crowding_skipped_entry_with_unhashable_symbol_never_crashes() -> None:
    """PR #249 P1-1: an untrusted skip-entry whose `symbol` is a JSON list
    must not crash building the skipped-symbols set (adding an unhashable
    value to a set raises TypeError). The bad entry is simply excluded
    from the set; the market row (present and usable) still normalizes."""
    data = detector_fixture(classification="CROWDED_SHORT")
    data["skipped"] = [{"symbol": ["not", "hashable"], "reason": "malformed"}]
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_CONFIRMED


def test_normalize_crowding_duplicate_symbol_rows_first_match_wins() -> None:
    """Duplicate `symbol` rows in markets[] -> first match wins (v2 P2-7)."""
    data = detector_fixture(classification="CROWDED_SHORT")
    data["markets"].append(
        {
            "symbol": SYMBOL,
            "status": "ok",
            "data_date": "2026-07-07",
            "classification": "CROWDED_LONG",
        }
    )
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.classification == "CROWDED_SHORT"


@pytest.mark.parametrize(
    "data_date_value,expected_reason",
    [
        (None, "detector_missing_data_date"),
        ("", "detector_missing_data_date"),
        (20260707, "detector_invalid_data_date"),
        ("not-a-date", "detector_invalid_data_date"),
        ("2026-07-20", "detector_future_data_date"),  # after AS_OF 2026-07-15
    ],
)
def test_normalize_crowding_data_date_guards(data_date_value, expected_reason) -> None:
    data = detector_fixture(run_context_data_date=data_date_value)
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == expected_reason


def test_normalize_crowding_stale_beyond_max_age() -> None:
    data = detector_fixture(run_context_data_date="2026-06-01")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_json_stale"


def test_normalize_crowding_near_stale_warning() -> None:
    # AS_OF 2026-07-15, data_date 2026-07-06 -> age 9, max 10 -> within 2.
    data = detector_fixture(run_context_data_date="2026-07-06")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_CONFIRMED
    assert "detector_near_stale" in result.warnings


def test_normalize_crowding_data_date_divergence_warning() -> None:
    data = detector_fixture(data_date="2026-07-01", run_context_data_date="2026-07-07")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert "detector_data_date_divergence" in result.warnings


def test_normalize_crowding_unknown_classification() -> None:
    data = detector_fixture(classification="WEIRD")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_unknown_classification"


@pytest.mark.parametrize("bad_classification", [["CROWDED_LONG"], {"a": 1}, 123, True])
def test_normalize_crowding_unhashable_or_wrong_type_classification_never_crashes(
    bad_classification,
) -> None:
    """PR #249 P1-1: `classification not in FADE_DIRECTION` requires a
    hashable operand -- an unhashable classification (list/dict) used to
    raise TypeError instead of failing closed. Every non-string type must
    degrade to detector_unknown_classification, never crash."""
    data = detector_fixture(classification=bad_classification)
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_unknown_classification"


def test_normalize_crowding_schema_unsupported() -> None:
    data = detector_fixture(schema_version="2.0")
    result = gl.normalize_crowding(data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_schema_unsupported"


def test_normalize_crowding_load_error_unreadable() -> None:
    result = gl.normalize_crowding(None, "unreadable", symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_unreadable"


def test_normalize_crowding_load_error_parse_error() -> None:
    result = gl.normalize_crowding(None, "parse_error", symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_parse_error"


def test_normalize_crowding_load_error_non_finite() -> None:
    """PR #249 user-review round 3: the CLI's whole-file non-finite scan
    reports this as a load_error, exactly like unreadable/parse_error --
    gate_logic never even sees the raw parsed data in this case."""
    result = gl.normalize_crowding(None, "non_finite", symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_non_finite"


@pytest.mark.parametrize("bad_shape", [["not", "a", "dict"], "a string", None, 42])
def test_normalize_crowding_wrong_top_level_shape(bad_shape) -> None:
    result = gl.normalize_crowding(bad_shape, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=10)
    assert result.state == gl.STATE_INVALID
    assert result.reason == "detector_malformed"


# --- Section 4: normalize_news / normalize_price_action ---------------------

CONFIRMED_CROWDING = gl.NormalizedInput(
    kind=gl.STEP_CROWDING,
    state=gl.STATE_CONFIRMED,
    classification="CROWDED_SHORT",
    direction="LONG",
)
UNUSABLE_CROWDING = gl.NormalizedInput(
    kind=gl.STEP_CROWDING, state=gl.STATE_INVALID, reason="detector_json_stale"
)


def news_fixture(
    *,
    symbol: str = SYMBOL,
    direction: str = "CROWDED_SHORT",
    verdict: str = "NOT_CONFIRMED",
    confidence: str = "HIGH",
    verdict_reason: str = "no_significant_drift",
    as_of: str = "2026-07-13",
    schema_version: str = "1.0",
) -> dict:
    """Mirrors the real news-reaction-failure-analyzer output shape
    (verified against analyze_news_reaction.py's output builder)."""
    return {
        "schema_version": schema_version,
        "skill": "news-reaction-failure-analyzer",
        "symbol": symbol,
        "direction": direction,
        "expected_direction": "BULLISH",
        "actual_reaction": "NO_REACTION",
        "verdict": verdict,
        "confidence": confidence,
        "relevant_events_used": 3,
        "aggregate": {"mean_z3": 0.1, "drift_stat": 0.2, "responded_ratio": 0.33},
        "evidence": [],
        "clusters": [],
        "dropped_events": [],
        "verdict_reason": verdict_reason,
        "run_context": {"as_of": as_of, "price_symbol": "GBPUSD"},
    }


def test_normalize_news_confirmed() -> None:
    data = news_fixture(verdict="CONFIRMED", verdict_reason=None, confidence="HIGH")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.confidence == "HIGH"
    assert result.age_days == 2


def test_normalize_news_not_confirmed_carries_upstream_reason() -> None:
    data = news_fixture(verdict="NOT_CONFIRMED", verdict_reason="no_significant_drift")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_NOT_CONFIRMED
    assert result.reason == "no_significant_drift"


def test_normalize_news_insufficient_evidence() -> None:
    data = news_fixture(verdict="INSUFFICIENT_EVIDENCE", verdict_reason="no_usable_events")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "no_usable_events"


def test_normalize_news_symbol_mismatch() -> None:
    data = news_fixture(symbol="D6")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_symbol_mismatch"


def test_normalize_news_direction_mismatch_only_checked_when_detector_usable() -> None:
    data = news_fixture(direction="CROWDED_LONG")  # detector says CROWDED_SHORT
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_direction_mismatch"

    # Same mismatched data, but detector is unusable -> check is skipped.
    result_skipped = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=UNUSABLE_CROWDING
    )
    assert result_skipped.reason != "news_direction_mismatch"


def test_normalize_news_missing_direction_key_is_malformed() -> None:
    data = news_fixture()
    del data["direction"]
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


def test_normalize_news_null_direction_is_insufficient_not_mismatch() -> None:
    """A provided `direction: null` is the report's OWN fail-closed exit
    (e.g. NRF's no_direction_provided early exit), not a mismatch against
    the detector's classification -- None != CROWDED_SHORT would otherwise
    always be truthy and misreport this as news_direction_mismatch (P3-1).
    """
    data = news_fixture(
        direction=None, verdict="INSUFFICIENT_EVIDENCE", verdict_reason="no_direction_provided"
    )
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "no_direction_provided"


def test_normalize_news_null_direction_without_verdict_reason_is_malformed() -> None:
    data = news_fixture(direction=None, verdict_reason=None)
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


def test_normalize_news_schema_unsupported() -> None:
    data = news_fixture(schema_version="2.0")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_schema_unsupported"


def test_normalize_news_unknown_verdict() -> None:
    data = news_fixture(verdict="MAYBE")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_unknown_verdict"


def test_normalize_news_unhashable_verdict_never_crashes() -> None:
    """THE USER'S PR #249 P1-1 REPRO: verdict: [] used to raise TypeError
    (`verdict not in valid_verdicts` requires a hashable operand) instead
    of failing closed with exit 0 + a report."""
    data = news_fixture(verdict=[])
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


@pytest.mark.parametrize("bad_verdict", [{"a": 1}, 123, True, None])
def test_normalize_news_wrong_type_verdict_is_malformed(bad_verdict) -> None:
    data = news_fixture(verdict=bad_verdict)
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


def test_normalize_news_unhashable_confidence_never_crashes() -> None:
    """THE USER'S PR #249 P1-1 REPRO: confidence: {} used to raise
    TypeError deep inside gate_confidence's CONFIDENCE_RANK.get(...)."""
    data = news_fixture(confidence={})
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


def test_normalize_news_unknown_confidence_string_fails_closed() -> None:
    """PR #249 P1-2 REPRO: confidence: "BANANA" used to pass straight
    through to gate_confidence unvalidated instead of failing closed."""
    data = news_fixture(verdict="CONFIRMED", confidence="BANANA")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_unknown_confidence"


def test_normalize_news_low_confidence_is_accepted_reserved_token() -> None:
    """LOW is a reserved token both upstreams document but never emit --
    accepted here, not rejected as unknown (PR #249 P1-2)."""
    data = news_fixture(verdict="CONFIRMED", confidence="LOW")
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.confidence == "LOW"


def test_normalize_news_non_string_direction_is_malformed_not_mismatch() -> None:
    """A non-null, non-string direction (e.g. a stray integer) is
    malformed input, not a legitimate mismatch to compare against the
    detector's classification (PR #249 P1-1)."""
    data = news_fixture(direction=123)
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_malformed"


def test_normalize_news_stale() -> None:
    data = news_fixture(as_of="2026-07-01")  # 14 days before AS_OF, max 7
    result = gl.normalize_news(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_json_stale"


def test_normalize_news_load_error_unreadable() -> None:
    result = gl.normalize_news(
        None, "unreadable", symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_unreadable"


def test_normalize_news_load_error_non_finite() -> None:
    result = gl.normalize_news(
        None, "non_finite", symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "news_non_finite"


def price_fixture(
    *,
    symbol: str = SYMBOL,
    direction: str = "CROWDED_SHORT",
    verdict: str = "CONFIRMED",
    confidence: str = "MEDIUM",
    verdict_reason: str = "key_reversal",
    as_of: str = "2026-07-14",
    schema_version: str = "1.0",
    stop_reference: float | None = 1.3720,
    include_handoff: bool = True,
    week_of: str = "2026-07-06",
) -> dict:
    """Mirrors the real technical-analyst contrarian-confirmation output
    shape (check_weekly_price_action.py's output builder)."""
    checks = {
        "weekly_key_reversal": {
            "triggered": True,
            "week_of": week_of,
            "detail": "new 12-week low reversed",
        },
        "failed_extreme": {"triggered": False, "week_of": None, "detail": ""},
        "failed_breakout": {"triggered": False, "week_of": None, "detail": ""},
    }
    swing_levels = {
        "nearest_swing_high": {"price": 1.4000, "week_of": week_of, "fallback": False},
        "nearest_swing_low": {"price": 1.3500, "week_of": week_of, "fallback": False},
        "stop_reference": stop_reference,
    }
    data = {
        "symbol": symbol,
        "direction": direction,
        "mode": "data",
        "verdict": verdict,
        "confidence": confidence,
        "verdict_reason": verdict_reason,
        "checks": checks if verdict == "CONFIRMED" else None,
        "swing_levels": swing_levels if verdict == "CONFIRMED" else None,
        "weekly_bars_used": 60,
        "last_completed_week": week_of,
        "run_context": {"as_of": as_of, "schema_version": schema_version},
    }
    if include_handoff:
        data["handoff"] = {
            "price_action": {
                "verdict": verdict,
                "confidence": confidence,
                "stop_reference": stop_reference,
                "report_path": "reports/ta_confirmation_B6_2026-07-14.json",
            }
        }
    return data


def test_normalize_price_action_confirmed_reads_stop_reference_from_handoff() -> None:
    data = price_fixture()
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.stop_reference == 1.3720
    assert result.entry_trigger == "price-action confirmation: key_reversal at week_of=2026-07-06"


def test_normalize_price_action_confirmed_falls_back_to_swing_levels_when_handoff_absent() -> None:
    data = price_fixture(include_handoff=False)
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.stop_reference == 1.3720


def test_normalize_price_action_confirmed_without_stop_reference_is_invalid() -> None:
    """Fail-closed: CONFIRMED without a usable stop_reference is not
    actionable -- a READY_FOR_PLAN without invalidation is unacceptable."""
    data = price_fixture(stop_reference=None, include_handoff=False)
    data["swing_levels"]["stop_reference"] = None
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_missing_stop_reference"


# --- Section 6: PR #249 user-review round 2 (P1-A / P1-B) -------------------


def test_normalize_price_action_confirmed_unknown_reason_p1_a_repro() -> None:
    """THE USER'S P1-A REPRO: verdict_reason "BANANA" on a CONFIRMED
    price-action report used to reach READY_FOR_PLAN with
    entry_trigger="price-action confirmation: BANANA" instead of failing
    closed against TA's actual verdict_reason contract."""
    data = price_fixture(verdict="CONFIRMED", verdict_reason="BANANA")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_unknown_reason"
    assert result.entry_trigger is None


def test_normalize_price_action_confirmed_missing_reason_p1_a_repro() -> None:
    """THE USER'S P1-A REPRO (missing variant): a null verdict_reason on a
    CONFIRMED report used to reach READY_FOR_PLAN with entry_trigger=null
    instead of failing closed."""
    data = price_fixture(verdict="CONFIRMED", verdict_reason=None)
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_price_action_confirmed_reasons_matches_technical_analyst_source() -> None:
    """Cross-skill consistency pin (PR #249 user-review round 2, P1-A): the
    hardcoded allowlist in gate_logic.PRICE_ACTION_CONFIRMED_REASONS must
    match technical-analyst's own weekly_price_action.CHECK_REASON_MAP
    values exactly. If TA ever adds a new confirming-signal token, this
    test fails loudly here instead of the gate silently rejecting every
    real report carrying that new token as price_action_unknown_reason."""
    import importlib.util

    ta_module_path = (
        Path(__file__).resolve().parents[3]
        / "technical-analyst"
        / "scripts"
        / "weekly_price_action.py"
    )
    assert ta_module_path.exists(), f"technical-analyst module not found at {ta_module_path}"
    spec = importlib.util.spec_from_file_location(
        "weekly_price_action_for_gate_test", ta_module_path
    )
    ta_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ta_module)
    assert set(ta_module.CHECK_REASON_MAP.values()) == gl.PRICE_ACTION_CONFIRMED_REASONS


@pytest.mark.parametrize(
    "bad_stop_reference",
    [float("inf"), float("-inf"), float("nan"), True, 0, -1.5, "1.372", None],
)
def test_normalize_price_action_confirmed_invalid_stop_reference_p1_b_repro(
    bad_stop_reference,
) -> None:
    """THE USER'S P1-B REPRO (and its variants): a non-finite, non-positive,
    boolean, or wrong-typed stop_reference must never reach READY_FOR_PLAN's
    invalidation_level. `None` is the pre-existing missing-value case
    (kept here for a single parametrized sweep); everything else is a
    value that was explicitly PROVIDED but is unusable."""
    data = price_fixture(stop_reference=bad_stop_reference, include_handoff=False)
    data["swing_levels"]["stop_reference"] = bad_stop_reference
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    if bad_stop_reference is None:
        assert result.reason == "price_action_missing_stop_reference"
    else:
        assert result.reason == "price_action_invalid_stop_reference"


def test_normalize_price_action_confirmed_valid_positive_stop_reference_control() -> None:
    """Control for the P1-B parametrized sweep: a normal, finite, positive
    stop_reference must still succeed."""
    data = price_fixture(stop_reference=1.372)
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.stop_reference == 1.372


def test_normalize_price_action_invalid_stop_reference_in_handoff_does_not_fall_back_to_swing_levels() -> (
    None
):
    """An explicit garbage handoff.stop_reference is a real report bug and
    must not be silently masked by a valid swing_levels fallback (v4
    design decision, pinned)."""
    data = price_fixture(stop_reference=1.372)  # valid swing_levels.stop_reference
    data["handoff"]["price_action"]["stop_reference"] = float("inf")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_invalid_stop_reference"


def test_build_gate_result_ready_invariant_catches_a_bypassed_bad_entry_trigger() -> None:
    """Defensive-invariant regression test: even if some future code path
    bypassed normalize_price_action's validation and handed
    build_gate_result a CONFIRMED price step with no entry_trigger, the
    READY_FOR_PLAN invariant assert must catch it rather than silently
    emitting an incomplete READY_FOR_PLAN."""
    crowding = _crowding("CONF_S")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_CONFIRMED, confidence="HIGH")
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE, state=gl.STATE_CONFIRMED, confidence="HIGH", stop_reference=1.37
    )  # entry_trigger deliberately omitted
    with pytest.raises(AssertionError, match="entry_trigger"):
        gl.build_gate_result(
            symbol=SYMBOL,
            crowding=crowding,
            news=news,
            price=price,
            max_detector_age_days=10,
            max_report_age_days=7,
            as_of=AS_OF,
        )


def test_build_gate_result_ready_invariant_catches_a_bypassed_bad_stop_reference() -> None:
    crowding = _crowding("CONF_S")
    news = gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_CONFIRMED, confidence="HIGH")
    price = gl.NormalizedInput(
        kind=gl.STEP_PRICE,
        state=gl.STATE_CONFIRMED,
        confidence="HIGH",
        entry_trigger="price-action confirmation: key_reversal",
        stop_reference=float("inf"),
    )
    with pytest.raises(AssertionError, match="invalidation_level"):
        gl.build_gate_result(
            symbol=SYMBOL,
            crowding=crowding,
            news=news,
            price=price,
            max_detector_age_days=10,
            max_report_age_days=7,
            as_of=AS_OF,
        )


def test_normalize_price_action_not_confirmed() -> None:
    data = price_fixture(verdict="NOT_CONFIRMED", verdict_reason="no_reversal_evidence")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_NOT_CONFIRMED
    assert result.reason == "no_reversal_evidence"


def test_normalize_price_action_insufficient_data() -> None:
    data = price_fixture(verdict="INSUFFICIENT_DATA", verdict_reason="no_price_source")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "no_price_source"


def test_normalize_price_action_schema_version_read_from_run_context_only() -> None:
    """TA carries schema_version ONLY at run_context.schema_version -- no
    top-level key exists. Reading top-level would silently disable the
    check (plan §3.2 v2 P1-3): a report with a VALID top-level
    schema_version but an UNSUPPORTED run_context.schema_version must
    still be rejected -- proving the top-level value is never consulted."""
    data = price_fixture()
    data["schema_version"] = "1.0"  # would pass if (wrongly) read top-level
    data["run_context"]["schema_version"] = "2.0"  # the actual read location
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_schema_unsupported"


def test_normalize_price_action_direction_mismatch() -> None:
    data = price_fixture(direction="CROWDED_LONG")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_direction_mismatch"


def test_normalize_price_action_null_direction_is_insufficient_not_mismatch() -> None:
    """Same fix as news (P3-1): a provided `direction: null` is TA's own
    fail-closed exit (no_direction_provided), not a mismatch."""
    data = price_fixture(
        direction=None,
        verdict="INSUFFICIENT_DATA",
        verdict_reason="no_direction_provided",
        stop_reference=None,
        include_handoff=False,
    )
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INSUFFICIENT
    assert result.reason == "no_direction_provided"


def test_normalize_price_action_null_direction_without_verdict_reason_is_malformed() -> None:
    data = price_fixture(
        direction=None, verdict_reason=None, stop_reference=None, include_handoff=False
    )
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_normalize_price_action_symbol_mismatch() -> None:
    data = price_fixture(symbol="D6")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_symbol_mismatch"


def test_normalize_price_action_missing_direction_key_is_malformed() -> None:
    data = price_fixture()
    del data["direction"]
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_normalize_price_action_load_error_parse_error() -> None:
    result = gl.normalize_price_action(
        None, "parse_error", symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_parse_error"


def test_normalize_price_action_load_error_non_finite() -> None:
    result = gl.normalize_price_action(
        None, "non_finite", symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_non_finite"


def test_normalize_price_action_unknown_verdict() -> None:
    data = price_fixture(verdict="MAYBE")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_unknown_verdict"


def test_normalize_price_action_unhashable_verdict_never_crashes() -> None:
    """Mirror of the user's PR #249 P1-1 repro for price-action."""
    data = price_fixture(verdict=[])
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_normalize_price_action_unhashable_confidence_never_crashes() -> None:
    data = price_fixture(confidence={})
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_normalize_price_action_unknown_confidence_string_fails_closed() -> None:
    data = price_fixture(verdict="CONFIRMED", confidence="BANANA")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_unknown_confidence"


def test_normalize_price_action_low_confidence_is_accepted_reserved_token() -> None:
    data = price_fixture(verdict="CONFIRMED", confidence="LOW")
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_CONFIRMED
    assert result.confidence == "LOW"


def test_normalize_price_action_non_string_direction_is_malformed_not_mismatch() -> None:
    data = price_fixture(direction=123)
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert result.state == gl.STATE_INVALID
    assert result.reason == "price_action_malformed"


def test_normalize_price_action_near_stale_warning() -> None:
    data = price_fixture(as_of="2026-07-09")  # AS_OF 2026-07-15, max 7 -> age 6
    result = gl.normalize_price_action(
        data, None, symbol=SYMBOL, as_of=AS_OF, max_age_days=7, detector=CONFIRMED_CROWDING
    )
    assert "price_action_near_stale" in result.warnings


# --- Section 5: gate_confidence / warnings at READY_FOR_PLAN ----------------


def _confirmed_news(confidence: str) -> gl.NormalizedInput:
    return gl.NormalizedInput(kind=gl.STEP_NEWS, state=gl.STATE_CONFIRMED, confidence=confidence)


def _confirmed_price(
    confidence: str, stop_reference: float = 1.37, entry_trigger: str = "x"
) -> gl.NormalizedInput:
    return gl.NormalizedInput(
        kind=gl.STEP_PRICE,
        state=gl.STATE_CONFIRMED,
        confidence=confidence,
        stop_reference=stop_reference,
        entry_trigger=entry_trigger,
    )


@pytest.mark.parametrize(
    "news_conf,price_conf,expected",
    [
        ("HIGH", "HIGH", "HIGH"),
        ("HIGH", "MEDIUM", "MEDIUM"),
        ("MEDIUM", "HIGH", "MEDIUM"),
        ("MEDIUM", "MEDIUM", "MEDIUM"),
        # LOW is a reserved-but-accepted token (PR #249 P1-2): it ranks
        # weakest of all three, below MEDIUM.
        ("HIGH", "LOW", "LOW"),
        ("LOW", "HIGH", "LOW"),
        ("MEDIUM", "LOW", "LOW"),
        ("LOW", "LOW", "LOW"),
    ],
)
def test_gate_confidence_is_weakest_link(news_conf, price_conf, expected) -> None:
    crowding = _crowding("CONF_S")
    news = _confirmed_news(news_conf)
    price = _confirmed_price(price_conf)
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    assert result["setup_status"] == "READY_FOR_PLAN"
    assert result["gate_confidence"] == expected


def test_price_confidence_medium_warning_at_ready() -> None:
    crowding = _crowding("CONF_S")
    news = _confirmed_news("HIGH")
    price = _confirmed_price("MEDIUM")
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    assert "price_action_confidence_medium" in result["warnings"]
    assert "news_confidence_medium" not in result["warnings"]


def test_news_confidence_medium_warning_at_ready() -> None:
    crowding = _crowding("CONF_S")
    news = _confirmed_news("MEDIUM")
    price = _confirmed_price("HIGH")
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    assert "news_confidence_medium" in result["warnings"]


def test_ready_for_plan_populates_entry_trigger_and_invalidation_level() -> None:
    crowding = _crowding("CONF_S")
    news = _confirmed_news("HIGH")
    price = _confirmed_price(
        "HIGH",
        stop_reference=1.3720,
        entry_trigger="price-action confirmation: key_reversal at week_of=2026-07-06",
    )
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    assert result["invalidation_level"] == 1.3720
    assert (
        result["entry_trigger"] == "price-action confirmation: key_reversal at week_of=2026-07-06"
    )
    assert result["direction"] == "LONG"


def test_inputs_block_shape_for_all_three_steps() -> None:
    crowding = _crowding("CONF_S")
    news = gl.pending_input(gl.STEP_NEWS)
    price = gl.pending_input(gl.STEP_PRICE)
    result = gl.build_gate_result(
        symbol=SYMBOL,
        crowding=crowding,
        news=news,
        price=price,
        max_detector_age_days=10,
        max_report_age_days=7,
        as_of=AS_OF,
    )
    assert set(result["inputs"]["crowding"]) == {
        "state",
        "classification",
        "data_date",
        "age_days",
        "report_path",
    }
    assert set(result["inputs"]["news_failure"]) == {
        "state",
        "verdict",
        "confidence",
        "verdict_reason",
        "as_of",
        "age_days",
        "report_path",
    }
    assert set(result["inputs"]["price_action"]) == {
        "state",
        "verdict",
        "confidence",
        "verdict_reason",
        "stop_reference",
        "as_of",
        "age_days",
        "report_path",
    }
    assert result["setup_status"] == "CROWDED"
    assert result["run_context"]["symbol"] == SYMBOL
    assert result["run_context"]["schema_version"] == "1.0"
