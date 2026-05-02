"""Tests for calculators.ma_extension_calculator."""

from ma_extension_calculator import calculate_ma_extension


def _close_only(closes):
    return calculate_ma_extension(closes=closes)


class TestMAExtensionPercent:
    def test_above_ma_returns_positive(self):
        closes = [50.0] * 19 + [55.0]  # 20 values, last 5 above
        out = _close_only(closes)
        # 20DMA = (50*19 + 55) / 20 = 50.25; ext% = (55-50.25)/50.25 ~= 9.45%
        assert out["ext_20dma_pct"] is not None
        assert out["ext_20dma_pct"] > 0

    def test_below_ma_returns_negative(self):
        closes = [50.0] * 19 + [40.0]
        out = _close_only(closes)
        assert out["ext_20dma_pct"] is not None
        assert out["ext_20dma_pct"] < 0

    def test_insufficient_history_returns_none(self):
        closes = [50.0] * 5  # < 10 values for 10DMA
        out = _close_only(closes)
        assert out["dma_10"] is None
        assert out["ext_10dma_pct"] is None
        assert out["ext_20dma_atr"] is None


class TestATRUnits:
    def test_returns_atr_extension_when_highs_lows_provided(self, parabolic_bars_chrono):
        closes = [b["close"] for b in parabolic_bars_chrono]
        highs = [b["high"] for b in parabolic_bars_chrono]
        lows = [b["low"] for b in parabolic_bars_chrono]
        out = calculate_ma_extension(closes=closes, highs=highs, lows=lows)
        assert out["ext_20dma_atr"] is not None
        assert out["atr_14"] is not None
        # Parabolic series — close should be many ATR-units above 20DMA
        assert out["ext_20dma_atr"] > 4.0

    def test_omits_atr_when_no_highs(self):
        closes = [50.0] * 30
        out = calculate_ma_extension(closes=closes)
        assert out["ext_20dma_atr"] is None
        assert out["atr_14"] is None
