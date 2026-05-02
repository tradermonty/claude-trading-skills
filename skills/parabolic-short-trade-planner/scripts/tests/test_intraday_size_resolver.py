"""Tests for intraday_size_resolver — share-count math at trigger fire.

Critical contract: the size_recipe.shares_formula string from
size_recipe_builder.py and the implementation here MUST stay in sync.
test_size_recipe_string_matches_resolver enforces the link by hand
(no eval), so a future formula change will fail loudly here.
"""

from __future__ import annotations

import math

import intraday_size_resolver as isr
import pytest


class TestResolveShares:
    def test_risk_constrained(self):
        # entry=100, stop=102, risk_per_share=2; risk_usd=200 → 100 shares
        # max_position=20000, cap=200 shares; risk wins (smaller) → 100
        n = isr.resolve_shares(
            entry_actual=100.0,
            stop_actual=102.0,
            risk_usd=200.0,
            max_position_value_usd=20_000.0,
        )
        assert n == 100

    def test_position_cap_constrained(self):
        # entry=100, stop=110, risk_per_share=10; risk_usd=10000 → 1000 shares
        # max_position=5000, cap=50 shares; cap wins (smaller) → 50
        n = isr.resolve_shares(
            entry_actual=100.0,
            stop_actual=110.0,
            risk_usd=10_000.0,
            max_position_value_usd=5_000.0,
        )
        assert n == 50

    def test_floor_truncates_partial_share(self):
        # 100.7 → 100, never 101
        n = isr.resolve_shares(
            entry_actual=100.0,
            stop_actual=101.0,
            risk_usd=100.7,
            max_position_value_usd=999_999.0,
        )
        assert n == 100  # floor(100.7)

    def test_stop_at_or_below_entry_raises(self):
        with pytest.raises(ValueError):
            isr.resolve_shares(
                entry_actual=100.0,
                stop_actual=100.0,
                risk_usd=200.0,
                max_position_value_usd=20_000.0,
            )
        with pytest.raises(ValueError):
            isr.resolve_shares(
                entry_actual=100.0,
                stop_actual=99.0,
                risk_usd=200.0,
                max_position_value_usd=20_000.0,
            )

    def test_zero_or_negative_inputs_raise(self):
        for bad_kw in (
            {"entry_actual": 0.0},
            {"entry_actual": -1.0},
            {"risk_usd": 0.0},
            {"risk_usd": -1.0},
            {"max_position_value_usd": 0.0},
            {"max_position_value_usd": -1.0},
        ):
            kwargs = {
                "entry_actual": 100.0,
                "stop_actual": 102.0,
                "risk_usd": 200.0,
                "max_position_value_usd": 20_000.0,
                **bad_kw,
            }
            with pytest.raises(ValueError):
                isr.resolve_shares(**kwargs)


class TestResolveSizeRecipe:
    def test_returns_resolved_dict(self):
        recipe = {
            "shares_formula": "floor(min(...))",
            "risk_usd": 200.0,
            "max_position_value_usd": 20_000.0,
        }
        out = isr.resolve_size_recipe(recipe, entry_actual=100.0, stop_actual=102.0)
        assert out["shares_actual"] == 100
        assert out["shares_formula"] == "floor(min(...))"
        # risk_at_trigger = 100 shares * $2/share = $200 exact
        assert out["risk_at_trigger_usd"] == 200.0


class TestSizeRecipeStringMatchesResolver:
    """v0.5b contract: the formula string in size_recipe_builder and
    the implementation here MUST stay in sync. We can't eval the
    string, but we can assert it mentions every input variable and
    operation the implementation uses."""

    def test_formula_string_mentions_all_inputs(self):
        from size_recipe_builder import SHARES_FORMULA

        for token in (
            "risk_usd",
            "stop_actual",
            "entry_actual",
            "max_position_value_usd",
            "min",
            "floor",
        ):
            assert token in SHARES_FORMULA, (
                f"size_recipe_builder.SHARES_FORMULA is missing {token!r}; "
                "if the formula changed, update intraday_size_resolver.resolve_shares "
                "in lockstep."
            )

    def test_resolver_matches_formula_for_known_inputs(self):
        """Hand-evaluate the formula against the resolver for a fixed
        input set. This catches "they both got changed but in different
        ways" regressions."""
        entry, stop, risk, cap = 100.0, 102.0, 200.0, 20_000.0
        # Manual formula application:
        expected = math.floor(min(risk / (stop - entry), cap / entry))
        actual = isr.resolve_shares(
            entry_actual=entry,
            stop_actual=stop,
            risk_usd=risk,
            max_position_value_usd=cap,
        )
        assert actual == expected
