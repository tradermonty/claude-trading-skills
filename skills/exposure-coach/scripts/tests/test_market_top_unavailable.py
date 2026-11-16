"""Unassessed market-top reports are missing inputs, never healthy scores."""

import pytest
from calculate_exposure import extract_top_risk_score


@pytest.mark.parametrize(
    "composite", [{"composite_score": None}, {"composite_score": 50, "data_available": False}]
)
def test_unavailable_market_top_is_missing(composite):
    assert (
        extract_top_risk_score(
            {
                "composite": composite,
                "top_risk_score": 100,
                "top_probability": 0,
                "distribution_days": 0,
            }
        )
        is None
    )


def test_legacy_market_top_score_still_inverts():
    assert extract_top_risk_score({"composite": {"composite_score": 0}}) == 100
