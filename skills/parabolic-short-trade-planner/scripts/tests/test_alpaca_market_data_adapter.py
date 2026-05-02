"""Tests for AlpacaMarketDataAdapter (mocked HTTP).

Coverage focus:
- Response shape: ``{"bars": [...], "next_page_token": ...}`` not a flat
  list. The adapter must extract ``bars`` and follow pagination.
- Bar conversion: Alpaca returns ``{"t": <UTC ISO>, "o": ..., ...}``;
  the adapter must rename to the contract shape ``{"ts_et": <ET ISO>,
  "o": ..., ..., "v": int}``.
- Time-zone math: ``until_et`` (ET) is converted to RFC3339 UTC for
  the ``start`` / ``end`` query params; never sent as ET-local.
- Regular-session filter: the adapter discards extended-hours bars
  even if Alpaca returns them.
- 404 → ``[]`` (not raise) so a delisted symbol can't abort the batch.
- Other HTTP errors propagate.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "adapters"
if str(ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_DIR))

from alpaca_market_data_adapter import AlpacaMarketDataAdapter

ET = ZoneInfo("America/New_York")


def _alpaca_bars_response(bars: list[dict], next_token: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "bars": bars,
        "next_page_token": next_token,
        "symbol": "AAPL",
    }
    resp.raise_for_status = MagicMock()
    return resp


def _alpaca_404() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 404
    resp.json.return_value = {"code": 40410000, "message": "asset not found"}
    resp.raise_for_status = MagicMock(
        side_effect=AssertionError("raise_for_status must not be called on 404 path")
    )
    return resp


def _bar_alpaca(ts_utc: str, c: float = 100.0, v: int = 1_000_000) -> dict:
    """Bar in Alpaca's wire shape (UTC `t`, single-letter OHLCV)."""
    return {
        "t": ts_utc,
        "o": c,
        "h": c + 0.5,
        "l": c - 0.5,
        "c": c,
        "v": v,
        "n": 1234,  # extra fields the adapter must ignore
        "vw": c,
    }


@pytest.fixture
def adapter():
    return AlpacaMarketDataAdapter(
        api_key="key",  # pragma: allowlist secret
        secret_key="secret",  # pragma: allowlist secret
    )


class TestHappyPath:
    def test_single_page_returns_converted_bars(self, adapter):
        # 09:30 ET on 2026-05-05 = 13:30 UTC (EDT, -04:00).
        # until_et=09:40 confirms both bars (09:30 closes at 09:35,
        # 09:35 closes at 09:40 — both ≤ 09:40).
        wire = [
            _bar_alpaca("2026-05-05T13:30:00Z", 150.00),
            _bar_alpaca("2026-05-05T13:35:00Z", 150.20),
        ]
        with patch("requests.get", return_value=_alpaca_bars_response(wire)):
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 9, 40, tzinfo=ET),
            )
        assert len(bars) == 2
        # Required dict shape
        assert set(bars[0].keys()) == {"ts_et", "o", "h", "l", "c", "v"}
        # ts_et carries an ET tz-offset suffix and is bar-OPEN time
        # (matches Alpaca wire); the bar covers [09:30, 09:35).
        assert bars[0]["ts_et"].startswith("2026-05-05T09:30:00")
        assert bars[0]["ts_et"].endswith("-04:00")
        assert bars[0]["c"] == 150.00

    def test_unconfirmed_current_minute_bar_excluded(self, adapter):
        # The 09:35 bar covers [09:35, 09:40) and is NOT confirmed at
        # until_et=09:35 — it confirms at 09:40. The Phase 3 contract
        # requires only confirmed bars, so the FSM never sees it.
        wire = [
            _bar_alpaca("2026-05-05T13:30:00Z", 150.00),
            _bar_alpaca("2026-05-05T13:35:00Z", 150.20),
        ]
        with patch("requests.get", return_value=_alpaca_bars_response(wire)):
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 9, 35, tzinfo=ET),
            )
        # Only the 09:30 bar (closes at 09:35) is confirmed.
        assert len(bars) == 1
        assert bars[0]["ts_et"].startswith("2026-05-05T09:30:00")

    def test_request_uses_rfc3339_utc_for_start_end(self, adapter):
        captured = {}

        def fake_get(url, headers=None, params=None, timeout=None):
            captured["params"] = params
            return _alpaca_bars_response([])

        with patch("requests.get", side_effect=fake_get):
            adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 12, 0, tzinfo=ET),  # noon ET = 16:00 UTC
            )
        # start should be 09:30 ET in UTC (=13:30Z), end should be the
        # close-of-bar moment (no later than until_et).
        assert captured["params"]["start"].endswith("Z")
        assert captured["params"]["end"].endswith("Z")
        assert "13:30:00" in captured["params"]["start"]
        assert "16:00:00" in captured["params"]["end"]
        assert captured["params"]["timeframe"] == "5Min"


class TestPagination:
    def test_follows_next_page_token(self, adapter):
        page1 = _alpaca_bars_response(
            [_bar_alpaca("2026-05-05T13:30:00Z", 150.0)],
            next_token="abc",
        )
        page2 = _alpaca_bars_response(
            [_bar_alpaca("2026-05-05T13:35:00Z", 150.5)],
            next_token=None,
        )
        with patch("requests.get", side_effect=[page1, page2]) as get:
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 9, 40, tzinfo=ET),
            )
        assert len(bars) == 2
        assert get.call_count == 2
        # Second call carries page_token=abc
        second_call_params = get.call_args_list[1].kwargs["params"]
        assert second_call_params.get("page_token") == "abc"


class TestRegularSessionFilter:
    def test_premarket_bars_dropped(self, adapter):
        # 08:00 ET = 12:00 UTC — outside regular session.
        wire = [
            _bar_alpaca("2026-05-05T12:00:00Z", 149.0),  # premarket
            _bar_alpaca("2026-05-05T13:30:00Z", 150.0),  # regular open
        ]
        with patch("requests.get", return_value=_alpaca_bars_response(wire)):
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
            )
        assert len(bars) == 1
        assert bars[0]["ts_et"].startswith("2026-05-05T09:30:00")

    def test_after_hours_bars_dropped(self, adapter):
        wire = [
            _bar_alpaca("2026-05-05T19:55:00Z", 150.0),  # 15:55 ET (last regular bar)
            _bar_alpaca("2026-05-05T20:00:00Z", 150.5),  # 16:00 ET (post-close)
            _bar_alpaca("2026-05-05T21:00:00Z", 151.0),  # after-hours
        ]
        with patch("requests.get", return_value=_alpaca_bars_response(wire)):
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 16, 30, tzinfo=ET),
            )
        # Only 15:55 ET survives (16:00 itself is the close, excluded).
        assert len(bars) == 1
        assert bars[0]["ts_et"].startswith("2026-05-05T15:55:00")


class TestErrorHandling:
    def test_404_returns_empty_list(self, adapter):
        with patch("requests.get", return_value=_alpaca_404()):
            bars = adapter.get_bars_5min(
                "DELISTED",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
            )
        assert bars == []

    def test_401_raises(self, adapter):
        bad = MagicMock()
        bad.status_code = 401
        bad.raise_for_status.side_effect = RuntimeError("HTTP 401")
        with patch("requests.get", return_value=bad):
            with pytest.raises(RuntimeError):
                adapter.get_bars_5min(
                    "AAPL",
                    session_date="2026-05-05",
                    until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
                )

    def test_5xx_raises(self, adapter):
        bad = MagicMock()
        bad.status_code = 500
        bad.raise_for_status.side_effect = RuntimeError("HTTP 500")
        with patch("requests.get", return_value=bad):
            with pytest.raises(RuntimeError):
                adapter.get_bars_5min(
                    "AAPL",
                    session_date="2026-05-05",
                    until_et=datetime(2026, 5, 5, 10, 0, tzinfo=ET),
                )


class TestUntilEtFilter:
    def test_bars_after_until_et_dropped(self, adapter):
        # until_et=09:40 confirms 09:30 (closes 09:35) and 09:35
        # (closes 09:40) but NOT 09:40 (closes 09:45).
        wire = [
            _bar_alpaca("2026-05-05T13:30:00Z", 150.0),
            _bar_alpaca("2026-05-05T13:35:00Z", 150.5),
            _bar_alpaca("2026-05-05T13:40:00Z", 151.0),
        ]
        with patch("requests.get", return_value=_alpaca_bars_response(wire)):
            bars = adapter.get_bars_5min(
                "AAPL",
                session_date="2026-05-05",
                until_et=datetime(2026, 5, 5, 9, 40, tzinfo=ET),
            )
        # 09:30 and 09:35 included; 09:40 dropped (still open at 09:40).
        assert len(bars) == 2


class TestConfig:
    def test_data_host_same_for_paper_and_live(self):
        # Whether ALPACA_PAPER is true or false, market data lives at
        # data.alpaca.markets. The adapter must not honour paper for
        # the URL choice.
        a_paper = AlpacaMarketDataAdapter(
            api_key="k",  # pragma: allowlist secret
            secret_key="s",  # pragma: allowlist secret
            paper=True,
        )
        a_live = AlpacaMarketDataAdapter(
            api_key="k",  # pragma: allowlist secret
            secret_key="s",  # pragma: allowlist secret
            paper=False,
        )
        assert a_paper.base_url == a_live.base_url
        assert "data.alpaca.markets" in a_paper.base_url

    def test_missing_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with pytest.raises(Exception):  # noqa: B017 — adapter should signal missing config
            AlpacaMarketDataAdapter()
