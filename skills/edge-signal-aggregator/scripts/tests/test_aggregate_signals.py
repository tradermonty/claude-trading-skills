"""
Tests for edge-signal-aggregator aggregate_signals.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aggregate_signals import (
    DEFAULT_CONFIG,
    aggregate_signals,
    apply_contradiction_adjustments,
    are_signals_similar,
    as_ticker_list,
    calculate_composite_score,
    calculate_recency_factor,
    calculate_text_similarity,
    calculate_ticker_overlap,
    deduplicate_signals,
    detect_contradictions,
    extract_signals_from_concepts,
    extract_signals_from_edge_candidates,
    extract_signals_from_themes,
    generate_markdown_report,
    horizon_bucket,
    load_config,
    normalize_direction,
    normalize_score,
    normalize_score_auto,
)


class TestNormalizeScore:
    """Tests for normalize_score function."""

    def test_numeric_score_in_range(self):
        """Test normalization of numeric score within range."""
        assert normalize_score(0.5) == 0.5
        assert normalize_score(0.0) == 0.0
        assert normalize_score(1.0) == 1.0

    def test_numeric_score_out_of_range(self):
        """Test normalization clamps values to [0, 1]."""
        assert normalize_score(1.5) == 1.0
        assert normalize_score(-0.5) == 0.0

    def test_letter_grades(self):
        """Test letter grade conversion."""
        assert normalize_score("A") == 1.0
        assert normalize_score("B") == 0.8
        assert normalize_score("C") == 0.6
        assert normalize_score("D") == 0.4
        assert normalize_score("F") == 0.2
        assert normalize_score("a") == 1.0  # Case insensitive

    def test_none_and_invalid(self):
        """Test handling of None and invalid values."""
        assert normalize_score(None) == 0.0
        assert normalize_score("invalid") == 0.0


class TestRecencyFactor:
    """Tests for calculate_recency_factor function."""

    def test_recent_timestamp(self):
        """Test recency factor for recent timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        factor = calculate_recency_factor(now, DEFAULT_CONFIG["recency"])
        assert factor == 1.0

    def test_old_timestamp(self):
        """Test recency factor for old timestamps."""
        factor = calculate_recency_factor("2020-01-01", DEFAULT_CONFIG["recency"])
        assert factor == 0.85

    def test_none_timestamp(self):
        """Test recency factor for missing timestamp."""
        factor = calculate_recency_factor(None, DEFAULT_CONFIG["recency"])
        assert factor == 0.85


class TestTickerOverlap:
    """Tests for calculate_ticker_overlap function."""

    def test_full_overlap(self):
        """Test identical ticker lists."""
        assert calculate_ticker_overlap(["AAPL", "MSFT"], ["AAPL", "MSFT"]) == 1.0

    def test_partial_overlap(self):
        """Test partial ticker overlap."""
        overlap = calculate_ticker_overlap(["AAPL", "MSFT"], ["AAPL", "GOOGL"])
        assert overlap == pytest.approx(1 / 3)  # 1 overlap, 3 union

    def test_no_overlap(self):
        """Test no ticker overlap."""
        assert calculate_ticker_overlap(["AAPL"], ["MSFT"]) == 0.0

    def test_empty_lists(self):
        """Test empty ticker lists."""
        assert calculate_ticker_overlap([], []) == 0.0
        assert calculate_ticker_overlap(["AAPL"], []) == 0.0


class TestTextSimilarity:
    """Tests for calculate_text_similarity function."""

    def test_identical_text(self):
        """Test identical text strings."""
        assert calculate_text_similarity("AI Infrastructure", "AI Infrastructure") == 1.0

    def test_partial_similarity(self):
        """Test partial text overlap."""
        sim = calculate_text_similarity("AI Infrastructure Growth", "AI Compute Growth")
        assert 0 < sim < 1

    def test_no_similarity(self):
        """Test completely different text."""
        sim = calculate_text_similarity("Energy Sector", "Technology Growth")
        assert sim == 0.0

    def test_empty_strings(self):
        """Test empty strings."""
        assert calculate_text_similarity("", "") == 0.0
        assert calculate_text_similarity("test", "") == 0.0


class TestSignalSimilarity:
    """Tests for are_signals_similar function."""

    def test_similar_signals(self):
        """Test detection of similar signals."""
        sig_a = {"title": "AI Growth", "tickers": ["NVDA", "AMD"], "direction": "LONG"}
        sig_b = {"title": "AI Growth Thesis", "tickers": ["NVDA", "AVGO"], "direction": "LONG"}
        assert are_signals_similar(sig_a, sig_b, DEFAULT_CONFIG)

    def test_different_direction(self):
        """Test that different directions are not similar."""
        sig_a = {"title": "AI Growth", "tickers": ["NVDA"], "direction": "LONG"}
        sig_b = {"title": "AI Growth", "tickers": ["NVDA"], "direction": "SHORT"}
        assert not are_signals_similar(sig_a, sig_b, DEFAULT_CONFIG)

    def test_different_signals(self):
        """Test that truly different signals are not similar."""
        sig_a = {"title": "AI Growth", "tickers": ["NVDA"], "direction": "LONG"}
        sig_b = {"title": "Energy Decline", "tickers": ["XOM"], "direction": "LONG"}
        assert not are_signals_similar(sig_a, sig_b, DEFAULT_CONFIG)


class TestDeduplication:
    """Tests for deduplicate_signals function."""

    def test_no_duplicates(self):
        """Test deduplication with no duplicates."""
        signals = [
            {
                "skill": "theme_detector",
                "signal_ref": "t1",
                "title": "AI",
                "tickers": ["NVDA"],
                "direction": "LONG",
                "raw_score": 0.8,
            },
            {
                "skill": "sector_analyst",
                "signal_ref": "s1",
                "title": "Energy",
                "tickers": ["XOM"],
                "direction": "SHORT",
                "raw_score": 0.7,
            },
        ]
        deduped, log = deduplicate_signals(signals, DEFAULT_CONFIG)
        assert len(deduped) == 2
        assert len(log) == 0

    def test_with_duplicates(self):
        """Test deduplication merges similar signals."""
        signals = [
            {
                "skill": "theme_detector",
                "signal_ref": "t1",
                "title": "AI Infrastructure",
                "tickers": ["NVDA", "AMD"],
                "direction": "LONG",
                "raw_score": 0.9,
            },
            {
                "skill": "edge_candidate_agent",
                "signal_ref": "e1",
                "title": "AI Infrastructure Growth",
                "tickers": ["NVDA", "AVGO"],
                "direction": "LONG",
                "raw_score": 0.85,
            },
        ]
        deduped, log = deduplicate_signals(signals, DEFAULT_CONFIG)
        assert len(deduped) == 1
        assert len(log) == 1
        assert len(deduped[0]["contributing_skills"]) == 2


class TestContradictionDetection:
    """Tests for detect_contradictions function."""

    def test_no_contradictions(self):
        """Test with no contradictions."""
        signals = [
            {"skill": "a", "title": "AI", "tickers": ["NVDA"], "direction": "LONG"},
            {"skill": "b", "title": "Energy", "tickers": ["XOM"], "direction": "SHORT"},
        ]
        contradictions = detect_contradictions(signals)
        assert len(contradictions) == 0

    def test_detects_contradiction(self):
        """Test detection of opposing signals."""
        signals = [
            {
                "skill": "sector_analyst",
                "signal_ref": "s1",
                "title": "Energy Bearish",
                "tickers": ["XOM"],
                "direction": "SHORT",
            },
            {
                "skill": "institutional_flow_tracker",
                "signal_ref": "i1",
                "title": "XOM Buying",
                "tickers": ["XOM"],
                "direction": "LONG",
            },
        ]
        contradictions = detect_contradictions(signals)
        assert len(contradictions) == 1
        assert contradictions[0]["severity"] == "MEDIUM"
        assert contradictions[0]["ticker"] == "XOM"
        assert contradictions[0]["signal_a_ref"] == "institutional_flow_tracker:i1"
        assert contradictions[0]["signal_b_ref"] == "sector_analyst:s1"

    def test_same_skill_contradiction_is_high_severity(self):
        """Test that same-skill contradictions are HIGH severity."""
        signals = [
            {
                "skill": "theme_detector",
                "signal_ref": "t1",
                "title": "AI Bull",
                "tickers": ["NVDA"],
                "direction": "LONG",
            },
            {
                "skill": "theme_detector",
                "signal_ref": "t2",
                "title": "AI Bear",
                "tickers": ["NVDA"],
                "direction": "SHORT",
            },
        ]
        contradictions = detect_contradictions(signals)
        assert len(contradictions) == 1
        assert contradictions[0]["severity"] == "HIGH"

    def test_different_horizons_are_low_severity(self):
        """Test LOW severity when horizons are clearly different."""
        signals = [
            {
                "skill": "sector_analyst",
                "signal_ref": "s1",
                "title": "Short-term pullback",
                "tickers": ["AAPL"],
                "direction": "SHORT",
                "time_horizon": "1-2 weeks",
            },
            {
                "skill": "edge_concept_synthesizer",
                "signal_ref": "c1",
                "title": "Long-term trend intact",
                "tickers": ["AAPL"],
                "direction": "LONG",
                "time_horizon": "12 months",
            },
        ]
        contradictions = detect_contradictions(signals)
        assert len(contradictions) == 1
        assert contradictions[0]["severity"] == "LOW"


class TestCompositeScore:
    """Tests for calculate_composite_score function."""

    def test_single_skill_score(self):
        """Test composite score with single skill."""
        signal = {
            "skill": "edge_candidate_agent",
            "signal_ref": "test",
            "raw_score": 0.8,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        result = calculate_composite_score(signal, DEFAULT_CONFIG)
        assert 0 < result["composite_score"] <= 1.0
        assert "confidence_breakdown" in result

    def test_multi_skill_agreement_bonus(self):
        """Test that multi-skill agreement increases score."""
        signal_single = {
            "skill": "edge_candidate_agent",
            "signal_ref": "test",
            "raw_score": 0.8,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        signal_multi = {
            "skill": "edge_candidate_agent",
            "signal_ref": "test",
            "raw_score": 0.8,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contributing_skills": [
                {"skill": "edge_candidate_agent", "signal_ref": "e1", "raw_score": 0.8},
                {"skill": "theme_detector", "signal_ref": "t1", "raw_score": 0.8},
                {"skill": "sector_analyst", "signal_ref": "s1", "raw_score": 0.8},
            ],
        }
        single_result = calculate_composite_score(signal_single, DEFAULT_CONFIG)
        multi_result = calculate_composite_score(signal_multi, DEFAULT_CONFIG)
        assert multi_result["composite_score"] > single_result["composite_score"]


class TestContradictionAdjustments:
    """Tests for contradiction penalty / exclusion application."""

    def test_medium_contradiction_penalizes_both_signals(self):
        """Medium contradiction should reduce both signal scores."""
        scored_signals = [
            {"_source_ref": "a:s1", "composite_score": 0.8},
            {"_source_ref": "b:s2", "composite_score": 0.7},
        ]
        contradictions = [
            {
                "contradiction_id": "c1",
                "severity": "MEDIUM",
                "signal_a_ref": "a:s1",
                "signal_b_ref": "b:s2",
            }
        ]
        adjusted, log = apply_contradiction_adjustments(
            scored_signals,
            contradictions,
            DEFAULT_CONFIG,
        )
        assert adjusted[0]["composite_score"] == pytest.approx(0.72, abs=1e-4)
        assert adjusted[1]["composite_score"] == pytest.approx(0.63, abs=1e-4)
        assert len(log) == 2
        assert all(item["action"] == "penalty" for item in log)

    def test_high_contradiction_excludes_signals(self):
        """High contradiction should exclude signals by default."""
        scored_signals = [
            {"_source_ref": "a:s1", "composite_score": 0.8},
            {"_source_ref": "a:s2", "composite_score": 0.7},
        ]
        contradictions = [
            {
                "contradiction_id": "c2",
                "severity": "HIGH",
                "signal_a_ref": "a:s1",
                "signal_b_ref": "a:s2",
            }
        ]
        adjusted, log = apply_contradiction_adjustments(
            scored_signals,
            contradictions,
            DEFAULT_CONFIG,
        )
        assert adjusted[0]["_excluded"] is True
        assert adjusted[1]["_excluded"] is True
        assert len(log) == 2
        assert all(item["action"] == "exclude" for item in log)


class TestExtractSignals:
    """Tests for signal extraction functions."""

    def test_extract_from_edge_candidates(self):
        """Test extraction from edge-candidate-agent format."""
        data = [
            {
                "_source_file": "test.json",
                "tickets": [
                    {
                        "ticket_id": "T001",
                        "title": "Test Signal",
                        "score": 0.85,
                        "tickers": ["AAPL"],
                        "direction": "LONG",
                    }
                ],
            }
        ]
        signals = extract_signals_from_edge_candidates(data)
        assert len(signals) == 1
        assert signals[0]["skill"] == "edge_candidate_agent"
        assert signals[0]["signal_ref"] == "T001"
        assert signals[0]["raw_score"] == 0.85

    def test_extract_from_edge_candidates_priority_score_0_to_100(self):
        """Test extraction supports priority_score on 0-100 scale."""
        data = [
            {
                "_source_file": "candidate.json",
                "tickets": [
                    {
                        "ticket_id": "T002",
                        "title": "VWAP hold setup",
                        "priority_score": 78,
                        "observation": {"symbol": "nvda"},
                        "direction": "bullish",
                    }
                ],
            }
        ]
        signals = extract_signals_from_edge_candidates(data)
        assert len(signals) == 1
        assert signals[0]["raw_score"] == pytest.approx(0.78, abs=1e-6)
        assert signals[0]["tickers"] == ["NVDA"]
        assert signals[0]["direction"] == "LONG"

    def test_extract_from_concepts_support_fields(self):
        """Test concept extraction reads support.avg_priority_score and symbols."""
        data = [
            {
                "_source_file": "concept.yaml",
                "concepts": [
                    {
                        "concept_id": "C001",
                        "title": "AI infra breadth",
                        "support": {
                            "avg_priority_score": 64,
                            "symbols": ["NVDA", "AVGO"],
                        },
                    }
                ],
            }
        ]
        signals = extract_signals_from_concepts(data)
        assert len(signals) == 1
        assert signals[0]["signal_ref"] == "C001"
        assert signals[0]["raw_score"] == pytest.approx(0.64, abs=1e-6)
        assert signals[0]["tickers"] == ["AVGO", "NVDA"]

    def test_extract_from_themes(self):
        """Test extraction from theme-detector format."""
        data = [
            {
                "_source_file": "test.json",
                "themes": [
                    {
                        "theme_id": "ai_infra",
                        "theme_name": "AI Infrastructure",
                        "strength": 0.9,
                        "tickers": ["NVDA", "AMD"],
                    }
                ],
                "generated_at": "2026-03-01T10:00:00Z",
            }
        ]
        signals = extract_signals_from_themes(data)
        assert len(signals) == 1
        assert signals[0]["skill"] == "theme_detector"
        assert signals[0]["title"] == "AI Infrastructure"

    def test_extract_from_themes_dict_all_format(self):
        """Test extraction supports themes.all dict format and heat fields."""
        data = [
            {
                "_source_file": "theme.json",
                "themes": {
                    "all": [
                        {
                            "theme_id": "t-all-1",
                            "theme_name": "Earnings gap continuation",
                            "heat": 72,
                            "representative_stocks": ["aapl", "msft"],
                            "direction": "up",
                        }
                    ]
                },
                "generated_at": "2026-03-01T10:00:00Z",
            }
        ]
        signals = extract_signals_from_themes(data)
        assert len(signals) == 1
        assert signals[0]["raw_score"] == pytest.approx(0.72, abs=1e-6)
        assert signals[0]["tickers"] == ["AAPL", "MSFT"]
        assert signals[0]["direction"] == "LONG"


class TestAggregateSignals:
    """Tests for main aggregate_signals function."""

    def test_empty_inputs(self):
        """Test aggregation with empty inputs."""
        result = aggregate_signals([], [], [], [], [], [], DEFAULT_CONFIG)
        assert result["summary"]["total_input_signals"] == 0
        assert result["summary"]["unique_signals_after_dedup"] == 0

    def test_with_sample_data(self):
        """Test aggregation with sample data."""
        edge_candidates = [
            {
                "tickets": [
                    {
                        "ticket_id": "T1",
                        "title": "AI Capex",
                        "score": 0.9,
                        "tickers": ["NVDA"],
                        "direction": "LONG",
                    }
                ]
            }
        ]
        themes = [
            {
                "themes": [
                    {
                        "theme_id": "ai",
                        "theme_name": "AI Growth",
                        "strength": 0.85,
                        "tickers": ["NVDA", "AMD"],
                    }
                ]
            }
        ]

        result = aggregate_signals(
            edge_candidates=edge_candidates,
            edge_concepts=[],
            themes=themes,
            sectors=[],
            institutional=[],
            hints=[],
            config=DEFAULT_CONFIG,
        )

        assert result["summary"]["total_input_signals"] == 2
        assert len(result["ranked_signals"]) > 0
        assert result["ranked_signals"][0]["rank"] == 1

    def test_high_contradiction_excludes_from_ranking(self):
        """Same-skill opposite signals should be excluded from final ranking."""
        edge_candidates = [
            {
                "tickets": [
                    {
                        "ticket_id": "T-long",
                        "title": "AAPL breakout",
                        "score": 0.9,
                        "tickers": ["AAPL"],
                        "direction": "LONG",
                    },
                    {
                        "ticket_id": "T-short",
                        "title": "AAPL breakdown",
                        "score": 0.8,
                        "tickers": ["AAPL"],
                        "direction": "SHORT",
                    },
                ]
            }
        ]

        result = aggregate_signals(
            edge_candidates=edge_candidates,
            edge_concepts=[],
            themes=[],
            sectors=[],
            institutional=[],
            hints=[],
            config=DEFAULT_CONFIG,
        )

        assert result["summary"]["contradictions_found"] == 1
        assert result["summary"]["contradiction_adjustments_applied"] == 2
        assert result["ranked_signals"] == []


class TestMarkdownReport:
    """Tests for markdown report generation."""

    def test_generates_valid_markdown(self):
        """Test that markdown generation produces valid output."""
        result = {
            "generated_at": "2026-03-02T07:00:00Z",
            "config": {"min_conviction": 0.5},
            "summary": {
                "total_input_signals": 10,
                "unique_signals_after_dedup": 8,
                "contradictions_found": 1,
                "signals_above_threshold": 5,
            },
            "ranked_signals": [
                {
                    "rank": 1,
                    "signal_id": "sig_001",
                    "title": "Test Signal",
                    "composite_score": 0.85,
                    "contributing_skills": [
                        {"skill": "test", "signal_ref": "t1", "raw_score": 0.85}
                    ],
                    "tickers": ["AAPL"],
                    "direction": "LONG",
                    "time_horizon": "3 months",
                    "confidence_breakdown": {
                        "multi_skill_agreement": 0.3,
                        "signal_strength": 0.4,
                        "recency": 0.25,
                    },
                }
            ],
            "contradictions": [],
            "deduplication_log": [],
        }
        md = generate_markdown_report(result)
        assert "# Edge Signal Aggregator Dashboard" in md
        assert "Test Signal" in md
        assert "Score: 0.85" in md


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_default_config(self):
        """Test loading default config when no file specified."""
        config = load_config(None)
        assert "weights" in config
        assert config["weights"]["edge_candidate_agent"] == 0.25

    def test_missing_config_file(self):
        """Test graceful handling of missing config file."""
        config = load_config("/nonexistent/path.yaml")
        assert "weights" in config  # Falls back to defaults


class TestIntegration:
    """Integration tests with file I/O."""

    def test_json_output(self, tmp_path: Path):
        """Test JSON file output."""
        import sys

        from aggregate_signals import main

        # Create sample input
        input_file = tmp_path / "edge_candidates.json"
        input_file.write_text(
            json.dumps(
                {
                    "tickets": [
                        {
                            "ticket_id": "T1",
                            "title": "Test",
                            "score": 0.8,
                            "tickers": ["AAPL"],
                            "direction": "LONG",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        # Run with captured output
        old_argv = sys.argv
        try:
            sys.argv = [
                "aggregate_signals.py",
                "--edge-candidates",
                str(input_file),
                "--output-dir",
                str(tmp_path),
            ]
            exit_code = main()
        finally:
            sys.argv = old_argv

        assert exit_code == 0

        # Check output files exist
        json_files = list(tmp_path.glob("edge_signal_aggregator_*.json"))
        md_files = list(tmp_path.glob("edge_signal_aggregator_*.md"))
        assert len(json_files) == 1
        assert len(md_files) == 1

        # Validate JSON structure
        with open(json_files[0]) as f:
            output = json.load(f)
        assert "schema_version" in output
        assert "ranked_signals" in output


class TestNormalizeDirection:
    """Tests for normalize_direction utility."""

    def test_long_variants(self):
        for label in ["long", "LONG", "bull", "bullish", "buy", "accumulation", "up"]:
            assert normalize_direction(label) == "LONG"

    def test_short_variants(self):
        for label in ["short", "SHORT", "bear", "bearish", "sell", "distribution", "down"]:
            assert normalize_direction(label) == "SHORT"

    def test_none_and_empty(self):
        assert normalize_direction(None) == "NEUTRAL"
        assert normalize_direction("") == "NEUTRAL"

    def test_custom_default(self):
        assert normalize_direction(None, default="LONG") == "LONG"


class TestAsTickerList:
    """Tests for as_ticker_list utility."""

    def test_string_list(self):
        assert as_ticker_list(["nvda", "AMD"]) == ["AMD", "NVDA"]

    def test_dict_list(self):
        assert as_ticker_list([{"symbol": "aapl"}, {"ticker": "msft"}]) == ["AAPL", "MSFT"]

    def test_comma_separated_string(self):
        assert as_ticker_list("NVDA, AMD, AAPL") == ["AAPL", "AMD", "NVDA"]

    def test_empty(self):
        assert as_ticker_list([]) == []
        assert as_ticker_list(None) == []


class TestNormalizeScoreAuto:
    """Tests for normalize_score_auto utility."""

    def test_zero_to_one_range(self):
        assert normalize_score_auto(0.75) == 0.75

    def test_zero_to_hundred_range(self):
        assert normalize_score_auto(85) == 0.85

    def test_over_hundred(self):
        assert normalize_score_auto(150) == 1.0

    def test_negative(self):
        assert normalize_score_auto(-5) == 0.0

    def test_none(self):
        assert normalize_score_auto(None) == 0.0

    def test_letter_grade(self):
        assert normalize_score_auto("A") == 1.0


class TestHorizonBucket:
    """Tests for horizon_bucket utility."""

    def test_numeric_day(self):
        assert horizon_bucket("20D") == "short"
        assert horizon_bucket("5d") == "short"

    def test_numeric_week(self):
        assert horizon_bucket("4W") == "short"
        assert horizon_bucket("16w") == "medium"

    def test_numeric_month(self):
        assert horizon_bucket("2M") == "short"
        assert horizon_bucket("6M") == "medium"
        assert horizon_bucket("12m") == "long"

    def test_text_horizons(self):
        assert horizon_bucket("1-3 months") == "short"
        assert horizon_bucket("3-6 months") == "medium"
        assert horizon_bucket("3 months") == "medium"
        assert horizon_bucket("6-12 months") == "long"

    def test_none_and_unknown(self):
        assert horizon_bucket(None) == "unknown"
        assert horizon_bucket("custom period") == "unknown"


class TestIndividualTicketYAML:
    """Test that individual ticket YAML files (no 'tickets' wrapper) are handled."""

    def test_single_ticket_dict_as_doc(self):
        """When a YAML file IS the ticket (not wrapped in tickets array)."""
        docs = [
            {
                "id": "ticket_001",
                "priority_score": 88.5,
                "observation": {"symbol": "NVDA"},
                "holding_horizon": "20D",
                "direction": "bullish",
                "title": "NVDA gap up",
                "_source_file": "tickets/exportable/ticket_001.yaml",
            }
        ]
        signals = extract_signals_from_edge_candidates(docs)
        assert len(signals) == 1
        assert signals[0]["tickers"] == ["NVDA"]
        assert signals[0]["raw_score"] == pytest.approx(0.885, rel=1e-2)
        assert signals[0]["direction"] == "LONG"
