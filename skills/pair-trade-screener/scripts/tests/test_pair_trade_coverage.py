"""Coverage-oriented contract tests for pair search and spread analysis (Issue #293).

All HTTP is faked, sleeps are patched, and price series are deterministic.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import analyze_spread
import find_pairs
import numpy as np
import pandas as pd
import pytest
import requests
import statsmodels_support

MODULES = (find_pairs, analyze_spread)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=False):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("bad json")
        return self._payload


def install_http(monkeypatch, module, handler):
    """Route module.requests.get to handler(url, **kwargs) and record calls."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        result = handler(url, **kwargs)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module, "_endpoint_failures", {})
    return calls


def history_payload(n=5, adj=True):
    """Newest-first FMP style payload: close = 100 + index (newest has highest index)."""
    rows = []
    for i in range(n):
        day = n - 1 - i  # newest first
        row = {"date": f"2025-01-{day + 1:02d}", "close": 100.0 + day}
        if adj:
            row["adjClose"] = 200.0 + day
        rows.append(row)
    return {"symbol": "AAA", "historical": rows}


def cointegrated_prices(length=320, seed=11):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-01", periods=length, freq="D")
    stock_b = 100 + np.cumsum(rng.normal(0, 0.8, length))
    spread = np.zeros(length)
    for position in range(1, length):
        spread[position] = 0.6 * spread[position - 1] + rng.normal(0, 0.5)
    stock_a = 1.2 * stock_b + spread
    return (
        pd.Series(stock_a, index=index, name="AAA"),
        pd.Series(stock_b, index=index, name="BBB"),
    )


def independent_walks(length=320):
    rng = np.random.default_rng(3)
    index = pd.date_range("2025-01-01", periods=length, freq="D")
    a = 100 + np.cumsum(rng.normal(0, 1.0, length))
    b = 100 + np.cumsum(rng.normal(0, 1.0, length))
    return pd.Series(a, index=index), pd.Series(b, index=index)


def pair_dict(**overrides):
    base = {
        "pair": "AAA/BBB",
        "stock_a": "AAA",
        "stock_b": "BBB",
        "correlation": 0.95,
        "beta": 1.2,
        "cointegration_pvalue": 0.01,
        "adf_statistic": -4.2,
        "critical_value_5pct": -2.9,
        "is_cointegrated": True,
        "half_life_days": 5.0,
        "current_zscore": 2.5,
        "signal": "SHORT",
        "strength": "★★★",
        "timestamp": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# statsmodels_support
# ---------------------------------------------------------------------------


def test_require_statsmodels_returns_callables():
    auto_reg, adfuller = statsmodels_support.require_statsmodels()

    assert auto_reg.__name__ == "AutoReg"
    assert adfuller.__name__ == "adfuller"


def test_require_statsmodels_missing_dependency_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "statsmodels.tsa.ar_model", None)

    with pytest.raises(RuntimeError) as excinfo:
        statsmodels_support.require_statsmodels()

    message = str(excinfo.value)
    assert "statsmodels>=0.14,<0.15 is required" in message
    assert statsmodels_support.INSTALL_COMMAND in message
    assert isinstance(excinfo.value.__cause__, ImportError)


# ---------------------------------------------------------------------------
# API key handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", MODULES)
def test_get_api_key_prefers_argument_over_environment(monkeypatch, module):
    monkeypatch.setenv("FMP_API_KEY", "from-env")  # pragma: allowlist secret

    assert module.get_api_key("from-arg") == "from-arg"


@pytest.mark.parametrize("module", MODULES)
def test_get_api_key_falls_back_to_environment(monkeypatch, module):
    monkeypatch.setenv("FMP_API_KEY", "from-env")  # pragma: allowlist secret

    assert module.get_api_key(None) == "from-env"


@pytest.mark.parametrize("module", MODULES)
def test_get_api_key_missing_exits_with_code_1(monkeypatch, capsys, module):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        module.get_api_key(None)

    assert excinfo.value.code == 1
    assert "FMP_API_KEY not found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# find_pairs.fetch_sector_stocks
# ---------------------------------------------------------------------------


def test_fetch_sector_stocks_filters_inactive_and_maps_fields(monkeypatch):
    payload = [
        {
            "symbol": "AAA",
            "companyName": "Alpha Inc",
            "marketCap": 5_000_000_000,
            "sector": "Technology",
            "exchangeShortName": "NASDAQ",
            "isActivelyTrading": True,
        },
        {"symbol": "DEAD", "isActivelyTrading": False},
        {"symbol": "BARE"},
    ]
    calls = install_http(monkeypatch, find_pairs, lambda url, **kw: FakeResponse(200, payload))

    stocks = find_pairs.fetch_sector_stocks("Technology", "key", 1_000)

    assert [s["symbol"] for s in stocks] == ["AAA", "BARE"]
    assert stocks[0] == {
        "symbol": "AAA",
        "name": "Alpha Inc",
        "marketCap": 5_000_000_000,
        "sector": "Technology",
        "exchange": "NASDAQ",
    }
    assert stocks[1] == {
        "symbol": "BARE",
        "name": "",
        "marketCap": 0,
        "sector": "Technology",
        "exchange": "",
    }
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.endswith("/stable/company-screener")
    assert kwargs["headers"] == {"apikey": "key"}  # pragma: allowlist secret
    assert kwargs["params"]["marketCapMoreThan"] == 1_000


def test_fetch_sector_stocks_falls_back_through_failures(monkeypatch, capsys):
    responses = iter(
        [requests.exceptions.ConnectionError("boom"), FakeResponse(200, [{"symbol": "ZZZ"}])]
    )
    calls = install_http(monkeypatch, find_pairs, lambda url, **kw: next(responses))

    stocks = find_pairs.fetch_sector_stocks("Energy", "key")

    assert [s["symbol"] for s in stocks] == ["ZZZ"]
    assert calls[1][0].endswith("/api/v3/stock-screener")
    assert "screener request failed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "first",
    (
        FakeResponse(500, None),
        FakeResponse(200, None, json_error=True),
        FakeResponse(200, []),
    ),
)
def test_fetch_sector_stocks_skips_bad_first_endpoint(monkeypatch, first):
    responses = iter([first, FakeResponse(200, [{"symbol": "OK"}])])
    calls = install_http(monkeypatch, find_pairs, lambda url, **kw: next(responses))

    stocks = find_pairs.fetch_sector_stocks("Energy", "key")

    assert [s["symbol"] for s in stocks] == ["OK"]
    assert len(calls) == 2


def test_fetch_sector_stocks_exits_when_nothing_found(monkeypatch, capsys):
    install_http(monkeypatch, find_pairs, lambda url, **kw: FakeResponse(200, []))

    with pytest.raises(SystemExit) as excinfo:
        find_pairs.fetch_sector_stocks("Nowhere", "key", 5_000_000)

    assert excinfo.value.code == 1
    assert "No stocks found in Nowhere sector with market cap > $5,000,000" in (
        capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# Historical price fetching (both modules share the same contract)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_stable_endpoint_uses_symbol_query(monkeypatch, module):
    calls = install_http(
        monkeypatch, module, lambda url, **kw: FakeResponse(200, history_payload())
    )

    data = module._fetch_raw_historical("AAA", "key", params={"x": 1})

    assert len(data["historical"]) == 5
    url, kwargs = calls[0]
    assert url.endswith("/stable/historical-price-eod/full")
    assert kwargs["params"] == {"x": 1, "symbol": "AAA"}
    assert kwargs["headers"] == {"apikey": "key"}  # pragma: allowlist secret


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_falls_back_to_v3_path(monkeypatch, module):
    def handler(url, **kw):
        if "stable" in url:
            return FakeResponse(404, None)
        return FakeResponse(200, history_payload())

    calls = install_http(monkeypatch, module, handler)

    data = module._fetch_raw_historical("BRK-B", "key")

    assert data["symbol"] == "AAA"
    assert calls[1][0].endswith("/api/v3/historical-price-full/BRK-B")
    assert calls[1][1]["params"] == {}
    assert module._endpoint_failures[module._FMP_HIST_ENDPOINTS[0][0]] == 1


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_unwraps_historical_stock_list(monkeypatch, module):
    payload = {
        "historicalStockList": [
            {"symbol": "OTHER", "historical": [{"date": "2025-01-01", "close": 1}]},
            {"symbol": "BRK.B", "historical": [{"date": "2025-01-02", "close": 2}]},
        ]
    }
    install_http(monkeypatch, module, lambda url, **kw: FakeResponse(200, payload))

    data = module._fetch_raw_historical("BRK-B", "key")

    assert data == {"symbol": "BRK.B", "historical": [{"date": "2025-01-02", "close": 2}]}


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_returns_none_for_unrecognized_payloads(monkeypatch, module):
    calls = install_http(
        monkeypatch,
        module,
        lambda url, **kw: FakeResponse(200, {"historicalStockList": [{"symbol": "X"}]}),
    )

    assert module._fetch_raw_historical("AAA", "key") is None
    assert len(calls) == 2
    assert all(count == 1 for count in module._endpoint_failures.values())


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_circuit_breaker_skips_failing_endpoint(monkeypatch, module):
    calls = install_http(
        monkeypatch,
        module,
        lambda url, **kw: requests.exceptions.Timeout("slow"),
    )

    for _ in range(3):
        assert module._fetch_raw_historical("AAA", "key") is None
    assert len(calls) == 6
    assert module._fetch_raw_historical("AAA", "key") is None
    assert len(calls) == 6  # both endpoints tripped, no further requests


@pytest.mark.parametrize("module", MODULES)
def test_raw_historical_success_resets_failure_counter(monkeypatch, module):
    install_http(monkeypatch, module, lambda url, **kw: FakeResponse(200, history_payload()))
    stable = module._FMP_HIST_ENDPOINTS[0][0]
    module._endpoint_failures[stable] = 2

    assert module._fetch_raw_historical("AAA", "key") is not None
    assert module._endpoint_failures[stable] == 0


@pytest.mark.parametrize("module", MODULES)
def test_fetch_historical_prices_orders_chronologically_and_prefers_adjclose(monkeypatch, module):
    install_http(monkeypatch, module, lambda url, **kw: FakeResponse(200, history_payload(5)))

    prices = module.fetch_historical_prices("AAA", "key", lookback_days=3)

    # newest 3 rows (days 4,3,2), reversed to chronological order
    assert list(prices.values) == [202.0, 203.0, 204.0]
    assert [d.day for d in prices.index] == [3, 4, 5]
    assert prices.name == "AAA"


@pytest.mark.parametrize("module", MODULES)
def test_fetch_historical_prices_falls_back_to_close(monkeypatch, module):
    install_http(
        monkeypatch, module, lambda url, **kw: FakeResponse(200, history_payload(3, adj=False))
    )

    prices = module.fetch_historical_prices("AAA", "key", lookback_days=10)

    assert list(prices.values) == [100.0, 101.0, 102.0]


def test_find_pairs_fetch_historical_prices_returns_none_without_data(monkeypatch):
    install_http(monkeypatch, find_pairs, lambda url, **kw: FakeResponse(500, None))

    assert find_pairs.fetch_historical_prices("AAA", "key") is None


def test_analyze_spread_fetch_historical_prices_reports_missing_data(monkeypatch, capsys):
    install_http(monkeypatch, analyze_spread, lambda url, **kw: FakeResponse(500, None))

    assert analyze_spread.fetch_historical_prices("AAA", "key") is None
    assert "ERROR: No data found for AAA" in capsys.readouterr().out


def test_fetch_price_data_batch_keeps_only_sufficient_history(monkeypatch, capsys):
    sleeps = []
    monkeypatch.setattr(find_pairs.time, "sleep", sleeps.append)
    long_series = pd.Series(np.arange(250.0), index=pd.date_range("2025-01-01", periods=250))
    short_series = long_series.iloc[:249]
    lookup = {"LONG": long_series, "SHORT": short_series, "NONE": None}
    monkeypatch.setattr(
        find_pairs, "fetch_historical_prices", lambda symbol, key, days: lookup[symbol]
    )

    result = find_pairs.fetch_price_data_batch(["LONG", "SHORT", "NONE"], "key", 500)

    assert list(result) == ["LONG"]
    assert sleeps == [0.3, 0.3, 0.3]
    out = capsys.readouterr().out
    assert "Failed: SHORT, NONE" in out
    assert "(250 days)" in out


# ---------------------------------------------------------------------------
# find_pairs statistics
# ---------------------------------------------------------------------------


def test_align_finite_prices_wraps_alignment_errors(monkeypatch):
    def boom(*_args, **_kwargs):
        raise TypeError("cannot concat")

    monkeypatch.setattr(find_pairs.pd, "concat", boom)

    with pytest.raises(ValueError, match="could not be aligned"):
        find_pairs._align_finite_prices([1, 2], [1, 2])


def test_align_finite_prices_requires_minimum_observations():
    a = pd.Series([1.0, np.nan, 3.0], index=[0, 1, 2])
    b = pd.Series([1.0, 2.0, np.inf], index=[0, 1, 2])

    with pytest.raises(ValueError, match="at least 2 paired finite observations"):
        find_pairs._align_finite_prices(a, b)


def test_align_finite_prices_inner_joins_on_index_and_coerces_text():
    a = pd.Series(["1", "2", "x", "4"], index=[0, 1, 2, 3])
    b = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0], index=[0, 1, 2, 3, 4])

    left, right = find_pairs._align_finite_prices(a, b)

    assert list(left.index) == [0, 1, 3]
    assert list(left.values) == [1.0, 2.0, 4.0]
    assert list(right.values) == [10.0, 20.0, 40.0]


def test_calculate_correlation_constant_series_is_none():
    index = pd.date_range("2025-01-01", periods=150)
    constant = pd.Series(np.ones(150), index=index)
    varying = pd.Series(np.arange(150.0), index=index)

    assert find_pairs.calculate_correlation(constant, varying) is None


def test_calculate_correlation_perfect_linear_relationship():
    index = pd.date_range("2025-01-01", periods=150)
    a = pd.Series(np.arange(150.0), index=index)

    assert find_pairs.calculate_correlation(a, a * 3 + 1) == pytest.approx(1.0)


def test_calculate_beta_recovers_slope_intercept_and_r_squared():
    index = pd.date_range("2025-01-01", periods=50)
    b = pd.Series(np.arange(1.0, 51.0), index=index)
    a = 2.5 * b + 7.0

    result = find_pairs.calculate_beta(a, b)

    assert result["beta"] == pytest.approx(2.5)
    assert result["intercept"] == pytest.approx(7.0)
    assert result["r_squared"] == pytest.approx(1.0)


def test_test_cointegration_returns_none_when_adf_fails(monkeypatch):
    def failing_adf(*_args, **_kwargs):
        raise ValueError("adf failure")

    monkeypatch.setattr(find_pairs, "require_statsmodels", lambda: (None, failing_adf))
    a, b = cointegrated_prices()

    assert find_pairs.test_cointegration(a, b, 1.2) is None


def test_test_cointegration_reports_critical_values_and_spread():
    a, b = cointegrated_prices()
    beta = find_pairs.calculate_beta(a, b)["beta"]

    result = find_pairs.test_cointegration(a, b, beta)

    assert result["is_cointegrated"] is True
    assert result["critical_value_1pct"] < result["critical_value_5pct"]
    assert result["critical_value_5pct"] < result["critical_value_10pct"] < 0
    assert result["adf_statistic"] < result["critical_value_1pct"]
    pd.testing.assert_series_equal(result["spread"], a - beta * b, check_names=False)


def test_test_cointegration_independent_walks_not_cointegrated():
    a, b = independent_walks()
    beta = find_pairs.calculate_beta(a, b)["beta"]

    result = find_pairs.test_cointegration(a, b, beta)

    assert result["is_cointegrated"] is False
    assert result["p_value"] >= 0.05


@pytest.mark.parametrize("module", MODULES)
def test_half_life_matches_ar1_coefficient(module):
    rng = np.random.default_rng(5)
    values = np.zeros(2000)
    for i in range(1, 2000):
        values[i] = 0.9 * values[i - 1] + rng.normal()
    spread = pd.Series(values)

    half_life = module.calculate_half_life(spread)

    assert half_life == pytest.approx(-np.log(2) / np.log(0.9), rel=0.25)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    "spread",
    (
        pd.Series([1.0, -1.0] * 50),  # phi near -1: not mean reverting
        pd.Series(1.1 ** np.arange(60)),  # explosive: phi > 1
        pd.Series([5.0]),  # too short, model fit raises
    ),
    ids=("negative-phi", "explosive", "too-short"),
)
def test_half_life_none_when_no_mean_reversion(module, spread):
    assert module.calculate_half_life(spread) is None


def test_current_zscore_uses_trailing_window():
    spread = pd.Series([100.0] * 10 + [0.0, 1.0, 2.0, 3.0, 4.0])

    zscore = find_pairs.calculate_current_zscore(spread, window=5)

    assert zscore == pytest.approx((4.0 - 2.0) / np.std([0, 1, 2, 3, 4], ddof=1))


def test_current_zscore_shrinks_window_for_short_series():
    spread = pd.Series([1.0, 2.0, 3.0])

    zscore = find_pairs.calculate_current_zscore(spread, window=90)

    assert zscore == pytest.approx(1.0)


def test_current_zscore_none_for_nonfinite_std():
    assert find_pairs.calculate_current_zscore(pd.Series([1.0])) is None


# ---------------------------------------------------------------------------
# analyze_pair
# ---------------------------------------------------------------------------


def patch_pipeline(monkeypatch, *, zscore, p_value=0.001, cointegrated=True, half_life=7.0):
    a, b = cointegrated_prices()
    spread = a - b
    monkeypatch.setattr(find_pairs, "calculate_correlation", lambda *_a: 0.91234)
    monkeypatch.setattr(
        find_pairs,
        "calculate_beta",
        lambda *_a: {"beta": 1.23456, "intercept": 0.0, "r_squared": 0.8},
    )
    monkeypatch.setattr(
        find_pairs,
        "test_cointegration",
        lambda *_a: {
            "is_cointegrated": cointegrated,
            "p_value": p_value,
            "adf_statistic": -3.98768,
            "critical_value_5pct": -2.87654,
            "spread": spread,
        },
    )
    half_life_calls = []

    def fake_half_life(_spread):
        half_life_calls.append(1)
        return half_life

    monkeypatch.setattr(find_pairs, "calculate_half_life", fake_half_life)
    monkeypatch.setattr(find_pairs, "calculate_current_zscore", lambda _s: zscore)
    return a, b, half_life_calls


@pytest.mark.parametrize(
    ("zscore", "p_value", "signal", "strength"),
    (
        (2.5, 0.001, "SHORT", "★★★"),
        (-2.5, 0.02, "LONG", "★★"),
        (1.0, 0.2, "NONE", "☆"),
        (2.0, 0.01, "NONE", "★★"),
        (-2.0, 0.05, "NONE", "☆"),
    ),
)
def test_analyze_pair_signal_and_strength_rules(monkeypatch, zscore, p_value, signal, strength):
    a, b, _ = patch_pipeline(monkeypatch, zscore=zscore, p_value=p_value)

    result = find_pairs.analyze_pair("AAA", "BBB", a, b)

    assert result["signal"] == signal
    assert result["strength"] == strength
    assert result["pair"] == "AAA/BBB"
    assert result["correlation"] == 0.9123
    assert result["beta"] == 1.2346
    assert result["adf_statistic"] == -3.9877
    assert result["critical_value_5pct"] == -2.8765
    assert result["half_life_days"] == 7.0
    assert result["current_zscore"] == round(zscore, 2)
    assert datetime.fromisoformat(result["timestamp"])


def test_analyze_pair_skips_half_life_when_not_cointegrated(monkeypatch):
    a, b, half_life_calls = patch_pipeline(monkeypatch, zscore=1.0, cointegrated=False)

    result = find_pairs.analyze_pair("AAA", "BBB", a, b)

    assert half_life_calls == []
    assert result["half_life_days"] is None
    assert result["is_cointegrated"] is False


def test_analyze_pair_rejects_low_correlation(monkeypatch):
    a, b, _ = patch_pipeline(monkeypatch, zscore=1.0)
    monkeypatch.setattr(find_pairs, "calculate_correlation", lambda *_a: 0.5)

    assert find_pairs.analyze_pair("AAA", "BBB", a, b, min_correlation=0.7) is None


def test_analyze_pair_rejects_missing_correlation(monkeypatch):
    a, b, _ = patch_pipeline(monkeypatch, zscore=1.0)
    monkeypatch.setattr(find_pairs, "calculate_correlation", lambda *_a: None)

    assert find_pairs.analyze_pair("AAA", "BBB", a, b) is None


def test_analyze_pair_rejects_beta_failure(monkeypatch):
    a, b, _ = patch_pipeline(monkeypatch, zscore=1.0)

    def bad_beta(*_a):
        raise ValueError("flat")

    monkeypatch.setattr(find_pairs, "calculate_beta", bad_beta)

    assert find_pairs.analyze_pair("AAA", "BBB", a, b) is None


def test_analyze_pair_rejects_failed_cointegration_test(monkeypatch):
    a, b, _ = patch_pipeline(monkeypatch, zscore=1.0)
    monkeypatch.setattr(find_pairs, "test_cointegration", lambda *_a: None)

    assert find_pairs.analyze_pair("AAA", "BBB", a, b) is None


def test_analyze_pair_end_to_end_on_real_series():
    a, b = cointegrated_prices()

    result = find_pairs.analyze_pair("AAA", "BBB", a, b, min_correlation=0.5)

    assert result["is_cointegrated"] is True
    assert result["strength"] == "★★★"
    assert result["beta"] == pytest.approx(1.2, abs=0.05)
    assert result["half_life_days"] > 0
    z = result["current_zscore"]
    assert result["signal"] == ("SHORT" if z > 2.0 else "LONG" if z < -2.0 else "NONE")


def test_analyze_pair_reports_independent_walks_as_not_cointegrated():
    a, b = independent_walks()

    result = find_pairs.analyze_pair("AAA", "BBB", a, b, min_correlation=0.0)

    assert result is not None
    assert result["is_cointegrated"] is False
    assert result["half_life_days"] is None


# ---------------------------------------------------------------------------
# screen_all_pairs, rank_pairs, save_results, print_summary
# ---------------------------------------------------------------------------


def test_screen_all_pairs_keeps_only_cointegrated_results(monkeypatch, capsys):
    outcomes = {
        ("A", "B"): pair_dict(pair="A/B"),
        ("A", "C"): pair_dict(pair="A/C", is_cointegrated=False),
        ("B", "C"): None,
    }
    monkeypatch.setattr(find_pairs, "analyze_pair", lambda sa, sb, pa, pb, mc: outcomes[(sa, sb)])
    data = {name: pd.Series([1.0]) for name in "ABC"}

    result = find_pairs.screen_all_pairs(data, min_correlation=0.8)

    assert [r["pair"] for r in result] == ["A/B"]
    out = capsys.readouterr().out
    assert "Total possible pairs: 3" in out
    assert "Minimum correlation: 0.8" in out
    assert "Found 1 cointegrated pairs" in out


def test_screen_all_pairs_swallows_type_and_value_errors(monkeypatch):
    def flaky(sa, sb, pa, pb, mc):
        if sb == "B":
            raise TypeError("bad")
        if sb == "C":
            raise ValueError("worse")
        return pair_dict(pair=f"{sa}/{sb}")

    monkeypatch.setattr(find_pairs, "analyze_pair", flaky)
    data = {name: pd.Series([1.0]) for name in "ABCD"}

    result = find_pairs.screen_all_pairs(data)

    assert [r["pair"] for r in result] == ["A/D", "B/D", "C/D"]


def test_screen_all_pairs_progress_reported_every_tenth_pair(monkeypatch, capsys):
    monkeypatch.setattr(find_pairs, "analyze_pair", lambda *_a: None)
    data = {f"S{i}": pd.Series([1.0]) for i in range(6)}  # 15 pairs

    assert find_pairs.screen_all_pairs(data) == []

    out = capsys.readouterr().out
    assert "[10/15] pairs analyzed" in out
    assert "[15/15] pairs analyzed" in out


def test_rank_pairs_sorts_by_pvalue_then_abs_zscore(capsys):
    pairs = [
        pair_dict(pair="C", cointegration_pvalue=0.02, current_zscore=0.1),
        pair_dict(pair="B", cointegration_pvalue=0.01, current_zscore=-1.0),
        pair_dict(pair="A", cointegration_pvalue=0.01, current_zscore=-3.0),
        pair_dict(pair="D", cointegration_pvalue=0.01, current_zscore=None),
    ]

    ranked = find_pairs.rank_pairs(pairs)

    assert [p["pair"] for p in ranked] == ["A", "B", "D", "C"]
    out = capsys.readouterr().out
    assert "1. A (p=0.0100, z=-3.00" in out
    assert "z=N/A" in out


def test_save_results_writes_metadata_counts(tmp_path):
    pairs = [
        pair_dict(pair="A/B"),
        pair_dict(pair="C/D", signal="NONE"),
        pair_dict(pair="E/F", is_cointegrated=False, signal="LONG"),
    ]
    out = tmp_path / "deep" / "dir" / "out.json"

    find_pairs.save_results(pairs, str(out))

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["metadata"]["total_pairs"] == 3
    assert payload["metadata"]["cointegrated_pairs"] == 2
    assert payload["metadata"]["active_signals"] == 2
    assert [p["pair"] for p in payload["pairs"]] == ["A/B", "C/D", "E/F"]


def test_print_summary_lists_signals_and_half_life(capsys):
    pairs = [
        pair_dict(pair="A/B", half_life_days=12.34),
        pair_dict(pair="C/D", half_life_days=None, signal="LONG", current_zscore=-2.2),
        pair_dict(pair="E/F", signal="NONE"),
        pair_dict(pair="G/H", is_cointegrated=False),
    ]

    find_pairs.print_summary(pairs)

    out = capsys.readouterr().out
    assert "Total pairs analyzed: 4" in out
    assert "Cointegrated pairs: 3" in out
    assert "Pairs with trade signals: 2" in out
    assert "Pair: A/B" in out
    assert "Half-Life: 12.3 days" in out
    assert "Pair: C/D" in out
    assert "Half-Life: N/A" in out
    assert "Z-Score: -2.20" in out
    assert "Pair: E/F" not in out
    assert "Pair: G/H" not in out


def test_print_summary_without_signals_omits_signal_section(capsys):
    find_pairs.print_summary([pair_dict(signal="NONE")])

    out = capsys.readouterr().out
    assert "Pairs with trade signals: 0" in out
    assert "ACTIVE TRADE SIGNALS" not in out


# ---------------------------------------------------------------------------
# find_pairs CLI
# ---------------------------------------------------------------------------


def run_find_pairs(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["find_pairs.py", *argv])
    return find_pairs.main()


@pytest.mark.parametrize(
    "argv",
    (
        [],
        ["--sector", "Tech", "--symbols", "A,B"],
        ["--symbols", "A,B", "--min-market-cap", "-1"],
        ["--symbols", "A,B", "--min-market-cap", "inf"],
        ["--symbols", "A,,B"],
        ["--symbols", "A"],
    ),
)
def test_find_pairs_more_invalid_cli_values_exit_2(monkeypatch, argv):
    with pytest.raises(SystemExit) as excinfo:
        run_find_pairs(monkeypatch, argv)

    assert excinfo.value.code == 2


def test_find_pairs_missing_api_key_exits_1(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        run_find_pairs(monkeypatch, ["--symbols", "AAA,BBB"])

    assert excinfo.value.code == 1


def test_find_pairs_sector_mode_normalizes_symbols_and_fetches(monkeypatch, tmp_path):
    a, b = cointegrated_prices()
    monkeypatch.setenv("FMP_API_KEY", "env-key")  # pragma: allowlist secret
    seen = {}

    def fake_sector(sector, key, cap):
        seen["sector"] = (sector, key, cap)
        return [{"symbol": "AAA"}, {"symbol": "BBB"}]

    def fake_batch(symbols, key, days):
        seen["batch"] = (symbols, key, days)
        return {"AAA": a, "BBB": b}

    monkeypatch.setattr(find_pairs, "fetch_sector_stocks", fake_sector)
    monkeypatch.setattr(find_pairs, "fetch_price_data_batch", fake_batch)
    screen_args = {}

    def fake_screen(price_data, min_corr):
        screen_args["args"] = (sorted(price_data), min_corr)
        return [pair_dict()]

    monkeypatch.setattr(find_pairs, "screen_all_pairs", fake_screen)
    out = tmp_path / "sector.json"

    run_find_pairs(
        monkeypatch,
        ["--sector", "Technology", "--min-correlation", "0.5", "--output", str(out)],
    )

    assert seen["sector"] == ("Technology", "env-key", 2_000_000_000)
    assert seen["batch"] == (["AAA", "BBB"], "env-key", 730)
    assert screen_args["args"] == (["AAA", "BBB"], 0.5)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [p["pair"] for p in payload["pairs"]] == ["AAA/BBB"]


def test_find_pairs_real_result_is_json_serializable(monkeypatch, tmp_path):
    # Regression: analyze_pair() used to return numpy.bool_ for
    # "is_cointegrated", so a real run with a cointegrated pair crashed in
    # save_results with "Object of type bool is not JSON serializable".
    a, b = cointegrated_prices()
    monkeypatch.setattr(find_pairs, "fetch_price_data_batch", lambda *_a: {"AAA": a, "BBB": b})
    out = tmp_path / "real.json"

    run_find_pairs(
        monkeypatch,
        [
            "--symbols",
            "AAA,BBB",
            "--api-key",
            "k",
            "--min-correlation",
            "0.5",
            "--output",
            str(out),
        ],
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [p["pair"] for p in payload["pairs"]] == ["AAA/BBB"]
    assert payload["pairs"][0]["is_cointegrated"] is True
    assert payload["metadata"]["cointegrated_pairs"] == 1


def test_find_pairs_symbols_are_uppercased_and_stripped(monkeypatch, tmp_path):
    captured = {}

    def fake_batch(symbols, key, days):
        captured["symbols"] = symbols
        return {}

    monkeypatch.setattr(find_pairs, "fetch_price_data_batch", fake_batch)

    with pytest.raises(SystemExit) as excinfo:
        run_find_pairs(
            monkeypatch,
            ["--symbols", " aaa , bbb ", "--api-key", "k", "--output", str(tmp_path / "x.json")],
        )

    assert excinfo.value.code == 1
    assert captured["symbols"] == ["AAA", "BBB"]


def test_find_pairs_exits_when_too_few_price_series(monkeypatch, capsys, tmp_path):
    a, _ = cointegrated_prices()
    monkeypatch.setattr(find_pairs, "fetch_price_data_batch", lambda *_a: {"AAA": a})
    out = tmp_path / "never.json"

    with pytest.raises(SystemExit) as excinfo:
        run_find_pairs(
            monkeypatch, ["--symbols", "AAA,BBB", "--api-key", "k", "--output", str(out)]
        )

    assert excinfo.value.code == 1
    assert "Need at least 2 stocks with valid data" in capsys.readouterr().out
    assert not out.exists()


def test_find_pairs_no_cointegrated_pairs_prints_hints_and_writes_empty(
    monkeypatch, capsys, tmp_path
):
    a, b = independent_walks()
    monkeypatch.setattr(find_pairs, "fetch_price_data_batch", lambda *_a: {"AAA": a, "BBB": b})
    out = tmp_path / "empty.json"

    run_find_pairs(
        monkeypatch,
        ["--symbols", "AAA,BBB", "--api-key", "k", "--min-correlation", "0", "--output", str(out)],
    )

    printed = capsys.readouterr().out
    assert "No cointegrated pairs found" in printed
    assert "Lowering --min-correlation threshold" in printed
    assert json.loads(out.read_text(encoding="utf-8"))["pairs"] == []


def test_find_pairs_cli_success_returns_zero(monkeypatch):
    monkeypatch.setattr(find_pairs, "main", lambda: None)

    assert find_pairs.cli() == 0


@pytest.mark.parametrize("error", (RuntimeError("rt"), ValueError("val")))
def test_find_pairs_cli_converts_errors_to_exit_code_1(monkeypatch, capsys, error):
    def failing():
        raise error

    monkeypatch.setattr(find_pairs, "main", failing)

    assert find_pairs.cli() == 1
    assert capsys.readouterr().err == f"ERROR: {error}\n"


# ---------------------------------------------------------------------------
# analyze_spread statistics
# ---------------------------------------------------------------------------


def test_calculate_hedge_ratio_aligns_on_common_dates():
    a_idx = pd.date_range("2025-01-01", periods=10)
    b_idx = pd.date_range("2025-01-04", periods=10)
    a = pd.Series(np.arange(10.0) * 2 + 1, index=a_idx)
    b = pd.Series(np.arange(10.0) + 3, index=b_idx)

    result = analyze_spread.calculate_hedge_ratio(a, b)

    assert len(result["aligned_a"]) == 7
    assert result["aligned_a"].index.equals(result["aligned_b"].index)
    assert result["beta"] == pytest.approx(2.0)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["r_value"] == pytest.approx(1.0)


def test_calculate_hedge_ratio_rejects_disjoint_and_nonfinite_inputs():
    idx = pd.date_range("2025-01-01", periods=5)
    other = pd.date_range("2026-01-01", periods=5)
    good = pd.Series(np.arange(5.0), index=idx)
    with pytest.raises(ValueError, match="non-constant"):
        analyze_spread.calculate_hedge_ratio(good, pd.Series(np.arange(5.0), index=other))

    bad = good.copy()
    bad.iloc[2] = np.nan
    with pytest.raises(ValueError, match="finite"):
        analyze_spread.calculate_hedge_ratio(bad, good)


def test_analyze_spread_test_cointegration_independent_walks():
    a, b = independent_walks()
    ratio = analyze_spread.calculate_hedge_ratio(a, b)
    spread = ratio["aligned_a"] - ratio["beta"] * ratio["aligned_b"]

    result = analyze_spread.test_cointegration(spread)

    assert result["is_cointegrated"] is False
    assert set(result["critical_values"]) == {"1%", "5%", "10%"}


def test_analyze_spread_test_cointegration_prints_error_on_failure(monkeypatch, capsys):
    def failing_adf(*_a, **_k):
        raise ValueError("nope")

    monkeypatch.setattr(analyze_spread, "require_statsmodels", lambda: (None, failing_adf))

    assert analyze_spread.test_cointegration(pd.Series([1.0, 2.0])) is None
    assert "Cointegration test failed: nope" in capsys.readouterr().out


def test_zscore_series_is_nan_until_window_filled():
    spread = pd.Series(np.arange(10.0))

    zscore = analyze_spread.calculate_zscore_series(spread, window=5)

    assert zscore.iloc[:4].isna().all()
    expected = (4.0 - 2.0) / np.std([0, 1, 2, 3, 4], ddof=1)
    assert zscore.iloc[4] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# ASCII chart
# ---------------------------------------------------------------------------


def test_ascii_chart_handles_empty_series():
    zscore = pd.Series([np.nan, np.nan])

    assert analyze_spread.generate_ascii_chart(zscore) == "No data available for chart"


def test_ascii_chart_layout_and_markers():
    values = np.concatenate([np.linspace(-2.5, 2.5, 100), np.zeros(20)])
    zscore = pd.Series(values)

    chart = analyze_spread.generate_ascii_chart(zscore, width=40, height=9)

    lines = chart.split("\n")
    assert "Z-Score History (Last 120 days)" in lines[1]
    assert lines[2] == "-" * 40
    rows = lines[3:12]
    assert len(rows) == 9
    assert rows[0].startswith(" 3.0 |")
    assert rows[4].startswith(" 0.0 |")
    assert rows[-1].startswith("-3.0 |")
    assert all(len(row) == 40 for row in rows)
    joined = "".join(rows)
    assert "*" in joined and "." in joined and "-" in joined
    assert lines[-1].strip() == "Time →"


def test_ascii_chart_uses_high_marker_and_threshold_rows():
    zscore = pd.Series(np.full(50, 1.7))

    chart = analyze_spread.generate_ascii_chart(zscore, width=30, height=7)

    assert "+" in chart
    assert "=" in chart  # +/-2.0 threshold guide on rows that land on +/-2.0


# ---------------------------------------------------------------------------
# print_analysis_report
# ---------------------------------------------------------------------------


def make_report_inputs(*, beta=1.2, cointegrated=True, p_value=0.001, length=150):
    a, b = cointegrated_prices(length=length)
    spread = a - beta * b
    zscore = analyze_spread.calculate_zscore_series(spread, window=90)
    coint = {
        "adf_statistic": -4.5,
        "p_value": p_value,
        "critical_values": {"1%": -3.5, "5%": -2.9, "10%": -2.6},
        "is_cointegrated": cointegrated,
    }
    beta_result = {"beta": beta, "r_value": 0.97, "r_squared": 0.94}
    return a, b, beta_result, spread, coint, zscore


def render_report(capsys, *, current_zscore, entry=2.0, exit_=0.5, half_life=20.0, **kwargs):
    a, b, beta_result, spread, coint, zscore = make_report_inputs(**kwargs)
    analyze_spread.print_analysis_report(
        "AAA",
        "BBB",
        a,
        b,
        beta_result,
        spread,
        coint,
        half_life,
        zscore,
        current_zscore,
        entry,
        exit_,
    )
    return capsys.readouterr().out, a, b


def test_report_short_spread_signal_and_sizing(capsys):
    out, a, b = render_report(capsys, current_zscore=2.4)

    assert "PAIR TRADE ANALYSIS: AAA / BBB" in out
    assert "Data Points: 150" in out
    assert "Correlation: 0.9700" in out
    assert "Hedge Ratio (Beta): 1.2000" in out
    assert "Result: ✅ COINTEGRATED (p < 0.05)" in out
    assert "Strength: ★★★ Very Strong" in out
    assert "Half-Life: 20.0 days" in out
    assert "Speed: Fast" in out
    assert "Signal: 🔻 SHORT SPREAD" in out
    assert "Action: Short AAA, Long BBB" in out
    assert "SHORT AAA: $5,000" in out
    assert f"@ ${a.iloc[-1]:.2f})" in out
    assert f"LONG BBB: ${5000 * 1.2:,.0f}" in out
    assert "Primary: Z-score crosses 0.5" in out
    assert "[ Z-SCORE CHART ]" in out


def test_report_long_spread_signal_and_sizing(capsys):
    out, _, _ = render_report(capsys, current_zscore=-2.4, p_value=0.03, half_life=45.0)

    assert "Strength: ★★ Moderate" in out
    assert "Speed: Moderate" in out
    assert "Signal: 🔺 LONG SPREAD" in out
    assert "Action: Long AAA, Short BBB" in out
    assert "LONG AAA: $5,000" in out
    assert f"SHORT BBB: ${5000 * 1.2:,.0f}" in out


def test_report_wait_signal_has_no_position_sizing(capsys):
    out, _, _ = render_report(capsys, current_zscore=0.5, half_life=90.0)

    assert "Signal: ⏸ WAIT (|z| < 2.0)" in out
    assert "Speed: Slow" in out
    assert "POSITION SIZING" not in out


def test_report_not_cointegrated_never_trades(capsys):
    out, _, _ = render_report(
        capsys, current_zscore=3.0, cointegrated=False, p_value=0.4, half_life=None
    )

    assert "Result: ❌ NOT COINTEGRATED (p ≥ 0.05)" in out
    assert "Half-Life: N/A (spread may not be mean-reverting)" in out
    assert "Signal: ⚠️ NO TRADE (pair not cointegrated)" in out
    assert "POSITION SIZING" not in out


def test_report_with_all_nan_zscore_divides_by_zero():
    # Pins current behavior: unreachable from main() (it raises first), but the
    # report itself does not guard against an empty z-score history.
    a, b, beta_result, spread, coint, _ = make_report_inputs(length=100)
    zscore = pd.Series(np.nan, index=spread.index)

    with pytest.raises(ZeroDivisionError):
        analyze_spread.print_analysis_report(
            "AAA", "BBB", a, b, beta_result, spread, coint, 10.0, zscore, 0.0, 2.0, 0.0
        )


# ---------------------------------------------------------------------------
# analyze_spread CLI
# ---------------------------------------------------------------------------


def run_analyze(monkeypatch, extra=()):
    argv = ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB", "--api-key", "k", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(analyze_spread.time, "sleep", lambda _s: None)
    return analyze_spread.main()


def test_analyze_spread_main_end_to_end_prints_report(monkeypatch, capsys):
    a, b = cointegrated_prices()
    lookup = {"AAA": a, "BBB": b}
    monkeypatch.setattr(
        analyze_spread, "fetch_historical_prices", lambda symbol, key, days: lookup[symbol]
    )

    run_analyze(monkeypatch, ["--entry-zscore", "1.0", "--exit-zscore", "0.25"])

    out = capsys.readouterr().out
    assert "PAIR TRADE ANALYSIS: AAA / BBB" in out
    assert "Result: ✅ COINTEGRATED" in out
    assert "Entry Threshold: ±1.0" in out
    assert "Exit Threshold: ±0.2" in out  # .1f display rounds 0.25 down


def test_analyze_spread_main_missing_prices_exit_1(monkeypatch):
    a, _ = cointegrated_prices()
    results = iter([a, None])
    monkeypatch.setattr(analyze_spread, "fetch_historical_prices", lambda *_a: next(results))

    with pytest.raises(SystemExit) as excinfo:
        run_analyze(monkeypatch)

    assert excinfo.value.code == 1


def test_analyze_spread_main_cointegration_failure_exit_1(monkeypatch):
    a, b = cointegrated_prices()
    results = iter([a, b])
    monkeypatch.setattr(analyze_spread, "fetch_historical_prices", lambda *_a: next(results))
    monkeypatch.setattr(analyze_spread, "test_cointegration", lambda _s: None)

    with pytest.raises(SystemExit) as excinfo:
        run_analyze(monkeypatch)

    assert excinfo.value.code == 1


def test_analyze_spread_main_short_history_raises_zscore_error(monkeypatch, capsys):
    a, b = cointegrated_prices(length=60)  # fewer than the 90-day z-score window
    lookup = {"AAA": a, "BBB": b}
    monkeypatch.setattr(
        analyze_spread, "fetch_historical_prices", lambda symbol, key, days: lookup[symbol]
    )
    monkeypatch.setattr(
        sys, "argv", ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB", "--api-key", "k"]
    )
    monkeypatch.setattr(analyze_spread.time, "sleep", lambda _s: None)

    assert analyze_spread.cli() == 1

    assert "could not calculate a finite z-score" in capsys.readouterr().err


def test_analyze_spread_main_missing_api_key_exit_1(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB"])

    with pytest.raises(SystemExit) as excinfo:
        analyze_spread.main()

    assert excinfo.value.code == 1


def test_analyze_spread_cli_success_returns_zero(monkeypatch):
    monkeypatch.setattr(analyze_spread, "main", lambda: None)

    assert analyze_spread.cli() == 0


@pytest.mark.parametrize("error", (RuntimeError("rt"), ValueError("val")))
def test_analyze_spread_cli_converts_errors_to_exit_code_1(monkeypatch, capsys, error):
    def failing():
        raise error

    monkeypatch.setattr(analyze_spread, "main", failing)

    assert analyze_spread.cli() == 1
    assert capsys.readouterr().err == f"ERROR: {error}\n"
