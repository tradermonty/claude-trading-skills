"""Remaining VCP readers reject consumed gaps without changing healthy output."""

import copy
import json
from pathlib import Path

import pytest
from calculators.relative_strength_calculator import calculate_relative_strength
from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import VCPPriceDataError
from calculators.volume_pattern_calculator import calculate_volume_pattern
from historical_scanner import build_quote_from_history
from report_generator import generate_json_report, generate_markdown_report
from screen_vcp import analyze_stock, is_stale_price, pre_filter_stock
from test_vcp_screener import _make_prices

MISSING = object()
INVALID = [MISSING, None, float("nan"), float("inf"), 0, -1, True, "100"]
QUOTE = {"price": 126, "yearHigh": 140, "yearLow": 70, "avgVolume": 1000000}
ZONES = [{"high_idx": 0, "low_idx": 10}]


def corrupt(history, index, field, value):
    if value is MISSING:
        history[index].pop(field, None)
    else:
        history[index][field] = value


def assert_unavailable(result, date):
    assert result["data_available"] is False
    assert result["score"] == 0
    assert date in result["data_gaps"]["bad_dates"]
    assert date in result["error"]


@pytest.mark.parametrize("benchmark", [False, True])
@pytest.mark.parametrize("index", [0, 63, 126, 189, 252])
@pytest.mark.parametrize("value", INVALID)
def test_rs_endpoints_only(benchmark, index, value):
    stock = _make_prices(260, daily_change=0.001)
    spy = _make_prices(260, daily_change=0.0005)
    bars = spy if benchmark else stock
    # A missing close can legitimately use adjClose, but no final zero fallback.
    bars[index].pop("adjClose")
    corrupt(bars, index, "close", value)
    assert_unavailable(calculate_relative_strength(stock, spy), bars[index]["date"])


@pytest.mark.parametrize("index", [0, 49, 149, 199, 221])
@pytest.mark.parametrize("value", INVALID)
def test_trend_consumed_closes(index, value):
    bars = _make_prices(260)
    bars[index].pop("adjClose")
    corrupt(bars, index, "close", value)
    assert_unavailable(calculate_trend_template(bars, QUOTE), bars[index]["date"])


@pytest.mark.parametrize(
    "field,index", [("volume", 0), ("volume", 49), ("volume", 119), ("close", 0), ("close", 1)]
)
@pytest.mark.parametrize("value", [MISSING, None, float("nan"), float("inf"), -1, True])
def test_volume_consumed_observations(field, index, value):
    bars = _make_prices(120)
    bars[0]["volume"] *= 2  # consumes close[1] for accumulation/distribution
    bars[index].pop("adjClose", None)
    corrupt(bars, index, field, value)
    assert_unavailable(
        calculate_volume_pattern(bars, pivot_price=100, contractions=ZONES), bars[index]["date"]
    )


@pytest.mark.parametrize("field,index", [("high", 251), ("low", 251), ("close", 0)])
@pytest.mark.parametrize("value", INVALID)
def test_historical_quote_never_fabricates_fields(field, index, value):
    bars = _make_prices(300)
    corrupt(bars, index, field, value)
    with pytest.raises(VCPPriceDataError) as exc:
        build_quote_from_history(bars, 0)
    assert bars[index]["date"] in str(exc.value)
    assert bars[index]["date"] in exc.value.data_gaps["bad_dates"]


@pytest.mark.parametrize("value", [MISSING, None, float("nan"), float("inf"), -1, True])
def test_historical_quote_requires_consumed_volume(value):
    bars = _make_prices(300)
    corrupt(bars, 49, "volume", value)
    with pytest.raises(VCPPriceDataError) as exc:
        build_quote_from_history(bars, 0)
    assert bars[49]["date"] in str(exc.value)


@pytest.mark.parametrize("field", ["high", "low", "close"])
@pytest.mark.parametrize("value", INVALID)
def test_stale_check_does_not_drop_bad_bars(field, value):
    bars = _make_prices(260)
    corrupt(bars, 9, field, value)
    with pytest.raises(VCPPriceDataError) as exc:
        is_stale_price(bars)
    assert bars[9]["date"] in str(exc.value)


@pytest.mark.parametrize("field", ["volume", "avgVolume"])
@pytest.mark.parametrize("value", [MISSING, None, float("nan"), float("inf"), -1, True])
def test_prefilter_quote_volume_unavailable(field, value):
    quote = {"date": "2026-11-13", "price": 100, "yearHigh": 110, "yearLow": 50, field: 1000000}
    corrupt([quote], 0, field, value)
    with pytest.raises(VCPPriceDataError) as exc:
        pre_filter_stock(quote)
    assert "2026-11-13" in str(exc.value)


def test_legitimate_adjusted_close_fallback_only_when_absent():
    bars = _make_prices(260)
    spy = _make_prices(260)
    expected_rs = calculate_relative_strength(bars, spy)
    expected_tt = calculate_trend_template(bars, QUOTE)
    expected_vol = calculate_volume_pattern(bars, pivot_price=100)
    for row in bars + spy:
        row.pop("close")
    assert calculate_relative_strength(bars, spy) == expected_rs
    assert calculate_trend_template(bars, QUOTE) == expected_tt
    assert calculate_volume_pattern(bars, pivot_price=100) == expected_vol
    bars[0]["close"] = None
    assert_unavailable(calculate_relative_strength(bars, spy), bars[0]["date"])


def test_each_reader_ignores_unconsumed_values():
    bars = _make_prices(300)
    spy = _make_prices(300)
    rs = calculate_relative_strength(bars, spy)
    stock_bad = copy.deepcopy(bars)
    spy_bad = copy.deepcopy(spy)
    for index in [1, 62, 127, 251, 253, 299]:
        corrupt(stock_bad, index, "close", None)
        corrupt(spy_bad, index, "close", float("nan"))
    assert calculate_relative_strength(stock_bad, spy_bad) == rs
    tt = calculate_trend_template(bars, QUOTE)
    bars[222]["close"] = None
    assert calculate_trend_template(bars, QUOTE) == tt
    vol = calculate_volume_pattern(bars, pivot_price=100, contractions=ZONES)
    bars[50]["volume"] = None
    bars[1]["close"] = None  # equal volumes never compare day 0/day 1
    assert calculate_volume_pattern(bars, pivot_price=100, contractions=ZONES) == vol
    bars = _make_prices(300)
    quote = build_quote_from_history(bars, 10)
    bars[0] = {"date": "future"}
    bars[262] = {"date": "older"}
    bars[60]["volume"] = None
    bars[11]["close"] = None
    assert build_quote_from_history(bars, 10) == quote
    bars = _make_prices(260)
    stale = is_stale_price(bars)
    bars[10] = {"date": "older"}
    assert is_stale_price(bars) == stale


def test_genuine_zero_volume_is_valid():
    bars = _make_prices(260, volume=0)
    assert calculate_volume_pattern(bars).get("data_available") is not False
    assert build_quote_from_history(bars, 0)["avgVolume"] == 0
    assert pre_filter_stock({**QUOTE, "avgVolume": 0, "volume": 0}) == (False, 0)
    assert pre_filter_stock({**QUOTE, "avgVolume": 0, "volume": 1000000})[0] is True


def test_empty_components_keep_legacy_insufficient_history_results():
    for result in [
        calculate_relative_strength([], []),
        calculate_trend_template([], QUOTE),
        calculate_volume_pattern([]),
    ]:
        assert "data_available" not in result
        assert "data_gaps" not in result
        assert result["error"]
    with pytest.raises(ValueError, match="history|offset|window"):
        build_quote_from_history([], 0)


def healthy_outputs(directory):
    bars = _make_prices(260, daily_change=0.001)
    spy = _make_prices(260, daily_change=0.0005)
    candidate = analyze_stock("HEALTHY", bars, QUOTE, spy, "Technology", "Healthy Corp")
    metadata = {
        "generated_at": "2026-11-13 12:00:00",
        "universe_description": "golden",
        "funnel": {"universe": 1},
    }
    generate_json_report([candidate], metadata, str(directory / "report.json"))
    generate_markdown_report([candidate], metadata, str(directory / "report.md"))
    return {
        "candidate": candidate,
        "json": (directory / "report.json").read_text(),
        "markdown": (directory / "report.md").read_text(),
    }


def test_healthy_candidate_and_reports_are_byte_identical(tmp_path):
    expected = json.loads((Path(__file__).parent / "healthy_remaining_reports.json").read_text())
    assert healthy_outputs(tmp_path) == expected


def test_missing_recent_volume_cannot_flip_into_breakout():
    bars = _make_prices(120)
    bars[0]["close"] = 105
    bars[0]["volume"] = 1500000
    assert calculate_volume_pattern(bars, pivot_price=100)["breakout_volume_detected"] is False
    bars[1].pop("volume")
    assert_unavailable(calculate_volume_pattern(bars, pivot_price=100), bars[1]["date"])


@pytest.mark.parametrize(
    "field,index", [("close", 252), ("close", 221), ("volume", 49), ("low", 9), ("high", 119)]
)
@pytest.mark.parametrize("value", [MISSING, float("nan")])
def test_screen_excludes_only_affected_candidate_with_dated_report(
    monkeypatch, tmp_path, capsys, field, index, value
):
    import screen_vcp
    from test_evaluation_coverage import history, run_screen

    monkeypatch.setattr(screen_vcp, "passes_trend_filter", lambda *args: True)
    bars = history()
    corrupt(bars, index, field, value)
    quote = {**QUOTE, "yearHigh": 130}
    report, markdown = run_screen(
        monkeypatch,
        tmp_path,
        {"BAD": quote, "GOOD": quote},
        {"SPY": history(), "BAD": bars, "GOOD": history()},
    )
    assert [r["symbol"] for r in report["results"]] == ["GOOD"]
    exclusions = report["metadata"]["price_bar_gap_exclusions"]
    assert len(exclusions) == 1
    assert exclusions[0]["symbol"] == "BAD"
    assert bars[index]["date"] in exclusions[0]["reason"]
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {"price_bar_gap": 1}
    assert "> Data quality warning: incomplete screening. 1 candidate(s)" in markdown
    assert f"\n\n- **BAD:** {exclusions[0]['reason']}\n\n" in markdown
    assert "Excluded (price-bar gaps): 1" in capsys.readouterr().out
    assert all(
        c.get("data_available") is not False
        for r in report["results"]
        for c in [
            r["relative_strength"],
            r["trend_template"],
            r["volume_pattern"],
            r["vcp_pattern"],
        ]
    )


@pytest.mark.parametrize("value", [MISSING, float("nan")])
def test_screen_records_quote_volume_gap(monkeypatch, tmp_path, value):
    from test_evaluation_coverage import quote, run_screen

    data = {**quote(), "date": "2026-11-13"}
    corrupt([data], 0, "volume", value)
    report, _ = run_screen(monkeypatch, tmp_path, {"BAD": data})
    assert report["results"] == []
    assert "2026-11-13" in report["metadata"]["price_bar_gap_exclusions"][0]["reason"]


@pytest.mark.parametrize("data", ["malformed", ["malformed"]])
def test_malformed_quote_does_not_abort_screen(monkeypatch, tmp_path, data):
    from test_evaluation_coverage import run_screen

    report, _ = run_screen(monkeypatch, tmp_path, {"BAD": data})
    assert report["results"] == []
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"


@pytest.mark.parametrize("value", [MISSING, float("nan")])
def test_screen_does_not_validate_old_unconsumed_fields(monkeypatch, tmp_path, value):
    import screen_vcp
    from test_evaluation_coverage import history, quote, run_screen

    data = quote(100)
    data["yearHigh"] = 110
    expected, _ = run_screen(
        monkeypatch, tmp_path / "expected", {"GOOD": data}, {"GOOD": history(), "SPY": history()}
    )
    bars = history()
    for field, index in [("close", 253), ("high", 120), ("low", 120), ("volume", 120)]:
        corrupt(bars, index, field, value)
    report, _ = run_screen(
        monkeypatch, tmp_path / "actual", {"GOOD": data}, {"GOOD": bars, "SPY": history()}
    )
    assert report["results"] == expected["results"]
    assert report["evaluation_coverage"] == expected["evaluation_coverage"]
    assert "price_bar_gap_exclusions" not in report["metadata"]

    parse_arguments = screen_vcp.parse_arguments

    def short_window():
        args = parse_arguments()
        args.lookback_days = 30
        return args

    monkeypatch.setattr(screen_vcp, "parse_arguments", short_window)
    expected, _ = run_screen(
        monkeypatch,
        tmp_path / "short-expected",
        {"GOOD": data},
        {"GOOD": history(), "SPY": history()},
    )
    bars = history()
    corrupt(bars, 30, "volume", value)
    report, _ = run_screen(
        monkeypatch, tmp_path / "short-actual", {"GOOD": data}, {"GOOD": bars, "SPY": history()}
    )
    assert report["results"] == expected["results"]
    assert report["evaluation_coverage"] == expected["evaluation_coverage"]
    assert "price_bar_gap_exclusions" not in report["metadata"]


@pytest.mark.parametrize("value", [MISSING, float("nan")])
def test_historical_scan_does_not_hide_benchmark_gap(value):
    from historical_scanner import scan_history

    bars = _make_prices(300)
    spy = copy.deepcopy(bars)
    spy[-1].pop("adjClose")
    corrupt(spy, len(spy) - 1, "close", value)
    with pytest.raises(VCPPriceDataError) as exc:
        scan_history("BAD", bars, spy)
    assert spy[-1]["date"] in str(exc.value)


@pytest.mark.parametrize("calculator", ["rs", "trend", "volume"])
def test_unavailable_component_never_reaches_composite(monkeypatch, capsys, calculator):
    import screen_vcp

    bars = _make_prices(260)
    if calculator == "rs":
        bars[252]["close"] = None
    elif calculator == "trend":
        bars[221]["close"] = None
    else:
        bars[49]["volume"] = None

    def unexpected(**kwargs):
        pytest.fail("Unavailable components must not reach composite scoring")

    monkeypatch.setattr(screen_vcp, "calculate_composite_score", unexpected)
    assert analyze_stock("BAD", bars, QUOTE, _make_prices(260)) is None
    assert "unavailable" in capsys.readouterr().err


def test_partial_rs_and_short_sma_validate_only_used_bars():
    bars = _make_prices(120)
    rs = calculate_relative_strength(bars, bars)
    tt = calculate_trend_template(bars, QUOTE)
    bars[50]["close"] = None
    assert calculate_relative_strength(bars, bars) == rs
    assert calculate_trend_template(bars, QUOTE) == tt
    bars[119]["close"] = None
    assert_unavailable(calculate_relative_strength(bars, bars), bars[119]["date"])


def test_breakout_planner_accepts_screened_json_with_exclusions(monkeypatch, tmp_path):
    import subprocess
    import sys

    import screen_vcp
    from test_evaluation_coverage import history, run_screen

    monkeypatch.setattr(screen_vcp, "passes_trend_filter", lambda *args: True)
    bad = history()
    bad[49]["volume"] = None
    quote = {**QUOTE, "yearHigh": 130}
    run_screen(
        monkeypatch,
        tmp_path,
        {"BAD": quote, "GOOD": quote},
        {"BAD": bad, "GOOD": history(), "SPY": history()},
    )
    planner = Path(__file__).parents[3] / "breakout-trade-planner/scripts/plan_breakout_trades.py"
    result = subprocess.run(
        [
            sys.executable,
            str(planner),
            "--input",
            str(next(tmp_path.glob("*.json"))),
            "--account-size",
            "100000",
            "--as-of",
            "2026-11-13",
            "--output-dir",
            str(tmp_path / "plans"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    plans = json.loads(next((tmp_path / "plans").glob("*.json")).read_text())
    assert "BAD" not in json.dumps(plans)
