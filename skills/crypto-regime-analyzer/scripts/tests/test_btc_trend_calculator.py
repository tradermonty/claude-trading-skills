"""Tests for Component 1: BTC Trend Structure Calculator."""

from calculators.btc_trend_calculator import calculate_btc_trend


def test_insufficient_history_flags_unavailable():
    result = calculate_btc_trend([100.0] * 50)
    assert result["data_available"] is False
    assert result["score"] == 50


def test_slope_requires_full_200dma_window_at_20_day_lookback():
    assert calculate_btc_trend([100.0] * 219)["data_available"] is False
    assert calculate_btc_trend([100.0] * 220)["data_available"] is True


def test_bull_stack_scores_high(trending_series):
    result = calculate_btc_trend(trending_series(n=400, daily_pct=0.3))
    assert result["data_available"] is True
    assert result["score"] >= 90  # 90 base + rising 200DMA
    assert "BULL STACK" in result["signal"]
    assert result["ma200_rising"] is True


def test_bear_stack_scores_low(trending_series):
    result = calculate_btc_trend(trending_series(n=400, daily_pct=-0.3))
    assert result["score"] <= 15
    assert "BEAR STACK" in result["signal"]
    assert result["ma200_rising"] is False


def test_pullback_between_mas(trending_series):
    # Long uptrend, then a sharp pullback below the 50DMA but above 200DMA.
    closes = trending_series(n=400, daily_pct=0.4)
    closes[-1] = closes[-1] * 0.85
    result = calculate_btc_trend(closes)
    assert result["data_available"] is True
    assert 45 <= result["score"] <= 80
    assert "PULLBACK" in result["signal"] or "PRICE BELOW" in result["signal"]


def test_score_clamped_to_bounds(trending_series):
    up = calculate_btc_trend(trending_series(n=400, daily_pct=1.0))
    down = calculate_btc_trend(trending_series(n=400, daily_pct=-1.0))
    assert 0 <= down["score"] <= up["score"] <= 100


def test_flat_series_is_neutral_with_flat_long_term_average():
    result = calculate_btc_trend([100.0] * 220)

    assert result["score"] == 50
    assert "FLAT" in result["signal"]
    assert "200DMA flat" in result["signal"]
    assert "BEAR STACK" not in result["signal"]
    assert "watch" not in result["signal"]
