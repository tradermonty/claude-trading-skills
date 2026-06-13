"""Issue #64: stable/historical-price-eod/full normalization for vcp-screener."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fmp_client import FMPClient


def _make_client():
    client = FMPClient(api_key="test_key")
    client.max_retries = 0
    return client


def _mock_response(status_code, json_payload, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    resp.text = text
    return resp


class TestEODFlatListSuccess:
    @patch("fmp_client.requests.Session")
    def test_get_historical_prices_normalizes_flat_list(self, mock_session_class):
        """Flat list response -> dict contract preserved."""
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

        result = client.get_historical_prices("SPY", days=2)
        assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
        assert result["symbol"] == "SPY"
        assert len(result["historical"]) == 2
        assert result["historical"][0]["close"] == 501.0

        first_call = mock_session.get.call_args_list[0]
        url = first_call[0][0]
        params = first_call[1]["params"]
        assert "historical-price-eod/full" in url
        assert "from" in params and "to" in params
        assert "timeseries" not in params


class TestFallbackTransparency:
    """When stable fails and the client falls back to v3, the user must
    see WHY the first endpoint was skipped — otherwise they get the v3
    'Legacy Endpoint' error with no context."""

    @patch("fmp_client.requests.Session")
    def test_stable_error_surfaced_when_falling_back_to_v3(
        self, mock_session_class, capsys
    ):
        """403 on stable, 403 on v3 — both errors must appear in stderr."""
        mock_session = MagicMock()
        mock_session.get.side_effect = [
            _mock_response(
                403, None,
                text='{"Error Message": "Special Endpoint: This symbol is not available..."}',
            ),
            _mock_response(
                403, None,
                text='{"Error Message": "Legacy Endpoint: only legacy users..."}',
            ),
        ]
        mock_session_class.return_value = mock_session

        client = _make_client()
        client.session = mock_session

        result = client.get_historical_prices("GOOG", days=10)
        assert result is None

        captured = capsys.readouterr()
        # Both endpoints' errors must be visible.
        assert "Special Endpoint" in captured.err, (
            f"stable endpoint error not surfaced. stderr:\n{captured.err}"
        )
        assert "Legacy Endpoint" in captured.err, (
            f"v3 endpoint error missing. stderr:\n{captured.err}"
        )
        # The user should also see which endpoint was tried first / fell back to.
        assert "stable" in captured.err.lower() or "fallback" in captured.err.lower(), (
            f"no fallback context in stderr:\n{captured.err}"
        )

    @patch("fmp_client.requests.Session")
    def test_stable_success_suppresses_warning(self, mock_session_class, capsys):
        """Happy path: stable succeeds, no fallback warning emitted."""
        mock_session = MagicMock()
        mock_session.get.return_value = _mock_response(
            200,
            [{"symbol": "AAPL", "date": "2026-01-01", "open": 1.0, "high": 1.0,
              "low": 1.0, "close": 1.0, "volume": 1000}],
        )
        mock_session_class.return_value = mock_session

        client = _make_client()
        client.session = mock_session

        result = client.get_historical_prices("AAPL", days=1)
        assert result is not None

        captured = capsys.readouterr()
        # Happy path must stay quiet — no spurious warnings.
        assert "WARN" not in captured.err, f"unexpected stderr:\n{captured.err}"
        assert "fallback" not in captured.err.lower()
