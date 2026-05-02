"""Tests for ssr_state_tracker — SSR Rule 201 evaluation + state file."""

import pytest
from ssr_state_tracker import (
    SSR_DROP_THRESHOLD_PCT,
    evaluate_ssr,
    load_prior_day_state,
    save_state,
)


class TestEvaluate:
    def test_drop_exactly_10pct_triggers(self):
        out = evaluate_ssr(prior_regular_close=100.0, current_price=90.0)
        assert out["ssr_triggered_today"] is True
        assert out["uptick_rule_active"] is True
        assert out["drop_from_prior_close_pct"] == pytest.approx(10.0)

    def test_drop_below_threshold_does_not_trigger(self):
        out = evaluate_ssr(prior_regular_close=100.0, current_price=92.0)
        assert out["ssr_triggered_today"] is False
        assert out["uptick_rule_active"] is False

    def test_invalid_prior_close_raises(self):
        with pytest.raises(ValueError):
            evaluate_ssr(prior_regular_close=0.0, current_price=80.0)

    def test_carryover_inherits_from_prior_state(self):
        prior = {"ssr_triggered_today": True}
        out = evaluate_ssr(prior_regular_close=100.0, current_price=99.0, prior_day_state=prior)
        assert out["ssr_triggered_today"] is False
        assert out["ssr_carryover_from_prior_day"] is True
        assert out["uptick_rule_active"] is True


class TestStatePersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        state = evaluate_ssr(prior_regular_close=100.0, current_price=85.0)
        save_state(tmp_path, "XYZ", "2026-04-30", state)
        loaded = load_prior_day_state(tmp_path, "XYZ", "2026-05-01")
        assert loaded is not None
        assert loaded["ssr_triggered_today"] is True
        assert loaded["prior_regular_close"] == 100.0

    def test_load_missing_returns_none(self, tmp_path):
        loaded = load_prior_day_state(tmp_path, "MISSING", "2026-04-30")
        assert loaded is None

    def test_carryover_via_state_file(self, tmp_path):
        # Yesterday: SSR triggered. Today: small move, but carryover applies.
        prior_state = evaluate_ssr(prior_regular_close=100.0, current_price=85.0)
        save_state(tmp_path, "XYZ", "2026-04-30", prior_state)
        prior = load_prior_day_state(tmp_path, "XYZ", "2026-05-01")
        today = evaluate_ssr(prior_regular_close=85.0, current_price=84.5, prior_day_state=prior)
        assert today["ssr_carryover_from_prior_day"] is True
        assert today["uptick_rule_active"] is True


class TestThresholdConstant:
    def test_constant_is_10(self):
        assert SSR_DROP_THRESHOLD_PCT == 10.0
