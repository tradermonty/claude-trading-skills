"""Unit tests for BEA, CommodityPriceAPI, and e-Stat clients (mocked HTTP)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.api_clients.bea_client import BEAClient, BEAObservation, _last_n_years  # noqa: E402
from scripts.api_clients.commodity_client import CommodityClient, CommodityPrice  # noqa: E402
from scripts.api_clients.estat_client import EStatClient, JapanStat  # noqa: E402


def _resp(status: int = 200, payload: dict | None = None):
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
# BEAClient
# ─────────────────────────────────────────────────────────────────────


class TestBEAClient:
    def _client(self):
        return BEAClient(api_key="bea_test_key")  # pragma: allowlist secret

    def test_last_n_years_with_lag(self):
        with patch("scripts.api_clients.bea_client.date") as mock_date:
            mock_date.today.return_value.year = 2026
            assert _last_n_years(5, lag=2) == "2020,2021,2022,2023,2024"
            assert _last_n_years(3, lag=0) == "2024,2025,2026"

    def test_get_nipa_parses_observations(self):
        client = self._client()
        payload = {
            "BEAAPI": {
                "Results": {
                    "UnitOfMeasure": "Percent",
                    "Data": [
                        {
                            "LineDescription": "Gross domestic product",
                            "TimePeriod": "2024",
                            "DataValue": "2.8",
                            "CL_UNIT": "Percent",
                        },
                        {
                            "LineDescription": "Personal consumption expenditures",
                            "TimePeriod": "2024",
                            "DataValue": "2,500.5",  # tests comma-stripping
                        },
                    ],
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            obs = client.get_nipa("T10101", frequency="A", year="2024")
        # Required params
        params = mock_get.call_args[1]["params"]
        assert params["UserID"] == "bea_test_key"  # pragma: allowlist secret
        assert params["ResultFormat"] == "JSON"
        assert params["DatasetName"] == "NIPA"
        assert params["TableName"] == "T10101"
        # Parsing
        assert len(obs) == 2
        assert isinstance(obs[0], BEAObservation)
        assert obs[0].value == 2.8
        assert obs[1].value == 2500.5  # comma stripped

    def test_top_level_error_raised(self):
        client = self._client()
        payload = {
            "BEAAPI": {
                "Error": {
                    "APIErrorDescription": "Error retrieving NIPA data.",
                    "APIErrorCode": "201",
                    "ErrorDetail": {
                        "Description": "No data exists for the Year/Frequencies passed."
                    },
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            with pytest.raises(RuntimeError, match="No data exists"):
                client.get_nipa("T10101", frequency="Q", year="2050")

    def test_get_nipa_empty_results(self):
        client = self._client()
        payload = {"BEAAPI": {"Results": {}}}
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            assert client.get_nipa("T10101") == []

    def test_real_gdp_growth_filter_falls_back_if_label_drift(self):
        client = self._client()
        # Line description doesn't match the filter — convenience method should
        # still return all rows rather than empty list (graceful degradation)
        payload = {
            "BEAAPI": {
                "Results": {
                    "Data": [
                        {
                            "LineDescription": "Some other line",
                            "TimePeriod": "2024",
                            "DataValue": "1.0",
                        }
                    ]
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            obs = client.real_gdp_growth(year="2024")
        assert len(obs) == 1  # returned despite no "Gross domestic product" match

    def test_error_message_does_not_echo_key(self):
        client = BEAClient(api_key="should_not_leak_in_errors_xyz")  # pragma: allowlist secret
        payload = {"BEAAPI": {"Error": {"APIErrorDescription": "bad"}}}
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            with pytest.raises(RuntimeError) as ei:
                client.get_nipa("T10101")
        assert "should_not_leak_in_errors_xyz" not in str(ei.value)


# ─────────────────────────────────────────────────────────────────────
# CommodityClient
# ─────────────────────────────────────────────────────────────────────


class TestCommodityClient:
    def _client(self):
        return CommodityClient(api_key="commodity_test_key")  # pragma: allowlist secret

    def test_symbol_resolution_friendly_to_code(self):
        client = self._client()
        assert client._resolve("BRENT") == "BRENTOIL-SPOT"
        assert client._resolve("brent") == "BRENTOIL-SPOT"  # case-insensitive
        assert client._resolve("GOLD") == "XAU"
        # Passthrough for unknown symbol
        assert client._resolve("CUSTOM-CODE") == "CUSTOM-CODE"

    def test_latest_uses_header_auth_not_query(self):
        client = self._client()
        payload = {
            "success": True,
            "timestamp": 1779976990,
            "rates": {"BRENTOIL-SPOT": 94.26, "XAU": 4430.93},
            "metadata": {
                "BRENTOIL-SPOT": {"unit": "Bbl", "quote": "USD"},
                "XAU": {"unit": "T.oz", "quote": "USD"},
            },
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            prices = client.latest(["BRENT", "GOLD"])
        # Auth is X-API-KEY header — not in query params
        headers = mock_get.call_args[1]["headers"]
        assert headers["X-API-KEY"] == "commodity_test_key"  # pragma: allowlist secret
        params = mock_get.call_args[1]["params"]
        assert "apikey" not in params and "access_key" not in params
        assert params["symbols"] == "BRENTOIL-SPOT,XAU"
        # Parsing: prices direct, not inverted
        assert len(prices) == 2
        assert isinstance(prices[0], CommodityPrice)
        assert prices[0].usd_price == 94.26
        assert prices[0].unit == "Bbl"
        assert prices[1].common_name == "Gold"

    def test_latest_handles_missing_metadata(self):
        client = self._client()
        # No metadata block — should default unit to "unit"
        payload = {"success": True, "timestamp": 1779976990, "rates": {"XAU": 4000.0}}
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            prices = client.latest(["GOLD"])
        assert prices[0].unit == "unit"

    def test_latest_skips_zero_or_missing_rates(self):
        client = self._client()
        payload = {
            "success": True,
            "timestamp": 1779976990,
            "rates": {"BRENTOIL-SPOT": 94.0, "XAU": 0, "PL": None},
            "metadata": {"BRENTOIL-SPOT": {"unit": "Bbl"}},
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            prices = client.latest(["BRENT", "GOLD", "PLATINUM"])
        # Only Brent kept; XAU=0 and PL=None dropped
        assert len(prices) == 1
        assert prices[0].symbol == "BRENTOIL-SPOT"

    def test_latest_returns_empty_on_unsuccessful_response(self):
        client = self._client()
        with patch.object(client._session, "get", return_value=_resp(200, {"success": False})):
            assert client.latest(["BRENT"]) == []

    def test_time_series_parses_per_day_rates(self):
        client = self._client()
        payload = {
            "success": True,
            "rates": {
                "2026-05-01": {"BRENTOIL-SPOT": 90.0},
                "2026-05-02": {"BRENTOIL-SPOT": 91.0},
            },
            "metadata": {"BRENTOIL-SPOT": {"unit": "Bbl"}},
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            series = client.time_series("BRENT", "2026-05-01", "2026-05-02")
        # Endpoint is /rates/time-series with startDate/endDate camelCase
        path = mock_get.call_args[0][0]
        assert "/rates/time-series" in path
        params = mock_get.call_args[1]["params"]
        assert params["startDate"] == "2026-05-01"
        assert params["endDate"] == "2026-05-02"
        # Sorted oldest -> newest
        assert len(series) == 2
        assert series[0].date == "2026-05-01"
        assert series[0].usd_price == 90.0


# ─────────────────────────────────────────────────────────────────────
# EStatClient
# ─────────────────────────────────────────────────────────────────────


class TestEStatClient:
    def _client(self):
        return EStatClient(api_key="estat_test_key")  # pragma: allowlist secret

    def test_get_stats_data_parses_value_list(self):
        client = self._client()
        payload = {
            "GET_STATS_DATA": {
                "STATISTICAL_DATA": {
                    "DATA_INF": {
                        "VALUE": [
                            {"@time": "2026-04", "@unit": "index", "@cat01": "CPI", "$": "108.7"},
                            {"@time": "2026-03", "@unit": "index", "@cat01": "CPI", "$": "108.2"},
                        ]
                    }
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            obs = client.get_stats_data("0003427113")
        # appId injected as auth param
        params = mock_get.call_args[1]["params"]
        assert params["appId"] == "estat_test_key"  # pragma: allowlist secret
        assert params["statsDataId"] == "0003427113"
        # Parsing
        assert len(obs) == 2
        assert isinstance(obs[0], JapanStat)
        assert obs[0].value == 108.7
        assert obs[0].time_period == "2026-04"
        assert obs[0].unit == "index"

    def test_get_stats_data_handles_single_value_as_dict(self):
        """e-Stat returns VALUE as dict (not list) when only one row matches."""
        client = self._client()
        payload = {
            "GET_STATS_DATA": {
                "STATISTICAL_DATA": {
                    "DATA_INF": {"VALUE": {"@time": "2026-04", "$": "108.7", "@unit": "index"}}
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            obs = client.get_stats_data("xyz")
        assert len(obs) == 1
        assert obs[0].value == 108.7

    def test_get_stats_data_skips_unparseable_value(self):
        client = self._client()
        payload = {
            "GET_STATS_DATA": {
                "STATISTICAL_DATA": {
                    "DATA_INF": {
                        "VALUE": [
                            {"@time": "2026-04", "$": "not_a_number"},
                            {"@time": "2026-03", "$": "108.2"},
                        ]
                    }
                }
            }
        }
        with patch.object(client._session, "get", return_value=_resp(200, payload)):
            obs = client.get_stats_data("xyz")
        # Bad row skipped; good row kept
        assert len(obs) == 1
        assert obs[0].value == 108.2

    def test_get_stats_data_empty_response(self):
        client = self._client()
        with patch.object(client._session, "get", return_value=_resp(200, {})):
            assert client.get_stats_data("xyz") == []
