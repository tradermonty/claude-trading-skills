"""Tests for report_generator — schema contract for Phase 1 output.

These tests fix the v1.0 JSON shape so downstream skills (Phase 2's
generate_pre_market_plan, trader-memory-core's thesis_ingest) can rely
on the keys without surprise changes.
"""

import json

from parabolic_report_generator import (
    SCHEMA_VERSION,
    SKILL_NAME,
    build_json_report,
    build_markdown_report,
    render_candidate,
)
from parabolic_scorer import calculate_composite_score


def _sample_candidate(ticker: str = "XYZ", grade: str = "A") -> dict:
    # Sub-scores tuned so the weighted composite lands in the A-band (≥85).
    components_raw = {
        "ma_extension": 95.0,
        "acceleration": 90.0,
        "volume_climax": 90.0,
        "range_expansion": 85.0,
        "liquidity": 80.0,
    }
    composite = calculate_composite_score(components_raw)
    return render_candidate(
        ticker=ticker,
        composite_result=composite,
        component_scores_raw=components_raw,
        raw_metrics={
            "return_5d_pct": 142.3,
            "ext_20dma_pct": 117.4,
            "volume_ratio_20d": 4.3,
            "atr_14": 6.10,
            "consecutive_green_days": 4,
            "adv_20d_usd": 42_100_000,
        },
        state_caps=["still_in_markup"],
        warnings=["too_early_to_short"],
        key_levels={
            "dma_10": 51.40,
            "dma_20": 43.80,
            "dma_50": 32.60,
            "prior_close": 78.45,
            "prior_close_source": "fmp_historical_eod",
            "session_high": 79.20,
            "session_low": 71.30,
        },
        invalidation_checks_passed=True,
        earnings_within_days=None,
        market_cap_usd=1_850_000_000,
    )


class TestTopLevelSchema:
    def test_required_keys_present(self):
        report = build_json_report(
            candidates=[_sample_candidate()],
            mode="safe_largecap",
            universe="sp500",
            as_of="2026-04-30",
        )
        for key in (
            "schema_version",
            "skill",
            "phase",
            "generated_at",
            "as_of",
            "data_source",
            "data_latency_sec",
            "mode",
            "universe",
            "candidates_total",
            "candidates_a_rank",
            "candidates",
        ):
            assert key in report, f"missing top-level key {key!r}"

    def test_schema_version_and_skill_constants(self):
        report = build_json_report(
            candidates=[], mode="safe_largecap", universe="sp500", as_of="2026-04-30"
        )
        assert report["schema_version"] == SCHEMA_VERSION == "1.0"
        assert report["skill"] == SKILL_NAME == "parabolic-short-trade-planner"
        assert report["phase"] == "screen"

    def test_a_rank_count_matches(self):
        a = _sample_candidate("AAA", "A")
        b = _sample_candidate("BBB", "A")
        c = _sample_candidate("CCC", "A")
        # Force one to D by zeroing its components
        c_low = render_candidate(
            ticker="LOW",
            composite_result=calculate_composite_score(
                {
                    n: 0.0
                    for n in [
                        "ma_extension",
                        "acceleration",
                        "volume_climax",
                        "range_expansion",
                        "liquidity",
                    ]
                }
            ),
            component_scores_raw={
                n: 0.0
                for n in [
                    "ma_extension",
                    "acceleration",
                    "volume_climax",
                    "range_expansion",
                    "liquidity",
                ]
            },
            raw_metrics={},
            state_caps=[],
            warnings=[],
            key_levels={},
            invalidation_checks_passed=True,
            earnings_within_days=None,
            market_cap_usd=2_000_000_000,
        )
        report = build_json_report(
            candidates=[a, b, c, c_low], mode="safe_largecap", universe="sp500", as_of="2026-04-30"
        )
        assert report["candidates_total"] == 4
        assert report["candidates_a_rank"] == 3


class TestCandidateSchema:
    def test_candidate_required_keys(self):
        c = _sample_candidate()
        for key in (
            "ticker",
            "rank",
            "score",
            "state_caps",
            "warnings",
            "components",
            "metrics",
            "key_levels",
            "invalidation_checks_passed",
            "earnings_within_2d",
            "market_cap_usd",
        ):
            assert key in c, f"missing candidate key {key!r}"

    def test_components_sum_to_score(self):
        c = _sample_candidate()
        weighted_sum = sum(c["components"].values())
        # Allow tiny rounding tolerance from the scorer's round(_, 1)
        assert abs(weighted_sum - c["score"]) < 0.6

    def test_components_keys_match_weight_table(self):
        c = _sample_candidate()
        assert set(c["components"].keys()) == {
            "ma_extension",
            "acceleration",
            "volume_climax",
            "range_expansion",
            "liquidity",
        }

    def test_earnings_within_2d_flag_logic(self):
        # earnings_within_days = 1 → flag is True
        composite = calculate_composite_score(
            {
                "ma_extension": 70.0,
                "acceleration": 70.0,
                "volume_climax": 70.0,
                "range_expansion": 70.0,
                "liquidity": 70.0,
            }
        )
        soon = render_candidate(
            ticker="SOON",
            composite_result=composite,
            component_scores_raw={},
            raw_metrics={},
            state_caps=[],
            warnings=[],
            key_levels={},
            invalidation_checks_passed=False,
            earnings_within_days=1,
            market_cap_usd=2_000_000_000,
        )
        assert soon["earnings_within_2d"] is True
        # earnings_within_days = 5 → flag is False
        far = render_candidate(
            ticker="FAR",
            composite_result=composite,
            component_scores_raw={},
            raw_metrics={},
            state_caps=[],
            warnings=[],
            key_levels={},
            invalidation_checks_passed=True,
            earnings_within_days=5,
            market_cap_usd=2_000_000_000,
        )
        assert far["earnings_within_2d"] is False


class TestSerialization:
    def test_json_roundtrip(self):
        report = build_json_report(
            candidates=[_sample_candidate()],
            mode="safe_largecap",
            universe="sp500",
            as_of="2026-04-30",
        )
        s = json.dumps(report)
        parsed = json.loads(s)
        assert parsed["candidates"][0]["ticker"] == "XYZ"
        assert parsed["schema_version"] == "1.0"


class TestMarkdown:
    def test_renders_header_and_grade_section(self):
        report = build_json_report(
            candidates=[_sample_candidate()],
            mode="safe_largecap",
            universe="sp500",
            as_of="2026-04-30",
        )
        md = build_markdown_report(report)
        assert "Parabolic Short Watchlist" in md
        assert "2026-04-30" in md
        assert "## A-rank" in md
        assert "XYZ" in md

    def test_empty_candidates_renders_placeholder(self):
        report = build_json_report(
            candidates=[], mode="safe_largecap", universe="sp500", as_of="2026-04-30"
        )
        md = build_markdown_report(report)
        assert "No candidates met" in md
