"""Tests for report_generator data quality assessment and markdown generation."""

from report_generator import _assess_data_quality, generate_markdown_report, generate_json_report


class TestAssessDataQuality:
    def _base_metadata(self):
        return {
            "data_sources": {
                "scanner_backend": {
                    "fmp_calls": 10,
                    "fmp_failures": 0,
                    "yf_calls": 0,
                    "yf_fallbacks": 0,
                },
            },
        }

    def test_all_healthy(self):
        """No issues should return ok status."""
        metadata = self._base_metadata()
        themes = [{"name": "Test"}]
        rankings = {"top": [{"name": "A"}], "bottom": [{"name": "B"}]}
        uptrend = {"Tech": {"ratio": 0.5, "latest_date": "2026-02-19"}}
        result = _assess_data_quality(themes, rankings, uptrend, metadata)
        assert result["status"] == "ok"
        assert not result["flags"]

    def test_high_fmp_failure_rate(self):
        """FMP failure rate > 20% should generate warning."""
        metadata = self._base_metadata()
        metadata["data_sources"]["scanner_backend"]["fmp_failures"] = 6
        themes = [{"name": "Test"}]
        rankings = {"top": [{"name": "A"}], "bottom": [{"name": "B"}]}
        uptrend = {"Tech": {"ratio": 0.5, "latest_date": "2026-02-19"}}
        result = _assess_data_quality(themes, rankings, uptrend, metadata)
        assert result["status"] == "warning"
        assert any("FMP API" in f for f in result["flags"])

    def test_yf_fallback_warning(self):
        """yfinance fallbacks should generate informational flag."""
        metadata = self._base_metadata()
        metadata["data_sources"]["scanner_backend"]["yf_fallbacks"] = 3
        themes = [{"name": "Test"}]
        rankings = {"top": [{"name": "A"}], "bottom": [{"name": "B"}]}
        uptrend = {"Tech": {"ratio": 0.5, "latest_date": "2026-02-19"}}
        result = _assess_data_quality(themes, rankings, uptrend, metadata)
        assert any("yfinance" in f.lower() for f in result["flags"])

    def test_no_themes(self):
        metadata = self._base_metadata()
        result = _assess_data_quality([], {"top": [], "bottom": []}, {}, metadata)
        assert result["status"] == "warning"

    def test_missing_scanner_backend(self):
        """Should handle missing scanner_backend gracefully."""
        metadata = {"data_sources": {}}
        themes = [{"name": "Test"}]
        rankings = {"top": [{"name": "A"}], "bottom": [{"name": "B"}]}
        uptrend = {"Tech": {"ratio": 0.5, "latest_date": "2026-02-19"}}
        result = _assess_data_quality(themes, rankings, uptrend, metadata)
        # Should not crash
        assert result["status"] in ("ok", "warning")


class TestLifecycleDataQualityInReport:
    def _make_theme(self, lifecycle_quality="sufficient"):
        return {
            "name": "Test Theme",
            "direction": "bullish",
            "heat": 65.0,
            "maturity": 45.0,
            "stage": "Trending",
            "confidence": "Medium",
            "heat_label": "Hot",
            "heat_breakdown": {"momentum_strength": 70.0},
            "maturity_breakdown": {"duration_estimate": 50.0, "extremity_clustering": 50.0},
            "lifecycle_data_quality": lifecycle_quality,
            "representative_stocks": ["AAPL"],
            "stock_details": [],
            "proxy_etfs": ["XLK"],
            "industries": ["Semiconductors"],
            "sector_weights": {"Technology": 1.0},
            "stock_data": "available",
            "data_mode": "enhanced",
            "stale_data_penalty": False,
            "theme_origin": "seed",
            "name_confidence": "high",
        }

    def test_insufficient_shows_note(self):
        """Insufficient lifecycle data quality should show note in markdown."""
        theme = self._make_theme("insufficient")
        json_data = generate_json_report(
            [theme], {"top": [], "bottom": []}, {},
            {"generated_at": "2026-02-19", "data_sources": {}},
        )
        md = generate_markdown_report(json_data)
        assert "Maturity based on defaults" in md

    def test_sufficient_no_note(self):
        """Sufficient lifecycle data quality should not show the note."""
        theme = self._make_theme("sufficient")
        json_data = generate_json_report(
            [theme], {"top": [], "bottom": []}, {},
            {"generated_at": "2026-02-19", "data_sources": {}},
        )
        md = generate_markdown_report(json_data)
        assert "Maturity based on defaults" not in md
