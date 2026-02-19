"""Tests for finviz_performance_client outlier winsorization."""

from finviz_performance_client import cap_outlier_performances, _apply_hard_caps, HARD_CAPS


class TestCapOutlierPerformances:
    def test_no_outliers(self):
        """Normal data should pass through unchanged."""
        data = [
            {"name": "A", "perf_1w": 2.0, "perf_1m": 5.0, "perf_3m": 10.0, "perf_6m": 15.0},
            {"name": "B", "perf_1w": -1.0, "perf_1m": 3.0, "perf_3m": 8.0, "perf_6m": 12.0},
        ]
        result = cap_outlier_performances(data)
        assert result[0]["perf_1w"] == 2.0
        assert result[1]["perf_1w"] == -1.0

    def test_outlier_capped(self):
        """Extreme outlier should be capped to z_threshold boundary."""
        data = [
            {"name": f"I{i}", "perf_1w": 2.0, "perf_1m": 5.0, "perf_3m": 10.0, "perf_6m": 15.0}
            for i in range(20)
        ]
        # Add extreme outlier
        data.append({"name": "Outlier", "perf_1w": 99.0, "perf_1m": 5.0,
                      "perf_3m": 10.0, "perf_6m": 15.0})
        result = cap_outlier_performances(data)
        outlier = next(r for r in result if r["name"] == "Outlier")
        # Should be capped and original preserved
        assert outlier["perf_1w"] < 99.0
        assert outlier.get("raw_perf_1w") == 99.0

    def test_raw_fields_preserved(self):
        """When an outlier is capped, raw_perf_* should store original value."""
        data = [
            {"name": f"I{i}", "perf_1w": 2.0, "perf_1m": 5.0, "perf_3m": 10.0, "perf_6m": 15.0}
            for i in range(20)
        ]
        data.append({"name": "Extreme", "perf_1w": -99.0, "perf_1m": 5.0,
                      "perf_3m": 10.0, "perf_6m": 15.0})
        result = cap_outlier_performances(data)
        extreme = next(r for r in result if r["name"] == "Extreme")
        assert "raw_perf_1w" in extreme
        assert extreme["raw_perf_1w"] == -99.0

    def test_none_values_skipped(self):
        """None performance values should not cause errors."""
        data = [
            {"name": "A", "perf_1w": 2.0, "perf_1m": None, "perf_3m": 10.0, "perf_6m": 15.0},
            {"name": "B", "perf_1w": None, "perf_1m": 3.0, "perf_3m": 8.0, "perf_6m": 12.0},
        ]
        result = cap_outlier_performances(data)
        assert result[0]["perf_1m"] is None
        assert result[1]["perf_1w"] is None

    def test_empty_input(self):
        assert cap_outlier_performances([]) == []

    def test_small_dataset_skipped(self):
        """With fewer than 5 entries, z-score winsorization should not apply
        but hard caps still apply."""
        data = [
            {"name": "A", "perf_1w": 99.0, "perf_1m": 5.0, "perf_3m": 10.0, "perf_6m": 15.0},
        ]
        result = cap_outlier_performances(data)
        # Hard cap clips to 30.0 even for small datasets
        assert result[0]["perf_1w"] == HARD_CAPS["perf_1w"]


class TestApplyHardCaps:
    def test_perf_1w_capped_positive(self):
        """perf_1w exceeding +30% should be capped to +30%."""
        data = [{"name": "A", "perf_1w": 87.0}]
        _apply_hard_caps(data)
        assert data[0]["perf_1w"] == 30.0
        assert data[0]["raw_perf_1w"] == 87.0

    def test_perf_1w_capped_negative(self):
        """perf_1w below -30% should be capped to -30%."""
        data = [{"name": "A", "perf_1w": -100.0}]
        _apply_hard_caps(data)
        assert data[0]["perf_1w"] == -30.0
        assert data[0]["raw_perf_1w"] == -100.0

    def test_within_cap_unchanged(self):
        """Values within hard cap range should not be modified."""
        data = [{"name": "A", "perf_1w": 15.0, "perf_1m": -40.0, "perf_3m": 50.0}]
        _apply_hard_caps(data)
        assert data[0]["perf_1w"] == 15.0
        assert data[0]["perf_1m"] == -40.0
        assert data[0]["perf_3m"] == 50.0
        assert "raw_perf_1w" not in data[0]
        assert "raw_perf_1m" not in data[0]
        assert "raw_perf_3m" not in data[0]

    def test_raw_not_overwritten_by_second_stage(self):
        """raw_perf_* set by hard cap should not be overwritten by z-score stage."""
        data = [{"name": f"I{i}", "perf_1w": 5.0} for i in range(20)]
        # Add one that triggers hard cap
        data.append({"name": "Extreme", "perf_1w": 50.0})
        cap_outlier_performances(data)
        extreme = next(r for r in data if r["name"] == "Extreme")
        # raw_perf_1w should store original 50.0 (from hard cap), not 30.0
        assert extreme["raw_perf_1w"] == 50.0

    def test_none_values_skipped(self):
        """None perf values should be skipped without error."""
        data = [{"name": "A", "perf_1w": None, "perf_1m": 70.0}]
        _apply_hard_caps(data)
        assert data[0]["perf_1w"] is None
        assert data[0]["perf_1m"] == 60.0

    def test_all_perf_keys_capped(self):
        """All perf_* keys should be capped at their respective limits."""
        data = [{
            "name": "A",
            "perf_1w": 999.0,
            "perf_1m": 999.0,
            "perf_3m": 999.0,
            "perf_6m": 999.0,
            "perf_1y": 999.0,
            "perf_ytd": 999.0,
        }]
        _apply_hard_caps(data)
        for key, cap in HARD_CAPS.items():
            assert data[0][key] == cap
