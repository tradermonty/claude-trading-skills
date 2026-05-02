"""End-to-end smoke test for generate_pre_market_plan.

Drives the full Phase 2 pipeline against a synthetic Phase 1 JSON so the
schema contract (schema_version, plans[*].entry_plans[*].plan_id, etc.)
is verified without a network call.
"""

import json

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
        report = json.loads((tmp_path / plan_file).read_text())
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
        report = json.loads(plan_file.read_text())
        # Default tradable-min-grade is B → C is filtered
        assert report["plans"] == []

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
        report = json.loads(plan_file.read_text())
        assert report["plans"][0]["ssr_state"]["uptick_rule_active"] is False
        # prior_close inheritance is the key contract
        assert report["plans"][0]["ssr_state"]["prior_regular_close"] == 78.45
        assert report["plans"][0]["ssr_state"]["prior_regular_close_source"] == "phase1_inherit"
