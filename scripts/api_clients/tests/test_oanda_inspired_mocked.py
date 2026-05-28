"""Unit tests for BIS + BLS clients (mocked HTTP).

These two clients were added after studying patterns from the oanda-trader
project — both use FREE public APIs (no key required for BIS, optional for BLS).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.api_clients.bis_client import BISClient, PolicyRateObservation  # noqa: E402
from scripts.api_clients.bls_client import BLSClient, BLSObservation  # noqa: E402


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
# BISClient
# ─────────────────────────────────────────────────────────────────────


class TestBISClient:
    def _sdmx_two_countries(self) -> dict:
        """Realistic mini SDMX-JSON: US + JP, 2 monthly periods each."""
        return {
            "data": {
                "structure": {
                    "dimensions": {
                        "series": [
                            {"id": "FREQ", "values": [{"id": "M"}]},
                            {
                                "id": "REF_AREA",
                                "values": [
                                    {"id": "US", "name": "United States"},
                                    {"id": "JP", "name": "Japan"},
                                ],
                            },
                        ],
                        "observation": [
                            {
                                "id": "TIME_PERIOD",
                                "values": [
                                    {"id": "2026-03"},
                                    {"id": "2026-04"},
                                ],
                            },
                        ],
                    }
                },
                "dataSets": [
                    {
                        "series": {
                            # FREQ_idx:REF_AREA_idx
                            "0:0": {"observations": {"0": [5.5], "1": [5.25]}},  # US
                            "0:1": {"observations": {"0": [0.1], "1": [0.10]}},  # JP
                        }
                    }
                ],
            }
        }

    def test_get_policy_rates_parses_sdmx(self):
        client = BISClient()
        payload = self._sdmx_two_countries()
        with patch.object(client._session, "get", return_value=_resp(200, payload)) as mock_get:
            rows = client.get_policy_rates(last_n_observations=2)
        # No auth — no apiKey/key in params
        params = mock_get.call_args[1]["params"]
        assert "apiKey" not in params and "key" not in params
        # Correct SDMX Accept header
        assert (
            mock_get.call_args[1]["headers"]["Accept"]
            == "application/vnd.sdmx.data+json;version=1.0.0"
        )
        # Each country × each period
        assert len(rows) == 4
        assert isinstance(rows[0], PolicyRateObservation)
        us_apr = [r for r in rows if r.country_code == "US" and r.period == "2026-04"][0]
        assert us_apr.rate_pct == pytest.approx(5.25)
        assert us_apr.country_name == "United States"

    def test_get_policy_rates_handles_malformed_sdmx(self):
        client = BISClient()
        with patch.object(client._session, "get", return_value=_resp(200, {"data": {}})):
            assert client.get_policy_rates() == []

    def test_latest_policy_rate_picks_newest_period(self):
        client = BISClient()
        with patch.object(
            client._session, "get", return_value=_resp(200, self._sdmx_two_countries())
        ):
            latest = client.latest_policy_rate("US")
        assert latest is not None
        # 2026-04 is newer than 2026-03
        assert latest.period == "2026-04"
        assert latest.rate_pct == 5.25

    def test_latest_policy_rate_unknown_country(self):
        client = BISClient()
        with patch.object(
            client._session, "get", return_value=_resp(200, self._sdmx_two_countries())
        ):
            assert client.latest_policy_rate("ZZ") is None

    def test_rate_differential_spread(self):
        client = BISClient()
        with patch.object(
            client._session, "get", return_value=_resp(200, self._sdmx_two_countries())
        ):
            diff = client.rate_differential("US", "JP")
        assert diff["spread_pp"] == pytest.approx(5.25 - 0.10)
        assert diff["country_a"] == "US"
        assert diff["country_b"] == "JP"
        assert diff["period"] == "2026-04"

    def test_rate_differential_missing_data(self):
        client = BISClient()
        with patch.object(
            client._session, "get", return_value=_resp(200, self._sdmx_two_countries())
        ):
            diff = client.rate_differential("US", "ZZ")
        assert diff["error"] == "missing_data"
        assert diff["have_a"] is True
        assert diff["have_b"] is False


# ─────────────────────────────────────────────────────────────────────
# BLSClient
# ─────────────────────────────────────────────────────────────────────


class TestBLSClient:
    def _series_response(self) -> dict:
        return {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "LNS14000000",
                        "data": [
                            {
                                "year": "2026",
                                "period": "M04",
                                "periodName": "April",
                                "value": "4.3",
                                "footnotes": [{"text": "preliminary"}],
                            },
                            {
                                "year": "2026",
                                "period": "M03",
                                "periodName": "March",
                                "value": "4.2",
                                "footnotes": [],
                            },
                        ],
                    }
                ]
            },
        }

    def _client(self):
        # Force no key so the test doesn't depend on env state
        return BLSClient(api_key=None)

    def test_get_series_parses_and_normalizes_period(self):
        client = self._client()
        with patch.object(
            client._session, "post", return_value=_resp(200, self._series_response())
        ) as mock_post:
            obs = client.get_series(["LNS14000000"], start_year=2026, end_year=2026)
        # POST endpoint + body
        assert "/timeseries/data/" in mock_post.call_args[0][0]
        body = mock_post.call_args[1]["json"]
        assert body["seriesid"] == ["LNS14000000"]
        assert body["startyear"] == "2026"
        # M04 -> "2026-04"
        assert len(obs) == 2
        assert isinstance(obs[0], BLSObservation)
        periods = sorted(o.period for o in obs)
        assert periods == ["2026-03", "2026-04"]

    def test_get_series_carries_footnotes(self):
        client = self._client()
        with patch.object(
            client._session, "post", return_value=_resp(200, self._series_response())
        ):
            obs = client.get_series(["LNS14000000"], start_year=2026, end_year=2026)
        prelim = [o for o in obs if o.period == "2026-04"][0]
        assert "preliminary" in prelim.footnotes

    def test_get_named_resolves_friendly_name(self):
        client = self._client()
        with patch.object(
            client._session, "post", return_value=_resp(200, self._series_response())
        ) as mock_post:
            client.get_named("unemployment_rate", start_year=2026)
        body = mock_post.call_args[1]["json"]
        # Friendly name maps to the canonical series ID
        assert body["seriesid"] == ["LNS14000000"]

    def test_get_named_rejects_unknown(self):
        client = self._client()
        with pytest.raises(KeyError, match="Unknown series name"):
            client.get_named("not_a_real_series", start_year=2026)

    def test_unsuccessful_status_raises_with_messages(self):
        client = self._client()
        bad = {
            "status": "REQUEST_NOT_PROCESSED",
            "message": ["The startyear parameter is invalid.", "Limit exceeded"],
        }
        with patch.object(client._session, "post", return_value=_resp(200, bad)):
            with pytest.raises(RuntimeError, match="REQUEST_NOT_PROCESSED"):
                client.get_series(["LNS14000000"], start_year=2026, end_year=2026)

    def test_key_injected_when_present(self):
        # Manually supply a key
        client = BLSClient(api_key="bls_test_key_xyz")  # pragma: allowlist secret
        with patch.object(
            client._session, "post", return_value=_resp(200, self._series_response())
        ) as mock_post:
            client.get_series(["LNS14000000"], start_year=2026, end_year=2026)
        body = mock_post.call_args[1]["json"]
        assert body["registrationkey"] == "bls_test_key_xyz"  # pragma: allowlist secret

    def test_no_key_means_no_key_in_body(self):
        client = self._client()
        with patch.object(
            client._session, "post", return_value=_resp(200, self._series_response())
        ) as mock_post:
            client.get_series(["LNS14000000"], start_year=2026, end_year=2026)
        body = mock_post.call_args[1]["json"]
        assert "registrationkey" not in body

    def test_invalid_value_skipped(self):
        client = self._client()
        payload = {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "X",
                        "data": [
                            {"year": "2026", "period": "M04", "value": "bad", "periodName": "Apr"},
                            {"year": "2026", "period": "M03", "value": "4.2", "periodName": "Mar"},
                        ],
                    }
                ]
            },
        }
        with patch.object(client._session, "post", return_value=_resp(200, payload)):
            obs = client.get_series(["X"], start_year=2026, end_year=2026)
        # Bad row dropped; good row kept
        assert len(obs) == 1
        assert obs[0].value == 4.2
