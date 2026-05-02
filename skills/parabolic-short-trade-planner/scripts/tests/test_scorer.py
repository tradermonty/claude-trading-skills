"""Tests for scorer.calculate_composite_score and grade_at_or_above."""

import pytest
from parabolic_scorer import COMPONENT_WEIGHTS, calculate_composite_score, grade_at_or_above


def _components(**overrides) -> dict:
    base = {
        "ma_extension": 80.0,
        "acceleration": 80.0,
        "volume_climax": 80.0,
        "range_expansion": 80.0,
        "liquidity": 80.0,
    }
    base.update(overrides)
    return base


class TestCompositeMath:
    def test_all_eighty_returns_eighty(self):
        out = calculate_composite_score(_components())
        assert out["score"] == pytest.approx(80.0)
        # Weights must sum to 1.0 — guard the invariant.
        assert sum(COMPONENT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_grade_a_at_85(self):
        out = calculate_composite_score(_components(ma_extension=100, acceleration=100))
        assert out["grade"] == "A"

    def test_grade_d_when_all_zero(self):
        out = calculate_composite_score(_components(**{k: 0 for k in COMPONENT_WEIGHTS}))
        assert out["grade"] == "D"

    def test_grade_b_in_70s(self):
        out = calculate_composite_score(
            _components(
                ma_extension=70, acceleration=70, volume_climax=70, range_expansion=70, liquidity=70
            )
        )
        assert out["grade"] == "B"


class TestComponentBreakdown:
    def test_breakdown_sums_to_score(self):
        out = calculate_composite_score(_components(ma_extension=90, liquidity=50))
        weighted = sum(b["weighted_score"] for b in out["component_breakdown"].values())
        assert weighted == pytest.approx(out["score"], abs=0.5)

    def test_weakest_strongest_identified(self):
        out = calculate_composite_score(_components(ma_extension=20, acceleration=95))
        assert out["weakest_component"] == "ma_extension"
        assert out["strongest_component"] == "acceleration"


class TestGradeAtOrAbove:
    def test_a_meets_b_threshold(self):
        assert grade_at_or_above("A", "B") is True

    def test_c_does_not_meet_b(self):
        assert grade_at_or_above("C", "B") is False

    def test_same_grade_passes(self):
        assert grade_at_or_above("B", "B") is True

    def test_unknown_grade_returns_false(self):
        assert grade_at_or_above("Z", "B") is False
