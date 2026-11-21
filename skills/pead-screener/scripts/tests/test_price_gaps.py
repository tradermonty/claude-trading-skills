import json
import sys
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import screen_pead
from _price_bars import read_price
from calculators.liquidity_calculator import calculate_liquidity
from calculators.weekly_candle_calculator import daily_to_weekly
from price_bar_utils import PriceBarGap
from report_generator import generate_json_report, generate_markdown_report
from screen_pead import analyze_stock, calculate_price_gap


def history():
    return [
        {
            "date": f"2026-02-{day:02}",
            "open": 100,
            "high": 110,
            "low": 95,
            "close": 105,
            "volume": 1_500_000,
        }
        for day in (13, 12, 11, 10, 9, 6, 5, 4, 3, 2)
    ]


@pytest.mark.parametrize("bad", [None, float("nan")])
@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_consumed_recent_bar_excludes_analysis(field, bad):
    prices = history()
    if bad is None:
        del prices[0][field]
    else:
        prices[0][field] = bad
    with pytest.raises(PriceBarGap, match="2026-02-13"):
        analyze_stock("BAD", prices, "2026-02-02", "bmo", 5, 105)


@pytest.mark.parametrize(
    "timing,date,index,field",
    [
        ("bmo", "2026-02-12", 1, "open"),
        ("bmo", "2026-02-12", 2, "close"),
        ("amc", "2026-02-12", 0, "open"),
        ("unknown", "2026-02-12", 1, "close"),
    ],
)
@pytest.mark.parametrize("bad", [None, float("nan")])
def test_gap_endpoints_unavailable(timing, date, index, field, bad):
    prices = history()
    assert calculate_price_gap(prices, date, timing) == -4.76
    if bad is None:
        del prices[index][field]
    else:
        prices[index][field] = bad
    with pytest.raises(PriceBarGap, match=prices[index]["date"]):
        calculate_price_gap(prices, date, timing)


def test_healthy_and_empty_contract():
    prices = history()
    original = deepcopy(prices)
    assert calculate_liquidity(prices, 105)["adv20_dollar"] == 157_500_000
    assert daily_to_weekly(prices)[0]["close"] == 105
    result = analyze_stock("GOOD", prices, "2026-02-02", "bmo", 5, 105)
    assert result["stage"] == "MONITORING"
    assert prices == original
    assert analyze_stock("EMPTY", [], "2026-02-02", "bmo", 5, 105) is None
    assert calculate_price_gap([], "2026-02-02", "bmo") == 0.0


def test_healthy_reports_byte_identical_to_pre_migration(tmp_path):
    result = analyze_stock("GOOD", history(), "2026-02-02", "bmo", 5, 105)
    metadata = {"generated_at": "2026-02-13 16:00:00"}
    fixtures = Path(__file__).parent / "fixtures"
    expected = json.loads((fixtures / "healthy_reports.json").read_text())
    for suffix, generate in [("json", generate_json_report), ("md", generate_markdown_report)]:
        output = tmp_path / f"healthy.{suffix}"
        generate([result], metadata, str(output))
        assert output.read_bytes() == expected[suffix].encode("utf-8")


@pytest.mark.parametrize("mode", ["A", "B"])
@pytest.mark.parametrize("bad", [None, float("nan")])
def test_main_records_dated_exclusion_and_continues(mode, bad, tmp_path, monkeypatch, capsys):
    prices = history()
    broken = deepcopy(prices)
    if bad is None:
        del broken[0]["close"]
    else:
        broken[0]["close"] = bad
    candidates = [
        {
            "symbol": symbol,
            "earnings_date": "2026-02-02",
            "earnings_timing": "bmo",
            "gap_pct": 5 if mode == "B" else None,
        }
        for symbol in ("BAD", "GOOD")
    ]
    client = MagicMock()
    client.get_historical_prices.side_effect = [
        {"historical": broken},
        {"historical": prices},
    ]
    client.get_api_stats.return_value = {
        "budget_remaining": 100,
        "api_calls_made": 2,
        "rate_limit_reached": False,
    }
    monkeypatch.setattr(screen_pead, "FMPClient", lambda **kwargs: client)
    monkeypatch.setattr(
        screen_pead, f"_get_candidates_mode_{mode.lower()}", lambda *args: (candidates, None)
    )
    argv = ["screen_pead.py", "--output-dir", str(tmp_path), "--min-gap", "0"]
    if mode == "B":
        argv += ["--candidates-json", "unused.json"]
    monkeypatch.setattr(sys, "argv", argv)
    screen_pead.main()
    report = json.loads(next(tmp_path.glob("pead_screener_*.json")).read_text())
    assert [r["symbol"] for r in report["results"]] == ["GOOD"]
    reason = report["metadata"]["price_bar_gap_exclusions"][0]
    assert reason["symbol"] == "BAD"
    assert "2026-02-13" in reason["reason"]
    assert "Unavailable" in reason["reason"]
    markdown = next(tmp_path.glob("*.md")).read_text()
    assert "> Data quality warning: incomplete screening. 1 candidate(s)" in markdown
    assert "\n\n- **BAD:** " in markdown
    assert "\n\n## Summary" in markdown
    assert "Price-bar gap exclusions: 1" in capsys.readouterr().out


def longer_history():
    days = [date(2026, 3, 13) - timedelta(days=i) for i in range(60)]
    return [
        {
            "date": day.isoformat(),
            "open": 110 if day < date(2026, 3, 2) else 100,
            "high": 115,
            "low": 95,
            "close": 105,
            "volume": 1_500_000,
        }
        for day in days
        if day.weekday() < 5
    ]


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("bad", [None, float("nan")])
def test_old_bar_outside_consumed_window_does_not_change_result(field, bad):
    prices = longer_history()
    expected = analyze_stock("GOOD", prices, "2026-02-16", "bmo", 5, 105)
    if bad is None:
        del prices[-1][field]
    else:
        prices[-1][field] = bad
    assert analyze_stock("GOOD", prices, "2026-02-16", "bmo", 5, 105) == expected


def test_pre_earnings_volume_is_consumed_but_ohlc_is_not():
    prices = longer_history()
    expected = analyze_stock("GOOD", prices, "2026-02-16", "bmo", 5, 105)
    pre = next(bar for bar in prices if bar["date"] == "2026-02-13")
    del pre["close"]
    assert analyze_stock("GOOD", prices, "2026-02-16", "bmo", 5, 105) == expected
    del pre["volume"]
    with pytest.raises(PriceBarGap, match="2026-02-09"):
        analyze_stock("GOOD", prices, "2026-02-16", "bmo", 5, 105)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), None, True, "105"])
def test_direct_analysis_rejects_invalid_current_price(value):
    with pytest.raises(PriceBarGap, match="2026-02-13"):
        analyze_stock("BAD", history(), "2026-02-02", "bmo", 5, value)


@pytest.mark.parametrize("field", ["open", "close"])
@pytest.mark.parametrize("value", [0, -1])
def test_price_reader_rejects_nonpositive_prices(field, value):
    assert read_price({field: value}, field) is None


def test_genuine_zero_volume_remains_valid():
    prices = history()
    for bar in prices:
        bar["volume"] = 0
    assert read_price({"volume": 0}, "volume", allow_zero=True) == 0
    assert daily_to_weekly(prices)[0]["volume"] == 0
    assert calculate_liquidity(prices, 105)["adv20_dollar"] == 0
    assert analyze_stock("GOOD", prices, "2026-02-02", "bmo", 5, 105) is not None


def test_multiple_exclusions_render_as_separate_list_items(tmp_path):
    output = tmp_path / "report.md"
    metadata = {
        "price_bar_gap_exclusions": [
            {"symbol": symbol, "reason": "Unavailable: close on 2026-02-13"}
            for symbol in ("BAD", "WORSE")
        ]
    }
    generate_markdown_report([], metadata, str(output))
    markdown = output.read_text()
    assert "2 candidate(s)" in markdown
    assert "\n\n- **BAD:** Unavailable: close on 2026-02-13\n- **WORSE:** " in markdown
    assert "\n\n## Summary" in markdown
