"""Tests for plan_breakout_trades module."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from plan_breakout_trades import (
    generate_plans,
    load_input,
    process_candidate,
    resolve_as_of,
    validate_result,
)


def _make_args(**overrides) -> argparse.Namespace:
    defaults = {
        "input": "test.json",
        "account_size": 100_000,
        "risk_pct": 0.5,
        "max_position_pct": 10.0,
        "max_sector_pct": 30.0,
        "max_portfolio_heat_pct": 6.0,
        "target_r_multiple": 2.0,
        "stop_buffer_pct": 1.0,
        "max_chase_pct": 2.0,
        "pivot_buffer_pct": 0.1,
        "current_exposure_json": None,
        "output_dir": "/tmp/test_plans",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_vcp_result(
    symbol: str = "TEST",
    score: float = 85.0,
    state: str = "Pre-breakout",
    valid_vcp: bool = True,
    pivot: float = 100.0,
    last_low: float = 95.0,
    sector: str = "Technology",
    price: float = 98.0,
    breakout_volume: bool = False,
    distance_from_pivot: float = -2.0,
) -> dict:
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Inc.",
        "sector": sector,
        "price": price,
        "market_cap": 50_000_000_000,
        "composite_score": score,
        "rating": "Strong VCP",
        "execution_state": state,
        "valid_vcp": valid_vcp,
        "entry_ready": False,
        "vcp_pattern": {
            "pivot_price": pivot,
            "contractions": [
                {"label": "T1", "high_price": 105.0, "low_price": 92.0, "depth_pct": 12.4},
                {"label": "T2", "high_price": pivot, "low_price": last_low, "depth_pct": 5.0},
            ],
            "atr_value": 2.5,
        },
        "volume_pattern": {
            "breakout_volume_detected": breakout_volume,
            "avg_volume_50d": 1_000_000,
            "dry_up_ratio": 0.5,
        },
        "pivot_proximity": {
            "stop_loss_price": last_low * 0.99,
            "risk_pct": 5.0,
            "distance_from_pivot_pct": distance_from_pivot,
        },
        "trend_template": {"score": 100},
        "relative_strength": {"rs_percentile": 80},
    }


def _make_input_data(results: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "metadata": {"generated_at": "2026-04-12 17:35:47"},
        "results": results,
        "summary": {"total": len(results)},
        "sector_distribution": {},
    }


class TestLoadInput:
    def test_missing_schema_version_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"results": []}, f)
            f.flush()
            with pytest.raises(ValueError, match="schema_version"):
                load_input(f.name)
            os.unlink(f.name)

    def test_wrong_schema_version_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema_version": "99.0", "results": []}, f)
            f.flush()
            with pytest.raises(ValueError, match="Unsupported"):
                load_input(f.name)
            os.unlink(f.name)

    def test_valid_input_loads(self):
        data = _make_input_data([_make_vcp_result()])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            loaded = load_input(f.name)
            assert len(loaded["results"]) == 1
            os.unlink(f.name)


class TestValidateResult:
    def test_valid_result(self):
        result = _make_vcp_result()
        is_valid, warnings = validate_result(result)
        assert is_valid
        assert warnings == []

    def test_missing_symbol(self):
        result = _make_vcp_result()
        del result["symbol"]
        is_valid, warnings = validate_result(result)
        assert not is_valid
        assert any("symbol" in w for w in warnings)

    def test_missing_contractions(self):
        result = _make_vcp_result()
        result["vcp_pattern"]["contractions"] = []
        is_valid, warnings = validate_result(result)
        assert not is_valid


class TestMinerviniGate:
    def test_prebreakout_strong_vcp_actionable(self):
        result = _make_vcp_result(score=85.0, state="Pre-breakout", valid_vcp=True)
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "actionable"
        assert classified["data"]["plan_type"] == "pending_breakout"
        assert classified["data"]["decision_code"] == "ACTIONABLE_PREBREAKOUT"

    def test_plan_session_skips_holiday_and_rolls_after_early_close(self):
        result = _make_vcp_result(score=85.0)
        args = _make_args()
        exposure = {"sector_exposure": {}, "open_risk_pct": 0}

        holiday = process_candidate(
            result,
            args,
            0.0,
            {},
            exposure,
            datetime(2026, 7, 3, 10, tzinfo=ZoneInfo("America/New_York")),
        )
        assert holiday["data"]["plan_valid_for_session"] == "2026-07-06"

        after_early_close = process_candidate(
            result,
            args,
            0.0,
            {},
            exposure,
            datetime(2026, 11, 27, 13, tzinfo=ZoneInfo("America/New_York")),
        )
        assert after_early_close["data"]["plan_valid_for_session"] == "2026-11-30"

    def test_prebreakout_risk_worst_over_8_rejected(self):
        # pivot=100, last_low=88 -> stop=87.12, worst=102 -> risk=14.58%
        result = _make_vcp_result(score=85.0, last_low=88.0)
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"
        assert "risk_pct_worst" in classified["data"]["reason"]

    def test_prebreakout_invalid_vcp_rejected(self):
        result = _make_vcp_result(valid_vcp=False)
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_prebreakout_developing_watchlist(self):
        result = _make_vcp_result(score=65.0, valid_vcp=True)
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "watchlist"

    def test_developing_invalid_vcp_rejected(self):
        result = _make_vcp_result(score=65.0, valid_vcp=False)
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_breakout_with_volume_revalidation(self):
        result = _make_vcp_result(
            score=85.0,
            state="Breakout",
            valid_vcp=True,
            breakout_volume=True,
            distance_from_pivot=1.5,
            price=101.0,
        )
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "revalidation"
        assert classified["data"]["plan_type"] == "late_breakout_revalidation"

    def test_breakout_no_volume_rejected(self):
        result = _make_vcp_result(
            score=85.0,
            state="Breakout",
            valid_vcp=True,
            breakout_volume=False,
            distance_from_pivot=1.5,
            price=101.0,
        )
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_breakout_price_above_worst_rejected(self):
        result = _make_vcp_result(
            score=85.0,
            state="Breakout",
            valid_vcp=True,
            breakout_volume=True,
            distance_from_pivot=1.5,
            price=110.0,
        )
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_extended_state_rejected(self):
        result = _make_vcp_result(state="Extended")
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_overextended_state_rejected(self):
        result = _make_vcp_result(state="Overextended")
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"

    def test_breakout_developing_does_not_watchlist(self):
        """Breakout candidates must not go to watchlist — they already crossed pivot."""
        result = _make_vcp_result(
            score=65.0,
            state="Breakout",
            valid_vcp=True,
            breakout_volume=True,
            distance_from_pivot=1.5,
            price=101.0,
        )
        args = _make_args()
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "rejected"
        assert classified["classification"] != "watchlist"


class TestPortfolioConstraints:
    def test_heat_ceiling_defers(self):
        result = _make_vcp_result(score=85.0)
        args = _make_args(max_portfolio_heat_pct=0.01)  # Tiny ceiling
        classified = process_candidate(
            result, args, 0.0, {}, {"sector_exposure": {}, "open_risk_pct": 0}
        )
        assert classified["classification"] == "deferred"

    def test_sector_constraint_constrains(self):
        result = _make_vcp_result(score=85.0, sector="Technology")
        args = _make_args(max_sector_pct=5.0)
        exposure = {"sector_exposure": {"Technology": 4.9}, "open_risk_pct": 0}
        classified = process_candidate(result, args, 0.0, {}, exposure)
        assert classified["classification"] == "constrained"


class TestGeneratePlans:
    def test_empty_results(self):
        data = _make_input_data([])
        args = _make_args(decision_as_of=resolve_as_of("2026-07-06"))
        plans = generate_plans(data, args)
        assert plans["schema_version"] == "1.0"
        assert plans["summary"]["actionable_count"] == 0
        assert plans["generated_at"] == "2026-07-06T00:00:00-04:00"

    @pytest.mark.parametrize("value", ["not-a-date", "2026-07-06T10:00:00"])
    def test_invalid_or_naive_as_of_rejected(self, value):
        with pytest.raises(ValueError, match="--as-of"):
            resolve_as_of(value)

    def test_score_order_processing(self):
        r1 = _make_vcp_result(symbol="HIGH", score=90.0)
        r2 = _make_vcp_result(symbol="LOW", score=75.0)
        data = _make_input_data([r2, r1])  # Lower score first in input
        args = _make_args()
        plans = generate_plans(data, args)
        if len(plans["actionable_orders"]) >= 2:
            assert plans["actionable_orders"][0]["symbol"] == "HIGH"

    def test_validation_failure_creates_warning(self):
        bad = {"symbol": "BAD"}  # Missing required fields
        data = _make_input_data([bad])
        args = _make_args()
        plans = generate_plans(data, args)
        assert len(plans["warnings"]) > 0
        assert plans["summary"]["rejected_count"] == 1

    def test_actionable_has_order_templates(self):
        result = _make_vcp_result(score=85.0)
        data = _make_input_data([result])
        args = _make_args()
        plans = generate_plans(data, args)
        assert plans["summary"]["actionable_count"] == 1
        order = plans["actionable_orders"][0]
        assert "pre_place" in order["order_templates"]
        assert "post_confirm" in order["order_templates"]
        assert order["order_templates"]["pre_place"]["type"] == "stop_limit"
        assert order["order_templates"]["post_confirm"]["type"] == "limit"

    def test_input_metadata_populated(self):
        data = _make_input_data([_make_vcp_result()])
        args = _make_args()
        plans = generate_plans(data, args)
        meta = plans["input_metadata"]
        assert meta["candidates_in_file"] == 1
        assert meta["input_scope"] == "top_n_only"
