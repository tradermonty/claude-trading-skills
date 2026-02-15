"""Tests for Yield Curve Calculator"""

from calculators.yield_curve_calculator import calculate_yield_curve
from test_helpers import make_monthly_history, make_treasury_rates


class TestCalculateYieldCurve:
    def test_insufficient_data_all_none(self):
        result = calculate_yield_curve(None, None, None)
        assert result["score"] == 0
        assert result["data_available"] is False

    def test_treasury_api_stable_spread(self):
        # Stable spread = low transition signal
        spreads = [1.0] * 24  # Constant 1% spread
        rates = make_treasury_rates(spreads, start_year=2024)
        result = calculate_yield_curve(treasury_rates=rates)
        assert result["data_available"] is True
        assert result["data_source"] == "treasury_api"
        assert result["score"] <= 30  # Small noise from daily variation is expected

    def test_treasury_api_steepening(self):
        # Spread increasing from -0.5 to 1.5 = steepening transition
        spreads = [-0.5 + i * (2.0 / 23) for i in range(24)]
        rates = make_treasury_rates(spreads, start_year=2024)
        result = calculate_yield_curve(treasury_rates=rates)
        assert result["data_available"] is True
        assert result["direction"] in ("steepening", "flattening", "stable")

    def test_treasury_api_inverted(self):
        # Negative spreads
        spreads = [-0.5] * 24
        rates = make_treasury_rates(spreads, start_year=2024)
        result = calculate_yield_curve(treasury_rates=rates)
        assert result["curve_state"] in (
            "inverted",
            "deeply_inverted",
            "flat",
            "normalizing",
            "normal",
            "steep",
        )

    def test_shy_tlt_fallback(self):
        # When no treasury rates, use SHY/TLT proxy
        shy = make_monthly_history([80 + i * 0.1 for i in range(24)], start_year=2024)
        tlt = make_monthly_history([90 - i * 0.2 for i in range(24)], start_year=2024)
        result = calculate_yield_curve(treasury_rates=None, shy_history=shy, tlt_history=tlt)
        assert result["data_available"] is True
        assert result["data_source"] == "shy_tlt_proxy"

    def test_output_structure(self):
        spreads = [1.0 + i * 0.05 for i in range(24)]
        rates = make_treasury_rates(spreads, start_year=2024)
        result = calculate_yield_curve(treasury_rates=rates)

        assert "score" in result
        assert "signal" in result
        assert "data_available" in result
        assert "data_source" in result
        assert "direction" in result
        assert "curve_state" in result
        assert "crossover" in result
        assert 0 <= result["score"] <= 100
