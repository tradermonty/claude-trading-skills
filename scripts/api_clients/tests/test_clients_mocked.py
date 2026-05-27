"""Unit tests for each API client with mocked HTTP — no network required.

Verifies:
    - Each client builds correct URL + auth params
    - JSON parsing into dataclasses is correct
    - Error paths return sensible empties or raise as documented
    - 429 backoff path is exercised (Polygon)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.api_clients.eia_client import EIAClient, EnergyPoint  # noqa: E402
from scripts.api_clients.finnhub_client import EconEvent, FinnhubClient  # noqa: E402
from scripts.api_clients.news_client import NewsClient, _parse_ts  # noqa: E402
from scripts.api_clients.polygon_client import Bar, PolygonClient  # noqa: E402
from scripts.api_clients.polymarket_client import PolymarketClient  # noqa: E402


def _resp(status: int = 200, payload: dict | None = None):
    """Build a fake requests.Response."""
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400:
        from requests import HTTPError

        r.raise_for_status.side_effect = HTTPError(f"HTTP {status}")
    else:
        r.raise_for_status.return_value = None
    return r


# ─────────────────────────────────────────────────────────────────────
# PolygonClient
# ─────────────────────────────────────────────────────────────────────


class TestPolygonClient:
    def _client(self):
        return PolygonClient(api_key="test_key", rate_limit_sec=0)  # pragma: allowlist secret

    def test_get_aggs_builds_path_and_parses(self):
        client = self._client()
        payload = {
            "results": [
                {
                    "t": 1700000000000,
                    "o": 100.0,
                    "h": 110.0,
                    "l": 99.0,
                    "c": 105.0,
                    "v": 1000,
                    "vw": 102.5,
                    "n": 50,
                },
                {"t": 1700086400000, "o": 105.0, "h": 115.0, "l": 104.0, "c": 112.0, "v": 1500},
            ]
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            bars = client.get_aggs("aapl", "day", "2026-01-01", "2026-01-02")
        # URL built correctly with uppercase ticker
        call_url = mock_get.call_args[0][0]
        assert "/v2/aggs/ticker/AAPL/range/1/day/2026-01-01/2026-01-02" in call_url
        # apiKey appended to params
        assert mock_get.call_args[1]["params"]["apiKey"] == "test_key"  # pragma: allowlist secret
        # Bars parsed correctly
        assert len(bars) == 2
        assert isinstance(bars[0], Bar)
        assert bars[0].close == 105.0
        assert bars[0].vwap == 102.5
        # Optional fields tolerate missing
        assert bars[1].vwap is None
        assert bars[1].transactions is None

    def test_get_aggs_empty_results(self):
        client = self._client()
        with patch.object(client._session, "get", return_value=_resp(200, {})):
            assert client.get_aggs("XYZ", "day", "2026-01-01", "2026-01-02") == []

    def test_429_triggers_single_retry(self):
        client = self._client()
        # First call 429, second succeeds — but sleep would block tests, so patch it
        responses = [_resp(429, {}), _resp(200, {"results": []})]
        with (
            patch.object(client._session, "get", side_effect=responses),
            patch("scripts.api_clients.polygon_client.time.sleep") as mock_sleep,
        ):
            result = client.get_aggs("X", "day", "2026-01-01", "2026-01-02")
        assert result == []
        # Confirm 60s backoff invoked
        mock_sleep.assert_called_with(60)

    def test_market_status(self):
        client = self._client()
        payload = {"market": "open", "serverTime": "2026-05-27T12:00:00Z"}
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            assert client.get_market_status()["market"] == "open"

    def test_throttle_respects_rate_limit(self):
        client = PolygonClient(api_key="test", rate_limit_sec=10.0)
        client._last_request = 1000.0
        with (
            patch("scripts.api_clients.polygon_client.time.time", side_effect=[1001.0, 1011.0]),
            patch("scripts.api_clients.polygon_client.time.sleep") as mock_sleep,
        ):
            client._throttle()
        # Elapsed = 1 sec, limit = 10 → must sleep 9 sec
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] == pytest.approx(9.0)


# ─────────────────────────────────────────────────────────────────────
# NewsClient
# ─────────────────────────────────────────────────────────────────────


class TestNewsClient:
    def test_requires_at_least_one_key(self, monkeypatch):
        # Block auto-load from real secrets file and force both keys absent
        monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)
        monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
        with patch("scripts.api_clients.news_client.get_api_key", return_value=None):
            with pytest.raises(RuntimeError, match="at least one"):
                NewsClient(marketaux_key=None, newsdata_key=None)

    def test_parse_ts_naive_becomes_utc(self):
        dt = _parse_ts("2026-05-27 12:00:00")
        assert dt.tzinfo is not None

    def test_parse_ts_zulu(self):
        dt = _parse_ts("2026-05-27T12:00:00Z")
        assert dt.tzinfo is not None

    def test_marketaux_falls_back_to_newsdata_when_empty(self):
        client = NewsClient(marketaux_key="mx", newsdata_key="newsdata_key")
        # Marketaux returns empty
        marketaux_resp = _resp(200, {"data": []})
        # Newsdata returns one item
        newsdata_resp = _resp(
            200,
            {
                "results": [
                    {
                        "title": "Fed holds rates",
                        "description": "Powell statement",
                        "link": "https://example.com/a",
                        "source_id": "Reuters",
                        "pubDate": "2026-05-27 12:00:00",
                    }
                ]
            },
        )
        with patch.object(client._session, "get", side_effect=[marketaux_resp, newsdata_resp]):
            items = client.get_market_news(tickers=["NVDA"], days=3, limit=5)
        assert len(items) == 1
        assert items[0].provider == "newsdata"
        assert items[0].source == "Reuters"

    def test_marketaux_returns_sentiment(self):
        client = NewsClient(marketaux_key="mx", newsdata_key="newsdata_key")
        marketaux_payload = {
            "data": [
                {
                    "title": "NVDA beats",
                    "description": "Earnings beat consensus",
                    "url": "https://x.com/1",
                    "source": "Bloomberg",
                    "published_at": "2026-05-27T10:00:00Z",
                    "entities": [
                        {"symbol": "NVDA", "sentiment_score": 0.8},
                        {"symbol": "AMD", "sentiment_score": 0.4},
                    ],
                    "keywords": "earnings,ai,chips",
                }
            ]
        }
        with patch.object(client._session, "get", return_value=_resp(200, marketaux_payload)):
            items = client.get_market_news(tickers=["NVDA"], limit=1)
        assert len(items) == 1
        assert items[0].sentiment == pytest.approx(0.6)  # mean of 0.8, 0.4
        assert "NVDA" in items[0].tickers

    def test_search_news_dedupes_by_url(self):
        client = NewsClient(marketaux_key="mx", newsdata_key="newsdata_key")
        # Same URL from both providers
        url = "https://dup.example/1"
        ma = _resp(
            200,
            {
                "data": [
                    {
                        "title": "A",
                        "url": url,
                        "source": "X",
                        "published_at": "2026-05-27T10:00:00Z",
                    }
                ]
            },
        )
        nd_resp_obj = _resp(
            200,
            {
                "results": [
                    {"title": "A", "link": url, "source_id": "X", "pubDate": "2026-05-27 10:00:00"}
                ]
            },
        )
        with patch.object(client._session, "get", side_effect=[ma, nd_resp_obj]):
            items = client.search_news("test", limit=10)
        assert len(items) == 1


# ─────────────────────────────────────────────────────────────────────
# EIAClient
# ─────────────────────────────────────────────────────────────────────


class TestEIAClient:
    def _client(self):
        return EIAClient(api_key="eia_test")  # pragma: allowlist secret

    def test_electricity_demand_parses_and_reverses(self):
        client = self._client()
        # EIA returns newest-first; client must reverse to oldest-first
        payload = {
            "response": {
                "data": [
                    {"period": "2026-05-26", "value": "2000000", "value-units": "MWh"},
                    {"period": "2026-05-25", "value": "1900000", "value-units": "MWh"},
                ]
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            points = client.electricity_demand("PJM", days=2)
        # Region code "PJM" passed in facets
        params = mock_get.call_args[1]["params"]
        assert params["facets[respondent][]"] == "PJM"
        assert params["facets[type][]"] == "D"
        # Order oldest -> newest
        assert points[0].period == "2026-05-25"
        assert points[-1].period == "2026-05-26"
        assert isinstance(points[0], EnergyPoint)
        assert points[-1].value == 2000000.0

    def test_unknown_region_passed_through_uppercased(self):
        client = self._client()
        with patch.object(client._session, "get", return_value=_resp(200, {})) as mock_get:
            client.electricity_demand("ercot", days=1)
        params = mock_get.call_args[1]["params"]
        # ERCOT mapped to ERCO
        assert params["facets[respondent][]"] == "ERCO"

    def test_yoy_insufficient_history(self):
        client = self._client()
        with patch.object(client, "electricity_demand", return_value=[]):
            out = client.power_demand_yoy("PJM")
        assert out["error"] == "insufficient_history"


# ─────────────────────────────────────────────────────────────────────
# FinnhubClient
# ─────────────────────────────────────────────────────────────────────


class TestFinnhubClient:
    def _client(self):
        return FinnhubClient(api_key="fh_test")  # pragma: allowlist secret

    def test_economic_calendar_parses(self):
        client = self._client()
        payload = {
            "economicCalendar": [
                {
                    "country": "US",
                    "event": "CPI",
                    "time": "2026-05-28 13:30:00",
                    "estimate": 3.2,
                    "actual": None,
                    "prev": 3.1,
                    "impact": "high",
                    "unit": "%",
                }
            ]
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            evs = client.economic_calendar()
        assert len(evs) == 1
        assert isinstance(evs[0], EconEvent)
        assert evs[0].impact == "high"
        assert evs[0].estimate == 3.2

    def test_earnings_calendar_skips_malformed(self):
        client = self._client()
        payload = {
            "earningsCalendar": [
                {"symbol": "AAPL", "date": "2026-05-28", "hour": "amc", "year": 2026, "quarter": 2},
                {"symbol": "BAD", "date": "not-a-date"},  # should be skipped
            ]
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            evs = client.earnings_calendar()
        assert len(evs) == 1
        assert evs[0].symbol == "AAPL"


# ─────────────────────────────────────────────────────────────────────
# PolymarketClient
# ─────────────────────────────────────────────────────────────────────


class TestPolymarketClient:
    def _client(self):
        return PolymarketClient(jwt_token=None)

    def test_parse_market_with_string_outcome_prices(self):
        client = self._client()
        # Some Gamma endpoints return outcomePrices as a string "[0.72, 0.28]"
        raw = {
            "id": "abc",
            "question": "Will Fed cut?",
            "slug": "fed-cut",
            "outcomePrices": "[0.72, 0.28]",
            "endDate": "2026-06-15T00:00:00Z",
            "volume24hr": "10000",
            "liquidity": "5000",
        }
        m = client._parse_market(raw)
        assert m.yes_price == pytest.approx(0.72)
        assert m.no_price == pytest.approx(0.28)
        assert m.implied_probability == pytest.approx(0.72)
        assert m.end_date is not None

    def test_parse_market_with_list_prices(self):
        client = self._client()
        raw = {
            "id": "x",
            "question": "Q",
            "outcomePrices": [0.55, 0.45],
            "volume24hr": 0,
            "liquidity": 0,
        }
        m = client._parse_market(raw)
        assert m.yes_price == pytest.approx(0.55)

    def test_search_markets_handles_http_error(self):
        client = self._client()
        from requests import HTTPError

        with patch.object(client._session, "get", side_effect=HTTPError("500")):
            assert client.search_markets("anything") == []

    def test_search_markets_passes_q_param(self):
        client = self._client()
        with patch.object(client._session, "get", return_value=_resp(200, [])) as mock_get:
            client.search_markets("Fed cut")
        params = mock_get.call_args[1]["params"]
        assert params["q"] == "Fed cut"
        assert params["active"] == "true"
