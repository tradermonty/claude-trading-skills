"""ftd-detector data gaps (issue #655) are read as DATA_GAP, never as a confirmation."""

import pytest
from report_loader import extract_signal
from scorer import (
    COMPONENT_WEIGHTS,
    calculate_bottom_confirmation,
    calculate_signal_convergence,
    classify_pattern,
)


def ftd_report(*, top_gap=None, ms_gap=None, signal="Strong FTD", score=85):
    market_state = {
        "combined_state": "FTD_CONFIRMED",
        "dual_confirmation": True,
        "ftd_index": "Both",
    }
    if ms_gap is not None:
        market_state["data_gap"] = ms_gap
    data = {
        "market_state": market_state,
        "quality_score": {"total_score": score, "signal": signal, "exposure_range": "75-100%"},
        "post_ftd_distribution": {"distribution_count": 0},
    }
    if top_gap is not None:
        data["data_gap"] = top_gap
    return data


@pytest.mark.parametrize(
    "kwargs",
    [
        {"top_gap": True},
        {"ms_gap": True},
        {"signal": "Unavailable: data gap", "score": 0},
    ],
    ids=["top_level", "market_state", "unavailable_signal"],
)
def test_gapped_ftd_report_is_data_gap(kwargs):
    sig = extract_signal("ftd_detector", ftd_report(**kwargs))
    assert sig["state"] == "DATA_GAP"
    assert sig["quality_score"] == 0
    assert sig["data_gap"] is True


def test_clean_ftd_report_is_unchanged():
    sig = extract_signal("ftd_detector", ftd_report(top_gap=False, ms_gap=False))
    assert sig["state"] == "FTD_CONFIRMED"
    assert sig["quality_score"] == 85
    assert sig["data_gap"] is False


def test_data_gap_scores_as_low_as_rally_failed_and_skips_ftd_bonus():
    gap = {"state": "DATA_GAP", "quality_score": 100, "dual_confirmation": True}
    assert calculate_bottom_confirmation({"ftd_detector": gap}) == 10
    failed = {"state": "RALLY_FAILED", "quality_score": 0}
    assert calculate_bottom_confirmation({"ftd_detector": failed}) == 10
    others = ["FTD_CONFIRMED", "FTD_WINDOW", "RALLY_ATTEMPT", "NO_SIGNAL", "CORRECTION"]
    others.append("FTD_INVALIDATED")
    for state in others:
        signal = {"ftd_detector": {"state": state, "quality_score": 0}}
        assert calculate_bottom_confirmation(signal) >= 10


@pytest.mark.parametrize("healed_state", ["FTD_INVALIDATED", "FTD_WINDOW", "RALLY_FAILED"])
def test_data_gap_convergence_equals_a_healed_zero_quality_run(healed_state):
    """A gap must not shift convergence relative to the healed zero-quality run.

    Dropping the FTD input for DATA_GAP was tried and rejected: removing the 0
    outlier tightens agreement, so convergence (and the composite) rose above
    the healed run in about 15% of the review's gapped cases.
    """
    others = {
        "market_breadth": {"composite_score": 70},
        "uptrend_analysis": {"composite_score": 70},
        "market_top": {"composite_score": 30},
        "macro_regime": {"composite_score": 70},
    }
    without_ftd = calculate_signal_convergence(dict(others))
    gap = calculate_signal_convergence(
        dict(others, ftd_detector={"state": "DATA_GAP", "quality_score": 0})
    )
    healed = calculate_signal_convergence(
        dict(others, ftd_detector={"state": healed_state, "quality_score": 0})
    )
    assert gap == healed
    assert gap < without_ftd  # i.e. excluding the gap would have raised it


def test_data_gap_never_drives_the_ftd_contrarian_pattern():
    signals = {
        "macro_regime": {"regime": "contraction", "composite_score": 20, "transition_level": "low"},
        "market_top": {"composite_score": 80},
        "ftd_detector": {"state": "DATA_GAP", "quality_score": 0},
        "market_breadth": {"composite_score": 25},
    }
    comp_scores = {k: {"score": 20} for k in COMPONENT_WEIGHTS}
    result = classify_pattern(signals, comp_scores, 30)
    assert result["all_pattern_scores"]["extreme_sentiment_contrarian"] == 45
    signals["ftd_detector"] = {"state": "FTD_CONFIRMED", "quality_score": 90}
    confirmed = classify_pattern(signals, comp_scores, 30)
    assert confirmed["all_pattern_scores"]["extreme_sentiment_contrarian"] == 100
