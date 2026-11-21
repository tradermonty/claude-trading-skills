"""Price-gap handling must not change healthy short-history behavior."""

import json
import math
from pathlib import Path

import pytest
from calculators import relative_strength_calculator as rs
from calculators.trend_template_calculator import calculate_trend_template
from calculators.volume_pattern_calculator import calculate_volume_pattern
from historical_scanner import scan_history
from screen_vcp import analyze_stock, pre_filter_stock
from test_evaluation_coverage import history, run_screen
from test_remaining_price_gaps import QUOTE
from test_vcp_screener import _make_prices

ANALYSIS_CASES = [(62, 260, 30), (49, 260, 30), (19, 260, 10), (260, 62, 120), (260, 0, 120)]
SCAN_CASES = [(62, 260, 30), (160, 62, 120), (160, 0, 120)]


def short_history_outputs():
    return {
        "analyses": [
            analyze_stock("SHORT", _make_prices(n), QUOTE, _make_prices(m), lookback_days=lookback)
            for n, m, lookback in ANALYSIS_CASES
        ],
        "scans": [
            scan_history("SHORT", _make_prices(n), _make_prices(m), lookback_days=lookback)
            for n, m, lookback in SCAN_CASES
        ],
    }


def test_short_healthy_screen_analysis_and_scans_match_prechange():
    expected = json.loads((Path(__file__).parent / "healthy_short_history.json").read_text())
    actual = short_history_outputs()
    assert all(result is not None for result in actual["analyses"])
    assert actual == expected


@pytest.mark.parametrize("length", [0, 19, 49, 62])
def test_insufficient_lengths_are_not_price_gaps(length):
    bars = _make_prices(length)
    components = [rs.calculate_relative_strength(bars, bars)]
    if length < 50:
        components.append(calculate_trend_template(bars, QUOTE))
    if length < 20:
        components.append(calculate_volume_pattern(bars))
    for component in components:
        assert component["score"] == 0
        assert "Insufficient" in component["error"]
        assert "data_available" not in component
        assert "data_gaps" not in component


@pytest.mark.parametrize(
    "length", [63, 64, 94, 95, 125, 126, 127, 188, 189, 190, 251, 252, 253, 260]
)
@pytest.mark.parametrize("short_benchmark", [False, True])
def test_all_rs_period_return_calls_have_validated_in_range_endpoints(
    monkeypatch, length, short_benchmark
):
    stock = _make_prices(300 if short_benchmark else length)
    benchmark = _make_prices(length if short_benchmark else 300)
    find_gaps = rs.find_close_gaps
    period_return = rs._period_return
    validated = []
    calls = []

    def record_validation(bars, indices):
        gaps = find_gaps(bars, indices)
        assert gaps["bad_bars"] == 0
        validated.append((len(bars), set(indices)))
        return gaps

    def checked_return(closes, period):
        assert 0 < period < len(closes)
        assert any(n == len(closes) and {0, period} <= indices for n, indices in validated)
        assert all(math.isfinite(closes[i]) and closes[i] > 0 for i in [0, period])
        calls.append(period)
        return period_return(closes, period)

    monkeypatch.setattr(rs, "find_close_gaps", record_validation)
    monkeypatch.setattr(rs, "_period_return", checked_return)
    result = rs.calculate_relative_strength(stock, benchmark)
    assert result["error"] is None
    assert len(calls) == 2 * len(result["period_details"])

    def unexpected(*args):
        pytest.fail("Universe ranking must not calculate price returns")

    monkeypatch.setattr(rs, "_period_return", unexpected)
    assert (
        rs.rank_relative_strength_universe({"SHORT": result})["SHORT"]["weighted_rs"]
        == result["weighted_rs"]
    )


@pytest.mark.parametrize("volume", [None, float("nan")])
def test_undated_quote_gap_continues_healthy_and_zero_volume_candidates(
    monkeypatch, tmp_path, volume
):
    quote = {"price": 100, "yearHigh": 105, "yearLow": 50, "volume": 500000}
    bad = {k: v for k, v in quote.items() if k != "volume"}
    if volume is not None:
        bad["volume"] = volume
    zero = {**quote, "volume": 0}
    assert pre_filter_stock(zero) == (False, 0)
    report, markdown = run_screen(
        monkeypatch,
        tmp_path,
        {"BAD": bad, "GOOD": quote, "ZERO": zero},
        {"GOOD": history(), "SPY": history()},
    )
    assert [row["symbol"] for row in report["results"]] == ["GOOD"]
    exclusions = report["metadata"]["price_bar_gap_exclusions"]
    assert [row["symbol"] for row in exclusions] == ["BAD"]
    assert "quote (date unavailable)" in exclusions[0]["reason"]
    assert exclusions[0]["data_gaps"]["source"] == "quote"
    assert "quote (date unavailable)" in markdown
    assert report["evaluation_coverage"]["evaluated"] == 2
    assert report["evaluation_coverage"]["not_evaluated_reasons"] == {"price_bar_gap": 1}
