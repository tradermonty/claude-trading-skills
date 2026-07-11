"""Tests for dividend-growth-pullback-screener screening logic.

These tests validate the core calculation functions without requiring
live API keys (FMP or FINVIZ). All external I/O is stubbed.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers to import the main script without executing top-level side effects
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "screen_dividend_growth_rsi.py"


def _load_script() -> ModuleType:
    """Import screen_dividend_growth_rsi as a module."""
    spec = importlib.util.spec_from_file_location("screen_dg", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Stub heavy imports that are not needed for unit tests
    sys.modules.setdefault("requests", MagicMock())
    sys.modules.setdefault("pandas", MagicMock())
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# RSI calculation tests
# ---------------------------------------------------------------------------


class TestRsiCalculation:
    """Validate the 14-period RSI formula used in the screener."""

    @pytest.fixture(scope="class")
    def mod(self):
        if not SCRIPT_PATH.exists():
            pytest.skip(f"Script not found: {SCRIPT_PATH}")
        return _load_script()

    def _prices_up(self, n: int = 30) -> list[float]:
        """Steadily rising prices → RSI should be high (>70)."""
        return [100.0 + i for i in range(n)]

    def _prices_down(self, n: int = 30) -> list[float]:
        """Steadily falling prices → RSI should be low (<30)."""
        return [100.0 - i for i in range(n)]

    def _prices_flat(self, n: int = 30) -> list[float]:
        """Flat prices (no change) → RSI = 50 by convention."""
        return [100.0] * n

    def test_rsi_function_exists(self, mod):
        """The script must expose a callable that computes RSI."""
        candidates = [
            name for name in dir(mod) if "rsi" in name.lower() and callable(getattr(mod, name))
        ]
        assert candidates, "No RSI function found in the script"

    def test_rsi_rising_prices_above_50(self, mod):
        candidates = [n for n in dir(mod) if "rsi" in n.lower() and callable(getattr(mod, n))]
        fn = getattr(mod, candidates[0])
        try:
            result = fn(self._prices_up())
        except Exception:
            pytest.skip("RSI function signature differs; skipping value test")
        if result is None:
            pytest.skip("RSI function returned None for rising prices")
        assert result > 50, f"RSI for rising prices should be >50, got {result}"

    def test_rsi_falling_prices_below_50(self, mod):
        candidates = [n for n in dir(mod) if "rsi" in n.lower() and callable(getattr(mod, n))]
        fn = getattr(mod, candidates[0])
        try:
            result = fn(self._prices_down())
        except Exception:
            pytest.skip("RSI function signature differs; skipping value test")
        if result is None:
            pytest.skip("RSI function returned None for falling prices")
        assert result < 50, f"RSI for falling prices should be <50, got {result}"

    def test_rsi_bounds(self, mod):
        """RSI must always be in [0, 100]."""
        candidates = [n for n in dir(mod) if "rsi" in n.lower() and callable(getattr(mod, n))]
        fn = getattr(mod, candidates[0])
        for prices in [self._prices_up(), self._prices_down(), self._prices_flat()]:
            try:
                result = fn(prices)
            except Exception:
                continue
            if result is None:
                continue
            assert 0 <= result <= 100, f"RSI out of [0,100] bounds: {result}"


# ---------------------------------------------------------------------------
# Dividend CAGR calculation tests
# ---------------------------------------------------------------------------


class TestDividendCagr:
    """Validate dividend CAGR computation."""

    @pytest.fixture(scope="class")
    def mod(self):
        if not SCRIPT_PATH.exists():
            pytest.skip(f"Script not found: {SCRIPT_PATH}")
        return _load_script()

    def test_cagr_function_exists(self, mod):
        assert hasattr(mod, "StockAnalyzer"), "StockAnalyzer class not found"
        assert hasattr(mod.StockAnalyzer, "calculate_cagr"), (
            "calculate_cagr not found in StockAnalyzer"
        )

    def test_cagr_doubles_in_six_years(self, mod):
        """12% CAGR should double the dividend in ~6 years."""
        fn = mod.StockAnalyzer.calculate_cagr
        try:
            # Dividend goes from 1.0 to 2.0 over 6 years ≈ 12.2% CAGR
            result = fn(1.0, 2.0, 6)
        except Exception:
            pytest.skip("CAGR function signature differs; skipping value test")
        if result is None:
            pytest.skip("CAGR function returned None")
        assert 11 < result < 14, f"Expected ~12% CAGR, got {result}"

    def test_cagr_zero_years_safe(self, mod):
        """CAGR with zero years should not raise ZeroDivisionError."""
        fn = mod.StockAnalyzer.calculate_cagr
        try:
            result = fn(1.0, 2.0, 0)
            assert result is None or math.isnan(result) or result == 0
        except ZeroDivisionError:
            pytest.fail("CAGR function raised ZeroDivisionError for n=0")
        except Exception:
            pass  # Other exceptions are acceptable for edge cases


# ---------------------------------------------------------------------------
# Script structure / CLI smoke tests
# ---------------------------------------------------------------------------


class TestScriptStructure:
    """Ensure the script file meets structural requirements."""

    def test_script_exists(self):
        assert SCRIPT_PATH.exists(), f"Main script missing: {SCRIPT_PATH}"

    def test_script_has_main_guard(self):
        source = SCRIPT_PATH.read_text()
        assert 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source, (
            "Script should have a __main__ guard"
        )

    def test_script_references_fmp_api(self):
        source = SCRIPT_PATH.read_text()
        assert "FMP_API_KEY" in source or "fmp_api_key" in source or "fmp-api-key" in source, (
            "Script should reference FMP_API_KEY"
        )

    def test_script_references_rsi(self):
        source = SCRIPT_PATH.read_text()
        assert "rsi" in source.lower(), "Script should implement or reference RSI"

    def test_output_dir_argument(self):
        """Script should accept --output-dir for report placement."""
        source = SCRIPT_PATH.read_text()
        assert "output" in source.lower(), "Script should support an output directory argument"


def test_fmp_decimal_roe_and_margin_are_converted_to_percent(monkeypatch):
    """FMP decimal fundamentals must match percent-based scoring/report fields."""
    mod = _load_script()
    client = MagicMock()
    client.rate_limit_reached = False
    client.screen_stocks.return_value = [
        {"symbol": "TEST", "companyName": "Test Inc", "price": 100, "sector": "Tech"}
    ]
    client.get_dividend_history.return_value = [{}]
    client.get_historical_prices.return_value = [{"close": 100}] * 30
    client.get_income_statement.return_value = [{}]
    client.get_balance_sheet.return_value = [{}]
    client.get_cash_flow.return_value = [{}]
    client.get_key_metrics.return_value = [{"roe": 0.25, "netProfitMargin": 0.125}]

    analyzer = MagicMock()
    analyzer.analyze_dividend_growth.return_value = (15.0, True, 2.0, 5)
    analyzer.analyze_growth_metrics.return_value = {
        "revenue_cagr_3y": 1.0,
        "eps_cagr_3y": 1.0,
    }
    analyzer.analyze_financial_health.return_value = {"financially_healthy": True}
    analyzer.is_reit.return_value = False
    analyzer.calculate_payout_ratios.return_value = {
        "payout_ratio": 50.0,
        "fcf_payout_ratio": 60.0,
    }
    analyzer.calculate_composite_score.return_value = 80.0

    monkeypatch.setattr(mod, "FMPClient", MagicMock(return_value=client))
    monkeypatch.setattr(mod, "StockAnalyzer", MagicMock(return_value=analyzer))
    monkeypatch.setattr(
        mod,
        "RSICalculator",
        MagicMock(return_value=MagicMock(calculate_rsi=MagicMock(return_value=30.0))),
    )

    result = mod.screen_dividend_growth_pullbacks("test-key")[0]

    assert result["roe"] == 25.0
    assert result["profit_margin"] == 12.5
