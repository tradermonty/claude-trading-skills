"""Tests for etf_scanner field-level merge logic."""

from unittest.mock import patch, MagicMock
from etf_scanner import ETFScanner


class TestBatchStockMetricsFieldMerge:
    """Test that FMP results with PE but missing RSI trigger yfinance for RSI only."""

    def test_pe_only_triggers_rsi_fallback(self):
        """When FMP returns PE but not RSI, yfinance should fill RSI."""
        scanner = ETFScanner(fmp_api_key="test_key")

        # Mock FMP to return PE but not RSI
        fmp_results = [
            {"symbol": "AAPL", "rsi_14": None, "dist_from_52w_high": None,
             "dist_from_52w_low": None, "pe_ratio": 25.0},
        ]

        # Mock yfinance to return RSI
        yf_results = [
            {"symbol": "AAPL", "rsi_14": 55.0, "dist_from_52w_high": 0.1,
             "dist_from_52w_low": 0.3, "pe_ratio": 24.0},
        ]

        with patch.object(scanner, '_batch_stock_metrics_fmp', return_value=fmp_results), \
             patch.object(scanner, '_batch_stock_metrics_yfinance', return_value=yf_results):
            results = scanner.batch_stock_metrics(["AAPL"])

        assert len(results) == 1
        r = results[0]
        # PE from FMP should be preserved
        assert r["pe_ratio"] == 25.0
        # RSI should come from yfinance
        assert r["rsi_14"] == 55.0

    def test_all_fields_present_no_yfinance(self):
        """When FMP returns all fields, yfinance should not be called."""
        scanner = ETFScanner(fmp_api_key="test_key")

        fmp_results = [
            {"symbol": "AAPL", "rsi_14": 60.0, "dist_from_52w_high": 0.05,
             "dist_from_52w_low": 0.3, "pe_ratio": 25.0},
        ]

        with patch.object(scanner, '_batch_stock_metrics_fmp', return_value=fmp_results) as fmp_mock, \
             patch.object(scanner, '_batch_stock_metrics_yfinance') as yf_mock:
            results = scanner.batch_stock_metrics(["AAPL"])
            # yfinance should not be called when all fields present
            yf_mock.assert_not_called()

        assert results[0]["pe_ratio"] == 25.0
        assert results[0]["rsi_14"] == 60.0

    def test_complete_missing_uses_yfinance(self):
        """When FMP returns nothing useful, full yfinance fallback."""
        scanner = ETFScanner(fmp_api_key="test_key")

        fmp_results = [
            {"symbol": "XYZ", "rsi_14": None, "dist_from_52w_high": None,
             "dist_from_52w_low": None, "pe_ratio": None},
        ]

        yf_results = [
            {"symbol": "XYZ", "rsi_14": 45.0, "dist_from_52w_high": 0.2,
             "dist_from_52w_low": 0.15, "pe_ratio": 18.0},
        ]

        with patch.object(scanner, '_batch_stock_metrics_fmp', return_value=fmp_results), \
             patch.object(scanner, '_batch_stock_metrics_yfinance', return_value=yf_results):
            results = scanner.batch_stock_metrics(["XYZ"])

        assert results[0]["rsi_14"] == 45.0
        assert results[0]["pe_ratio"] == 18.0

    def test_stats_stock_context_set(self):
        """batch_stock_metrics should set context to 'stock'."""
        scanner = ETFScanner(fmp_api_key="test_key")

        fmp_stock_results = [
            {"symbol": "AAPL", "rsi_14": 60.0, "dist_from_52w_high": 0.05,
             "dist_from_52w_low": 0.3, "pe_ratio": 25.0},
        ]

        with patch.object(scanner, '_batch_stock_metrics_fmp', return_value=fmp_stock_results):
            scanner.batch_stock_metrics(["AAPL"])

        # After batch_stock_metrics, context should be "stock"
        assert scanner._current_stats_context == "stock"
        # Manually increment to verify context routes correctly
        scanner._stats["stock"]["fmp_calls"] = 5
        scanner._stats["etf"]["fmp_calls"] = 3
        stats = scanner.backend_stats()
        assert stats["fmp_calls"] == 8  # flat total
        assert stats["stock"]["fmp_calls"] == 5
        assert stats["etf"]["fmp_calls"] == 3

    def test_stats_etf_context_set(self):
        """batch_etf_volume_ratios should set context to 'etf'."""
        scanner = ETFScanner(fmp_api_key="test_key")

        fmp_etf_results = {
            "XLK": {"symbol": "XLK", "vol_20d": 1000.0, "vol_60d": 800.0, "vol_ratio": 1.25},
        }

        with patch.object(scanner, '_batch_etf_volume_ratios_fmp', return_value=fmp_etf_results):
            scanner.batch_etf_volume_ratios(["XLK"])

        # After batch_etf_volume_ratios, context should be "etf"
        assert scanner._current_stats_context == "etf"

    def test_stats_flat_backward_compat(self):
        """backend_stats() should include flat totals for backward compatibility."""
        scanner = ETFScanner()
        stats = scanner.backend_stats()
        # Flat keys should exist
        assert "fmp_calls" in stats
        assert "fmp_failures" in stats
        assert "yf_calls" in stats
        assert "yf_fallbacks" in stats
        # Nested keys should exist
        assert "stock" in stats
        assert "etf" in stats
        # All should be zero initially
        assert stats["fmp_calls"] == 0
        assert stats["stock"]["fmp_calls"] == 0
        assert stats["etf"]["fmp_calls"] == 0

    def test_field_merge_preserves_fmp_values(self):
        """Field-level merge should not overwrite existing FMP values with yfinance."""
        scanner = ETFScanner(fmp_api_key="test_key")

        fmp_results = [
            {"symbol": "AAPL", "rsi_14": None, "dist_from_52w_high": 0.05,
             "dist_from_52w_low": None, "pe_ratio": 25.0},
        ]

        yf_results = [
            {"symbol": "AAPL", "rsi_14": 55.0, "dist_from_52w_high": 0.08,
             "dist_from_52w_low": 0.3, "pe_ratio": 24.0},
        ]

        with patch.object(scanner, '_batch_stock_metrics_fmp', return_value=fmp_results), \
             patch.object(scanner, '_batch_stock_metrics_yfinance', return_value=yf_results):
            results = scanner.batch_stock_metrics(["AAPL"])

        r = results[0]
        # FMP values should be preserved
        assert r["pe_ratio"] == 25.0
        assert r["dist_from_52w_high"] == 0.05
        # yfinance fills only None fields
        assert r["rsi_14"] == 55.0
        assert r["dist_from_52w_low"] == 0.3
