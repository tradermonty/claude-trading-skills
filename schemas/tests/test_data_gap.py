"""Tests for schemas/data_gap.py — DataGapCollector utility."""

from __future__ import annotations

from schemas.data_gap import DataGapCollector


class TestDataGapCollector:
    def test_empty_collector(self):
        c = DataGapCollector("test-skill")
        assert c.to_list() == []
        assert c.derive_confidence() == "HIGH"
        assert c.can_continue() is True
        assert c.has_critical() is False
        assert len(c) == 0
        assert not c  # bool(c) is False when empty

    def test_add_gap(self):
        c = DataGapCollector("test-skill")
        c.add(
            severity="HIGH",
            description="API empty",
            affected_decision="scoring",
            remediation="retry",
            can_continue=False,
        )
        assert len(c) == 1
        assert c.can_continue() is False
        assert c.derive_confidence() == "LOW"

    def test_add_api_key_missing(self):
        c = DataGapCollector("vcp-screener")
        c.add_api_key_missing("FMP", "FMP_API_KEY")
        gaps = c.to_list()
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "CRITICAL"
        assert gaps[0]["can_continue"] is False
        assert "FMP_API_KEY" in gaps[0]["remediation"]

    def test_add_api_empty_response(self):
        c = DataGapCollector("vcp-screener")
        c.add_api_empty_response("FMP", "historical-price", symbol="SPY")
        gaps = c.to_list()
        assert gaps[0]["severity"] == "HIGH"
        assert "SPY" in gaps[0]["description"]

    def test_add_stale_data_medium(self):
        c = DataGapCollector("market-breadth-analyzer")
        c.add_stale_data("market_breadth_csv", age_days=4, threshold_days=5)
        assert c.derive_confidence() == "MEDIUM"

    def test_add_stale_data_high(self):
        c = DataGapCollector("market-breadth-analyzer")
        c.add_stale_data("market_breadth_csv", age_days=11, threshold_days=5)
        assert c.derive_confidence() == "LOW"

    def test_add_small_sample_high(self):
        c = DataGapCollector("backtest-expert")
        c.add_small_sample(n_trades=10, minimum=30)
        gaps = c.to_list()
        assert gaps[0]["severity"] == "HIGH"
        assert c.derive_confidence() == "LOW"

    def test_add_small_sample_medium(self):
        c = DataGapCollector("backtest-expert")
        c.add_small_sample(n_trades=50, minimum=30)
        gaps = c.to_list()
        assert gaps[0]["severity"] == "MEDIUM"
        assert c.derive_confidence() == "MEDIUM"

    def test_add_low_liquidity_critical(self):
        c = DataGapCollector("vcp-screener")
        c.add_low_liquidity("TINY", avg_volume=50_000)
        gaps = c.to_list()
        assert gaps[0]["severity"] == "CRITICAL"
        assert c.has_critical() is True

    def test_add_low_liquidity_high(self):
        c = DataGapCollector("vcp-screener")
        c.add_low_liquidity("ILLIQ", avg_volume=200_000)
        gaps = c.to_list()
        assert gaps[0]["severity"] == "HIGH"
        # HIGH liquidity gap: skill can continue (flags it) but should not generate trade plan
        assert c.can_continue() is True
        assert "Exclude" in gaps[0]["remediation"]

    def test_derive_confidence_multiple_gaps(self):
        c = DataGapCollector("exposure-coach")
        c.add(severity="LOW", description="x", affected_decision="y", remediation="z", can_continue=True)
        c.add(severity="MEDIUM", description="a", affected_decision="b", remediation="c", can_continue=True)
        # Worst is MEDIUM → confidence MEDIUM
        assert c.derive_confidence() == "MEDIUM"

    def test_derive_confidence_critical_overrides(self):
        c = DataGapCollector("exposure-coach")
        c.add(severity="LOW", description="x", affected_decision="y", remediation="z", can_continue=True)
        c.add(severity="CRITICAL", description="a", affected_decision="b", remediation="c", can_continue=False)
        assert c.derive_confidence() == "LOW"
        assert c.has_critical() is True

    def test_summary_non_empty(self):
        c = DataGapCollector("vcp-screener")
        c.add(severity="HIGH", description="x", affected_decision="y", remediation="z", can_continue=False)
        s = c.summary()
        assert "HIGH:1" in s
        assert "1 data gap" in s

    def test_summary_empty(self):
        c = DataGapCollector("vcp-screener")
        assert c.summary() == "No data gaps"

    def test_gap_ids_unique(self):
        c = DataGapCollector("test")
        for _ in range(5):
            c.add(
                severity="LOW",
                description="dup",
                affected_decision="x",
                remediation="y",
                can_continue=True,
            )
        ids = [g["gap_id"] for g in c.to_list()]
        assert len(set(ids)) == 5
