"""Tests for Sentiment Calculator"""

from calculators.sentiment_calculator import calculate_sentiment


class TestSentimentMissingData:
    """Test missing data handling."""

    def test_all_none_returns_50(self):
        """All inputs None → score=50, data_available=False."""
        result = calculate_sentiment()
        assert result["score"] == 50
        assert result["data_available"] is False
        assert "NO DATA" in result["signal"]

    def test_partial_data_is_available(self):
        """At least one input → data_available=True."""
        result = calculate_sentiment(vix_level=15.0)
        assert result["data_available"] is True

    def test_vix_only(self):
        result = calculate_sentiment(vix_level=15.0)
        assert result["score"] == 10  # VIX 15 → +10pt

    def test_put_call_only(self):
        result = calculate_sentiment(put_call_ratio=0.65)
        assert result["score"] == 30  # PC < 0.70 → +30pt


class TestSentimentScoring:
    """Boundary tests for sentiment scoring."""

    def test_extreme_complacency(self):
        """Low VIX + low P/C + steep contango = max score."""
        result = calculate_sentiment(
            vix_level=11.0,
            put_call_ratio=0.55,
            vix_term_structure="steep_contango",
        )
        assert result["score"] == 100  # 30+40+30=100

    def test_high_fear(self):
        """High VIX + high P/C + backwardation = 0 or negative."""
        result = calculate_sentiment(
            vix_level=30.0,
            put_call_ratio=0.95,
            vix_term_structure="backwardation",
        )
        assert result["score"] == 0  # -10+0+(-10) = -20 → clamped to 0

    def test_moderate_sentiment(self):
        result = calculate_sentiment(
            vix_level=15.0,
            put_call_ratio=0.75,
            vix_term_structure="contango",
        )
        # VIX 15→10, PC 0.75→15, contango→15 = 40
        assert result["score"] == 40

    def test_margin_debt_not_scored(self):
        """Margin debt is context only, should not affect score."""
        without = calculate_sentiment(vix_level=15.0)
        with_margin = calculate_sentiment(vix_level=15.0, margin_debt_yoy_pct=40.0)
        assert without["score"] == with_margin["score"]
