"""Tests for calculate_exposure.py."""

import json

from calculate_exposure import (
    CRITICAL_INPUTS,
    WEIGHTS,
    calculate_composite_score,
    determine_bias,
    determine_confidence,
    determine_exposure_ceiling,
    determine_participation,
    determine_recommendation,
    extract_breadth_score,
    extract_ftd_score,
    extract_regime_name,
    extract_regime_score,
    extract_top_risk_score,
    extract_uptrend_score,
    generate_markdown_report,
    generate_rationale,
    load_json_file,
)


class TestExtractBreadthScore:
    """Tests for breadth score extraction."""

    def test_direct_breadth_score(self):
        data = {"breadth_score": 75}
        assert extract_breadth_score(data) == 75

    def test_composite_score_fallback(self):
        data = {"composite_score": 60}
        assert extract_breadth_score(data) == 60

    def test_ad_ratio_calculation_high(self):
        data = {"ad_ratio": 2.0, "nh_nl_ratio": 4.0}
        assert extract_breadth_score(data) == 90

    def test_ad_ratio_calculation_mid(self):
        data = {"ad_ratio": 1.2, "nh_nl_ratio": 1.5}
        assert extract_breadth_score(data) == 65

    def test_ad_ratio_calculation_low(self):
        data = {"ad_ratio": 0.5, "nh_nl_ratio": 0.3}
        assert extract_breadth_score(data) == 20

    def test_nested_composite_score(self):
        # market-breadth-analyzer nests its 0-100 health score under "composite"
        data = {"composite": {"composite_score": 72}}
        assert extract_breadth_score(data) == 72

    def test_flat_takes_priority_over_nested(self):
        data = {"breadth_score": 65, "composite": {"composite_score": 10}}
        assert extract_breadth_score(data) == 65

    def test_non_dict_composite_ignored(self):
        data = {"composite": "n/a", "ad_ratio": 2.0, "nh_nl_ratio": 4.0}
        assert extract_breadth_score(data) == 90

    def test_none_input(self):
        assert extract_breadth_score(None) is None

    def test_empty_dict(self):
        assert extract_breadth_score({}) is None


class TestExtractUptrendScore:
    """Tests for uptrend score extraction."""

    def test_direct_score(self):
        data = {"uptrend_score": 80}
        assert extract_uptrend_score(data) == 80

    def test_uptrend_pct_high(self):
        data = {"uptrend_pct": 60}
        score = extract_uptrend_score(data)
        assert score >= 75

    def test_uptrend_pct_mid(self):
        data = {"uptrend_pct": 40}
        score = extract_uptrend_score(data)
        assert 50 <= score <= 80

    def test_uptrend_pct_low(self):
        data = {"uptrend_pct": 15}
        score = extract_uptrend_score(data)
        assert score < 30

    def test_nested_composite_score(self):
        # uptrend-analyzer stores its score under "composite"
        data = {"composite": {"composite_score": 72}}
        assert extract_uptrend_score(data) == 72

    def test_nested_composite_uptrend_pct(self):
        data = {"composite": {"uptrend_pct": 60}}
        assert extract_uptrend_score(data) >= 75

    def test_flat_takes_priority_over_nested(self):
        data = {"uptrend_score": 80, "composite": {"composite_score": 10}}
        assert extract_uptrend_score(data) == 80

    def test_non_dict_composite_ignored(self):
        data = {"composite": "n/a", "uptrend_pct": 40}
        score = extract_uptrend_score(data)
        assert 50 <= score <= 80

    def test_none_input(self):
        assert extract_uptrend_score(None) is None

    def test_empty_dict(self):
        assert extract_uptrend_score({}) is None


class TestExtractRegimeScore:
    """Tests for regime score extraction."""

    def test_broadening_regime(self):
        data = {"regime": "Broadening"}
        assert extract_regime_score(data) == 80

    def test_contraction_regime(self):
        data = {"regime": "contraction"}
        assert extract_regime_score(data) == 20

    def test_current_regime_field(self):
        data = {"current_regime": "Transitional"}
        assert extract_regime_score(data) == 50

    def test_direct_regime_score(self):
        data = {"regime_score": 65}
        assert extract_regime_score(data) == 65

    def test_nested_regime_dict_current_regime(self):
        # macro-regime-detector emits regime as a nested object
        data = {"regime": {"current_regime": "Broadening"}}
        assert extract_regime_score(data) == 80

    def test_nested_regime_dict_unknown_defaults_50(self):
        data = {"regime": {"current_regime": "Sideways"}}
        assert extract_regime_score(data) == 50

    def test_nested_regime_dict_no_current_regime(self):
        data = {"regime": {"regime_label": "Risk-On"}}
        assert extract_regime_score(data) is None

    def test_none_input(self):
        assert extract_regime_score(None) is None

    def test_empty_dict(self):
        assert extract_regime_score({}) is None


class TestExtractRegimeName:
    """Tests for regime name extraction (incl. nested dict regression)."""

    def test_flat_string_regime(self):
        assert extract_regime_name({"regime": "broadening"}) == "Broadening"

    def test_flat_current_regime(self):
        assert extract_regime_name({"current_regime": "contraction"}) == "Contraction"

    def test_nested_label_preferred(self):
        data = {"regime": {"regime_label": "Risk-On", "current_regime": "broadening"}}
        assert extract_regime_name(data) == "Risk-on"

    def test_nested_current_regime_fallback(self):
        data = {"regime": {"current_regime": "transitional"}}
        assert extract_regime_name(data) == "Transitional"

    def test_nested_empty_dict_returns_unknown(self):
        assert extract_regime_name({"regime": {}}) == "Unknown"

    def test_dict_input_does_not_raise(self):
        # Regression: previously data["regime"].capitalize() raised on dict
        data = {"regime": {"current_regime": "broadening"}}
        result = extract_regime_name(data)
        assert isinstance(result, str)

    def test_none_input(self):
        assert extract_regime_name(None) == "Unknown"

    def test_empty_dict(self):
        assert extract_regime_name({}) == "Unknown"


class TestExtractTopRiskScore:
    """Tests for top risk score extraction."""

    def test_direct_score(self):
        data = {"top_risk_score": 30}
        assert extract_top_risk_score(data) == 30

    def test_top_probability_high(self):
        # High probability = low score (inverted)
        data = {"top_probability": 80}
        assert extract_top_risk_score(data) == 20

    def test_top_probability_low(self):
        # Low probability = high score
        data = {"top_probability": 10}
        assert extract_top_risk_score(data) == 90

    def test_distribution_days_few(self):
        data = {"distribution_days": 1}
        assert extract_top_risk_score(data) == 90

    def test_distribution_days_many(self):
        data = {"distribution_days": 8}
        assert extract_top_risk_score(data) == 15

    def test_nested_composite_inverted_high_risk(self):
        # market-top-detector composite=85 (Critical/Top Formation) -> low score
        data = {"composite": {"composite_score": 85}}
        assert extract_top_risk_score(data) == 15

    def test_nested_composite_inverted_low_risk(self):
        # composite=15 (Green/Normal) -> high (safe) score
        data = {"composite": {"composite_score": 15}}
        assert extract_top_risk_score(data) == 85

    def test_flat_takes_priority_over_nested(self):
        # explicit top_risk_score is already exposure-friendly; not inverted
        data = {"top_risk_score": 40, "composite": {"composite_score": 85}}
        assert extract_top_risk_score(data) == 40


class TestExtractFtdScore:
    """Tests for Follow-Through-Day score extraction (high = bullish, NOT inverted)."""

    def test_direct_ftd_score(self):
        assert extract_ftd_score({"ftd_score": 70}) == 70

    def test_nested_quality_score_strong(self):
        # ftd-detector real shape: strong FTD -> high score (bullish, direct)
        data = {"quality_score": {"total_score": 82, "signal": "Strong FTD"}}
        assert extract_ftd_score(data) == 82

    def test_nested_quality_score_no_ftd(self):
        data = {"quality_score": {"total_score": 0, "signal": "No FTD"}}
        assert extract_ftd_score(data) == 0

    def test_legacy_anomaly_level_still_supported(self):
        assert extract_ftd_score({"anomaly_level": "none"}) == 90

    def test_none_and_empty(self):
        assert extract_ftd_score(None) is None
        assert extract_ftd_score({}) is None


class TestRealUpstreamShapesAllCount:
    """Regression: the real upstream JSON shapes must all produce a score.

    Reproduces the reported bug where breadth/top_risk/ftd silently returned
    None (only regime + uptrend counted), forcing a missing-critical haircut
    and a CASH_PRIORITY / LOW-confidence verdict.
    """

    def test_all_five_inputs_extracted(self):
        breadth = {"composite": {"composite_score": 70}}  # market-breadth-analyzer
        uptrend = {"composite": {"composite_score": 65}}  # uptrend-analyzer
        regime = {"regime": {"current_regime": "broadening"}}  # macro-regime-detector
        top_risk = {"composite": {"composite_score": 20}}  # market-top-detector (low risk)
        ftd = {"quality_score": {"total_score": 75}}  # ftd-detector (strong FTD)

        scores = {
            "breadth": extract_breadth_score(breadth),
            "uptrend": extract_uptrend_score(uptrend),
            "regime": extract_regime_score(regime),
            "top_risk": extract_top_risk_score(top_risk),
            "ftd": extract_ftd_score(ftd),
        }
        # The bug: breadth/top_risk/ftd were None. All five must now resolve.
        assert all(v is not None for v in scores.values()), scores
        assert scores["breadth"] == 70
        assert scores["top_risk"] == 80  # inverted: 100 - 20
        assert scores["ftd"] == 75  # direct

        composite, provided, missing = calculate_composite_score(
            {**scores, "institutional": None, "sector": None, "theme": None}
        )
        # No critical input missing -> no haircut; healthy composite, not cash-priority
        assert set(missing).isdisjoint(CRITICAL_INPUTS)
        assert composite > 50


class TestCalculateCompositeScore:
    """Tests for composite score calculation."""

    def test_all_inputs_provided(self):
        scores = {
            "regime": 80,
            "top_risk": 70,
            "breadth": 65,
            "uptrend": 60,
            "institutional": 75,
            "sector": 70,
            "theme": 65,
            "ftd": 80,
        }
        composite, provided, missing = calculate_composite_score(scores)
        assert len(provided) == 8
        assert len(missing) == 0
        # Weighted average check
        expected = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
        assert abs(composite - expected) < 0.1

    def test_missing_critical_inputs(self):
        scores = {
            "regime": None,  # critical
            "top_risk": None,  # critical
            "breadth": 65,  # critical but present
            "uptrend": 60,
            "institutional": 75,
            "sector": 70,
            "theme": 65,
            "ftd": 80,
        }
        composite, provided, missing = calculate_composite_score(scores)
        assert "regime" in missing
        assert "top_risk" in missing
        # Haircut applied: 2 critical missing * 10 = 20
        assert len(provided) == 6

    def test_no_inputs(self):
        scores = {k: None for k in WEIGHTS}
        composite, provided, missing = calculate_composite_score(scores)
        assert composite == 50.0  # Default when no inputs
        assert len(provided) == 0
        assert len(missing) == 8


class TestDetermineExposureCeiling:
    """Tests for exposure ceiling mapping."""

    def test_high_composite(self):
        assert determine_exposure_ceiling(90) >= 90

    def test_mid_composite(self):
        ceiling = determine_exposure_ceiling(60)
        assert 50 <= ceiling <= 80

    def test_low_composite(self):
        ceiling = determine_exposure_ceiling(25)
        assert ceiling <= 30

    def test_very_low_composite(self):
        ceiling = determine_exposure_ceiling(10)
        assert ceiling <= 10


class TestDetermineRecommendation:
    """Tests for recommendation logic."""

    def test_cash_priority_low_composite(self):
        rec = determine_recommendation(25, 50, 0)
        assert rec == "CASH_PRIORITY"

    def test_cash_priority_low_top_risk(self):
        rec = determine_recommendation(60, 20, 0)
        assert rec == "CASH_PRIORITY"

    def test_reduce_only_mid_composite(self):
        rec = determine_recommendation(45, 50, 0)
        assert rec == "REDUCE_ONLY"

    def test_reduce_only_missing_critical(self):
        rec = determine_recommendation(60, 50, 2)
        assert rec == "REDUCE_ONLY"

    def test_new_entry_allowed(self):
        rec = determine_recommendation(70, 60, 0)
        assert rec == "NEW_ENTRY_ALLOWED"


class TestDetermineBias:
    """Tests for bias determination."""

    def test_inflationary_regime(self):
        bias = determine_bias("Inflationary", 50, None, None)
        assert bias == "VALUE"

    def test_contraction_regime(self):
        bias = determine_bias("Contraction", 50, None, None)
        assert bias == "DEFENSIVE"

    def test_broadening_with_strong_theme(self):
        bias = determine_bias("Broadening", 75, None, None)
        assert bias == "GROWTH"

    def test_sector_leadership_technology(self):
        sector_data = {"leadership": "Technology"}
        bias = determine_bias("Transitional", 50, sector_data, None)
        assert bias == "GROWTH"

    def test_sector_leadership_financials(self):
        sector_data = {"leadership": "Financials"}
        bias = determine_bias("Transitional", 50, sector_data, None)
        assert bias == "VALUE"

    def test_neutral_default(self):
        bias = determine_bias("Transitional", 50, None, None)
        assert bias == "NEUTRAL"


class TestDetermineParticipation:
    """Tests for participation assessment."""

    def test_broad_participation(self):
        part = determine_participation(70, 65, {"dispersion": 0.05})
        assert part == "BROAD"

    def test_narrow_participation(self):
        part = determine_participation(30, 35, {"dispersion": 0.25})
        assert part == "NARROW"

    def test_moderate_participation(self):
        part = determine_participation(55, 40, {"dispersion": 0.10})
        assert part == "MODERATE"


class TestDetermineConfidence:
    """Tests for confidence level."""

    def test_high_confidence(self):
        provided = list(WEIGHTS.keys())[:6]
        missing = list(WEIGHTS.keys())[6:]
        # Remove critical from missing
        missing = [m for m in missing if m not in CRITICAL_INPUTS]
        conf = determine_confidence(provided, missing)
        assert conf == "HIGH"

    def test_medium_confidence(self):
        provided = ["regime", "breadth", "uptrend", "sector"]
        missing = ["top_risk", "ftd", "theme", "institutional"]
        conf = determine_confidence(provided, missing)
        assert conf == "MEDIUM"

    def test_low_confidence(self):
        provided = ["sector", "theme"]
        missing = ["regime", "top_risk", "breadth", "uptrend", "ftd", "institutional"]
        conf = determine_confidence(provided, missing)
        assert conf == "LOW"


class TestGenerateRationale:
    """Tests for rationale generation."""

    def test_rationale_includes_participation(self):
        rationale = generate_rationale(
            70, "NEW_ENTRY_ALLOWED", "BROAD", "GROWTH", {"top_risk": 80, "regime": 75}, []
        )
        assert "Broad participation" in rationale

    def test_rationale_includes_missing_inputs(self):
        rationale = generate_rationale(
            60, "REDUCE_ONLY", "MODERATE", "NEUTRAL", {"breadth": 60}, ["regime", "top_risk"]
        )
        assert "Missing critical inputs" in rationale

    def test_rationale_cash_priority(self):
        rationale = generate_rationale(
            25, "CASH_PRIORITY", "NARROW", "DEFENSIVE", {"top_risk": 20}, []
        )
        assert "preservation" in rationale.lower()


class TestGenerateMarkdownReport:
    """Tests for markdown report generation."""

    def test_markdown_contains_exposure(self):
        result = {
            "generated_at": "2026-03-16T07:00:00Z",
            "confidence": "HIGH",
            "exposure_ceiling_pct": 75,
            "component_scores": {
                "breadth_score": 65,
                "regime_score": 80,
            },
            "recommendation": "NEW_ENTRY_ALLOWED",
            "bias": "GROWTH",
            "participation": "BROAD",
            "rationale": "Test rationale.",
            "inputs_missing": [],
        }
        md = generate_markdown_report(result)
        assert "75%" in md
        assert "NEW_ENTRY_ALLOWED" in md
        assert "GROWTH" in md

    def test_markdown_includes_missing(self):
        result = {
            "generated_at": "2026-03-16T07:00:00Z",
            "confidence": "MEDIUM",
            "exposure_ceiling_pct": 50,
            "component_scores": {"breadth_score": 60},
            "recommendation": "REDUCE_ONLY",
            "bias": "NEUTRAL",
            "participation": "NARROW",
            "rationale": "Caution advised.",
            "inputs_missing": ["regime", "top_risk"],
        }
        md = generate_markdown_report(result)
        assert "Missing Inputs" in md
        assert "regime" in md


class TestLoadJsonFile:
    """Tests for JSON file loading."""

    def test_load_valid_file(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_data = {"key": "value"}
        test_file.write_text(json.dumps(test_data), encoding="utf-8")
        result = load_json_file(test_file)
        assert result == test_data

    def test_load_nonexistent_file(self, tmp_path):
        result = load_json_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_none_path(self):
        result = load_json_file(None)
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        test_file = tmp_path / "invalid.json"
        test_file.write_text("not valid json", encoding="utf-8")
        result = load_json_file(test_file)
        assert result is None


class TestIntegration:
    """Integration tests for the full pipeline."""

    def test_full_pipeline_with_all_inputs(self, tmp_path):
        """Test complete flow with all inputs provided."""
        import sys

        from calculate_exposure import main

        # Create mock input files
        breadth_file = tmp_path / "breadth.json"
        breadth_file.write_text(json.dumps({"breadth_score": 70}), encoding="utf-8")

        regime_file = tmp_path / "regime.json"
        regime_file.write_text(json.dumps({"regime": "Broadening"}), encoding="utf-8")

        top_risk_file = tmp_path / "top_risk.json"
        top_risk_file.write_text(json.dumps({"top_risk_score": 75}), encoding="utf-8")

        uptrend_file = tmp_path / "uptrend.json"
        uptrend_file.write_text(json.dumps({"uptrend_score": 65}), encoding="utf-8")

        output_dir = tmp_path / "reports"

        # Mock sys.argv
        original_argv = sys.argv
        sys.argv = [
            "calculate_exposure.py",
            "--breadth",
            str(breadth_file),
            "--regime",
            str(regime_file),
            "--top-risk",
            str(top_risk_file),
            "--uptrend",
            str(uptrend_file),
            "--output-dir",
            str(output_dir),
            "--json-only",
        ]

        try:
            result = main()
            assert result == 0

            # Check output files exist
            json_files = list(output_dir.glob("exposure_posture_*.json"))
            assert len(json_files) == 1

            # Validate JSON content
            with open(json_files[0]) as f:
                data = json.load(f)
            assert "exposure_ceiling_pct" in data
            assert "recommendation" in data
            assert data["confidence"] in ["HIGH", "MEDIUM", "LOW"]
        finally:
            sys.argv = original_argv

    def test_partial_inputs_reduce_confidence(self, tmp_path):
        """Test that missing critical inputs reduce confidence."""
        import sys

        from calculate_exposure import main

        # Create only one non-critical input
        sector_file = tmp_path / "sector.json"
        sector_file.write_text(json.dumps({"sector_score": 60}), encoding="utf-8")

        output_dir = tmp_path / "reports"

        original_argv = sys.argv
        sys.argv = [
            "calculate_exposure.py",
            "--sector",
            str(sector_file),
            "--output-dir",
            str(output_dir),
            "--json-only",
        ]

        try:
            result = main()
            assert result == 0

            json_files = list(output_dir.glob("exposure_posture_*.json"))
            with open(json_files[0]) as f:
                data = json.load(f)

            # All critical inputs missing → LOW confidence
            assert data["confidence"] == "LOW"
            # Missing critical inputs triggers haircut → lower exposure
            assert data["exposure_ceiling_pct"] < 50
        finally:
            sys.argv = original_argv
