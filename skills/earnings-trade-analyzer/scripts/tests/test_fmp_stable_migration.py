"""FMP /api/v3 → /stable migration tests for earnings-trade-analyzer.

Covers the two hardcoded-v3 call sites:
- get_earnings_calendar  -> /stable/earnings-calendar (underscore form 404s on
  all tiers; the hyphenated name is the live one, pinned in _PATH_RENAME_NO_SYMBOL)
- get_company_profiles   -> per-symbol /stable/profile (stable rejects comma
  batching, so the method must issue one request per symbol)
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fmp_client import FMPClient


def _make_client():
    return FMPClient(api_key="test_key", max_api_calls=100)  # pragma: allowlist secret


def _mock_response(status_code, json_payload, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    resp.text = text
    return resp


class TestEarningsCalendarMigration:
    def test_earnings_calendar_hits_stable_hyphen(self):
        client = _make_client()
        seen = []

        def mock_get(url, params=None, timeout=None):
            seen.append((url, params or {}))
            return _mock_response(200, [{"symbol": "AAPL", "date": "2026-06-01"}])

        client.session.get = mock_get
        result = client.get_earnings_calendar("2026-06-01", "2026-06-08")

        assert len(seen) == 1
        url, params = seen[0]
        # underscore /stable form 404s for all tiers; the hyphenated name is the live one
        assert "/stable/earnings-calendar" in url
        assert "/api/v3/" not in url
        assert params.get("from") == "2026-06-01"
        assert params.get("to") == "2026-06-08"
        assert result == [{"symbol": "AAPL", "date": "2026-06-01"}]


class TestCompanyProfilesPerSymbol:
    def test_profiles_issued_one_request_per_symbol_on_stable(self):
        client = _make_client()
        seen = []

        def mock_get(url, params=None, timeout=None):
            params = params or {}
            seen.append((url, params))
            sym = params.get("symbol")
            return _mock_response(200, [{"symbol": sym, "marketCap": 1000}])

        client.session.get = mock_get
        result = client.get_company_profiles(["AAPL", "MSFT"])

        # Two symbols -> two separate /stable/profile?symbol= calls (no comma batch)
        assert len(seen) == 2
        for url, params in seen:
            assert "/stable/profile" in url
            assert "/api/v3/" not in url
            assert "," not in params.get("symbol", "")
        assert set(result.keys()) == {"AAPL", "MSFT"}
        assert result["AAPL"]["marketCap"] == 1000
