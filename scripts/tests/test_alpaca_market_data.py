"""Alpaca-first market data in the generated FMP clients.

Alpaca is the default source for the data it actually carries (US equity / ETF
daily OHLCV and the quote fields derivable from it). FMP stays the source for
everything else (fundamentals, calendars, profiles, non-US symbols, indices)
and the fallback whenever Alpaca is unconfigured, disabled, or returns nothing.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VCP_SCRIPTS = REPO_ROOT / "skills" / "vcp-screener" / "scripts"

GENERATED_CLIENTS = [
    # family A (quote surface)
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
    "skills/ftd-detector/scripts/fmp_client.py",
    # family B
    "skills/pead-screener/scripts/fmp_client.py",
    "skills/earnings-trade-analyzer/scripts/fmp_client.py",
    "skills/ibd-distribution-day-monitor/scripts/fmp_client.py",
    "skills/value-dividend-screener/scripts/fmp_client.py",
    # specials
    "skills/canslim-screener/scripts/fmp_client.py",
    "skills/macro-regime-detector/scripts/fmp_client.py",
    "skills/market-top-detector/scripts/fmp_client.py",
]
GARP_CLIENT = "skills/us-undervalued-growth-screener/scripts/fmp_client.py"
QUOTE_CLIENTS = [
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
    "skills/ftd-detector/scripts/fmp_client.py",
    "skills/canslim-screener/scripts/fmp_client.py",
    "skills/market-top-detector/scripts/fmp_client.py",
]


def _load_file(path: pathlib.Path, name: str):
    sys.modules.pop(name, None)
    for shared in ("_fmp_compat", "_alpaca_data"):
        sys.modules.pop(shared, None)
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


@pytest.fixture
def alpaca_mod():
    return _load_file(VCP_SCRIPTS / "_alpaca_data.py", "_alpaca_data_under_test")


@pytest.fixture
def alpaca_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")  # pragma: allowlist secret
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")  # pragma: allowlist secret
    monkeypatch.delenv("MARKET_DATA_SOURCE", raising=False)
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret


def _bar(day: int, close: float, volume: int = 1_000_000, high=None, low=None):
    return {
        "t": f"2026-01-{day:02d}T05:00:00Z",
        "o": close - 1,
        "h": high if high is not None else close + 1,
        "l": low if low is not None else close - 2,
        "c": close,
        "v": volume,
    }


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


# --- symbol eligibility -------------------------------------------------------


@pytest.mark.parametrize("sym", ["AAPL", "SPY", "BRK-B", "BRK.B", "QQQ", "F"])
def test_us_symbols_are_alpaca_eligible(alpaca_mod, sym):
    assert alpaca_mod.is_us_equity_symbol(sym)


@pytest.mark.parametrize(
    "sym", ["RHM.DE", "SAP.DE", "NOVO-B.CO", "^GSPC", "EURUSD=X", "BTC-USD", "", "aapl", "TOOLONG"]
)
def test_non_us_symbols_are_not_alpaca_eligible(alpaca_mod, sym):
    assert not alpaca_mod.is_us_equity_symbol(sym)


# --- enablement ---------------------------------------------------------------


def test_from_env_none_without_keys(alpaca_mod, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    assert alpaca_mod.AlpacaDailyBars.from_env() is None


def test_from_env_none_when_fmp_forced(alpaca_mod, alpaca_env, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_SOURCE", "fmp")
    assert alpaca_mod.AlpacaDailyBars.from_env() is None


def test_from_env_enabled_with_keys(alpaca_mod, alpaca_env):
    assert alpaca_mod.AlpacaDailyBars.from_env() is not None


# --- bars ---------------------------------------------------------------------


def test_daily_bars_fmp_shape_most_recent_first_and_trimmed(alpaca_mod, alpaca_env):
    calls = []

    def fake_get(url, params):
        calls.append(params)
        return _Resp(200, {"bars": {"AAPL": [_bar(d, 100 + d) for d in range(1, 11)]}})

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = fake_get
    out = a.daily_bars(["AAPL"], days=5)
    rows = out["AAPL"]
    assert len(rows) == 5
    assert rows[0]["date"] == "2026-01-10"
    assert rows[0]["close"] == 110
    assert set(rows[0]) >= {"date", "open", "high", "low", "close", "adjClose", "volume"}
    assert calls[0]["timeframe"] == "1Day"
    assert calls[0]["adjustment"] == "split"


def test_daily_bars_batches_symbols_and_maps_class_shares(alpaca_mod, alpaca_env):
    seen = []

    def fake_get(url, params):
        seen.append(params["symbols"])
        return _Resp(200, {"bars": {"BRK.B": [_bar(1, 500)], "MSFT": [_bar(1, 400)]}})

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = fake_get
    out = a.daily_bars(["BRK-B", "MSFT"], days=10)
    assert len(seen) == 1
    assert "BRK.B" in seen[0].split(",")
    assert out["BRK-B"][0]["close"] == 500  # keyed back to the requested spelling
    assert out["MSFT"][0]["close"] == 400


def test_daily_bars_follows_pagination(alpaca_mod, alpaca_env):
    pages = [
        _Resp(200, {"bars": {"AAPL": [_bar(1, 1)]}, "next_page_token": "p2"}),
        _Resp(200, {"bars": {"AAPL": [_bar(2, 2)]}, "next_page_token": None}),
    ]
    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = lambda url, params: pages.pop(0)
    rows = a.daily_bars(["AAPL"], days=10)["AAPL"]
    assert [r["close"] for r in rows] == [2, 1]


def test_daily_bars_falls_back_to_iex_feed_on_403(alpaca_mod, alpaca_env):
    feeds = []

    def fake_get(url, params):
        feeds.append(params["feed"])
        if params["feed"] == "sip":
            return _Resp(403, {"message": "subscription does not permit querying recent SIP data"})
        return _Resp(200, {"bars": {"AAPL": [_bar(1, 1)]}})

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = fake_get
    assert a.daily_bars(["AAPL"], days=5)["AAPL"][0]["close"] == 1
    assert feeds == ["sip", "iex"]


def test_daily_bars_skips_ineligible_and_swallows_errors(alpaca_mod, alpaca_env):
    def boom(url, params):
        raise OSError("network down")

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = boom
    assert a.daily_bars(["AAPL", "RHM.DE"], days=5) == {}


def test_daily_bars_cached_per_symbol(alpaca_mod, alpaca_env):
    n = {"calls": 0}

    def fake_get(url, params):
        n["calls"] += 1
        return _Resp(200, {"bars": {"AAPL": [_bar(d, d) for d in range(1, 21)]}})

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = fake_get
    a.daily_bars(["AAPL"], days=20)
    a.daily_bars(["AAPL"], days=10)
    assert n["calls"] == 1


# --- quotes -------------------------------------------------------------------


def test_quotes_derived_from_bars(alpaca_mod, alpaca_env):
    bars = [_bar(d, 100 + d, volume=1000 * d, high=200 if d == 3 else None) for d in range(1, 11)]
    bars[0]["l"] = 50  # 52w low on day 1

    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = lambda url, params: _Resp(200, {"bars": {"AAPL": bars}})
    q = a.quotes(["AAPL"])["AAPL"]
    assert q["symbol"] == "AAPL"
    assert q["price"] == 110
    assert q["previousClose"] == 109
    assert q["change"] == pytest.approx(1)
    assert q["changesPercentage"] == pytest.approx(100 / 109)
    assert q["yearHigh"] == 200
    assert q["yearLow"] == 50
    assert q["volume"] == 10_000
    assert q["avgVolume"] == pytest.approx(sum(1000 * d for d in range(1, 11)) / 10)
    assert q["dataSource"] == "alpaca"
    assert "marketCap" not in q  # Alpaca has no fundamentals; never fabricate them


# --- generated clients route through Alpaca -----------------------------------


class _FakeAlpaca:
    def __init__(self, bars=None):
        self.bars = bars or {}

    def daily_bars(self, symbols, days):
        return {s: self.bars[s][:days] for s in symbols if s in self.bars}

    def quotes(self, symbols):
        return {
            s: {"symbol": s, "price": self.bars[s][0]["close"]} for s in symbols if s in self.bars
        }


ROWS = [
    {
        "date": "2026-01-02",
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
        "adjClose": 1.5,
        "volume": 10,
    }
]


def _client(rel_path):
    path = REPO_ROOT / rel_path
    mod = _load_file(path, "_alp_client_" + path.parent.parent.name.replace("-", "_"))
    return mod, mod.FMPClient(api_key="test_key")  # pragma: allowlist secret


def _no_yfinance(client, monkeypatch):
    for name in ("_get_from_yfinance", "_get_hist_from_yfinance", "_get_quote_from_yfinance"):
        if hasattr(client, name):
            monkeypatch.setattr(client, name, lambda *a, **k: None)


def _quotes(client, symbols):
    if hasattr(client, "get_batch_quotes"):
        return client.get_batch_quotes(symbols)
    return {q["symbol"]: q for q in client.get_quote(",".join(symbols)) or []}


def _unwrap(result):
    return result["historical"] if isinstance(result, dict) else result


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_client_has_alpaca_when_keys_set(rel_path, alpaca_env):
    _, client = _client(rel_path)
    assert client._alpaca is not None


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_client_alpaca_disabled_when_fmp_forced(rel_path, alpaca_env, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_SOURCE", "fmp")
    _, client = _client(rel_path)
    assert client._alpaca is None


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_client_history_prefers_alpaca(rel_path, alpaca_env, monkeypatch):
    _, client = _client(rel_path)
    client._alpaca = _FakeAlpaca({"AAPL": ROWS})
    monkeypatch.setattr(
        client, "_rate_limited_get", lambda *a, **k: pytest.fail("FMP must not be called")
    )
    assert _unwrap(client.get_historical_prices("AAPL", days=5)) == ROWS


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_client_history_falls_back_to_fmp(rel_path, alpaca_env, monkeypatch):
    _, client = _client(rel_path)
    client._alpaca = _FakeAlpaca({})  # Alpaca has nothing for this symbol
    called = {"fmp": 0}

    def fake_fmp(*a, **k):
        called["fmp"] += 1
        return None

    monkeypatch.setattr(client, "_rate_limited_get", fake_fmp)
    _no_yfinance(client, monkeypatch)
    client.get_historical_prices("RHM.DE", days=5)
    assert called["fmp"] >= 1


@pytest.mark.parametrize("rel_path", QUOTE_CLIENTS)
def test_client_quotes_prefer_alpaca(rel_path, alpaca_env, monkeypatch):
    _, client = _client(rel_path)
    client._alpaca = _FakeAlpaca({"AAPL": ROWS, "MSFT": ROWS})
    monkeypatch.setattr(
        client, "_rate_limited_get", lambda *a, **k: pytest.fail("FMP must not be called")
    )
    got = _quotes(client, ["AAPL", "MSFT"])
    assert set(got) == {"AAPL", "MSFT"}
    single = client.get_quote("AAPL")
    assert single[0]["symbol"] == "AAPL"


@pytest.mark.parametrize("rel_path", QUOTE_CLIENTS)
def test_client_quotes_fall_back_to_fmp_for_missing(rel_path, alpaca_env, monkeypatch):
    _, client = _client(rel_path)
    client._alpaca = _FakeAlpaca({"AAPL": ROWS})
    asked = []

    def fake_quote(self_, symbols):
        asked.append(symbols)
        return [{"symbol": s, "price": 9} for s in symbols.split(",")]

    monkeypatch.setattr(type(client), "_fmp_get_quote", fake_quote)
    got = _quotes(client, ["AAPL", "RHM.DE"])
    assert got["AAPL"]["price"] == 1.5
    assert got["RHM.DE"]["price"] == 9
    assert all("AAPL" not in a for a in asked)


def test_garp_history_prefers_alpaca(alpaca_env, monkeypatch, tmp_path):
    path = REPO_ROOT / GARP_CLIENT
    mod = _load_file(path, "_alp_client_garp")
    client = mod.FMPClient(
        api_key="test_key", cache_path=tmp_path / "c.sqlite3"
    )  # pragma: allowlist secret
    assert client._alpaca is not None

    class _Fake:
        def daily_bars_between(self, symbol, from_date, to_date):
            if symbol != "AAPL":
                return None
            return [dict(ROWS[0], date="2026-01-01"), dict(ROWS[0], date="2026-01-02")]

    client._alpaca = _Fake()
    monkeypatch.setattr(
        client, "_stable_then_v3", lambda *a, **k: pytest.fail("FMP must not be called")
    )
    rows = client.get_historical_prices("AAPL", from_date="2026-01-01", to_date="2026-01-02")
    assert [r["date"] for r in rows] == ["2026-01-02", "2026-01-01"]

    called = {"fmp": 0}

    def fake_fmp(*a, **k):
        called["fmp"] += 1
        return []

    monkeypatch.setattr(client, "_stable_then_v3", fake_fmp)
    client.get_historical_prices("RHM.DE", from_date="2026-01-01", to_date="2026-01-02")
    assert called["fmp"] == 1


def test_daily_bars_between_filters_range(alpaca_mod, alpaca_env):
    a = alpaca_mod.AlpacaDailyBars.from_env()
    a._http_get = lambda url, params: _Resp(
        200, {"bars": {"AAPL": [_bar(d, d) for d in range(1, 6)]}}
    )
    rows = a.daily_bars_between("AAPL", "2026-01-02", "2026-01-04")
    assert [r["date"] for r in rows] == ["2026-01-02", "2026-01-03", "2026-01-04"]
    assert a.daily_bars_between("RHM.DE", "2026-01-02", "2026-01-04") is None
