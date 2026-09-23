"""Report content contracts, including action-guidance threshold boundaries."""

import copy
import json
from datetime import date

import pytest
from report_generator import generate_json_report, generate_markdown_report


def render(tmp_path, analysis):
    path = tmp_path / "report.md"
    generate_markdown_report(analysis, str(path))
    return path.read_text(encoding="utf-8")


def test_json_preserves_analysis_and_serializes_dates(tmp_path):
    analysis = {
        "metadata": {"generated_at": date(2026, 3, 30)},
        "market_state": {"combined_state": "FTD_CONFIRMED", "dual_confirmation": False},
        "sp500": {"current_price": 101.25, "ftd": {"ftd_low": 97.5}},
        "nasdaq": {"current_price": None},
        "quality_score": {"total_score": 60, "exposure_range": "50-75%"},
    }
    original = copy.deepcopy(analysis)
    output = tmp_path / "report.json"
    generate_json_report(analysis, str(output))
    expected = copy.deepcopy(analysis)
    expected["metadata"]["generated_at"] = "2026-03-30"
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert analysis == original


@pytest.mark.parametrize(
    "score,expected,absent",
    [
        (59, "Cautious exposure increase with tight stops", "Gradually increase exposure"),
        (60, "Gradually increase exposure", "Cautious exposure increase with tight stops"),
        (79, "Gradually increase exposure", "Aggressively increase equity exposure"),
        (80, "Aggressively increase equity exposure", "Gradually increase exposure"),
    ],
)
def test_confirmed_guidance_at_score_boundaries(tmp_path, score, expected, absent):
    markdown = render(
        tmp_path,
        {
            "market_state": {"combined_state": "FTD_CONFIRMED"},
            "quality_score": {"total_score": score},
        },
    )
    assert expected in markdown
    assert absent not in markdown
    assert f"**{score}/100**" in markdown


@pytest.mark.parametrize(
    "state,expected",
    [
        ("FTD_WINDOW", "Do not buy ahead of FTD confirmation"),
        ("RALLY_ATTEMPT", "Too early to act - wait for Day 4+"),
        ("CORRECTION", "Stay defensive, preserve capital"),
        ("FTD_INVALIDATED", "Reduce exposure back to defensive levels"),
        ("RALLY_FAILED", "Remain in cash/defensive"),
    ],
)
def test_unconfirmed_states_never_use_confirmed_guidance(tmp_path, state, expected):
    # Even a stale high score cannot select confirmed-state guidance.
    markdown = render(
        tmp_path,
        {"market_state": {"combined_state": state}, "quality_score": {"total_score": 100}},
    )
    assert expected in markdown
    assert "Aggressively increase equity exposure" not in markdown
    assert "Gradually increase exposure with each successful breakout" not in markdown


def test_no_signal_renders_uptrend_status_and_normal_market_guidance(tmp_path):
    markdown = render(
        tmp_path,
        {
            "market_state": {"combined_state": "NO_SIGNAL"},
            "quality_score": {"total_score": 100},
        },
    )
    assert "| **Current State** | ⚪ **No Signal (Uptrend)** |" in markdown
    assert "No correction detected - normal market conditions" in markdown
    assert "FTD monitoring not applicable in uptrend" in markdown
    assert "Aggressively increase equity exposure" not in markdown
    assert "Gradually increase exposure with each successful breakout" not in markdown


def test_rally_details_skip_index_without_an_active_rally(tmp_path):
    markdown = render(
        tmp_path,
        {
            "market_state": {"combined_state": "RALLY_ATTEMPT"},
            "sp500": {},
            "nasdaq": {
                "swing_low": {"date": "2026-03-23", "price": 380, "decline_pct": -5},
                "rally_attempt": {"day1_date": "2026-03-24", "current_day_count": 2},
            },
            "quality_score": {"total_score": 0},
        },
    )
    assert "### NASDAQ/QQQ" in markdown
    assert "### S&P 500" not in markdown


def test_minimal_report_handles_absent_optional_analysis(tmp_path):
    markdown = render(tmp_path, {})
    assert "**Generated:** N/A" in markdown
    assert "| **Current State** | ⚪ **UNKNOWN** |" in markdown
    assert "| NASDAQ/QQQ | N/A | N/A | N/A | N/A | None |" in markdown
    for section in [
        "Rally Attempt Details",
        "FTD Signal",
        "Quality Score Breakdown",
        "Post-FTD Health",
    ]:
        assert f"## {section}" not in markdown


@pytest.mark.parametrize(
    "volume_above_avg,expected",
    [(True, "Above 50-day avg"), (False, "Below 50-day avg"), (None, "N/A")],
)
def test_ftd_volume_evidence_is_not_inferred_when_missing(tmp_path, volume_above_avg, expected):
    markdown = render(
        tmp_path,
        {"sp500": {"ftd": {"ftd_detected": True, "volume_above_avg": volume_above_avg}}},
    )
    assert f"| **Volume** | {expected} |" in markdown
    assert "### S&P 500 FTD" in markdown
    assert "### NASDAQ/QQQ FTD" not in markdown


@pytest.mark.parametrize("invalidated", [True, False])
def test_health_details_and_watch_levels_preserve_risk_evidence(tmp_path, invalidated):
    analysis = {
        "market_state": {"combined_state": "FTD_INVALIDATED" if invalidated else "FTD_CONFIRMED"},
        "sp500": {
            "lookback_high": 110,
            "swing_low": {"date": "2026-03-23", "price": 95, "decline_pct": -5},
            "rally_attempt": {
                "day1_date": "2026-03-24",
                "current_day_count": 8,
                "invalidated": invalidated,
                "invalidation_reason": "Closed below swing low",
            },
            "ftd": {"ftd_detected": True, "ftd_date": "2026-03-30", "ftd_low": 97.5},
        },
        "quality_score": {
            "total_score": 0 if invalidated else 80,
            "breakdown": {"post_ftd": "Distribution on Day 2: -20"},
        },
        "post_ftd_distribution": {
            "distribution_count": 1,
            "days_monitored": 3,
            "details": [
                {"day": 2, "date": "2026-04-01", "change_pct": -1.25, "volume_change_pct": 20}
            ],
        },
        "ftd_invalidation": {
            "invalidated": invalidated,
            "invalidation_date": "2026-04-01",
            "days_after_ftd": 2,
            "invalidation_close": 97,
            "ftd_low": 97.5,
            "days_since_ftd": 3,
        },
        "power_trend": {
            "power_trend": not invalidated,
            "conditions_met": 0 if invalidated else 3,
            "ema_21": 99,
            "sma_50": 98,
            "ema_above_sma": True,
            "sma_50_rising": not invalidated,
            "price_above_21ema": not invalidated,
        },
    }
    original = copy.deepcopy(analysis)
    markdown = render(tmp_path, analysis)
    assert analysis == original
    assert "| Post Ftd | Distribution on Day 2: -20 |" in markdown
    assert "Distribution Days Since FTD:** 1 (in 3 days monitored)" in markdown
    assert "Day 2: 2026-04-01 (-1.25%, vol +20.0%)" in markdown
    assert "Swing Low: $95.00 (2026-03-23)" in markdown
    assert "FTD Day Low (invalidation level): $97.50" in markdown
    assert "Lookback High: $110.00" in markdown
    assert "21 EMA: $99.00 (> 50 SMA: $98.00)" in markdown
    if invalidated:
        assert "**INVALIDATED:** Closed below swing low" in markdown
        assert (
            "**FTD INVALIDATED** on 2026-04-01 (Day 2, close $97.00 below FTD low $97.50)"
            in markdown
        )
        assert "**Power Trend:** No (0/3 conditions)" in markdown
        assert "50 SMA Rising: No" in markdown
        assert "**FTD Valid:**" not in markdown
    else:
        assert "**FTD Valid:** 3 days since FTD (FTD low: $97.50)" in markdown
        assert "**Power Trend:** YES (3/3 conditions)" in markdown
        assert "Price above 21 EMA: Yes" in markdown
        assert "**FTD INVALIDATED**" not in markdown


@pytest.mark.parametrize("writer", [generate_json_report, generate_markdown_report])
def test_report_write_failure_is_not_announced_as_success(tmp_path, capsys, writer):
    # A directory is an unwritable report destination on both Unix and Windows.
    with pytest.raises(OSError):
        writer({}, str(tmp_path))
    assert "report saved" not in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
