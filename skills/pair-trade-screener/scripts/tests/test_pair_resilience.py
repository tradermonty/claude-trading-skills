"""Batch fail-fast, price-basis reporting and malformed-row handling (PR #641 review)."""

import json
import sys
import time
from datetime import date, timedelta

import analyze_spread
import find_pairs
import numpy as np
import pytest
import requests

TOKEN = "PAIR_FIXTURE_ONLY"  # pragma: allowlist secret
ADJUSTED = "/stable/historical-price-eod/dividend-adjusted"
FULL = "/stable/historical-price-eod/full"
SCREENER = "/stable/company-screener"


class Response:
    def __init__(self, data=None, status=200):
        self.status_code = status
        self.text = "synthetic"
        self.data = data

    def json(self):
        return self.data


def _days(n):
    start = date(2026, 10, 30)
    return [(start - timedelta(days=i)).isoformat() for i in range(n)]


def adjusted_rows(symbol, n=300, seed=0):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.normal(0, 1, n))
    return [
        {"symbol": symbol, "date": day, "adjClose": float(price)}
        for day, price in zip(_days(n), prices[::-1])
    ]


def full_rows(symbol, n=300, seed=0):
    return [
        {"symbol": symbol, "date": r["date"], "close": r["adjClose"]}
        for r in adjusted_rows(symbol, n, seed)
    ]


@pytest.fixture
def routed(monkeypatch):
    """Route by URL suffix; handlers get the request params."""
    state = {"calls": [], "sleeps": [], "handlers": {}}

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, url, params=None, timeout=None):
            state["calls"].append((url, dict(params or {})))
            for suffix, handler in state["handlers"].items():
                if url.endswith(suffix):
                    return handler(dict(params or {}))
            raise AssertionError(f"unrouted request: {url}")

    monkeypatch.setattr(requests, "Session", Session)
    monkeypatch.setattr(time, "sleep", state["sleeps"].append)
    return state


def _symbols(n):
    return [f"S{i:02d}" for i in range(n)]


def test_always_429_batch_cost_is_bounded_not_proportional(routed):
    routed["handlers"][ADJUSTED] = lambda p: Response(status=429)
    routed["handlers"][FULL] = lambda p: Response(status=429)

    assert find_pairs.fetch_price_data_batch(_symbols(1), TOKEN) == {}
    single_calls, single_sleep = len(routed["calls"]), sum(routed["sleeps"])

    routed["calls"].clear()
    routed["sleeps"].clear()
    assert find_pairs.fetch_price_data_batch(_symbols(20), TOKEN) == {}

    assert len(routed["calls"]) == single_calls == 2
    assert sum(routed["sleeps"]) <= single_sleep + 1.0
    assert sum(routed["sleeps"]) < 70


def test_quota_death_mid_batch_keeps_earlier_symbols_and_stops(routed):
    def adjusted(params):
        if params["symbol"] in ("S00", "S01"):
            return Response(adjusted_rows(params["symbol"]))
        return Response(status=429)

    routed["handlers"][ADJUSTED] = adjusted
    routed["handlers"][FULL] = lambda p: Response(status=429)

    result = find_pairs.fetch_price_data_batch(_symbols(10), TOKEN)

    assert list(result) == ["S00", "S01"]
    requested = {c[1].get("symbol") for c in routed["calls"]}
    assert requested == {"S00", "S01", "S02"}  # nothing requested after the latch
    assert sum(routed["sleeps"]) < 70


def test_analyze_spread_shares_one_client_across_both_legs(routed, monkeypatch, capsys):
    routed["handlers"][ADJUSTED] = lambda p: Response(status=429)
    routed["handlers"][FULL] = lambda p: Response(status=429)
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_spread.py", "--stock-a", "AAA", "--stock-b", "BBB", "--api-key", TOKEN],
    )
    with pytest.raises(SystemExit):
        analyze_spread.main()
    # Leg B reuses the latched client: 2 calls for A, none for B.
    assert len(routed["calls"]) == 2
    assert {c[1]["symbol"] for c in routed["calls"]} == {"AAA"}


def test_429_waits_sixty_seconds_before_retrying(routed):
    answers = [Response(status=429), Response(adjusted_rows("AAA"))]
    routed["handlers"][ADJUSTED] = lambda p: answers.pop(0)

    prices = find_pairs.fetch_historical_prices("AAA", TOKEN)

    assert prices is not None
    assert 60 in routed["sleeps"]
    assert len(routed["calls"]) == 2


def _mixed_handlers(routed):
    def adjusted(params):
        if params["symbol"] == "RAW":
            return Response(status=402)
        return Response(adjusted_rows(params["symbol"], seed=1))

    routed["handlers"][ADJUSTED] = adjusted
    routed["handlers"][FULL] = lambda p: Response(full_rows(p["symbol"], seed=2))


def test_mixed_price_bases_warn_and_are_recorded(routed, capsys, tmp_path, monkeypatch):
    _mixed_handlers(routed)

    price_data = find_pairs.fetch_price_data_batch(["ADJ", "RAW"], TOKEN)

    err = capsys.readouterr().err
    assert err.count("RAW: using raw close prices that are NOT dividend-adjusted") == 1
    assert "mixed price bases in one run" in err and "RAW" in err
    basis = find_pairs.summarize_price_basis(price_data)
    assert basis == {"ADJ": "dividend_adjusted", "RAW": "close"}

    out = tmp_path / "out.json"
    find_pairs.save_results([], str(out), basis)
    assert json.loads(out.read_text())["metadata"]["price_basis"] == basis


def test_all_adjusted_run_does_not_warn(routed, capsys):
    routed["handlers"][ADJUSTED] = lambda p: Response(adjusted_rows(p["symbol"]))
    find_pairs.fetch_price_data_batch(["AAA", "BBB"], TOKEN)
    assert "WARN" not in capsys.readouterr().err


def test_analyze_spread_prints_price_basis(routed, monkeypatch, capsys):
    _mixed_handlers(routed)
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_spread.py", "--stock-a", "ADJ", "--stock-b", "RAW", "--api-key", TOKEN],
    )
    try:
        analyze_spread.main()
    except SystemExit:
        pass
    captured = capsys.readouterr()
    assert "Price basis: ADJ=dividend_adjusted, RAW=close" in captured.out
    assert "mixed price bases between the two legs" in captured.err


def test_bad_row_outside_lookback_window_does_not_drop_symbol(routed):
    rows = full_rows("AAA", n=800)
    rows[799]["close"] = None  # oldest row, far outside the 730-row window
    routed["handlers"][ADJUSTED] = lambda p: Response(status=402)
    routed["handlers"][FULL] = lambda p: Response(rows)

    prices = find_pairs.fetch_historical_prices("AAA", TOKEN)

    assert prices is not None and len(prices) == 730


def test_bad_row_inside_lookback_window_still_rejects(routed):
    rows = full_rows("AAA", n=800)
    rows[10]["close"] = None
    routed["handlers"][ADJUSTED] = lambda p: Response(status=402)
    routed["handlers"][FULL] = lambda p: Response(rows)
    routed["handlers"]["/api/v3/historical-price-full/AAA"] = lambda p: Response(status=403)

    assert find_pairs.fetch_historical_prices("AAA", TOKEN) is None


def test_bad_adjusted_row_outside_window_is_ignored(routed):
    rows = adjusted_rows("AAA", n=800)
    rows[799]["adjClose"] = "bad"
    routed["handlers"][ADJUSTED] = lambda p: Response(rows)

    prices = find_pairs.fetch_historical_prices("AAA", TOKEN)

    assert len(prices) == 730 and prices.attrs["price_basis"] == "dividend_adjusted"


@pytest.mark.parametrize("bad_value", [0, 0.0, -1.5])
def test_non_positive_adjusted_price_falls_back_without_crashing(routed, bad_value):
    rows = adjusted_rows("AAA", n=300)
    rows[5]["adjClose"] = bad_value
    routed["handlers"][ADJUSTED] = lambda p: Response(rows)
    routed["handlers"][FULL] = lambda p: Response(full_rows("AAA", n=300))

    prices = find_pairs.fetch_historical_prices("AAA", TOKEN)

    assert prices is not None and prices.attrs["price_basis"] == "close"


def test_non_string_symbol_outside_window_is_controlled_not_a_crash(routed):
    rows = full_rows("AAA", n=800)
    rows[799]["symbol"] = 123
    routed["handlers"][ADJUSTED] = lambda p: Response(status=402)
    routed["handlers"][FULL] = lambda p: Response(rows)
    routed["handlers"]["/api/v3/historical-price-full/AAA"] = lambda p: Response(status=403)

    assert find_pairs.fetch_historical_prices("AAA", TOKEN) is None


def test_foreign_rows_do_not_shift_the_validated_window(routed):
    # 730 foreign rows sit first, so the target's rows are all past raw index 730
    # but are the ones actually used after normalization.
    rows = full_rows("OTHER", n=730) + full_rows("AAA", n=300)
    rows[730 + 10]["close"] = None
    routed["handlers"][ADJUSTED] = lambda p: Response(status=402)
    routed["handlers"][FULL] = lambda p: Response(rows)
    routed["handlers"]["/api/v3/historical-price-full/AAA"] = lambda p: Response(status=403)

    assert find_pairs.fetch_historical_prices("AAA", TOKEN) is None


def test_midnight_datetime_dates_are_accepted(routed):
    rows = [dict(r, date=r["date"] + " 00:00:00") for r in full_rows("AAA", n=300)]
    routed["handlers"][ADJUSTED] = lambda p: Response(status=402)
    routed["handlers"][FULL] = lambda p: Response(rows)

    prices = find_pairs.fetch_historical_prices("AAA", TOKEN)

    assert prices is not None and len(prices) == 300


def test_null_symbol_screener_row_is_dropped_not_fatal(routed, capsys):
    routed["handlers"][SCREENER] = lambda p: Response(
        [
            {"symbol": "AAA", "isActivelyTrading": True},
            {"symbol": None, "isActivelyTrading": False},
            {"symbol": "  "},
            None,
            "junk",
        ]
    )
    stocks = find_pairs.fetch_sector_stocks("Energy", TOKEN)
    assert [s["symbol"] for s in stocks] == ["AAA"]
    assert "dropped 4 screener row(s)" in capsys.readouterr().err


@pytest.mark.parametrize("body", [{"a": 1}, "x", 5])
def test_non_list_screener_body_is_still_rejected(routed, body):
    routed["handlers"][SCREENER] = lambda p: Response(body)
    with pytest.raises(SystemExit):
        find_pairs.fetch_sector_stocks("Energy", TOKEN)
