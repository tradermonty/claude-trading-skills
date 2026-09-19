"""Behavioral coverage for the generated FMP client ET anchor (issue #427).

The generated client derives the price/history query window from the
America/New_York calendar date (``_et_today``) instead of the runner's
local clock. These tests exercise the happy path, boundary/error paths,
and the fail-closed tzdata behaviour directly on the module, independent
of any live FMP request.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import fmp_client
import pytest


def test_et_today_converts_aware_now_to_et_date():
    tokyo_noon = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert fmp_client._et_today(tokyo_noon).isoformat() == "2026-01-14"


def test_et_today_returns_et_date_for_utc_evening():
    utc_late = datetime(2026, 7, 15, 2, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert fmp_client._et_today(utc_late).isoformat() == "2026-07-14"


def test_et_today_default_uses_now():
    today = fmp_client._et_today()
    assert isinstance(today, date)


def test_et_today_rejects_naive_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        fmp_client._et_today(datetime(2026, 1, 15, 12, 0, 0))


def test_et_today_fails_closed_on_missing_tzdata(monkeypatch):
    def _boom(_key):
        raise ZoneInfoNotFoundError("No tzdata")

    monkeypatch.setattr(fmp_client, "ZoneInfo", _boom)
    with pytest.raises(RuntimeError, match="tzdata"):
        fmp_client._et_today()


def test_stable_hist_url_uses_et_window(monkeypatch):
    et_date = (
        datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        .astimezone(ZoneInfo("America/New_York"))
        .date()
    )
    monkeypatch.setattr(fmp_client, "_et_today", lambda now=None: et_date)
    base, params = fmp_client._stable_hist_url("https://base", "SPY", {"timeseries": 10})
    assert params["symbol"] == "SPY"
    assert params["to"] == et_date.isoformat()
    assert params["from"] == (et_date - timedelta(days=20)).isoformat()
    assert "timeseries" not in params


def test_stable_hist_url_no_timeseries_noop():
    base, params = fmp_client._stable_hist_url("https://base", "SPY", {"other": "1"})
    assert params == {"other": "1", "symbol": "SPY"}


def test_v3_hist_url_preserves_base_and_params():
    base, params = fmp_client._v3_hist_url(
        "https://base/historical-price-full", "SPY", {"timeseries": 10}
    )
    assert base.endswith("/historical-price-full/SPY")
    assert params == {"timeseries": 10}
