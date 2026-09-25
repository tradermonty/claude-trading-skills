"""End-to-end smoke test for generate_pre_market_plan.

Drives the full Phase 2 pipeline against a synthetic Phase 1 JSON so the
schema contract (schema_version, plans[*].entry_plans[*].plan_id, etc.)
is verified without a network call.
"""

import json
from datetime import date, timedelta

import generate_pre_market_plan as g2


def _phase1_json(tmp_path, ticker="XYZ", rank="B", prior_close=78.45) -> str:
    payload = {
        "schema_version": "1.0",
        "skill": "parabolic-short-trade-planner",
        "phase": "screen",
        "as_of": "2026-04-30",
        "candidates": [
            {
                "ticker": ticker,
                "rank": rank,
                "score": 71.4,
                "state_caps": [],
                "warnings": ["too_early_to_short"],
                "components": {
                    "ma_extension": 21.5,
                    "acceleration": 17.3,
                    "volume_climax": 14.0,
                    "range_expansion": 11.4,
                    "liquidity": 7.2,
                },
                "metrics": {"atr_14": 6.10, "return_5d_pct": 88.2},
                "key_levels": {
                    "dma_10": 51.40,
                    "dma_20": 43.80,
                    "prior_close": prior_close,
                    "prior_close_source": "fmp_historical_eod",
                },
                "invalidation_checks_passed": True,
                "earnings_within_2d": False,
                "market_cap_usd": 5_000_000_000,
            }
        ],
    }
    p = tmp_path / "phase1.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


class TestGeneratePlan:
    def test_b_grade_candidate_yields_plan_with_three_triggers(self, tmp_path):
        in_path = _phase1_json(tmp_path)
        rc = g2.main(
            [
                "--candidates-json",
                in_path,
                "--broker",
                "none",  # no Alpaca; use ManualBrokerAdapter
                "--output-dir",
                str(tmp_path),
                "--ssr-state-dir",
                str(tmp_path / "ssr"),
                "--tradable-min-grade",
                "B",
            ]
        )
        assert rc == 0
        out_files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".json")
        plan_file = next(f for f in out_files if "plan" in f)
        report = json.loads((tmp_path / plan_file).read_text(encoding="utf-8"))
        assert report["schema_version"] == "1.0"
        assert report["phase"] == "pre_market_plan"
        assert len(report["plans"]) == 1
        plan = report["plans"][0]
        assert plan["ticker"] == "XYZ"
        # Manual adapter blocks new shorts → plan still rendered, just gated
        assert plan["trade_allowed_without_manual"] is False
        assert "borrow_inventory_unavailable" in plan["blocking_manual_reasons"]
        # Three trigger plans, each with a unique plan_id
        ids = [ep["plan_id"] for ep in plan["entry_plans"]]
        assert len(ids) == 3
        assert len(set(ids)) == 3
        # Size recipe must use the formula, never a baked-in shares count
        for ep in plan["entry_plans"]:
            assert "shares_formula" in ep["size_recipe"]
            assert "shares" not in ep  # never at the entry-plan level

    def test_c_grade_filtered_by_default_tradable_min(self, tmp_path):
        in_path = _phase1_json(tmp_path, rank="C")
        rc = g2.main(
            [
                "--candidates-json",
                in_path,
                "--broker",
                "none",
                "--output-dir",
                str(tmp_path),
                "--ssr-state-dir",
                str(tmp_path / "ssr"),
            ]
        )
        assert rc == 0
        plan_file = next(p for p in tmp_path.iterdir() if "plan" in p.name and p.suffix == ".json")
        report = json.loads(plan_file.read_text(encoding="utf-8"))
        # Default tradable-min-grade is B → C is filtered
        assert report["plans"] == []

    def test_as_of_override_advances_carryover(self, tmp_path):
        """`--as-of` is a date override used by the Day-2 carryover smoke
        step. Without it, the runbook would have to re-run Phase 1 just
        to bump the date — an unwanted dependency on FMP for what is
        purely an SSR-state test.

        Flow:
          1. Run Phase 2 for the Phase 1 as_of date (Day 1) so a state
             file is created for the surviving ticker.
          2. Mutate that file to set ssr_triggered_today=True (simulating
             a real Rule 201 fire that the MVP cannot detect on its own
             because aftermarket data isn't wired in yet).
          3. Re-run Phase 2 with --as-of bumped to Day 2 and check that
             ssr_carryover_from_prior_day flips to True.
        """
        in_path = _phase1_json(tmp_path, rank="B")
        ssr_dir = tmp_path / "ssr"
        # Day 1: produce the state file via the normal pipeline.
        rc = g2.main(
            [
                "--candidates-json",
                in_path,
                "--broker",
                "none",
                "--output-dir",
                str(tmp_path),
                "--ssr-state-dir",
                str(ssr_dir),
                "--tradable-min-grade",
                "B",
            ]
        )
        assert rc == 0
        # Day 1 state file: ticker XYZ, as_of 2026-04-30.
        state_d1 = ssr_dir / "ssr_state_XYZ_2026-04-30.json"
        assert state_d1.exists(), "Day-1 SSR state file should have been written"
        d1_payload = json.loads(state_d1.read_text(encoding="utf-8"))
        # Force the trigger flag so Day 2 has a non-trivial carryover input.
        d1_payload["ssr_triggered_today"] = True
        state_d1.write_text(json.dumps(d1_payload), encoding="utf-8")

        # Day 2: same Phase 1 JSON, but advance --as-of by one calendar day.
        day2 = (date.fromisoformat("2026-04-30") + timedelta(days=1)).isoformat()
        rc = g2.main(
            [
                "--candidates-json",
                in_path,
                "--broker",
                "none",
                "--output-dir",
                str(tmp_path),
                "--ssr-state-dir",
                str(ssr_dir),
                "--tradable-min-grade",
                "B",
                "--as-of",
                day2,
                "--output-prefix",
                "parabolic_short_plan_day2",
            ]
        )
        assert rc == 0
        day2_report_path = tmp_path / f"parabolic_short_plan_day2_{day2}.json"
        report = json.loads(day2_report_path.read_text(encoding="utf-8"))
        assert report["as_of"] == day2, "--as-of must override the Phase 1 JSON's as_of"
        assert len(report["plans"]) == 1
        ssr_state = report["plans"][0]["ssr_state"]
        assert ssr_state["ssr_carryover_from_prior_day"] is True
        assert ssr_state["uptick_rule_active"] is True

    def test_a_grade_with_low_prior_close_keeps_ssr_clean(self, tmp_path):
        # No SSR drop scenario — the planner should not flag uptick rule.
        in_path = _phase1_json(tmp_path, rank="A", prior_close=78.45)
        rc = g2.main(
            [
                "--candidates-json",
                in_path,
                "--broker",
                "none",
                "--output-dir",
                str(tmp_path),
                "--ssr-state-dir",
                str(tmp_path / "ssr"),
                "--tradable-min-grade",
                "B",
            ]
        )
        assert rc == 0
        plan_file = next(p for p in tmp_path.iterdir() if "plan" in p.name and p.suffix == ".json")
        report = json.loads(plan_file.read_text(encoding="utf-8"))
        assert report["plans"][0]["ssr_state"]["uptick_rule_active"] is False
        # prior_close inheritance is the key contract
        assert report["plans"][0]["ssr_state"]["prior_regular_close"] == 78.45
        assert report["plans"][0]["ssr_state"]["prior_regular_close_source"] == "phase1_inherit"
