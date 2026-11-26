"""A long-lived FTD_CONFIRMED is not a fresh bottom signal.

Before the ftd-detector forward replay, FTD_CONFIRMED lasted about 60 sessions. The
fresh-FTD extras (quality bonus, dual bonus, the contrarian pattern's +40) keep that
meaning: they apply only while the FTD is at most 60 sessions old.
"""

from report_loader import extract_signal
from scorer import COMPONENT_WEIGHTS, calculate_bottom_confirmation, classify_pattern


def confirmed(days_since_ftd, quality=90, dual=True):
    sig = {
        "state": "FTD_CONFIRMED",
        "quality_score": quality,
        "dual_confirmation": dual,
        "post_ftd_distribution_count": 0,
    }
    if days_since_ftd is not None:
        sig["days_since_ftd"] = days_since_ftd
    return {"ftd_detector": sig}


def test_fresh_ftd_keeps_the_quality_and_dual_bonus():
    assert calculate_bottom_confirmation(confirmed(30)) == 93.0  # 80 + 8 + 5
    assert calculate_bottom_confirmation(confirmed(60)) == 93.0


def test_old_ftd_keeps_the_base_state_score_without_the_extras():
    assert calculate_bottom_confirmation(confirmed(200)) == 80
    assert calculate_bottom_confirmation(confirmed(61)) == 80


def test_unknown_age_is_treated_as_fresh_for_older_reports():
    assert calculate_bottom_confirmation(confirmed(None)) == 93.0


def contrarian_score(signals):
    comp = {k: {"score": 20} for k in COMPONENT_WEIGHTS}
    full = {
        "macro_regime": {"regime": "contraction", "composite_score": 20, "transition_level": "low"},
        "market_top": {"composite_score": 80},
        "market_breadth": {"composite_score": 25},
        **signals,
    }
    result = classify_pattern(full, comp, 30)
    return result["all_pattern_scores"]["extreme_sentiment_contrarian"]


def test_contrarian_pattern_extras_need_a_fresh_ftd():
    assert contrarian_score(confirmed(30)) == 100  # 40 + 15 + 20 + 15 + 10
    assert contrarian_score(confirmed(200)) == 45  # the FTD adds nothing
    assert contrarian_score(confirmed(None)) == 100


def test_report_loader_reads_the_ftd_age_from_the_source_lifecycle():
    data = {
        "market_state": {"combined_state": "FTD_CONFIRMED", "dual_confirmation": False},
        "quality_score": {"total_score": 85, "signal": "Strong FTD"},
        "post_ftd_distribution": {"distribution_count": 0},
        "ftd_invalidation": {"invalidated": False, "days_since_ftd": 200},
    }
    assert extract_signal("ftd_detector", data)["days_since_ftd"] == 200
    del data["ftd_invalidation"]
    assert extract_signal("ftd_detector", data)["days_since_ftd"] is None


def with_status(signals, market_status):
    signals["ftd_detector"]["market_status"] = market_status
    return signals


def test_extras_need_the_uptrend_not_to_be_under_pressure():
    fresh = confirmed(30)
    assert calculate_bottom_confirmation(with_status(fresh, "confirmed_uptrend")) == 93.0
    pressured = with_status(confirmed(30), "uptrend_under_pressure")
    assert calculate_bottom_confirmation(pressured) == 80  # the base state score is unchanged
    assert contrarian_score(with_status(confirmed(30), "confirmed_uptrend")) == 100
    assert contrarian_score(pressured) == 45


def test_both_conditions_are_required_for_the_extras():
    old_and_confirmed = with_status(confirmed(200), "confirmed_uptrend")
    assert calculate_bottom_confirmation(old_and_confirmed) == 80
    old_and_pressured = with_status(confirmed(200), "uptrend_under_pressure")
    assert calculate_bottom_confirmation(old_and_pressured) == 80
    unknown_status = with_status(confirmed(30), None)  # older reports: not under pressure
    assert calculate_bottom_confirmation(unknown_status) == 93.0


def test_report_loader_reads_the_market_status():
    data = {
        "market_state": {
            "combined_state": "FTD_CONFIRMED",
            "market_status": "uptrend_under_pressure",
        },
        "quality_score": {"total_score": 85, "signal": "Strong FTD"},
        "ftd_invalidation": {"days_since_ftd": 10},
    }
    assert extract_signal("ftd_detector", data)["market_status"] == "uptrend_under_pressure"
    del data["market_state"]["market_status"]
    assert extract_signal("ftd_detector", data)["market_status"] is None
