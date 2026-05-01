#!/usr/bin/env python3
"""
Tests for FMP stable/v3 endpoint fallback in canslim-screener.

Tier A (4): Fallback logic
Tier B (4): Response normalization
Tier B+ (2): Shape validation
Caller regression (2): screen_canslim.py behavior on failure
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_client():
    """Create FMPClient with a fake API key."""
    with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}):  # pragma: allowlist secret
        from fmp_client import FMPClient

        client = FMPClient(api_key="test_key")
    return client


def _mock_response(status_code=200, json_data=None, text=""):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Tier A — Fallback logic (4 tests)
# ---------------------------------------------------------------------------


class TestFallbackLogic:
    """Verify stable-first, v3-fallback behavior."""

    def test_quote_stable_success(self):
        """Stable 200 returns data; v3 is never called."""
        client = _make_client()
        stable_resp = _mock_response(200, [{"symbol": "^GSPC", "price": 5000}])

        call_count = {"n": 0}

        def fake_get(url, params=None, timeout=30):
            call_count["n"] += 1
            if "stable" in url:
                return stable_resp
            pytest.fail("v3 endpoint should not be called")

        client.session.get = fake_get
        result = client.get_quote("^GSPC")
        assert result == [{"symbol": "^GSPC", "price": 5000}]
        assert call_count["n"] == 1

    def test_quote_stable_403_falls_back_to_v3(self):
        """Stable 403 → v3 200 → returns v3 data."""
        client = _make_client()
        stable_resp = _mock_response(403, None, "Forbidden")
        v3_resp = _mock_response(200, [{"symbol": "^GSPC", "price": 5100}])

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_quote("^GSPC")
        assert result == [{"symbol": "^GSPC", "price": 5100}]

    def test_quote_both_fail(self):
        """Both endpoints 403 → returns None."""
        client = _make_client()
        resp_403 = _mock_response(403, None, "Forbidden")

        client.session.get = MagicMock(return_value=resp_403)
        result = client.get_quote("^GSPC")
        assert result is None

    def test_historical_fallback_to_v3(self):
        """Stable 403 → v3 200 → returns v3 historical data."""
        client = _make_client()
        stable_resp = _mock_response(403, None, "Forbidden")
        v3_data = {"symbol": "^GSPC", "historical": [{"date": "2026-03-20", "close": 5000}]}
        v3_resp = _mock_response(200, v3_data)

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_historical_prices("^GSPC", days=80)
        assert result is not None
        assert "historical" in result
        assert result["historical"][0]["close"] == 5000


# ---------------------------------------------------------------------------
# Tier B — Response normalization (4 tests)
# ---------------------------------------------------------------------------


class TestResponseNormalization:
    """Verify response shape handling for stable vs v3 formats."""

    def test_historical_stable_v3_format_passthrough(self):
        """Stable returns v3-like {"historical": [...]} → returned as-is."""
        client = _make_client()
        data = {"symbol": "^GSPC", "historical": [{"date": "2026-03-20", "close": 5000}]}
        resp = _mock_response(200, data)
        client.session.get = MagicMock(return_value=resp)

        result = client.get_historical_prices("^GSPC", days=80)
        assert result == data

    def test_historical_stable_batch_format_exact_match(self):
        """Stable returns historicalStockList with matching symbol → normalized."""
        client = _make_client()
        batch_data = {
            "historicalStockList": [
                {
                    "symbol": "^GSPC",
                    "historical": [{"date": "2026-03-20", "close": 5000}],
                }
            ]
        }
        resp = _mock_response(200, batch_data)
        client.session.get = MagicMock(return_value=resp)

        result = client.get_historical_prices("^GSPC", days=80)
        assert result is not None
        assert result["symbol"] == "^GSPC"
        assert result["historical"] == [{"date": "2026-03-20", "close": 5000}]

    def test_historical_stable_batch_no_match_falls_back_to_v3(self):
        """Stable batch has wrong symbol → continue to v3 → v3 200."""
        client = _make_client()
        batch_data = {"historicalStockList": [{"symbol": "SPY", "historical": [{"close": 500}]}]}
        stable_resp = _mock_response(200, batch_data)
        v3_data = {"symbol": "^GSPC", "historical": [{"close": 5000}]}
        v3_resp = _mock_response(200, v3_data)

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_historical_prices("^GSPC", days=80)
        assert result is not None
        assert result["historical"][0]["close"] == 5000

    def test_historical_batch_no_match_returns_none_when_v3_also_fails(self):
        """Stable batch no match + v3 403 → returns None."""
        client = _make_client()
        batch_data = {"historicalStockList": [{"symbol": "SPY", "historical": [{"close": 500}]}]}
        stable_resp = _mock_response(200, batch_data)
        v3_resp = _mock_response(403, None, "Forbidden")

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_historical_prices("^GSPC", days=80)
        assert result is None


# ---------------------------------------------------------------------------
# Tier B+ — Shape validation (2 tests)
# ---------------------------------------------------------------------------


class TestShapeValidation:
    """Reject truthy-but-wrong-shape responses."""

    def test_quote_rejects_non_list_response(self):
        """Stable returns truthy dict → skipped, falls back to v3."""
        client = _make_client()
        error_data = {"Error Message": "Invalid API KEY"}
        stable_resp = _mock_response(200, error_data)
        v3_data = [{"symbol": "^GSPC", "price": 5000}]
        v3_resp = _mock_response(200, v3_data)

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_quote("^GSPC")
        assert result == v3_data

    def test_historical_rejects_non_dict_response(self):
        """Stable returns truthy list → skipped, falls back to v3."""
        client = _make_client()
        stable_resp = _mock_response(200, [1, 2, 3])
        v3_data = {"symbol": "^GSPC", "historical": [{"close": 5000}]}
        v3_resp = _mock_response(200, v3_data)

        def fake_get(url, params=None, timeout=30):
            if "stable" in url:
                return stable_resp
            return v3_resp

        client.session.get = fake_get
        result = client.get_historical_prices("^GSPC", days=80)
        assert result == v3_data


# ---------------------------------------------------------------------------
# Symbol mismatch protection (3 tests)
# ---------------------------------------------------------------------------


class TestSymbolMismatch:
    """Reject responses where returned symbol doesn't match the request."""

    def test_quote_symbol_mismatch_falls_back(self):
        """Single-symbol quote returning wrong symbol is rejected."""
        client = _make_client()
        wrong = _mock_response(200, [{"symbol": "SPY", "price": 500.0}])
        correct = _mock_response(200, [{"symbol": "^GSPC", "price": 5000.0}])
        client.session.get = MagicMock(side_effect=[wrong, correct])

        result = client.get_quote("^GSPC")
        assert result == [{"symbol": "^GSPC", "price": 5000.0}]
        assert client.session.get.call_count == 2

    def test_historical_symbol_mismatch_falls_back(self):
        """Single-symbol historical returning wrong symbol is rejected."""
        client = _make_client()
        wrong = _mock_response(200, {"symbol": "SPY", "historical": [{"close": 500}]})
        correct = _mock_response(200, {"symbol": "^GSPC", "historical": [{"close": 5000}]})
        client.session.get = MagicMock(side_effect=[wrong, correct])

        result = client.get_historical_prices("^GSPC", days=80)
        assert result["symbol"] == "^GSPC"
        assert client.session.get.call_count == 2

    def test_batch_quote_skips_symbol_check(self):
        """Multi-symbol (batch) quote does not apply symbol mismatch check."""
        client = _make_client()
        batch_data = [{"symbol": "^GSPC", "price": 5000}, {"symbol": "^VIX", "price": 20}]
        resp = _mock_response(200, batch_data)
        client.session.get = MagicMock(return_value=resp)

        result = client.get_quote("^GSPC,^VIX")
        assert result == batch_data
        assert client.session.get.call_count == 1


# ---------------------------------------------------------------------------
# Caller regression (2 tests)
# ---------------------------------------------------------------------------


class TestCallerRegression:
    """Verify screen_canslim.py behavior when FMP endpoints fail."""

    def test_canslim_exits_on_quote_failure(self):
        """get_quote("^GSPC") → None causes sys.exit(1)."""
        with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}):  # pragma: allowlist secret
            from fmp_client import FMPClient

            with patch.object(FMPClient, "get_quote", return_value=None):
                with patch("sys.argv", ["screen_canslim.py", "--max-candidates", "1"]):
                    import screen_canslim

                    with pytest.raises(SystemExit) as exc_info:
                        screen_canslim.main()
                    assert exc_info.value.code == 1

    def test_canslim_continues_on_historical_failure(self, capsys):
        """get_historical_prices("^GSPC") → None prints EMA fallback warning and continues."""
        with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}):  # pragma: allowlist secret
            from fmp_client import FMPClient

            mock_quote = [
                {
                    "symbol": "^GSPC",
                    "price": 5000.0,
                    "yearHigh": 5200.0,
                    "yearLow": 4200.0,
                    "changesPercentage": 0.5,
                }
            ]
            mock_vix = [{"symbol": "^VIX", "price": 15.0}]

            def mock_get_quote(symbols):
                if "^GSPC" in symbols and "^VIX" not in symbols:
                    return mock_quote
                if "^VIX" in symbols:
                    return mock_vix
                return mock_quote

            with (
                patch.object(FMPClient, "get_quote", side_effect=mock_get_quote),
                patch.object(FMPClient, "get_historical_prices", return_value=None),
                patch.object(FMPClient, "get_income_statement", return_value=None),
                patch.object(FMPClient, "get_profile", return_value=None),
                patch.object(FMPClient, "get_institutional_holders", return_value=None),
                patch(
                    "sys.argv", ["screen_canslim.py", "--max-candidates", "1", "--universe", "AAPL"]
                ),
            ):
                import screen_canslim

                # Should NOT raise SystemExit — historical failure is non-fatal
                try:
                    screen_canslim.main()
                except SystemExit:
                    pytest.fail("screen_canslim.main() should not exit when historical prices fail")

            captured = capsys.readouterr()
            assert "EMA fallback" in captured.out or "historical data unavailable" in captured.out


class TestEODFlatListSuccess:
    """Issue #64: stable EOD flat list -> public method success (regression)."""

    @patch("fmp_client.requests.Session")
    def test_get_historical_prices_normalizes_flat_list(self, mock_session_class):
        """Flat list response from new EOD endpoint -> dict contract preserved."""
        mock_session = MagicMock()
        mock_session.get.return_value = _mock_response(
            200,
            [
                {
                    "symbol": "SPY",
                    "date": "2026-04-29",
                    "open": 500.0,
                    "high": 502.0,
                    "low": 499.0,
                    "close": 501.0,
                    "volume": 1_000_000,
                },
                {
                    "symbol": "SPY",
                    "date": "2026-04-28",
                    "open": 498.0,
                    "high": 501.0,
                    "low": 497.0,
                    "close": 500.0,
                    "volume": 1_100_000,
                },
            ],
        )
        mock_session_class.return_value = mock_session

        client = _make_client()
        client.session = mock_session
        client.max_retries = 0

        result = client.get_historical_prices("SPY", days=2)
        assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
        assert result["symbol"] == "SPY"
        assert len(result["historical"]) == 2
        assert result["historical"][0]["close"] == 501.0

        # URL regression: must hit /historical-price-eod/full with from/to (not timeseries)
        first_call = mock_session.get.call_args_list[0]
        url = first_call[0][0]
        params = first_call[1]["params"]
        assert "historical-price-eod/full" in url
        assert "from" in params and "to" in params
        assert "timeseries" not in params
