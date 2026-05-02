"""Tests for size_recipe_builder.build_size_recipe."""

import pytest
from size_recipe_builder import SHARES_FORMULA, SIZING_RULE, build_size_recipe


class TestBasicMath:
    def test_default_sizing(self):
        out = build_size_recipe(
            account_size=100_000,
            risk_bps=50,
            max_position_pct=5.0,
            max_short_exposure_pct=20.0,
        )
        assert out["risk_usd"] == 500.0  # 0.5% of 100k
        assert out["max_position_value_usd"] == 5000.0  # 5% of 100k
        assert out["max_short_exposure_usd"] == 20000.0
        assert out["sizing_rule_applied"] == SIZING_RULE
        assert out["shares_formula"] == SHARES_FORMULA

    def test_max_short_exposure_check_passed_when_room(self):
        out = build_size_recipe(
            account_size=100_000,
            risk_bps=50,
            max_position_pct=5.0,
            max_short_exposure_pct=20.0,
            current_short_exposure=10_000,  # 10k room left vs 5k position cap
        )
        assert out["max_short_exposure_check_passed"] is True
        assert out["max_position_value_usd"] == 5000.0

    def test_short_exposure_squeezes_position_cap(self):
        # Already shorted $18k of $20k cap → $2k room. Position cap should
        # tighten from $5k to $2k to fit.
        out = build_size_recipe(
            account_size=100_000,
            risk_bps=50,
            max_position_pct=5.0,
            max_short_exposure_pct=20.0,
            current_short_exposure=18_000,
        )
        assert out["max_short_exposure_check_passed"] is False
        assert out["max_position_value_usd"] == 2000.0

    def test_at_or_above_short_cap_zeros_position(self):
        out = build_size_recipe(
            account_size=100_000,
            risk_bps=50,
            max_position_pct=5.0,
            max_short_exposure_pct=20.0,
            current_short_exposure=20_000,
        )
        assert out["max_position_value_usd"] == 0.0
        assert out["max_short_exposure_check_passed"] is False


class TestValidation:
    def test_negative_account_raises(self):
        with pytest.raises(ValueError):
            build_size_recipe(
                account_size=-1, risk_bps=50, max_position_pct=5.0, max_short_exposure_pct=20.0
            )

    def test_zero_risk_raises(self):
        with pytest.raises(ValueError):
            build_size_recipe(
                account_size=100_000,
                risk_bps=0,
                max_position_pct=5.0,
                max_short_exposure_pct=20.0,
            )
