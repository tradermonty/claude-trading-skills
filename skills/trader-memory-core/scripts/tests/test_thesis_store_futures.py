"""Tests for trader-memory-core futures (contracts/multiplier/direction) support.

Covers plan_A.md §3 test items 2-14 (item 1 — existing ~160 equity tests all
green — is the baseline regression gate in test_thesis_store.py /
test_thesis_review.py / test_trader_memory_cli.py, not duplicated here):
LONG/SHORT round-trip exact P&L, multiplier differentiation, silent-wrong
prevention (D4), _validate_thesis futures invariants, schema additive
backward-compat, attach_futures_position() handoff validation (3-class
loader, NO_TRADE / invalid direction / invalid contracts / invalid
multiplier), KeyError safety, futures PARTIALLY_CLOSED validate,
report-type misfeed rejection (both directions), direct
open_position(contracts=...) round-trip, postmortem unit-aware rendering,
and the re-attach status guard.

This file is self-contained (like the other test_*.py files in this
directory) — it does not import helpers from test_thesis_store.py.
"""

import hashlib
import json
from pathlib import Path

import pytest
import thesis_review
import thesis_store

# -- Helpers -------------------------------------------------------------------


def _make_thesis_data(**overrides):
    data = {
        "ticker": "ES1",
        "thesis_type": "pivot_breakout",
        "thesis_statement": "ES futures thesis for testing",
        "origin": {"skill": "test-skill", "output_file": "test_output.json"},
    }
    data.update(overrides)
    return data


def _register_and_get(state_dir, **overrides):
    data = _make_thesis_data(**overrides)
    tid = thesis_store.register(state_dir, data)
    thesis = thesis_store.get(state_dir, tid)
    return tid, thesis


def _make_equity_position_report(tmp_path, **overrides):
    """Mirrors the real (equity) position-sizer report shape
    (mode="shares" — see test_thesis_store.py's own _make_position_report
    for the canonical version; a local copy here since this suite's files
    are self-contained). Used only by the cross-attach guard tests."""
    report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {
            "entry_price": 150.00,
            "stop_price": 142.00,
            "account_size": 100000,
            "risk_pct": 1.0,
        },
        "calculations": {
            "fixed_fractional": {"method": "fixed_fractional", "shares": 125},
        },
        "final_recommended_shares": 125,
        "final_position_value": 18750.00,
        "final_risk_dollars": 1000.00,
        "final_risk_pct": 0.01,
    }
    report.update(overrides)
    report_path = tmp_path / "equity_position_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return str(report_path)


def _make_futures_report(tmp_path, **overrides):
    """Mirrors the real futures-position-sizer SIZED report shape
    (futures-position-sizer/scripts/futures_sizing.py::_base_result /
    size_futures_position — schema_version/symbol/direction/sizing_status/
    entry/stop/contract_spec/risk_per_contract_usd/contracts/
    total_risk_usd/risk_pct_of_account, no "mode" field)."""
    report = {
        "schema_version": "1.0",
        "symbol": "ES",
        "direction": "LONG",
        "sizing_status": "SIZED",
        "no_trade_reason": None,
        "entry": 5000.0,
        "stop": 4980.0,
        "stop_distance_points": 20.0,
        "stop_distance_ticks": "80",
        "contract_spec": {
            "multiplier": 50,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "currency": "USD",
            "source": "cme",
            "verified": "2026-01-01",
        },
        "risk_per_contract_usd": 1000.0,
        "risk_budget_usd": 2000.0,
        "contracts": 2,
        "total_risk_usd": 2000.0,
        "risk_pct_of_account": 2.0,
        "max_contracts_cap_applied": False,
        "fx_rate_used": 1.0,
        "margin_note": "Margin requirements vary by broker.",
        "warnings": [],
        "run_context": {
            "symbol": "ES",
            "as_of": "2026-05-01",
            "schema_version": "1.0",
            "skill": "futures-position-sizer",
        },
    }
    report.update(overrides)
    report_path = tmp_path / "futures_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return str(report_path)


def _active_futures(
    tmp_path,
    contracts,
    multiplier=50,
    direction="LONG",
    entry_price=5000.0,
    symbol="ES",
    ticker=None,
    **overrides,
):
    """Register → ENTRY_READY → attach-futures-position → ACTIVE @2026-05-01
    (backdated chain, mirrors test_thesis_store.py's _active_with_shares)."""
    ticker = ticker or symbol
    tid, _ = _register_and_get(tmp_path, ticker=ticker, _source_date="2026-05-01", **overrides)
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    report_path = _make_futures_report(
        tmp_path,
        symbol=symbol,
        direction=direction,
        contracts=contracts,
        contract_spec={
            "multiplier": multiplier,
            "tick_size": 0.25,
            "tick_value": multiplier * 0.25,
            "currency": "USD",
            "source": "cme",
            "verified": "2026-01-01",
        },
        entry=entry_price,
    )
    thesis_store.attach_futures_position(tmp_path, tid, report_path)
    thesis_store.open_position(
        tmp_path,
        tid,
        entry_price,
        "2026-05-01T00:00:00+00:00",
        event_date="2026-05-01T00:00:00+00:00",
    )
    return tid


def _active_equity(tmp_path, shares, entry_price=100.0, ticker="EQ1", **overrides):
    """Minimal equity ACTIVE-thesis helper — local copy, not imported from
    test_thesis_store.py (this suite's files are self-contained), mirrors
    test_thesis_store.py's _active_with_shares."""
    tid, _ = _register_and_get(
        tmp_path,
        ticker=ticker,
        thesis_type="growth_momentum",
        _source_date="2026-05-01",
        **overrides,
    )
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid,
        entry_price,
        "2026-05-01T00:00:00+00:00",
        shares=shares,
        event_date="2026-05-01T00:00:00+00:00",
    )
    return tid


def _state_file_hash(state_dir, thesis_id: str) -> str:
    """SHA-256 of the on-disk thesis YAML file — for byte-exact
    before/after comparison around a rejected mutation (P1 addendum, user
    re-review: every rejection case must leave state unchanged, not just
    "logically" unchanged)."""
    path = Path(state_dir) / f"{thesis_id}.yaml"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_file_hash(state_dir) -> str:
    """SHA-256 of the on-disk _index.json file (P1-B/P1-C, user
    re-review: a rejection must leave BOTH the thesis YAML and the index
    untouched — _save_index() is only ever reached after _save_thesis()
    succeeds, but this pins that structural guarantee explicitly)."""
    path = Path(state_dir) / thesis_store.INDEX_FILE
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- Tests: round-trip P&L (plan §3 test#2/#3/#4) ------------------------------


def test_futures_round_trip_long_exact_pnl(tmp_path: Path):
    """ES mult=50, attach contracts=2 entry=5000 stop=4980 LONG → ACTIVE →
    trim 1@5040 (+2000) → close remainder 1@5060 (+3000) → cumulative
    +5000, pnl_pct 1.0 (notional basis: 5000*50*2=500000)."""
    tid = _active_futures(
        tmp_path,
        contracts=2,
        multiplier=50,
        direction="LONG",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESLONG",
    )
    t = thesis_store.trim(tmp_path, tid, 1, 5040.0, "2026-05-10")
    assert t["status"] == "PARTIALLY_CLOSED"
    trim_entry = t["status_history"][-1]
    assert trim_entry["realized_pnl"] == 2000.0
    assert trim_entry["quantity_sold"] == 1
    assert trim_entry["proceeds"] == round(5040.0 * 50 * 1, 2)

    t = thesis_store.close(tmp_path, tid, "target_hit", 5060.0, "2026-05-20T00:00:00+00:00")
    assert t["status"] == "CLOSED"
    assert t["position"]["quantity_remaining"] == 0
    assert t["outcome"]["pnl_dollars"] == 5000.0
    assert t["outcome"]["pnl_pct"] == 1.0
    ledger = [h["realized_pnl"] for h in t["status_history"] if "realized_pnl" in h]
    assert ledger == [2000.0, 3000.0]


def test_futures_round_trip_short_profit_and_loss_signs(tmp_path: Path):
    """SHORT crowded-long fade. entry=5000, exit=4950 → +2500 (profit); a
    mirrored SHORT closed at 5050 → -2500 (loss)."""
    tid_profit = _active_futures(
        tmp_path,
        contracts=1,
        multiplier=50,
        direction="SHORT",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESSHORTP",
    )
    t = thesis_store.close(tmp_path, tid_profit, "target_hit", 4950.0, "2026-05-10T00:00:00+00:00")
    assert t["outcome"]["pnl_dollars"] == 2500.0

    tid_loss = _active_futures(
        tmp_path,
        contracts=1,
        multiplier=50,
        direction="SHORT",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESSHORTL",
    )
    t = thesis_store.close(tmp_path, tid_loss, "stop_hit", 5050.0, "2026-05-10T00:00:00+00:00")
    assert t["outcome"]["pnl_dollars"] == -2500.0


def test_futures_multiplier_differentiates_dollar_pnl(tmp_path: Path):
    """Same 20-point move, ES(mult=50) vs NQ(mult=20) must produce
    different dollar P&L: +1000 vs +400."""
    tid_es = _active_futures(
        tmp_path,
        contracts=1,
        multiplier=50,
        direction="LONG",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESMULT",
    )
    t_es = thesis_store.close(tmp_path, tid_es, "target_hit", 5020.0, "2026-05-10T00:00:00+00:00")

    tid_nq = _active_futures(
        tmp_path,
        contracts=1,
        multiplier=20,
        direction="LONG",
        entry_price=5000.0,
        symbol="NQ",
        ticker="NQMULT",
    )
    t_nq = thesis_store.close(tmp_path, tid_nq, "target_hit", 5020.0, "2026-05-10T00:00:00+00:00")

    assert t_es["outcome"]["pnl_dollars"] == 1000.0
    assert t_nq["outcome"]["pnl_dollars"] == 400.0
    assert t_es["outcome"]["pnl_dollars"] != t_nq["outcome"]["pnl_dollars"]


# -- Tests: silent-wrong prevention / KeyError safety (plan §3 test#5/#9) ------


def test_futures_close_never_returns_per_unit_value(tmp_path: Path):
    """A futures thesis closed via close() must never reach the legacy
    no-position per-unit branch (multiplier-ignorant) and never raise
    KeyError on position['shares'] (which futures theses don't have)."""
    tid = _active_futures(
        tmp_path,
        contracts=3,
        multiplier=50,
        direction="LONG",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESSILENT",
    )
    assert "shares" not in thesis_store.get(tmp_path, tid)["position"]
    t = thesis_store.close(tmp_path, tid, "manual", 5010.0, "2026-05-10T00:00:00+00:00")
    per_unit_wrong_value = round(5010.0 - 5000.0, 2) * 3  # legacy no-position formula
    correct_value = round((5010.0 - 5000.0) * 50 * 3 * 1, 2)
    assert correct_value == 1500.0
    assert t["outcome"]["pnl_dollars"] == correct_value
    assert t["outcome"]["pnl_dollars"] != per_unit_wrong_value


def test_futures_terminate_never_returns_per_unit_value(tmp_path: Path):
    """Same guard as above, via terminate() → INVALIDATED (D4)."""
    tid = _active_futures(
        tmp_path,
        contracts=3,
        multiplier=50,
        direction="LONG",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESSILENT2",
    )
    t = thesis_store.terminate(
        tmp_path,
        tid,
        "INVALIDATED",
        "thesis broke",
        actual_price=5010.0,
        actual_date="2026-05-10T00:00:00+00:00",
    )
    assert t["status"] == "INVALIDATED"
    assert t["outcome"]["pnl_dollars"] == 1500.0


def test_futures_trim_never_touches_shares_key(tmp_path: Path):
    """trim() on a futures thesis succeeds without ever touching
    position['shares'] (which doesn't exist on a futures thesis — the
    equity trim() code at position['shares'] would KeyError)."""
    tid = _active_futures(
        tmp_path,
        contracts=4,
        multiplier=50,
        direction="LONG",
        entry_price=5000.0,
        symbol="ES",
        ticker="ESTRIMKEY",
    )
    position = thesis_store.get(tmp_path, tid)["position"]
    assert "shares" not in position
    assert "shares_remaining" not in position
    t = thesis_store.trim(tmp_path, tid, 2, 5010.0, "2026-05-10")
    assert t["status"] == "PARTIALLY_CLOSED"
    assert t["position"]["quantity_remaining"] == 2


def test_update_rejects_injecting_futures_shaped_position(tmp_path: Path):
    """P1 addendum (user re-review): update() must reject an attempt to
    inject a fresh futures-shaped position onto a non-futures thesis — not
    just modify an already-futures one. Before this fix, the resulting
    quantity-less position would only be caught later by
    open_position()'s own defensive guard (still exercised directly in
    test_open_futures_position_direct_call_rejects_missing_quantity
    below); now update() itself refuses the injection immediately."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNOQTY", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError, match="update\\(\\) cannot modify position"):
        thesis_store.update(tmp_path, tid, {"position": {"asset_type": "futures"}})
    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["position"] is None


def test_open_futures_position_direct_call_rejects_missing_quantity(tmp_path: Path):
    """_open_futures_position()'s own "requires position.quantity" guard
    (defense-in-depth: unreachable through the public API now that
    update() blocks injecting a futures-shaped position and
    attach_futures_position()/direct-open always set quantity atomically)
    still fires when called directly with a pre-corrupted thesis dict —
    exercised directly, same pattern as other _validate_thesis()-direct
    tests in this suite."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNOQTYDIRECT", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis = thesis_store.get(tmp_path, tid)
    thesis["position"] = {"asset_type": "futures"}  # in-memory only, never saved
    with pytest.raises(ValueError, match="requires position.quantity"):
        thesis_store._open_futures_position(
            tmp_path,
            thesis,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            reason="position opened",
            contracts=None,
            multiplier=None,
            direction=None,
            contract_symbol=None,
            contract_currency=None,
            event_date=None,
        )


# -- Tests: P1/P2 addendum-2 — update() bypass + save-time validator ---------
# (user re-review round 2, money-critical: update() had no guard on
# "position" at all, and the JSON Schema alone does not reject nan/inf.)


def test_update_rejects_position_rewrite_on_active_futures_sign_flip_regression(
    tmp_path: Path,
):
    """New-P1 (MOST CRITICAL): update() must reject rewriting position on
    an ALREADY-ACTIVE futures thesis — the P1-1 sign-flip bug reopened
    through a different API (update() instead of re-attach). LONG 2
    contracts @5000 opened, then update(id, {"position": {**pos,
    "direction": "SHORT"}}) must be rejected; state and the subsequent
    close() P&L must be unaffected (still the correct LONG-side value)."""
    tid = _active_futures(
        tmp_path, contracts=2, multiplier=50, direction="LONG", ticker="ESUPDATESIGN"
    )
    thesis = thesis_store.get(tmp_path, tid)
    flipped = dict(thesis["position"])
    flipped["direction"] = "SHORT"
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match=r"update\(\) cannot modify position"):
        thesis_store.update(tmp_path, tid, {"position": flipped})

    assert _state_file_hash(tmp_path, tid) == before
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["direction"] == "LONG"

    t = thesis_store.close(tmp_path, tid, "manual", 4900.0, "2026-05-10T00:00:00+00:00")
    # (4900-5000)*50*2*(+1) = -10000, NOT +10000
    assert t["outcome"]["pnl_dollars"] == -10000.0


def test_update_rejects_nan_multiplier_on_active_futures(tmp_path: Path):
    """New-P2: update() attempting to overwrite position with a NaN
    multiplier on an already-futures thesis is rejected by the update()
    blanket guard itself — since the thesis is already futures, ANY
    position write via update() is blocked regardless of content."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESUPDATENAN")
    thesis = thesis_store.get(tmp_path, tid)
    corrupted = dict(thesis["position"])
    corrupted["multiplier"] = float("nan")
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match=r"update\(\) cannot modify position"):
        thesis_store.update(tmp_path, tid, {"position": corrupted})

    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["position"]["multiplier"] == 50


def test_update_rejects_injecting_futures_position_with_nan_multiplier(tmp_path: Path):
    """New-P1/P2: injecting a FRESH futures-shaped position (on a
    non-futures thesis) with a NaN multiplier via update() is rejected by
    the same blanket update() guard — the incoming value is futures-shaped
    so it is blocked before the field-level validator ever runs."""
    tid, _ = _register_and_get(tmp_path, ticker="ESFRESHNAN", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError, match=r"update\(\) cannot modify position"):
        thesis_store.update(
            tmp_path,
            tid,
            {
                "position": {
                    "asset_type": "futures",
                    "quantity": 2,
                    "quantity_remaining": 2,
                    "quantity_unit": "contracts",
                    "multiplier": float("nan"),
                    "direction": "LONG",
                    "contract_spec": {"currency": "USD"},
                }
            },
        )
    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["position"] is None


def test_update_equity_position_unaffected(tmp_path: Path):
    """Regression pin: update() touching position on an EQUITY thesis is
    entirely unaffected by the new futures guard (out of scope, existing
    behavior preserved)."""
    tid = _active_equity(tmp_path, 10, ticker="EQUPDATE")
    t = thesis_store.update(tmp_path, tid, {"position": {"shares": 10, "note": "test"}})
    assert t["position"]["shares"] == 10


def test_validate_futures_position_fields_rejects_nonfinite_multiplier(tmp_path: Path):
    """_save_thesis() common validator boundary: multiplier=nan (P2 —
    JSON Schema's exclusiveMinimum does NOT reject nan; verified
    empirically that nan compares False against both <= and > checks)."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALMULTNAN")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["multiplier"] = float("nan")
    with pytest.raises(ValueError, match="position.multiplier is invalid"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_infinite_multiplier(tmp_path: Path):
    """_save_thesis() common validator boundary: multiplier=inf (schema's
    exclusiveMinimum also does not reject inf, since there's no maximum)."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALMULTINF")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["multiplier"] = float("inf")
    with pytest.raises(ValueError, match="position.multiplier is invalid"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_non_integer_quantity(tmp_path: Path):
    """_save_thesis() common validator boundary: quantity=1.5 (P1-4 whole-
    contracts invariant). Caught by the JSON Schema's "type": "integer"
    constraint (added in the P1-4 fix) BEFORE _validate_futures_position_
    fields() ever runs — this pins that the schema layer still rejects a
    fractional quantity even via a raw dict mutation that bypasses every
    Python-level validator (attach/open/trim all use _valid_positive_int,
    but this simulates a caller that skips them entirely)."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALQTYFRAC")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity"] = 1.5
    with pytest.raises(ValueError, match="not of type 'integer'"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_non_integer_quantity_remaining(
    tmp_path: Path,
):
    """_save_thesis() common validator boundary: quantity_remaining=1.5 —
    same schema-layer rejection as quantity above."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALREMFRAC")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity_remaining"] = 1.5
    with pytest.raises(ValueError, match="not of type 'integer'"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_quantity_remaining_exceeds_quantity(
    tmp_path: Path,
):
    """_save_thesis() common validator boundary: quantity_remaining (3) >
    quantity (2) — the universal, status-agnostic sanity bound (distinct
    from the status-specific ACTIVE/CLOSED/PARTIALLY_CLOSED exact-equality
    invariants already enforced elsewhere in _validate_thesis())."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALEXCEED")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity_remaining"] = 3
    with pytest.raises(ValueError, match="must be <= quantity"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_null_direction(tmp_path: Path):
    """_save_thesis() common validator boundary: direction=None. The
    schema itself allows null (["LONG","SHORT",null]) — direction is
    optional for an EQUITY thesis, which never sets it — so this is a
    case the schema literally cannot express ("non-null only when this
    is a futures thesis" is cross-field/conditional). This is exactly
    what _validate_futures_position_fields() exists to catch."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALDIRNULL")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["direction"] = None
    with pytest.raises(ValueError, match="position.direction is invalid"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_non_usd_currency(tmp_path: Path):
    """_save_thesis() common validator boundary: contract_spec.currency
    != "USD"."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALCURREUR")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["contract_spec"]["currency"] = "EUR"
    with pytest.raises(ValueError, match="position.contract_spec.currency is invalid"):
        thesis_store._validate_thesis(t)


def test_validate_futures_position_fields_rejects_missing_currency(tmp_path: Path):
    """_save_thesis() common validator boundary: contract_spec.currency
    missing entirely."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESVALNOCURR")
    t = thesis_store.get(tmp_path, tid)
    del t["position"]["contract_spec"]["currency"]
    with pytest.raises(ValueError, match="position.contract_spec.currency is invalid"):
        thesis_store._validate_thesis(t)


# -- Tests: P1 addendum-3 — cross-attach contamination (user re-review, -----
#    money-critical: same root cause as the update() guard, but in
#    attach_position()/attach_futures_position() themselves) ----------------


def test_attach_position_rejects_cross_attach_when_futures_already_attached(tmp_path: Path):
    """The exact repro from user re-review: attach_futures_position(SHORT,
    3 contracts, mult=1000, CL, USD) then attach_position() (equity) must
    be rejected, not silently overwrite the futures position. Before this
    fix, the equity attach succeeded — direction/multiplier/quantity/
    contract_spec vanished, _is_futures(thesis) flipped to False, and
    open_position()/close() mis-dispatched into the legacy EQUITY
    per-unit path: a SHORT 3x1000 ($80->$70) profit of +$30,000 was
    recorded as an equity per-unit loss of -$1,000 (wrong sign AND wrong
    magnitude). This test proves the guard AND that the correct futures
    P&L is still reachable once the contaminating attach is rejected."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCROSSATTACH1")
    futures_report = _make_futures_report(
        tmp_path,
        symbol="CL",
        direction="SHORT",
        contracts=3,
        entry=80.0,
        stop=85.0,
        contract_spec={
            "multiplier": 1000,
            "tick_size": 0.01,
            "tick_value": 10.0,
            "currency": "USD",
            "source": "nymex",
            "verified": "2026-01-01",
        },
    )
    thesis_store.attach_futures_position(tmp_path, tid, futures_report)
    before = _state_file_hash(tmp_path, tid)

    equity_report = _make_equity_position_report(tmp_path)
    with pytest.raises(ValueError, match="cannot attach an equity position"):
        thesis_store.attach_position(tmp_path, tid, equity_report)

    assert _state_file_hash(tmp_path, tid) == before
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["direction"] == "SHORT"
    assert t["position"]["multiplier"] == 1000
    assert t["position"]["quantity"] == 3
    assert "shares" not in t["position"]

    # Correct futures P&L is still computable end-to-end after the
    # rejected cross-attach — nothing was corrupted.
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 80.0, "2026-05-01T00:00:00+00:00")
    t = thesis_store.close(tmp_path, tid, "manual", 70.0, "2026-05-10T00:00:00+00:00")
    # (70-80)*1000*3*(-1) = +30000, NOT the equity per-unit -1000
    assert t["outcome"]["pnl_dollars"] == 30000.0


def test_attach_futures_position_rejects_cross_attach_when_equity_already_attached(
    tmp_path: Path,
):
    """Reverse direction: attach_position() (equity) then
    attach_futures_position() must be rejected — before this fix, the
    equity sizing data (shares/position_value/risk_dollars) would be
    silently discarded (data loss) with no error."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCROSSATTACH2")
    equity_report = _make_equity_position_report(tmp_path)
    thesis_store.attach_position(tmp_path, tid, equity_report)
    before = _state_file_hash(tmp_path, tid)

    futures_report = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match="cannot attach a futures position"):
        thesis_store.attach_futures_position(tmp_path, tid, futures_report)

    assert _state_file_hash(tmp_path, tid) == before
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares"] == 125
    assert "asset_type" not in t["position"]


# -- Tests: P1-B — huge-integer OverflowError (user re-review) ---------------


def test_valid_positive_int_accepts_max_contracts_boundary():
    """P1-B: _MAX_CONTRACTS itself (int form) is a valid contract count —
    the boundary is inclusive."""
    assert (
        thesis_store._valid_positive_int(thesis_store._MAX_CONTRACTS) == thesis_store._MAX_CONTRACTS
    )


def test_valid_positive_int_rejects_one_above_max_contracts():
    """P1-B: _MAX_CONTRACTS + 1 (still an ordinary, non-overflowing int)
    is rejected — the sanity cap, not just the overflow guard."""
    assert thesis_store._valid_positive_int(thesis_store._MAX_CONTRACTS + 1) is None


def test_valid_nonneg_int_accepts_max_contracts_boundary():
    assert (
        thesis_store._valid_nonneg_int(thesis_store._MAX_CONTRACTS) == thesis_store._MAX_CONTRACTS
    )


def test_valid_nonneg_int_rejects_one_above_max_contracts():
    assert thesis_store._valid_nonneg_int(thesis_store._MAX_CONTRACTS + 1) is None


def test_valid_positive_int_rejects_huge_int_without_overflow_error():
    """P1-B (user re-review, money-critical): a 400-digit Python int must
    return None (clean rejection) — the original bug raised an UNCAUGHT
    OverflowError from math.isfinite()/float() instead."""
    assert thesis_store._valid_positive_int(10**400) is None  # must not raise


def test_valid_nonneg_int_rejects_huge_int_without_overflow_error():
    assert thesis_store._valid_nonneg_int(10**400) is None  # must not raise


def test_valid_finite_positive_rejects_huge_int_without_overflow_error():
    assert thesis_store._valid_finite_positive(10**400) is None  # must not raise


def test_open_position_direct_open_rejects_huge_contracts(tmp_path: Path):
    """P1-B: contracts=10**400 via the direct-open Python API must be
    rejected with a clean ValueError, and leave the thesis YAML AND the
    index untouched."""
    tid, _ = _register_and_get(tmp_path, ticker="ESHUGEQTY", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    with pytest.raises(ValueError, match="requires a positive whole number of contracts"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=10**400,
            multiplier=50,
            direction="LONG",
            contract_currency="USD",
        )
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_cli_open_position_rejects_huge_contracts_string(tmp_path: Path):
    """P1-B: the CLI --contracts flag rejects a 401-digit string at
    argparse level (exit 2 — a usage error, no traceback), before it can
    ever reach the business logic layer."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIHUGE", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    huge_digits = "1" + "0" * 400
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--contracts",
                huge_digits,
                "--multiplier",
                "50",
                "--direction",
                "LONG",
                "--contract-currency",
                "USD",
            ]
        )
    # argparse usage errors exit 2 -- an uncaught OverflowError/other
    # exception would instead propagate as a non-SystemExit traceback.
    assert exc_info.value.code == 2


def test_attach_futures_rejects_huge_contracts_in_report(tmp_path: Path):
    """P1-B: a SIZED report with contracts=10**400 (schema-valid JSON,
    no decimal point -> parses as an arbitrary-precision Python int) must
    be rejected cleanly."""
    tid, _ = _register_and_get(tmp_path, ticker="ESHUGEREPORTQTY")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path, contracts=10**400)
    with pytest.raises(ValueError, match="invalid contracts"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_attach_futures_rejects_huge_multiplier_in_report(tmp_path: Path):
    """P1-B: a SIZED report with contract_spec.multiplier=10**400 must be
    rejected cleanly (this field has no fixed sanity cap of its own, so
    the fix here is the OverflowError catch in _valid_finite_positive())."""
    tid, _ = _register_and_get(tmp_path, ticker="ESHUGEREPORTMULT")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(
        tmp_path,
        contract_spec={
            "multiplier": 10**400,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "currency": "USD",
            "source": "cme",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="invalid contract_spec.multiplier"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_validate_futures_position_fields_rejects_huge_quantity_remaining(tmp_path: Path):
    """P1-B: quantity_remaining=10**400 (schema itself does not reject
    this -- verified empirically that Draft7Validator's "integer"/
    exclusiveMinimum check does not raise or flag a huge int) must still
    be rejected by _validate_futures_position_fields()'s own bound,
    cleanly, without an OverflowError."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESHUGEREM")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity_remaining"] = 10**400
    with pytest.raises(ValueError, match="position.quantity_remaining is invalid"):
        thesis_store._validate_thesis(t)


# -- Tests: P1-C — expected-entry/expected-stop fail-open (user re-review) ---


@pytest.mark.parametrize(
    "bad_expected,suffix",
    [
        (float("nan"), "NAN"),
        (float("inf"), "INF"),
        (float("-inf"), "NEGINF"),
        (0.0, "ZERO"),
        (-100.0, "NEG"),
        (True, "BOOL"),
    ],
)
def test_attach_futures_rejects_invalid_expected_entry(tmp_path, bad_expected, suffix):
    """P1-C (user re-review, money-critical): expected_entry itself must
    be finite and positive, checked BEFORE ever comparing against the
    report. The original bug: expected_entry=nan silently matched ANY
    report value, since every comparison against nan is False."""
    tid, _ = _register_and_get(tmp_path, ticker=f"ESBADEXPE{suffix}")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match="expected_entry must be a finite positive number"):
        thesis_store.attach_futures_position(
            tmp_path, tid, report_path, expected_entry=bad_expected
        )
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


@pytest.mark.parametrize(
    "bad_expected,suffix",
    [
        (float("nan"), "NAN"),
        (float("inf"), "INF"),
        (float("-inf"), "NEGINF"),
        (0.0, "ZERO"),
        (-100.0, "NEG"),
        (True, "BOOL"),
    ],
)
def test_attach_futures_rejects_invalid_expected_stop(tmp_path, bad_expected, suffix):
    """P1-C: same guard for expected_stop."""
    tid, _ = _register_and_get(tmp_path, ticker=f"ESBADEXPS{suffix}")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match="expected_stop must be a finite positive number"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_stop=bad_expected)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


@pytest.mark.parametrize(
    "bad_report_value,suffix",
    [
        (None, "NONE"),
        ("not_a_number", "STR"),
        ({"nested": 1}, "DICT"),
        ([1, 2], "LIST"),
    ],
)
def test_attach_futures_rejects_expected_entry_with_invalid_report_entry(
    tmp_path, bad_report_value, suffix
):
    """P1-C (user re-review, money-critical): once expected_entry is
    given, the report's own entry field becomes MANDATORY. The original
    bug: `if expected is not None and report_value is not None:` — a
    missing/null report entry short-circuited the `and` to False, so NO
    check ran at all (an unverifiable expectation silently passed)."""
    tid, _ = _register_and_get(tmp_path, ticker=f"ESEXPBADREP{suffix}")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path, entry=bad_report_value)
    with pytest.raises(ValueError, match="report entry is invalid or missing"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_entry=5000.0)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_attach_futures_rejects_expected_stop_with_missing_report_stop(tmp_path: Path):
    """P1-C: same guard for expected_stop / report stop."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEXPSTOPMISSING")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path, stop=None)
    with pytest.raises(ValueError, match="report stop is invalid or missing"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_stop=4980.0)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_attach_futures_expected_entry_within_tolerance_succeeds(tmp_path: Path):
    """P1-C: at (or fractionally under, accounting for float64
    representation noise) the 0.01 tolerance boundary, this is NOT a
    mismatch — verified via computation: abs(10.0-10.01) ==
    0.009999999999999787 (just under 0.01, the closest float64
    representation of an exact 0.01 gap)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEXPTOLOK")
    report_path = _make_futures_report(tmp_path, entry=10.0)
    t = thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_entry=10.01)
    assert t["position"]["quantity"] == 2  # default from _make_futures_report


def test_attach_futures_expected_entry_exceeds_tolerance_raises(tmp_path: Path):
    """P1-C: clearly beyond the 0.01 tolerance IS a mismatch — verified
    via computation: abs(5000.0-5000.015) == 0.015000000000327418."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEXPTOLFAIL")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path, entry=5000.0)
    with pytest.raises(ValueError, match="Entry price mismatch"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_entry=5000.015)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_attach_futures_expected_stop_exceeds_tolerance_raises(tmp_path: Path):
    """P1-C: same mismatch guard for expected_stop."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEXPSTOPTOLFAIL")
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    report_path = _make_futures_report(tmp_path, stop=4980.0)
    with pytest.raises(ValueError, match="Stop price mismatch"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_stop=4980.5)
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index


def test_attach_futures_normal_expected_price_match_no_regression(tmp_path: Path):
    """P1-C regression guard: ordinary matching expected_entry/
    expected_stop (the common case) still succeeds after the fix."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEXPNORMAL")
    report_path = _make_futures_report(tmp_path, entry=5000.0, stop=4980.0)
    t = thesis_store.attach_futures_position(
        tmp_path, tid, report_path, expected_entry=5000.0, expected_stop=4980.0
    )
    assert t["position"]["quantity"] == 2


def test_cli_attach_futures_position_rejects_nan_expected_entry(tmp_path: Path):
    """P1-C: the CLI --expected-entry flag rejects "nan" at argparse
    level (exit 2, no traceback) via the dedicated
    _strict_positive_finite_float parser."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLINANEXP")
    sd = str(tmp_path)
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "attach-futures-position",
                tid,
                "--report",
                report_path,
                "--expected-entry",
                "nan",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_attach_futures_position_rejects_infinite_expected_stop(tmp_path: Path):
    """P1-C: the CLI --expected-stop flag rejects "inf" at argparse level."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIINFEXP")
    sd = str(tmp_path)
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "attach-futures-position",
                tid,
                "--report",
                report_path,
                "--expected-stop",
                "inf",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_attach_futures_position_rejects_zero_expected_entry(tmp_path: Path):
    """P1-C: the CLI parser also rejects 0/negative for
    --expected-entry/--expected-stop (unlike --actual-price/--price,
    which deliberately allow 0 for the shared equity path)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIZEROEXP")
    sd = str(tmp_path)
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "attach-futures-position",
                tid,
                "--report",
                report_path,
                "--expected-entry",
                "0",
            ]
        )
    assert exc_info.value.code == 2


# -- Tests: _validate_thesis futures invariants (plan §3 test#6) --------------


def test_validate_thesis_futures_active_mismatch_raises(tmp_path: Path):
    tid = _active_futures(tmp_path, contracts=2, ticker="ESACT1")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity_remaining"] = 3  # > quantity (2)
    with pytest.raises(ValueError, match="quantity_remaining"):
        thesis_store._validate_thesis(t)


def test_validate_thesis_futures_closed_nonzero_remaining_raises(tmp_path: Path):
    tid = _active_futures(tmp_path, contracts=2, ticker="ESACT2")
    t = thesis_store.close(tmp_path, tid, "manual", 5010.0, "2026-05-10T00:00:00+00:00")
    assert t["status"] == "CLOSED"
    t["position"]["quantity_remaining"] = 1  # should be 0 post-close
    with pytest.raises(ValueError, match="quantity_remaining == 0"):
        thesis_store._validate_thesis(t)


# -- Tests: schema additive backward-compat (plan §3 test#7) ------------------


def test_schema_additive_equity_thesis_still_valid(tmp_path: Path):
    """Existing equity thesis (no futures fields at all) validates cleanly
    against the schema extended with additive futures properties (D1)."""
    tid = _active_equity(tmp_path, 10)
    t = thesis_store.get(tmp_path, tid)
    assert "asset_type" not in t["position"]
    assert "quantity" not in t["position"]
    thesis_store._validate_thesis(t)  # no raise


# -- Tests: attach_futures_position() handoff validation (plan §3 test#8) -----


def test_attach_futures_rejects_no_trade(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESNOTRADE")
    report_path = _make_futures_report(
        tmp_path, sizing_status="NO_TRADE", no_trade_reason="risk_below_one_contract", contracts=0
    )
    with pytest.raises(ValueError, match="sizing_status"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_rejects_invalid_direction(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESBADDIR")
    report_path = _make_futures_report(tmp_path, direction="BOTH")
    with pytest.raises(ValueError, match="invalid direction"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


@pytest.mark.parametrize(
    "bad_contracts,ticker",
    [(0, "ESBADQZERO"), (-1, "ESBADQNEG"), (True, "ESBADQBOOL")],
)
def test_attach_futures_rejects_invalid_contracts(tmp_path, bad_contracts, ticker):
    """Bool-exclude -> isfinite -> range, in that order (checklist #10/10a):
    a bare `True` must not silently pass as 1 contract."""
    tid, _ = _register_and_get(tmp_path, ticker=ticker)
    report_path = _make_futures_report(tmp_path, contracts=bad_contracts)
    with pytest.raises(ValueError, match="invalid contracts"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


@pytest.mark.parametrize(
    "bad_multiplier,ticker",
    [(0, "ESBADMZERO"), (-5, "ESBADMNEG"), (True, "ESBADMBOOL")],
)
def test_attach_futures_rejects_invalid_multiplier(tmp_path, bad_multiplier, ticker):
    tid, _ = _register_and_get(tmp_path, ticker=ticker)
    report_path = _make_futures_report(
        tmp_path,
        contract_spec={
            "multiplier": bad_multiplier,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "currency": "USD",
            "source": "cme",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="invalid contract_spec.multiplier"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_mismatched_entry_raises(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESMISMATCH")
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match="Entry price mismatch"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path, expected_entry=9999.0)


def test_attach_futures_missing_report_raises_file_not_found(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESMISSING")
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        thesis_store.attach_futures_position(tmp_path, tid, str(missing))


def test_attach_futures_rejects_parse_error(tmp_path: Path):
    """3-class loader tag: parse_error (invalid JSON syntax)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESPARSEERR")
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="parse_error"):
        thesis_store.attach_futures_position(tmp_path, tid, str(bad_path))


def test_attach_futures_rejects_unreadable_encoding(tmp_path: Path):
    """3-class loader tag: unreadable (not valid UTF-8)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESUNREADABLE")
    bad_path = tmp_path / "bad_encoding.json"
    bad_path.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ValueError, match="unreadable"):
        thesis_store.attach_futures_position(tmp_path, tid, str(bad_path))


def test_attach_futures_rejects_non_finite(tmp_path: Path):
    """3-class loader tag: non_finite (bare Infinity literal anywhere in
    the parsed structure — json.loads accepts it as a non-standard
    extension; _contains_non_finite scans the whole structure)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNONFINITE")
    bad_path = tmp_path / "non_finite.json"
    bad_path.write_text(
        '{"sizing_status": "SIZED", "direction": "LONG", "contracts": 2, '
        '"contract_spec": {"multiplier": Infinity}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non_finite"):
        thesis_store.attach_futures_position(tmp_path, tid, str(bad_path))


# -- Tests: futures PARTIALLY_CLOSED validate (plan §3 test#10) ---------------


def test_futures_partially_closed_validates_cleanly(tmp_path: Path):
    """A partially-trimmed futures thesis passes _validate_thesis (P1 — the
    original bug: the pre-fix PARTIALLY_CLOSED block unconditionally
    required position.shares/shares_remaining and would crash here)."""
    tid = _active_futures(tmp_path, contracts=4, ticker="ESPC1")
    t = thesis_store.trim(tmp_path, tid, 1, 5010.0, "2026-05-10")
    assert t["status"] == "PARTIALLY_CLOSED"
    thesis_store._validate_thesis(t)  # no raise


def test_futures_partially_closed_quantity_remaining_out_of_range_raises(tmp_path: Path):
    tid = _active_futures(tmp_path, contracts=4, ticker="ESPC2")
    thesis_store.trim(tmp_path, tid, 1, 5010.0, "2026-05-10")
    t = thesis_store.get(tmp_path, tid)
    t["position"]["quantity_remaining"] = 4  # == quantity, not < quantity
    with pytest.raises(ValueError, match="0 < quantity_remaining"):
        thesis_store._validate_thesis(t)
    t["position"]["quantity_remaining"] = 0  # not > 0
    with pytest.raises(ValueError, match="0 < quantity_remaining"):
        thesis_store._validate_thesis(t)


def test_equity_partially_closed_requires_shares_remaining_unaffected(tmp_path: Path):
    """Regression pin: the pre-existing equity PARTIALLY_CLOSED invariant
    (test_thesis_store.py::test_partially_closed_requires_shares_remaining)
    is untouched by the futures branch."""
    tid = _active_equity(tmp_path, 10, ticker="EQPC")
    thesis_store.trim(tmp_path, tid, 4, 120.0, "2026-05-10")
    t = thesis_store.get(tmp_path, tid)
    del t["position"]["shares_remaining"]
    with pytest.raises(ValueError, match="requires position.shares_remaining"):
        thesis_store._validate_thesis(t)


# -- Tests: report-type misfeed rejection, both directions (plan §3 test#11) --


def test_attach_futures_rejects_equity_report(tmp_path: Path):
    """An equity position-sizer report (mode='shares') fed to
    attach_futures_position() must be rejected."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEQREPORT")
    equity_report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {"entry_price": 150.0, "stop_price": 142.0},
        "calculations": {"fixed_fractional": {"method": "fixed_fractional", "shares": 100}},
        "final_recommended_shares": 100,
        "final_position_value": 15000.0,
        "final_risk_dollars": 800.0,
        "final_risk_pct": 0.008,
    }
    report_path = tmp_path / "equity_report.json"
    report_path.write_text(json.dumps(equity_report), encoding="utf-8")
    with pytest.raises(ValueError, match="sizing_status"):
        thesis_store.attach_futures_position(tmp_path, tid, str(report_path))


def test_attach_position_rejects_futures_report(tmp_path: Path):
    """A futures-position-sizer SIZED report fed to attach_position()
    (equity) must be rejected by the existing mode != 'shares' check —
    reverse direction, no code change, pinned by this test."""
    tid, _ = _register_and_get(tmp_path, ticker="ESFUTREPORT")
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match="expected 'shares'"):
        thesis_store.attach_position(tmp_path, tid, report_path)


# -- Tests: direct open_position(contracts=...), no attach (plan §3 test#12) --


def test_open_position_direct_contracts_round_trip(tmp_path: Path):
    """open_position(contracts=...) without a prior attach_futures_position()
    call builds the futures position from scratch."""
    tid, _ = _register_and_get(tmp_path, ticker="ESDIRECT", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    t = thesis_store.open_position(
        tmp_path,
        tid,
        5000.0,
        "2026-05-01T00:00:00+00:00",
        contracts=2,
        multiplier=50,
        direction="SHORT",
        contract_symbol="ES",
        contract_currency="USD",
        event_date="2026-05-01T00:00:00+00:00",
    )
    assert t["status"] == "ACTIVE"
    assert t["position"]["asset_type"] == "futures"
    assert t["position"]["quantity"] == 2
    assert t["position"]["quantity_remaining"] == 2
    assert t["position"]["multiplier"] == 50
    assert t["position"]["direction"] == "SHORT"
    assert t["position"]["contract_symbol"] == "ES"
    assert t["position"]["contract_spec"]["currency"] == "USD"

    t = thesis_store.close(tmp_path, tid, "manual", 4950.0, "2026-05-10T00:00:00+00:00")
    assert t["status"] == "CLOSED"
    # (4950-5000)*50*2*(-1) = 5000
    assert t["outcome"]["pnl_dollars"] == 5000.0


def test_open_position_contracts_requires_multiplier_and_direction(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESMISSING", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="requires multiplier and direction"):
        thesis_store.open_position(tmp_path, tid, 5000.0, "2026-05-01T00:00:00+00:00", contracts=2)


def test_open_position_direct_contracts_rejects_negative_contracts(tmp_path: Path):
    """P2: direct-open validates contracts the same way attach_futures_position()
    does — a futures-specific ValueError, not the generic schema
    exclusiveMinimum message surfaced later at _save_thesis() time."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNEGQTY", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="requires a positive whole number of contracts"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=-2,
            multiplier=50,
            direction="LONG",
            contract_currency="USD",
        )


def test_open_position_direct_contracts_rejects_fractional_contracts(tmp_path: Path):
    """P1-4 (user independent review): futures trade in whole contracts
    only — contracts=1.5 must be rejected outright, never silently
    floored or accepted as-is."""
    tid, _ = _register_and_get(tmp_path, ticker="ESFRACQTY", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="requires a positive whole number of contracts"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=1.5,
            multiplier=50,
            direction="LONG",
            contract_currency="USD",
        )


def test_open_position_direct_contracts_rejects_negative_multiplier(tmp_path: Path):
    """P2: same futures-specific validation for an invalid multiplier."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNEGMULT", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="requires a finite positive multiplier"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=2,
            multiplier=-50,
            direction="LONG",
            contract_currency="USD",
        )


# -- Tests: P1 fixes from user independent review (money-critical) -----------


def test_attach_futures_position_rejected_on_active_sign_flip_regression(tmp_path: Path):
    """P1-1 (user independent review, MOST CRITICAL): re-attaching on
    ACTIVE must be rejected — the exact scenario that silently flipped
    P&L sign before this fix. LONG 2 contracts @5000 opened, then a SHORT
    SIZED report re-attached: without the fix this would overwrite
    position.direction to SHORT and a subsequent close @4900 would record
    +10000 instead of the correct -10000 for the original LONG."""
    tid = _active_futures(
        tmp_path, contracts=2, multiplier=50, direction="LONG", ticker="ESSIGNFLIP"
    )
    short_report = _make_futures_report(tmp_path, direction="SHORT", contracts=2)
    with pytest.raises(ValueError, match=r"attach_futures_position\(\) not allowed"):
        thesis_store.attach_futures_position(tmp_path, tid, short_report)

    # State must be UNCHANGED — direction still LONG — and closing still
    # produces the correct LONG-side P&L.
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["direction"] == "LONG"
    t = thesis_store.close(tmp_path, tid, "manual", 4900.0, "2026-05-10T00:00:00+00:00")
    # (4900-5000)*50*2*(+1) = -10000, NOT +10000
    assert t["outcome"]["pnl_dollars"] == -10000.0


def test_attach_futures_position_rejected_on_active_same_direction(tmp_path: Path):
    """P1-1: ACTIVE re-attach is rejected even when direction would be
    unchanged — the guard is status-based, not sign-based (simplicity /
    no room for a "safe re-attach" special case to regress later)."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESACTIVENOOP")
    report_path = _make_futures_report(tmp_path, contracts=3)
    with pytest.raises(ValueError, match=r"attach_futures_position\(\) not allowed"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_rejects_non_usd_currency(tmp_path: Path):
    """P1-2 (user independent review): this skill has no FX conversion —
    a non-USD contract (e.g. FESX/EUR) must be rejected fail-closed
    rather than silently computing P&L in the wrong currency magnitude."""
    tid, _ = _register_and_get(tmp_path, ticker="FESXEUR")
    report_path = _make_futures_report(
        tmp_path,
        symbol="FESX",
        contracts=18,
        contract_spec={
            "multiplier": 10,
            "tick_size": 1.0,
            "tick_value": 10.0,
            "currency": "EUR",
            "source": "eurex",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="non-USD futures not supported"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_rejects_fractional_contracts(tmp_path: Path):
    """P1-4 (user independent review): a SIZED report with a fractional
    contracts field (schema violation from a hostile/buggy upstream) must
    be rejected, not silently accepted as-is."""
    tid, _ = _register_and_get(tmp_path, ticker="ESFRACREPORT")
    report_path = _make_futures_report(tmp_path, contracts=1.5)
    with pytest.raises(ValueError, match="invalid contracts"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_open_position_direct_open_rejects_nan_price(tmp_path: Path):
    """P1-3 (user independent review, money-critical): a NaN actual_price
    must be rejected at open time, before it can NaN-poison every
    downstream P&L computation."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNANOPEN", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="requires a finite positive actual_price"):
        thesis_store.open_position(
            tmp_path,
            tid,
            float("nan"),
            "2026-05-01T00:00:00+00:00",
            contracts=2,
            multiplier=50,
            direction="LONG",
        )
    # State must be unchanged — thesis never reached ACTIVE.
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_close_futures_rejects_infinite_price(tmp_path: Path):
    """P1-3: an Infinity exit price must be rejected at close time —
    state (status, outcome) must stay unchanged, not persist inf/nan."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESINFCLOSE")
    with pytest.raises(ValueError, match="requires a finite positive actual_price"):
        thesis_store.close(tmp_path, tid, "manual", float("inf"), "2026-05-10T00:00:00+00:00")
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["outcome"]["pnl_dollars"] is None


def test_trim_futures_rejects_nan_price(tmp_path: Path):
    """P1-3: a NaN trim price must be rejected — position must stay
    unchanged (no partial trim applied)."""
    tid = _active_futures(tmp_path, contracts=4, ticker="ESNANTRIM")
    with pytest.raises(ValueError, match="requires a finite positive price"):
        thesis_store.trim(tmp_path, tid, 1, float("nan"), "2026-05-10")
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["position"]["quantity_remaining"] == 4


def test_trim_futures_rejects_fractional_contracts_sold(tmp_path: Path):
    """P1-4: contracts_sold=0.5 must be rejected — trim() never sells a
    fractional futures contract."""
    tid = _active_futures(tmp_path, contracts=4, ticker="ESFRACTRIM")
    with pytest.raises(ValueError, match="positive whole number of contracts"):
        thesis_store.trim(tmp_path, tid, 0.5, 5010.0, "2026-05-10")
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["position"]["quantity_remaining"] == 4


def test_terminate_futures_rejects_infinite_price(tmp_path: Path):
    """P1-3: terminate()'s optional actual_price must also be validated
    when provided — an Infinity exit price must be rejected."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESINFTERM")
    with pytest.raises(ValueError, match="requires a finite positive actual_price"):
        thesis_store.terminate(
            tmp_path,
            tid,
            "INVALIDATED",
            "thesis broke",
            actual_price=float("inf"),
            actual_date="2026-05-10T00:00:00+00:00",
        )
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"


def test_terminate_futures_no_price_still_works(tmp_path: Path):
    """P1-3 regression guard: terminate() without actual_price (the
    partial-outcome path) must still work — the new validation only fires
    when a price IS given."""
    tid = _active_futures(tmp_path, contracts=2, ticker="ESTERMNOPRICE")
    t = thesis_store.terminate(tmp_path, tid, "INVALIDATED", "thesis broke")
    assert t["status"] == "INVALIDATED"
    assert t["outcome"]["pnl_dollars"] is None


def test_cli_open_position_rejects_nan_actual_price(tmp_path: Path):
    """P1-3: the CLI --actual-price flag rejects nan/inf at argparse
    level (before even reaching open_position())."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLINAN", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit):
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "nan",
                "--actual-date",
                "2026-05-01",
                "--contracts",
                "2",
                "--multiplier",
                "50",
                "--direction",
                "LONG",
            ]
        )


def test_cli_open_position_rejects_fractional_contracts(tmp_path: Path):
    """P1-4: the CLI --contracts flag rejects a fractional string like
    "1.5" at argparse level."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIFRAC", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit):
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--contracts",
                "1.5",
                "--multiplier",
                "50",
                "--direction",
                "LONG",
            ]
        )


def test_open_position_rejects_both_shares_and_contracts(tmp_path: Path):
    """P3-2: providing both --shares and --contracts is never meaningful —
    fail loud instead of silently picking one via dispatch order."""
    tid, _ = _register_and_get(tmp_path, ticker="ESBOTHQTY", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="not both"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            shares=10,
            contracts=2,
            multiplier=50,
            direction="LONG",
        )


def test_cli_open_position_rejects_both_shares_and_contracts(tmp_path: Path):
    """Same guard, exercised through the CLI (--shares and --contracts
    together)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIBOTH", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    with pytest.raises(ValueError, match="not both"):
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--shares",
                "10",
                "--contracts",
                "2",
            ]
        )


# -- Tests: P1 addendum fixes from user re-review (money-critical) -----------


def test_close_futures_rejects_overflow_with_finite_operands(tmp_path: Path):
    """P1 addendum-1 (user re-review, teaching 10b — guard the output, not
    just the input): contracts=2, multiplier=1e308, entry=1, exit=2 — every
    INPUT is individually finite, but (2-1)*1e308*2 overflows to inf. Must
    be rejected before persisting, not saved as YAML `.inf`."""
    tid, _ = _register_and_get(tmp_path, ticker="ESOVERFLOW", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    t = thesis_store.open_position(
        tmp_path,
        tid,
        1.0,
        "2026-05-01T00:00:00+00:00",
        contracts=2,
        multiplier=1e308,
        direction="LONG",
        contract_currency="USD",
        event_date="2026-05-01T00:00:00+00:00",
    )
    assert t["status"] == "ACTIVE"
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match="not finite"):
        thesis_store.close(tmp_path, tid, "manual", 2.0, "2026-05-10T00:00:00+00:00")

    assert _state_file_hash(tmp_path, tid) == before
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["outcome"]["pnl_dollars"] is None


def test_trim_futures_rejects_overflow_with_finite_operands(tmp_path: Path):
    """P1 addendum-1: same overflow guard on the partial-trim leg (which
    computes realized/proceeds itself, not via _finalize_futures_outcome)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESOVERFLOWTRIM", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid,
        1.0,
        "2026-05-01T00:00:00+00:00",
        contracts=2,
        multiplier=1e308,
        direction="LONG",
        contract_currency="USD",
        event_date="2026-05-01T00:00:00+00:00",
    )
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match="not finite"):
        thesis_store.trim(tmp_path, tid, 1, 2.0, "2026-05-10")

    assert _state_file_hash(tmp_path, tid) == before
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["position"]["quantity_remaining"] == 2


def test_open_position_direct_open_requires_contract_currency(tmp_path: Path):
    """P1 addendum-2 (user re-review): a direct open has no contract_spec
    to read a currency from — --contract-currency is REQUIRED, never
    silently assumed to be USD."""
    tid, _ = _register_and_get(tmp_path, ticker="ESNOCURR", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match="requires contract_currency"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=2,
            multiplier=50,
            direction="LONG",
        )

    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_open_position_direct_open_rejects_non_usd_currency(tmp_path: Path):
    """P1 addendum-2: a direct open with a non-USD --contract-currency
    must be rejected fail-closed, same as the attach path."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEURDIRECT", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError, match="non-USD futures not supported"):
        thesis_store.open_position(
            tmp_path,
            tid,
            5000.0,
            "2026-05-01T00:00:00+00:00",
            contracts=2,
            multiplier=50,
            direction="LONG",
            contract_currency="EUR",
        )

    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_cli_open_position_direct_open_requires_contract_currency(tmp_path: Path):
    """Same guard exercised through the CLI (no --contract-currency)."""
    tid, _ = _register_and_get(tmp_path, ticker="ESCLINOCURR", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    with pytest.raises(ValueError, match="requires contract_currency"):
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--contracts",
                "2",
                "--multiplier",
                "50",
                "--direction",
                "LONG",
            ]
        )


def test_attach_futures_rejects_missing_currency_field(tmp_path: Path):
    """P1 addendum-3 (user re-review): contract_spec.currency missing
    entirely must be rejected — no fallback to any other field."""
    tid, _ = _register_and_get(tmp_path, ticker="ESMISSCURR")
    report_path = _make_futures_report(
        tmp_path,
        contract_spec={
            "multiplier": 50,
            "tick_size": 0.25,
            "tick_value": 12.5,
            # no "currency" key at all
            "source": "cme",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="missing contract_spec.currency"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_rejects_empty_currency_string(tmp_path: Path):
    """P1 addendum-3: an empty-string currency must be rejected — not
    treated as a falsy-but-acceptable value."""
    tid, _ = _register_and_get(tmp_path, ticker="ESEMPTYCURR")
    report_path = _make_futures_report(
        tmp_path,
        contract_spec={
            "multiplier": 50,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "currency": "",
            "source": "cme",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="missing contract_spec.currency"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_attach_futures_currency_fallback_to_top_level_removed(tmp_path: Path):
    """P1 addendum-3 regression: a report with contract_spec.currency
    missing but a top-level report["currency"]="USD" must STILL be
    rejected — the earlier fallback-to-top-level-currency behavior was
    removed; contract_spec is the SOLE source of truth."""
    tid, _ = _register_and_get(tmp_path, ticker="ESFALLBACKGONE")
    report_path = _make_futures_report(
        tmp_path,
        currency="USD",  # top-level — must NOT be consulted anymore
        contract_spec={
            "multiplier": 50,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "source": "cme",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError, match="missing contract_spec.currency"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


def test_trim_futures_quantity_remaining_is_canonical_int(tmp_path: Path):
    """P1 addendum-4: quantity_remaining is stored as a genuine Python
    int, never a float like 2.0 (schema now requires "type": "integer")."""
    tid = _active_futures(tmp_path, contracts=4, ticker="ESCANONICAL")
    t = thesis_store.trim(tmp_path, tid, 1, 5010.0, "2026-05-10")
    assert t["position"]["quantity_remaining"] == 3
    assert isinstance(t["position"]["quantity_remaining"], int)
    assert not isinstance(t["position"]["quantity_remaining"], bool)

    t = thesis_store.trim(tmp_path, tid, 3, 5020.0, "2026-05-15")
    assert t["status"] == "CLOSED"
    assert t["position"]["quantity_remaining"] == 0
    assert isinstance(t["position"]["quantity_remaining"], int)


def test_rejected_futures_mutations_leave_state_file_byte_identical(tmp_path: Path):
    """P1 addendum (user re-review): sweeps the money-critical rejection
    paths above against a single ACTIVE futures thesis and confirms the
    on-disk YAML file is byte-for-byte unchanged after each one — not
    just "logically" unchanged."""
    tid = _active_futures(tmp_path, contracts=2, multiplier=50, ticker="ESHASHSWEEP")
    before = _state_file_hash(tmp_path, tid)

    with pytest.raises(ValueError):
        thesis_store.close(tmp_path, tid, "manual", float("inf"), "2026-05-10T00:00:00+00:00")
    assert _state_file_hash(tmp_path, tid) == before

    with pytest.raises(ValueError):
        thesis_store.trim(tmp_path, tid, 1, float("nan"), "2026-05-10")
    assert _state_file_hash(tmp_path, tid) == before

    with pytest.raises(ValueError):
        thesis_store.trim(tmp_path, tid, 0.5, 5010.0, "2026-05-10")
    assert _state_file_hash(tmp_path, tid) == before

    with pytest.raises(ValueError):
        thesis_store.terminate(
            tmp_path,
            tid,
            "INVALIDATED",
            "broke",
            actual_price=float("inf"),
            actual_date="2026-05-10T00:00:00+00:00",
        )
    assert _state_file_hash(tmp_path, tid) == before

    short_report = _make_futures_report(tmp_path, direction="SHORT")
    with pytest.raises(ValueError):
        thesis_store.attach_futures_position(tmp_path, tid, short_report)
    assert _state_file_hash(tmp_path, tid) == before

    eur_report = _make_futures_report(
        tmp_path,
        contract_spec={
            "multiplier": 10,
            "tick_size": 1.0,
            "tick_value": 10.0,
            "currency": "EUR",
            "source": "eurex",
            "verified": "2026-01-01",
        },
    )
    with pytest.raises(ValueError):
        thesis_store.attach_futures_position(tmp_path, tid, eur_report)
    assert _state_file_hash(tmp_path, tid) == before


# -- Tests: postmortem unit-aware rendering (plan §3 test#13) -----------------


def test_postmortem_futures_rows(tmp_path: Path):
    state_dir = tmp_path / "theses"
    tid = _active_futures(state_dir, contracts=2, multiplier=50, direction="LONG", ticker="ESPM")
    thesis_store.close(state_dir, tid, "target_hit", 5050.0, "2026-05-10T00:00:00+00:00")
    journal_dir = tmp_path / "journal"
    pm_path = thesis_review.generate_postmortem(tid, str(state_dir), journal_dir=str(journal_dir))
    content = Path(pm_path).read_text()
    assert "Contracts" in content
    assert "Multiplier" in content
    assert "Total Risk" in content
    assert "Risk/Contract" in content
    assert "Shares |" not in content


def test_postmortem_equity_rows_unaffected(tmp_path: Path):
    """D7: equity postmortem still shows Shares/Position Value/Risk ($) —
    unaffected by the futures branch."""
    state_dir = tmp_path / "theses"
    tid = _active_equity(state_dir, 10, ticker="EQPM")
    thesis_store.close(state_dir, tid, "target_hit", 110.0, "2026-05-10T00:00:00+00:00")
    journal_dir = tmp_path / "journal"
    pm_path = thesis_review.generate_postmortem(tid, str(state_dir), journal_dir=str(journal_dir))
    content = Path(pm_path).read_text()
    assert "Shares |" in content
    assert "Position Value" in content
    assert "Contracts |" not in content


# -- Tests: re-attach status guard (plan §3 test#14) ---------------------------


@pytest.mark.parametrize("end_status", ["ACTIVE", "PARTIALLY_CLOSED", "CLOSED", "INVALIDATED"])
def test_attach_futures_position_rejected_post_open(tmp_path: Path, end_status):
    """attach_futures_position() must refuse ACTIVE / PARTIALLY_CLOSED /
    CLOSED / INVALIDATED (P1-1: unlike equity's attach_position(), ACTIVE
    is ALSO rejected here — re-writing quantity_remaining == quantity
    would violate the invariant and clobber the trim ledger for
    PARTIALLY_CLOSED/CLOSED/INVALIDATED, and would silently overwrite
    `direction` — a P&L sign-flip risk — for ACTIVE; see
    test_attach_futures_position_rejected_on_active_sign_flip_regression
    for the concrete sign-flip scenario)."""
    tid = _active_futures(tmp_path, contracts=4, ticker=f"ESG{end_status[:3]}")

    if end_status == "ACTIVE":
        pass  # already ACTIVE straight out of _active_futures()
    elif end_status == "PARTIALLY_CLOSED":
        thesis_store.trim(tmp_path, tid, 1, 5010.0, "2026-05-10")
    elif end_status == "CLOSED":
        thesis_store.trim(tmp_path, tid, 4, 5010.0, "2026-05-10")  # trim-to-zero
    else:  # INVALIDATED
        thesis_store.terminate(tmp_path, tid, "INVALIDATED", "thesis broke")

    assert thesis_store.get(tmp_path, tid)["status"] == end_status
    report_path = _make_futures_report(tmp_path)
    with pytest.raises(ValueError, match=r"attach_futures_position\(\) not allowed"):
        thesis_store.attach_futures_position(tmp_path, tid, report_path)


# -- Tests: CLI subcommands (attach-futures-position / --contracts /
#    --contracts-sold) -------------------------------------------------------


def test_cli_attach_futures_and_trim_subcommands(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIFLOW", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )

    report_path = _make_futures_report(tmp_path, contracts=4)
    assert (
        thesis_store.main(
            ["--state-dir", sd, "attach-futures-position", tid, "--report", report_path]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["quantity"] == 4

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "trim",
                tid,
                "--contracts-sold",
                "2",
                "--price",
                "5010",
                "--date",
                "2026-05-05",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "PARTIALLY_CLOSED"
    assert t["position"]["quantity_remaining"] == 2


def test_cli_trim_requires_exactly_one_of_shares_or_contracts_sold(tmp_path: Path):
    tid = _active_futures(tmp_path, contracts=2, ticker="ESCLIGUARD")
    sd = str(tmp_path)
    with pytest.raises(ValueError, match="exactly one of"):
        thesis_store.main(
            ["--state-dir", sd, "trim", tid, "--price", "5010", "--date", "2026-05-05"]
        )


def test_cli_open_position_direct_contracts(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="ESCLIDIR", _source_date="2026-05-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "ok",
                "--event-date",
                "2026-05-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "5000",
                "--actual-date",
                "2026-05-01",
                "--contracts",
                "2",
                "--multiplier",
                "50",
                "--direction",
                "SHORT",
                "--contract-symbol",
                "ES",
                "--contract-currency",
                "USD",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["position"]["quantity"] == 2
    assert t["position"]["direction"] == "SHORT"
