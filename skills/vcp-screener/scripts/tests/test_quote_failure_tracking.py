"""Tests for free-tier FMP reliability patch:
- v3 legacy-403 triggers immediate endpoint disable (not threshold-based)
- per-symbol quote failures are recorded with correct category
- get_quote_failures() returns the full failure log
- _categorize_failure() maps status+body to the right category
"""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmp_client import FMPClient, _categorize_failure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LEGACY_403_BODY = '{"Error Message": "Legacy Endpoint : Due to Legacy endpoints being no longer supported"}'
PAID_402_BODY = "Premium Query Parameter: This value set for 'symbol' is not available under your current subscription"


def _make_response(status: int, body: str) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = body
    r.json.return_value = None  # won't be called for non-200
    return r


def _make_client() -> FMPClient:
    return FMPClient(api_key="test_key_placeholder")


# ---------------------------------------------------------------------------
# _categorize_failure
# ---------------------------------------------------------------------------

class TestCategorizFailure:
    def test_legacy_403(self):
        assert _categorize_failure(403, LEGACY_403_BODY) == "legacy_endpoint_retired"

    def test_paid_402(self):
        assert _categorize_failure(402, PAID_402_BODY) == "paid_tier_required"

    def test_premium_in_body_any_status(self):
        assert _categorize_failure(200, "Premium content") == "paid_tier_required"

    def test_404(self):
        assert _categorize_failure(404, "") == "symbol_not_found"

    def test_429(self):
        assert _categorize_failure(429, "") == "rate_limit_exceeded"

    def test_no_endpoint(self):
        assert _categorize_failure(0, "") == "no_endpoint_available"

    def test_generic_status(self):
        assert _categorize_failure(500, "") == "http_500"


# ---------------------------------------------------------------------------
# v3 immediate disable on Legacy 403
# ---------------------------------------------------------------------------

class TestLegacy403ImmediateDisable:
    def test_v3_disabled_after_single_legacy_403(self):
        """v3 endpoint must be disabled after the FIRST Legacy 403, not after threshold=3."""
        client = _make_client()
        v3_base = "https://financialmodelingprep.com/api/v3/quote"

        # Stable returns 402 (paid), v3 returns Legacy 403
        stable_resp = _make_response(402, PAID_402_BODY)
        v3_resp = _make_response(403, LEGACY_403_BODY)

        call_responses = [stable_resp, v3_resp]
        call_idx = [0]

        def fake_get(url, params=None, timeout=30):
            resp = call_responses[call_idx[0]]
            call_idx[0] += 1
            return resp

        client.session.get = fake_get

        result = client.get_quote("AAPL")

        assert result is None
        assert v3_base in client._disabled_endpoints, (
            "v3 should be immediately disabled after one Legacy 403"
        )
        assert client._endpoint_failures.get(v3_base, 0) == 0, (
            "failure counter should not be incremented for immediate-disable"
        )

    def test_v3_not_disabled_on_regular_403(self):
        """A non-Legacy 403 still goes through the normal threshold."""
        client = _make_client()
        v3_base = "https://financialmodelingprep.com/api/v3/quote"

        generic_403_resp = _make_response(403, '{"error": "Unauthorized"}')
        stable_resp = _make_response(402, PAID_402_BODY)

        call_responses = [stable_resp, generic_403_resp]
        call_idx = [0]

        def fake_get(url, params=None, timeout=30):
            resp = call_responses[call_idx[0] % len(call_responses)]
            call_idx[0] += 1
            return resp

        client.session.get = fake_get
        client.get_quote("AAPL")

        assert v3_base not in client._disabled_endpoints, (
            "v3 must NOT be immediately disabled for a non-Legacy 403"
        )
        assert client._endpoint_failures.get(v3_base, 0) == 1


# ---------------------------------------------------------------------------
# Per-symbol failure tracking
# ---------------------------------------------------------------------------

class TestQuoteFailureTracking:
    def _run_failed_quote(self, symbol: str, stable_status: int, stable_body: str) -> FMPClient:
        client = _make_client()

        def fake_get(url, params=None, timeout=30):
            r = MagicMock()
            r.status_code = stable_status
            r.text = stable_body
            r.json.return_value = None
            return r

        # Disable the v3 fallback so only stable is attempted
        v3_base = "https://financialmodelingprep.com/api/v3/quote"
        client._disabled_endpoints.add(v3_base)
        client.session.get = fake_get
        client.get_quote(symbol)
        return client

    def test_failure_recorded_on_402(self):
        client = self._run_failed_quote("AVGO", 402, PAID_402_BODY)
        failures = client.get_quote_failures()
        assert len(failures) == 1
        assert failures[0]["symbol"] == "AVGO"
        assert failures[0]["http_status"] == 402
        assert failures[0]["error_category"] == "paid_tier_required"

    def test_no_failure_on_success(self):
        client = _make_client()

        def fake_get(url, params=None, timeout=30):
            r = MagicMock()
            r.status_code = 200
            r.text = ""
            r.json.return_value = [{"symbol": "AAPL", "price": 300}]
            return r

        client.session.get = fake_get
        result = client.get_quote("AAPL")
        assert result is not None
        assert client.get_quote_failures() == []

    def test_multiple_failures_accumulated(self):
        client = _make_client()
        v3_base = "https://financialmodelingprep.com/api/v3/quote"
        client._disabled_endpoints.add(v3_base)

        def fake_get(url, params=None, timeout=30):
            r = MagicMock()
            r.status_code = 402
            r.text = PAID_402_BODY
            r.json.return_value = None
            return r

        client.session.get = fake_get
        client.get_quote("AVGO")
        client.get_quote("HD")
        client.get_quote("CAT")

        failures = client.get_quote_failures()
        assert len(failures) == 3
        symbols = [f["symbol"] for f in failures]
        assert "AVGO" in symbols
        assert "HD" in symbols
        assert "CAT" in symbols

    def test_get_quote_failures_returns_copy(self):
        """Mutating the returned list must not affect internal state."""
        client = _make_client()
        v3_base = "https://financialmodelingprep.com/api/v3/quote"
        client._disabled_endpoints.add(v3_base)

        def fake_get(url, params=None, timeout=30):
            r = MagicMock()
            r.status_code = 402
            r.text = PAID_402_BODY
            r.json.return_value = None
            return r

        client.session.get = fake_get
        client.get_quote("AVGO")
        returned = client.get_quote_failures()
        returned.clear()
        assert len(client.get_quote_failures()) == 1


# ---------------------------------------------------------------------------
# Historical endpoint must NOT record quote failures
# ---------------------------------------------------------------------------

class TestHistoricalDoesNotLogQuoteFailure:
    def test_historical_failure_not_in_quote_log(self):
        client = _make_client()

        def fake_get(url, params=None, timeout=30):
            r = MagicMock()
            r.status_code = 403
            r.text = LEGACY_403_BODY
            r.json.return_value = None
            return r

        client.session.get = fake_get
        client.get_historical_prices("SPY", days=10)
        assert client.get_quote_failures() == [], (
            "Historical failures must not appear in quote_failures"
        )
