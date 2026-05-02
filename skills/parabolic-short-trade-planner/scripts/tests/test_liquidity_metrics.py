"""Tests for calculators.liquidity_calculator."""

import pytest
from liquidity_metrics_calculator import (
    adv_dollars,
    calculate_liquidity,
    latest_volume_ratio,
)


class TestADV:
    def test_basic_calculation(self):
        closes = [10.0] * 20
        volumes = [1_000_000] * 20
        # ADV = 10 * 1M = 10M
        assert adv_dollars(closes, volumes) == pytest.approx(10_000_000)

    def test_insufficient_history_returns_none(self):
        assert adv_dollars([10.0] * 5, [1_000_000] * 5, period=20) is None


class TestVolumeRatio:
    def test_latest_higher_returns_above_one(self):
        volumes = [1_000_000] * 20 + [4_000_000]
        ratio = latest_volume_ratio(volumes)
        assert ratio == pytest.approx(4.0)


class TestAggregated:
    def test_score_zero_at_10m_adv(self):
        closes = [10.0] * 20
        volumes = [1_000_000] * 20
        out = calculate_liquidity(closes, volumes)
        assert out["adv_20d_usd"] == pytest.approx(10_000_000)
        assert out["liquidity_score_0_to_10"] == pytest.approx(0.0)

    def test_score_caps_at_max_for_large_adv(self):
        closes = [100.0] * 20
        volumes = [10_000_000] * 20  # ADV = $1B → log10 = 9 > hi=8.5
        out = calculate_liquidity(closes, volumes)
        assert out["liquidity_score_0_to_10"] == pytest.approx(10.0)
