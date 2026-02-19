"""Tests for allocation_engine.py"""

import pytest

from allocation_engine import (
    generate_allocation,
    calculate_position_sizing,
    ZONE_BASE_ALLOCATIONS,
)


class TestBaseAllocations:
    """Verify base allocation structure and constraints."""

    def test_all_zones_sum_to_100(self):
        """Every zone's base allocation must sum to 100%."""
        for zone, alloc in ZONE_BASE_ALLOCATIONS.items():
            total = sum(alloc.values())
            assert abs(total - 100) < 0.01, (
                f"Zone '{zone}' sums to {total}, expected 100"
            )

    def test_all_zones_present(self):
        assert "Maximum Conviction" in ZONE_BASE_ALLOCATIONS
        assert "High Conviction" in ZONE_BASE_ALLOCATIONS
        assert "Moderate Conviction" in ZONE_BASE_ALLOCATIONS
        assert "Low Conviction" in ZONE_BASE_ALLOCATIONS
        assert "Capital Preservation" in ZONE_BASE_ALLOCATIONS


class TestGenerateAllocation:
    """Test the full allocation pipeline."""

    def test_max_conviction_equity_heavy(self):
        result = generate_allocation(
            conviction_score=85,
            zone="Maximum Conviction",
            pattern="policy_pivot_anticipation",
            regime="broadening",
        )
        assert result["equity"] >= 80
        assert result["cash"] <= 10
        assert _total(result) == 100

    def test_capital_preservation_cash_heavy(self):
        result = generate_allocation(
            conviction_score=10,
            zone="Capital Preservation",
            pattern="unsustainable_distortion",
            regime="contraction",
        )
        assert result["cash"] >= 35
        assert result["equity"] <= 30
        assert _total(result) == 100

    def test_high_conviction_balanced(self):
        result = generate_allocation(
            conviction_score=70,
            zone="High Conviction",
            pattern="policy_pivot_anticipation",
            regime="broadening",
        )
        assert result["equity"] >= 60
        assert _total(result) == 100

    def test_moderate_conviction(self):
        result = generate_allocation(
            conviction_score=50,
            zone="Moderate Conviction",
            pattern="wait_and_observe",
            regime="transitional",
        )
        assert 40 <= result["equity"] <= 70
        assert _total(result) == 100

    def test_low_conviction(self):
        result = generate_allocation(
            conviction_score=30,
            zone="Low Conviction",
            pattern="wait_and_observe",
            regime="contraction",
        )
        assert result["equity"] <= 50
        assert result["cash"] >= 25
        assert _total(result) == 100

    def test_contraction_regime_shifts_to_defensive(self):
        """Contraction regime should reduce equity vs broadening."""
        broadening = generate_allocation(
            conviction_score=60, zone="High Conviction",
            pattern="wait_and_observe", regime="broadening",
        )
        contraction = generate_allocation(
            conviction_score=60, zone="High Conviction",
            pattern="wait_and_observe", regime="contraction",
        )
        assert contraction["equity"] < broadening["equity"]

    def test_wait_pattern_raises_cash(self):
        """wait_and_observe pattern should increase cash allocation."""
        active = generate_allocation(
            conviction_score=60, zone="High Conviction",
            pattern="policy_pivot_anticipation", regime="broadening",
        )
        wait = generate_allocation(
            conviction_score=60, zone="High Conviction",
            pattern="wait_and_observe", regime="broadening",
        )
        assert wait["cash"] >= active["cash"]

    def test_output_has_all_asset_classes(self):
        result = generate_allocation(
            conviction_score=50, zone="Moderate Conviction",
            pattern="wait_and_observe", regime="transitional",
        )
        assert "equity" in result
        assert "cash" in result
        assert "bonds" in result
        assert "alternatives" in result

    def test_all_values_non_negative(self):
        result = generate_allocation(
            conviction_score=50, zone="Moderate Conviction",
            pattern="wait_and_observe", regime="transitional",
        )
        for k, v in result.items():
            if k != "rationale":
                assert v >= 0, f"{k} is negative: {v}"

    def test_extreme_contrarian_boosts_equity(self):
        """Extreme contrarian (FTD confirmed in bear) should be aggressive."""
        normal = generate_allocation(
            conviction_score=40, zone="Moderate Conviction",
            pattern="wait_and_observe", regime="contraction",
        )
        contrarian = generate_allocation(
            conviction_score=40, zone="Moderate Conviction",
            pattern="extreme_sentiment_contrarian", regime="contraction",
        )
        assert contrarian["equity"] >= normal["equity"]


class TestPositionSizing:
    """Test position sizing calculations."""

    def test_max_conviction_large_positions(self):
        sizing = calculate_position_sizing(conviction_score=85, zone="Maximum Conviction")
        assert sizing["max_single_position"] >= 15
        assert sizing["daily_vol_target"] >= 0.3

    def test_preservation_small_positions(self):
        sizing = calculate_position_sizing(conviction_score=10, zone="Capital Preservation")
        assert sizing["max_single_position"] <= 5
        assert sizing["daily_vol_target"] <= 0.2

    def test_output_structure(self):
        sizing = calculate_position_sizing(conviction_score=50, zone="Moderate Conviction")
        assert "max_single_position" in sizing
        assert "daily_vol_target" in sizing
        assert "max_positions" in sizing


def _total(alloc: dict) -> float:
    """Sum only numeric allocation values (rounded to avoid FP noise)."""
    return round(sum(v for k, v in alloc.items() if isinstance(v, (int, float))), 1)
