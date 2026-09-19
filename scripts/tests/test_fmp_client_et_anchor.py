"""ET-anchor regression tests for generated FMP clients (issue #427).

``_stable_hist_url`` and the ``v3_to_stable`` shim used to bound the
price/history window with the runner's local ``date.today()``. On runners
whose local date differs from the America/New_York date (Asia/Tokyo evenings,
UTC after 20:00 ET) the from/to window shifted by a day. The generated
clients now derive the window from ``_et_today()``.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

CLIENTS_WITH_ET_TODAY = [
    "skills/pead-screener/scripts/fmp_client.py",
    "skills/earnings-trade-analyzer/scripts/fmp_client.py",
    "skills/ibd-distribution-day-monitor/scripts/fmp_client.py",
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
    "skills/ftd-detector/scripts/fmp_client.py",
    "skills/canslim-screener/scripts/fmp_client.py",
    "skills/macro-regime-detector/scripts/fmp_client.py",
    "skills/market-top-detector/scripts/fmp_client.py",
]

COMPAT_MODULES = [
    "skills/pead-screener/scripts/_fmp_compat.py",
    "skills/earnings-trade-analyzer/scripts/_fmp_compat.py",
    "skills/ibd-distribution-day-monitor/scripts/_fmp_compat.py",
    "skills/vcp-screener/scripts/_fmp_compat.py",
    "skills/parabolic-short-trade-planner/scripts/_fmp_compat.py",
]

# (instant, expected ET date): Tokyo evening (local ET+1), UTC after 20:00 ET,
# EDT/EST representatives, and the spring-forward DST transition.
VECTORS = [
    ("2026-01-15T12:00:00+09:00", "2026-01-14"),  # Tokyo noon = previous ET day
    ("2026-07-15T02:00:00+00:00", "2026-07-14"),  # 22:00 EDT previous day
    ("2026-07-15T12:00:00+00:00", "2026-07-15"),  # summer midday EDT
    ("2026-01-15T12:00:00+00:00", "2026-01-15"),  # winter midday EST
    ("2026-03-08T06:59:00+00:00", "2026-03-08"),  # 01:59 EST, pre-transition
    ("2026-03-08T07:01:00+00:00", "2026-03-08"),  # 03:01 EDT, post-transition
]


def _load(rel_path: str):
    abs_path = REPO_ROOT / rel_path
    name = "_fmp_et_" + abs_path.parent.parent.name.replace("-", "_") + "_" + abs_path.stem
    for mod_name in (name, "_fmp_compat"):
        sys.modules.pop(mod_name, None)
    sys.path.insert(0, str(abs_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(abs_path.parent))


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
@pytest.mark.parametrize("instant,expected", VECTORS)
def test_et_today_conversion(rel_path, instant, expected):
    mod = _load(rel_path)
    assert mod._et_today(datetime.fromisoformat(instant)).isoformat() == expected


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
def test_et_today_dst_transition_offset_change(rel_path):
    """Spring-forward boundary: same ET date, different UTC offset each side."""
    mod = _load(rel_path)
    before = datetime.fromisoformat("2026-03-08T06:59:00+00:00")
    after = datetime.fromisoformat("2026-03-08T07:01:00+00:00")
    assert mod._et_today(before).isoformat() == "2026-03-08"
    assert mod._et_today(after).isoformat() == "2026-03-08"
    tz = ZoneInfo("America/New_York")
    assert before.astimezone(tz).utcoffset() != after.astimezone(tz).utcoffset()


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
def test_et_today_rejects_naive_now(rel_path):
    mod = _load(rel_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        mod._et_today(datetime(2026, 1, 15, 12, 0, 0))


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
def test_et_today_missing_tzdata_raises_actionable(rel_path, monkeypatch):
    mod = _load(rel_path)

    def _boom(_key):
        raise ZoneInfoNotFoundError("No time zone found with key America/New_York")

    monkeypatch.setattr(mod, "ZoneInfo", _boom)
    with pytest.raises(RuntimeError, match="tzdata"):
        mod._et_today()


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
def test_stable_hist_url_uses_et_window(rel_path, monkeypatch):
    mod = _load(rel_path)
    anchor = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    et_date = anchor.astimezone(ZoneInfo("America/New_York")).date()
    assert et_date.isoformat() == "2026-01-14"  # guard: vector really is ET+1
    monkeypatch.setattr(mod, "_et_today", lambda now=None: et_date)
    base, params = mod._stable_hist_url("https://base", "SPY", {"timeseries": 10})
    assert params["to"] == "2026-01-14"
    assert params["from"] == (et_date - timedelta(days=20)).isoformat()
    assert params["symbol"] == "SPY"
    assert "timeseries" not in params


@pytest.mark.parametrize("rel_path", CLIENTS_WITH_ET_TODAY)
def test_stable_hist_url_no_timeseries_noop(rel_path):
    mod = _load(rel_path)
    base, params = mod._stable_hist_url("https://base", "SPY", {"other": "1"})
    assert params == {"other": "1", "symbol": "SPY"}


def test_garp_client_has_no_local_clock():
    """us-undervalued-growth-screener client must not bound windows on date.today()."""
    text = (REPO_ROOT / "skills/us-undervalued-growth-screener/scripts/fmp_client.py").read_text()
    assert "date.today()" not in text


@pytest.mark.parametrize("rel_path", COMPAT_MODULES)
def test_compat_window_uses_et_date(rel_path, monkeypatch):
    mod = _load(rel_path)
    anchor = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    et_date = anchor.astimezone(ZoneInfo("America/New_York")).date()
    monkeypatch.setattr(mod, "_et_today", lambda now=None: et_date)
    url, params = mod.v3_to_stable(
        "https://financialmodelingprep.com/api/v3/historical-price-full/SPY",
        {"timeseries": 10},
    )
    assert url.endswith("/historical-price-eod/full")
    assert params["to"] == et_date.isoformat()
    assert params["from"] == (et_date - timedelta(days=20)).isoformat()


@pytest.mark.parametrize(
    "rel_path,method",
    [
        ("skills/macro-regime-detector/scripts/fmp_client.py", "_get_from_yfinance"),
        ("skills/market-top-detector/scripts/fmp_client.py", "_get_hist_from_yfinance"),
    ],
)
def test_yfinance_fallback_end_is_et_date(rel_path, method, monkeypatch):
    mod = _load(rel_path)
    anchor = datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    et_date = anchor.astimezone(ZoneInfo("America/New_York")).date()
    monkeypatch.setattr(mod, "_et_today", lambda now=None: et_date)
    captured = {}

    class _FakeYF:
        @staticmethod
        def download(symbol, **kwargs):
            captured.update(kwargs)
            return None

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)
    client = mod.FMPClient(api_key=None)
    assert getattr(client, method)("SPY", 100) is None
    assert captured["end"] == et_date.isoformat()
    assert captured["start"] == (et_date - timedelta(days=int(100 * 1.5))).isoformat()
