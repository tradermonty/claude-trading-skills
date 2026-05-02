"""Tests for calculators.parabolic_score_calculator."""

from parabolic_score_calculator import (
    calculate_component_scores,
    score_liquidity,
    score_ma_extension,
    score_range_expansion,
    score_volume_climax,
)


class TestSubScores:
    def test_ma_extension_high_when_far_from_20dma(self):
        score = score_ma_extension({"ext_20dma_pct": 100.0, "ext_20dma_atr": 8.0})
        assert score >= 70

    def test_ma_extension_zero_when_at_ma(self):
        score = score_ma_extension({"ext_20dma_pct": 0.0, "ext_20dma_atr": 0.0})
        assert score == 0

    def test_volume_climax_clamps(self):
        assert score_volume_climax(10.0) == 100
        assert score_volume_climax(1.0) == 0

    def test_range_expansion_at_threshold(self):
        # ratio 1.2 → score 0; ratio 3.0 → score 100
        assert score_range_expansion(1.2) == 0
        assert score_range_expansion(3.0) == 100

    def test_liquidity_scales_to_100(self):
        assert score_liquidity(10.0) == 100
        assert score_liquidity(0.0) == 0


class TestAggregation:
    def test_returns_components_and_raw_metrics(self, parabolic_bars_chrono):
        opens = [b["open"] for b in parabolic_bars_chrono]
        highs = [b["high"] for b in parabolic_bars_chrono]
        lows = [b["low"] for b in parabolic_bars_chrono]
        closes = [b["close"] for b in parabolic_bars_chrono]
        volumes = [b["volume"] for b in parabolic_bars_chrono]
        out = calculate_component_scores(
            closes=closes, opens=opens, highs=highs, lows=lows, volumes=volumes
        )
        assert set(out["components"].keys()) == {
            "ma_extension",
            "acceleration",
            "volume_climax",
            "range_expansion",
            "liquidity",
        }
        # Parabolic fixture should score high on MA extension
        assert out["components"]["ma_extension"] > 50
