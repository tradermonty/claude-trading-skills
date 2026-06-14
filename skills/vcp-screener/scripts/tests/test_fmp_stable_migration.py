"""FMP /api/v3 → /stable migration tests for vcp-screener.

Proves the hardcoded-v3 call site (get_sp500_constituents) now targets
/stable, and that the stable→v3 fallback list (get_quote / get_historical
via _request_with_fallback) is left intact — i.e. a v3 fallback URL is
still attempted as a real /api/v3/ request, not rewritten back to stable.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fmp_client import FMPClient


def _make_client():
    return FMPClient(api_key="test_key")  # pragma: allowlist secret


def _mock_response(status_code, json_payload, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    resp.text = text
    return resp


class TestHardcodedCallSiteMigratedToStable:
    """Methods that bypass the fallback list now build /stable URLs."""

    def test_sp500_constituents_hits_stable(self):
        client = _make_client()
        seen = []

        def mock_get(url, params=None, timeout=None):
            seen.append((url, params or {}))
            return _mock_response(200, [{"symbol": "AAPL"}, {"symbol": "MSFT"}])

        client.session.get = mock_get
        result = client.get_sp500_constituents()

        assert len(seen) == 1
        url, _ = seen[0]
        assert "/stable/sp500-constituent" in url
        assert "/api/v3/" not in url
        assert result == [{"symbol": "AAPL"}, {"symbol": "MSFT"}]


class TestFallbackContractPreserved:
    """The stable→v3 fallback list must still reach a real /api/v3/ URL."""

    def test_quote_stable_403_falls_back_to_real_v3(self):
        client = _make_client()
        seen = []

        def mock_get(url, params=None, timeout=None):
            seen.append(url)
            if "stable" in url:
                return _mock_response(403, None, text="Forbidden")
            return _mock_response(200, [{"symbol": "^GSPC", "price": 5500.0}])

        client.session.get = mock_get
        result = client.get_quote("^GSPC")

        # Fallback must have attempted a genuine /api/v3/ URL (not a rewritten stable URL)
        assert any("/api/v3/" in u for u in seen)
        assert result == [{"symbol": "^GSPC", "price": 5500.0}]
