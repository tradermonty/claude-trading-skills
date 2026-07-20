"""Tests for Component 4: Perpetual Funding Regime Calculator."""

import math

import pytest
from calculators.funding_calculator import calculate_funding_regime


def test_too_few_symbols_flags_unavailable():
    result = calculate_funding_regime({"BTCUSDT": 0.0001})
    assert result["data_available"] is False


def test_none_rates_are_ignored():
    result = calculate_funding_regime({"BTCUSDT": 0.0001, "ETHUSDT": None})
    assert result["data_available"] is False


def test_neutral_baseline_funding_is_healthy():
    result = calculate_funding_regime({"BTCUSDT": 0.0001, "ETHUSDT": 0.00008})
    assert result["score"] == 75
    assert "NEUTRAL" in result["signal"]


def test_negative_funding_is_washed_out():
    result = calculate_funding_regime({"BTCUSDT": -0.0003, "ETHUSDT": -0.0002})
    assert result["score"] == 80
    assert "WASHED OUT" in result["signal"]


def test_extreme_funding_is_euphoric():
    result = calculate_funding_regime({"BTCUSDT": 0.0009, "ETHUSDT": 0.0008})
    assert result["score"] == 10
    assert "EUPHORIC" in result["signal"]


def test_annualization_math():
    # +0.01%/8h -> 3 periods/day * 365 = ~10.95% annualized
    result = calculate_funding_regime({"A": 0.0001, "B": 0.0001})
    assert abs(result["annualized_pct"] - 10.95) < 0.01


@pytest.mark.parametrize(
    ("rate", "expected_score"),
    [
        (-0.00010, 80),
        (-0.000099, 65),
        (-0.000001, 65),
        (0.0, 75),
        (0.00010, 75),
        (0.000101, 55),
        (0.00030, 55),
        (0.000301, 30),
        (0.00060, 30),
        (0.000601, 10),
    ],
)
def test_funding_band_boundaries(rate, expected_score):
    result = calculate_funding_regime({"A": rate, "B": rate})
    assert result["score"] == expected_score


def test_extreme_finite_funding_never_produces_non_finite_output():
    """Finite inputs must not turn into Infinity during averaging/annualizing."""
    result = calculate_funding_regime({"A": 1e308, "B": 1e308})

    assert result["data_available"] is False
    assert "invalid" in result["signal"].lower()
    assert all(not isinstance(value, float) or math.isfinite(value) for value in result.values())
