"""Round-6 review: honest ranking scope — a 4% economic sample is never a market ranking."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import evaluate_candidates as EVAL  # noqa: E402
import run_pipeline as PIPELINE  # noqa: E402


class ClassifyRankingScopeTests(unittest.TestCase):
    def test_seed_sample_is_scoped_never_marketwide(self) -> None:
        # The reviewer's case: 180 attempted of 2,371 listed (98 evaluable).
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=180,
                listing_universe_count=2371,
                economic_scope_complete=False,
                unresolved_queue_count=0,
            ),
            "final_scoped",
        )

    def test_unresolved_queue_is_diagnostic(self) -> None:
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=180,
                listing_universe_count=2371,
                economic_scope_complete=False,
                unresolved_queue_count=5,
            ),
            "diagnostic",
        )

    def test_full_universe_attempt_is_marketwide(self) -> None:
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=2371,
                listing_universe_count=2371,
                economic_scope_complete=True,
                unresolved_queue_count=0,
            ),
            "final_marketwide",
        )

    def test_zero_attempts_fail_closed_to_diagnostic(self) -> None:
        # Round-7 review: a run that attempted nothing proved nothing about
        # any subset — never final_scoped.
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=0,
                listing_universe_count=2371,
                economic_scope_complete=False,
                unresolved_queue_count=0,
            ),
            "diagnostic",
        )
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=180,
                listing_universe_count=0,
                economic_scope_complete=False,
                unresolved_queue_count=0,
            ),
            "diagnostic",
        )

    def test_full_attempt_without_scope_completeness_stays_scoped(self) -> None:
        # Attempt counts alone are not enough: the exact-count economic
        # completeness verdict must agree.
        self.assertEqual(
            PIPELINE.classify_ranking_scope(
                economic_attempt_count=2371,
                listing_universe_count=2371,
                economic_scope_complete=False,
                unresolved_queue_count=0,
            ),
            "final_scoped",
        )


def _audit(
    *,
    universe: int = 2371,
    seeds: int = 180,
    covered: int = 0,
    mode: str = "per_symbol_fallback",
    unresolved: int = 0,
    probe: int = 35,
    evaluable: int = 98,
    snapshot_verified: bool = False,
) -> dict:
    return {
        "universe": {"row_count": universe},
        "enrichment": {"unresolved_count": unresolved},
        "candidate_pool": {
            "generation_audit": {
                "estimate_acquisition_mode": mode,
                "economic_attempt_count": seeds,
                "economically_evaluable_count": evaluable,
                "seed_audit": {"seed_limit_effective": seeds},
                "bulk_estimate_audit": {
                    "covered_symbol_count": covered,
                    "universe_symbol_count": universe,
                },
                "quality_probe": {"attempted": [f"S{i}" for i in range(probe)]},
                "snapshot_verification": {
                    "ready_for_screening": snapshot_verified,
                    "snapshot_verification_digest": "a" * 64 if snapshot_verified else None,
                    "classification_matches_universe": snapshot_verified,
                    "classified_total": universe if snapshot_verified else 0,
                },
            }
        },
    }


class DeriveRankingScopeTests(unittest.TestCase):
    def test_run16_shape_is_final_scoped_with_coverage(self) -> None:
        info = EVAL._derive_ranking_scope(_audit(), deep_dive_count=3)
        self.assertEqual(info["ranking_scope"], "final_scoped")
        self.assertEqual(info["economic_attempt_count"], 180)
        self.assertAlmostEqual(info["economic_attempt_coverage_pct"], 7.591734, places=4)
        self.assertEqual(info["economically_evaluable_count"], 98)
        self.assertAlmostEqual(info["economically_evaluable_coverage_pct"], 4.133277, places=4)
        self.assertEqual(info["quality_probe_count"], 35)
        self.assertEqual(info["deep_dive_count"], 3)
        self.assertAlmostEqual(info["deep_dive_coverage_pct"], 0.126529, places=4)

    def test_unresolved_queue_marks_diagnostic(self) -> None:
        info = EVAL._derive_ranking_scope(_audit(unresolved=4), deep_dive_count=0)
        self.assertEqual(info["ranking_scope"], "diagnostic")

    def test_zero_attempts_derive_as_diagnostic(self) -> None:
        info = EVAL._derive_ranking_scope(_audit(seeds=0, evaluable=0), deep_dive_count=0)
        self.assertEqual(info["ranking_scope"], "diagnostic")

    def test_missing_attempt_count_fails_closed(self) -> None:
        # Round-8 review: the evaluator must copy discovery's ACTUAL count,
        # and a missing field is a diagnostic, never a reconstructed limit.
        audit = _audit()
        del audit["candidate_pool"]["generation_audit"]["economic_attempt_count"]
        info = EVAL._derive_ranking_scope(audit, deep_dive_count=3)
        self.assertEqual(info["ranking_scope"], "diagnostic")

    def test_attempts_exceeding_universe_fail_closed(self) -> None:
        # The reviewer's reproduction: 50-name universe, seed LIMIT 180 —
        # 360% coverage must never appear as a scoped conclusion.
        info = EVAL._derive_ranking_scope(_audit(universe=50, seeds=180), deep_dive_count=3)
        self.assertEqual(info["ranking_scope"], "diagnostic")

    def test_bulk_full_coverage_is_marketwide(self) -> None:
        info = EVAL._derive_ranking_scope(
            _audit(mode="analyst_estimates_bulk", covered=2371), deep_dive_count=3
        )
        self.assertEqual(info["ranking_scope"], "final_marketwide")
        self.assertEqual(info["economic_attempt_count"], 2371)

    def test_partial_bulk_coverage_stays_scoped(self) -> None:
        info = EVAL._derive_ranking_scope(
            _audit(mode="analyst_estimates_bulk", covered=600), deep_dive_count=3
        )
        self.assertEqual(info["ranking_scope"], "final_scoped")
        self.assertEqual(info["economic_attempt_count"], 600)

    def test_verified_sharded_snapshot_is_marketwide(self) -> None:
        info = EVAL._derive_ranking_scope(
            _audit(
                mode="sharded_snapshot",
                seeds=2371,
                evaluable=1800,
                snapshot_verified=True,
            ),
            deep_dive_count=5,
        )
        self.assertEqual(info["ranking_scope"], "final_marketwide")

    def test_unverified_sharded_snapshot_is_diagnostic(self) -> None:
        info = EVAL._derive_ranking_scope(
            _audit(mode="sharded_snapshot", seeds=2371, evaluable=1800),
            deep_dive_count=5,
        )
        self.assertEqual(info["ranking_scope"], "diagnostic")

    def test_marketwide_markdown_drops_scoped_pilot_warning(self) -> None:
        report = {
            "ranking_scope": "final_marketwide",
            "ranking_status": "final",
            "strict_mode": True,
            "analysis_as_of": "2026-09-05T12:00:00+00:00",
            "coverage": {
                "listing_universe_count": 2371,
                "economic_attempt_count": 2371,
            },
            "ranked_candidates": [],
            "conditional": [],
            "review_required": [],
            "screened_out": [],
            "excluded": [],
        }
        markdown = EVAL.render_markdown(report, language="en")
        self.assertNotIn("Scoped Pilot", markdown)
        self.assertNotIn("NOT a market-wide ranking", markdown)

        report["ranking_scope"] = "final_scoped"
        report["coverage"]["economic_attempt_count"] = 180
        markdown = EVAL.render_markdown(report, language="en")
        self.assertIn("Scoped Pilot", markdown)
        self.assertIn("NOT a market-wide ranking", markdown)


if __name__ == "__main__":
    unittest.main()
