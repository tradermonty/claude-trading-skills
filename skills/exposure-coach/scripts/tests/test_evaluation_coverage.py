"""Declared unavailable evidence must not become a neutral or bullish score."""

import calculate_exposure as coach
import pytest


@pytest.mark.parametrize(
    "extractor,field",
    [
        (coach.extract_breadth_score, "breadth_score"),
        (coach.extract_uptrend_score, "uptrend_score"),
        (coach.extract_top_risk_score, "top_risk_score"),
        (coach.extract_regime_score, "regime_score"),
        (coach.extract_ftd_score, "ftd_score"),
        (coach.extract_theme_score, "theme_score"),
        (coach.extract_sector_score, "sector_score"),
        (coach.extract_institutional_score, "institutional_score"),
    ],
)
@pytest.mark.parametrize(
    "coverage",
    [
        {
            "schema_version": "1.0",
            "universe_size": 1,
            "evaluated": 0,
            "not_evaluated": 1,
            "not_evaluated_reasons": {"provider_error": 1},
            "verdict": "not_evaluable",
        },
        {"schema_version": "future", "verdict": "complete"},
    ],
)
def test_declared_unavailable_or_invalid_input_is_excluded(extractor, field, coverage):
    assert extractor({field: 100, "evaluation_coverage": coverage}) is None


def test_complete_and_legacy_inputs_keep_their_score():
    data = {"breadth_score": 80}
    assert coach.extract_breadth_score(data) == 80
    data["evaluation_coverage"] = {
        "schema_version": "1.0",
        "universe_size": 1,
        "evaluated": 1,
        "not_evaluated": 0,
        "not_evaluated_reasons": {},
        "verdict": "complete",
    }
    assert coach.extract_breadth_score(data) == 80
