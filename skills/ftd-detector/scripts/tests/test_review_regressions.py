"""Review cases that escaped the initial #765 suite."""

import copy

import pytest
import rally_tracker as tracker
from helpers import make_bar, make_rally_history
from post_ftd_monitor import assess_post_ftd_health


def histories():
    bars, low, day1, ftd = make_rally_history(rally_days=8, ftd_day=5, ftd_gain_pct=2.1)
    return bars, low, day1, ftd


def test_pressure_reduces_numeric_quality_without_failing_rally():
    clean, _, day1, ftd = histories()
    clean_result = assess_post_ftd_health(tracker.get_market_state(clean[::-1], []), clean, [])
    pressured = copy.deepcopy(clean)
    price = (clean[day1]["low"] + clean[ftd]["low"]) / 2
    pressured.append(make_bar(price, low=(price + clean[day1]["low"]) / 2))
    result = assess_post_ftd_health(tracker.get_market_state(pressured[::-1], []), pressured, [])
    assert result["combined_state"] == "FTD_CONFIRMED"
    assert result["quality_score"]["total_score"] < clean_result["quality_score"]["total_score"]
    assert result["quality_score"]["total_score"] <= 59


def test_missing_low_inside_the_rally_is_not_silently_skipped():
    bars, _, day1, _ = histories()
    bars.extend([make_bar(bars[-1]["close"] * 0.99), make_bar(bars[-1]["close"] * 1.005)])
    assert tracker.analyze_single_index(bars, "Test")["state"] == "FTD_CONFIRMED"
    del bars[day1]["low"]
    result = tracker.analyze_single_index(bars, "Test")
    assert result.get("data_gap") is True
    assert result["state"] == "NO_SIGNAL"
    assert "invalid low" in result["error"]


@pytest.mark.parametrize("failed_key", ["sp500", "nasdaq"])
def test_mixed_health_uses_the_valid_event_consistently(failed_key):
    good, _, day1, _ = histories()
    failed = copy.deepcopy(good)
    failed.append(make_bar(failed[day1]["low"] - 1))
    sp, nq = (failed, good) if failed_key == "sp500" else (good, failed)
    state = tracker.get_market_state(sp[::-1], nq[::-1])
    result = assess_post_ftd_health(state, sp, nq)
    expected = "NASDAQ" if failed_key == "sp500" else "S&P 500"
    assert result["combined_state"] == "FTD_CONFIRMED"
    assert result["ftd_index"] == expected
    assert result["quality_score"]["ftd_source"] == expected
    assert result["quality_score"]["total_score"] > 0
    assert result["ftd_invalidation"]["invalidated"] is False


def test_proxy_data_quality_note_uses_instrument_identity(tmp_path):
    from report_generator import generate_markdown_report

    label = "QQQ (Nasdaq-100 ETF proxy)"
    analysis = {
        "metadata": {"instruments": {"nasdaq": {"label": label}}},
        "market_state": {"data_gap": True, "combined_state": "NO_SIGNAL"},
        "nasdaq": {"index": label, "data_gap": True, "error": "Day 1 low missing"},
    }
    path = tmp_path / "quality.md"
    generate_markdown_report(analysis, str(path))
    text = path.read_text()
    assert f"{label}: Day 1 low missing" in text
    assert "NASDAQ:" not in text
