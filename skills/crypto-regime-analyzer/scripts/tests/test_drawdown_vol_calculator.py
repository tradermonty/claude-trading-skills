"""Tests for Component 5: Drawdown & Volatility Position Calculator."""

from calculators.drawdown_vol_calculator import calculate_drawdown_vol


def test_insufficient_history_flags_unavailable(trending_series):
    result = calculate_drawdown_vol(trending_series(n=100))
    assert result["data_available"] is False


def test_near_highs_scores_high(trending_series):
    result = calculate_drawdown_vol(trending_series(n=400, daily_pct=0.2))
    assert result["data_available"] is True
    assert result["drawdown_pct"] < 5
    assert result["score"] >= 75


def test_deep_drawdown_scores_low(trending_series):
    closes = trending_series(n=400, daily_pct=0.2)
    peak = closes[-1]
    closes.extend([peak * (1 - 0.006 * i) for i in range(1, 101)])  # ~60% dd
    result = calculate_drawdown_vol(closes)
    assert result["drawdown_pct"] > 50
    assert result["score"] <= 35


def test_capitulation_floor_holds(trending_series):
    # >65% drawdown with a violent final leg -> elevated vol, floor at 15.
    closes = trending_series(n=400, daily_pct=0.2)
    peak = closes[-1]
    price = peak
    for i in range(120):
        price *= 0.985 if i < 100 else 0.93  # accelerating crash at the end
        closes.append(price)
    result = calculate_drawdown_vol(closes)
    assert result["drawdown_pct"] > 65
    assert result["score"] >= 15


def test_score_within_bounds(trending_series):
    for pct in (0.5, 0.0, -0.5):
        result = calculate_drawdown_vol(trending_series(n=400, daily_pct=pct))
        if result["data_available"]:
            assert 0 <= result["score"] <= 100
