"""Tests for Leading Stock Calculator"""

from calculators.leading_stock_calculator import (
    _evaluate_etf,
    calculate_leading_stock_health,
)


class TestEvaluateETF:
    """Test individual ETF evaluation."""

    def test_near_highs_healthy(self):
        quote = {"price": 100, "yearHigh": 102, "yearLow": 80}
        history = [{"close": 100 - i * 0.1, "volume": 1000000} for i in range(60)]
        result = _evaluate_etf("TEST", quote, history)
        assert result["deterioration_score"] <= 20

    def test_deep_correction(self):
        quote = {"price": 70, "yearHigh": 100, "yearLow": 65}
        history = [{"close": 70 + i * 0.3, "volume": 1000000} for i in range(60)]
        result = _evaluate_etf("TEST", quote, history)
        assert result["deterioration_score"] >= 30


class TestCalculateLeadingStockHealth:
    """Test composite leading stock calculation."""

    def test_no_data_returns_50(self):
        """No quotes → score 50 (neutral), data_available=False."""
        result = calculate_leading_stock_health({}, {})
        assert result["score"] == 50
        assert result["etfs_evaluated"] == 0
        assert result["data_available"] is False

    def test_healthy_leaders(self):
        quotes = {}
        historical = {}
        for sym in ["ARKK", "WCLD", "IGV"]:
            quotes[sym] = {"price": 100, "yearHigh": 102, "yearLow": 80}
            historical[sym] = [{"close": 100 - i * 0.05, "volume": 1000000} for i in range(60)]
        result = calculate_leading_stock_health(quotes, historical)
        assert result["score"] <= 30  # Healthy
        assert result["data_available"] is True

    def test_amplification_at_60pct(self):
        """60%+ ETFs deteriorating triggers 1.3x amplification."""
        quotes = {}
        historical = {}
        # All ETFs in deep correction: -30% from high, below 50DMA
        for sym in ["ARKK", "WCLD", "IGV", "XBI", "SOXX", "SMH", "KWEB", "TAN"]:
            quotes[sym] = {"price": 70, "yearHigh": 100, "yearLow": 60}
            # Create declining history so price is well below MAs
            historical[sym] = [
                {"close": 70 + i * 0.5, "high": 72 + i * 0.5, "volume": 1000000} for i in range(60)
            ]
        result = calculate_leading_stock_health(quotes, historical)
        assert result["amplified"] is True
