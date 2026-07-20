"""Tests for Component 3: BTC Dominance Regime Calculator."""

from calculators.dominance_calculator import calculate_dominance_regime


def _dom_series(start: float, end: float, n: int = 40) -> list:
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def test_insufficient_history_flags_unavailable():
    result = calculate_dominance_regime([55.0] * 10, btc_trend_up=True)
    assert result["data_available"] is False


def test_alt_rotation_regime_scores_highest():
    result = calculate_dominance_regime(_dom_series(58, 52), btc_trend_up=True)
    assert result["score"] >= 85
    assert "ALT ROTATION" in result["signal"]


def test_btc_led_regime_is_constructive():
    result = calculate_dominance_regime(_dom_series(52, 58), btc_trend_up=True)
    assert 60 <= result["score"] <= 70
    assert "BTC-LED" in result["signal"]


def test_derisking_regime_scores_lowest():
    result = calculate_dominance_regime(_dom_series(58, 52), btc_trend_up=False)
    assert result["score"] <= 15
    assert "DE-RISKING" in result["signal"]


def test_washout_extreme_contrarian_bump():
    defensive = calculate_dominance_regime(_dom_series(58, 61), btc_trend_up=False)
    washout = calculate_dominance_regime(_dom_series(60, 64), btc_trend_up=False)
    assert washout["score"] == defensive["score"] + 5
    assert "washout" in washout["signal"]


def test_flat_dominance_uses_flat_branch():
    result = calculate_dominance_regime([55.0] * 40, btc_trend_up=True)
    assert result["direction"] == "flat"
    assert result["score"] == 75
