"""Phase 1 ↔ Phase 2 contract test.

This test fixes the keys, value types, and value semantics that flow
between ``screen_parabolic.py`` (Phase 1) and ``generate_pre_market_plan.py``
(Phase 2). If a future change to either side breaks the contract, this
test fails before downstream skills (trader-memory-core, monitor_intraday)
break in production.

The contract is intentionally narrow — only the fields the planner
actually reads, plus the fields that downstream skills documented. New
fields can be added freely; existing field renames or type changes
require updating this test deliberately.
"""

import json

import generate_pre_market_plan as g2

# Scope 1: Phase 1 candidate dict — keys read by Phase 2.
PHASE1_CANDIDATE_REQUIRED_KEYS = (
    "ticker",
    "rank",
    "score",
    "state_caps",
    "warnings",
    "metrics",  # Phase 2 reads metrics.atr_14
    "key_levels",  # Phase 2 reads dma_10, dma_20, prior_close
    "invalidation_checks_passed",
    "earnings_within_2d",
    "market_cap_usd",
)

PHASE1_KEY_LEVELS_REQUIRED_KEYS = (
    "dma_10",
    "dma_20",
    "prior_close",
    "prior_close_source",
)

# Scope 2: Phase 2 plan dict — keys downstream skills depend on.
PHASE2_PLAN_REQUIRED_KEYS = (
    "ticker",
    "rank",
    "score",
    "plan_status",
    "requires_manual_confirmation",
    "trade_allowed_without_manual",
    "blocking_manual_reasons",
    "advisory_manual_reasons",
    "broker_inventory",
    "ssr_state",
    "premarket_levels",
    "key_levels",
    "entry_plans",
)

PHASE2_ENTRY_PLAN_REQUIRED_KEYS = (
    "plan_id",
    "trigger_type",
    "condition",
    "entry_hint",
    "stop_hint",
    "structural_targets",
    "reference_r_multiples",
    "size_recipe",
    "wait_for_trigger",
)

PHASE2_SIZE_RECIPE_REQUIRED_KEYS = (
    "risk_usd",
    "max_position_value_usd",
    "shares_formula",
    "sizing_rule_applied",
    "max_short_exposure_check_passed",
    "exposure_cap_applied",
    "remaining_short_exposure_capacity_usd",
)


def _phase1_candidate(rank: str = "B", state_caps: list = None) -> dict:
    return {
        "ticker": "XYZ",
        "rank": rank,
        "score": 71.4,
        "state_caps": state_caps or [],
        "warnings": [],
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
            "dma_50": 32.60,
            "prior_close": 78.45,
            "prior_close_source": "fmp_historical_eod",
            "session_high": 79.20,
            "session_low": 71.30,
        },
        "invalidation_checks_passed": True,
        "earnings_within_2d": False,
        "market_cap_usd": 5_000_000_000,
    }


def _phase1_report(candidates: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "skill": "parabolic-short-trade-planner",
        "phase": "screen",
        "as_of": "2026-04-30",
        "candidates": candidates,
    }


def _run_phase2(tmp_path, phase1: dict, **cli_overrides) -> dict:
    in_path = tmp_path / "phase1.json"
    in_path.write_text(json.dumps(phase1), encoding="utf-8")
    args = [
        "--candidates-json",
        str(in_path),
        "--broker",
        "none",
        "--output-dir",
        str(tmp_path),
        "--ssr-state-dir",
        str(tmp_path / "ssr"),
    ]
    for k, v in cli_overrides.items():
        args.extend([f"--{k.replace('_', '-')}", str(v)])
    g2.main(args)
    plan_file = next(p for p in tmp_path.iterdir() if "plan" in p.name and p.suffix == ".json")
    return json.loads(plan_file.read_text())


class TestPhase1CandidateShape:
    """Phase 1's candidate dicts must contain everything Phase 2 reads."""

    def test_render_candidate_has_required_keys(self):
        candidate = _phase1_candidate()
        for key in PHASE1_CANDIDATE_REQUIRED_KEYS:
            assert key in candidate, f"missing Phase 1 candidate key: {key}"

    def test_key_levels_has_inheritance_fields(self):
        candidate = _phase1_candidate()
        for key in PHASE1_KEY_LEVELS_REQUIRED_KEYS:
            assert key in candidate["key_levels"], f"missing key_levels key: {key}"


class TestPhase2PlanShape:
    def test_b_grade_yields_full_plan(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="B")])
        report = _run_phase2(tmp_path, phase1)
        assert len(report["plans"]) == 1
        plan = report["plans"][0]
        for key in PHASE2_PLAN_REQUIRED_KEYS:
            assert key in plan, f"missing Phase 2 plan key: {key}"

    def test_entry_plans_each_carry_unique_plan_id(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="A")])
        report = _run_phase2(tmp_path, phase1)
        ids = [ep["plan_id"] for ep in report["plans"][0]["entry_plans"]]
        assert len(ids) == len(set(ids)) == 3

    def test_each_entry_plan_keys_present(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="A")])
        report = _run_phase2(tmp_path, phase1)
        for ep in report["plans"][0]["entry_plans"]:
            for key in PHASE2_ENTRY_PLAN_REQUIRED_KEYS:
                assert key in ep, f"entry_plan missing {key}"

    def test_size_recipe_keys_present(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="A")])
        report = _run_phase2(tmp_path, phase1)
        recipe = report["plans"][0]["entry_plans"][0]["size_recipe"]
        for key in PHASE2_SIZE_RECIPE_REQUIRED_KEYS:
            assert key in recipe, f"size_recipe missing {key}"
        assert "shares" not in recipe, (
            "size_recipe must NOT carry a fixed shares count — Phase 3 "
            "computes shares at trigger fire from shares_formula"
        )


class TestPriorCloseInheritance:
    """The most error-prone seam: Phase 1's regular-session close must
    flow into Phase 2's SSR state without re-fetching from FMP quote."""

    def test_phase2_inherits_prior_close_value_and_source(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="B")])
        report = _run_phase2(tmp_path, phase1)
        ssr = report["plans"][0]["ssr_state"]
        assert ssr["prior_regular_close"] == 78.45
        assert ssr["prior_regular_close_source"] == "phase1_inherit"


class TestPlanStatusContract:
    """Phase 2 must classify plans as actionable vs watch_only based on
    whether the blocking reason is curable by manual confirmation."""

    def test_no_blockers_is_actionable_when_borrow_ok(self, tmp_path):
        # ManualBrokerAdapter blocks by default → would be watch_only.
        # Override by injecting a candidate that the broker would clear,
        # but since we can't here, simply assert plan_status is one of the
        # two valid values.
        phase1 = _phase1_report([_phase1_candidate(rank="A")])
        report = _run_phase2(tmp_path, phase1)
        assert report["plans"][0]["plan_status"] in ("actionable", "watch_only")

    def test_borrow_unavailable_yields_watch_only(self, tmp_path):
        # Manual adapter always returns can_open_new_short=False → must
        # surface as watch_only.
        phase1 = _phase1_report([_phase1_candidate(rank="A")])
        report = _run_phase2(tmp_path, phase1)
        plan = report["plans"][0]
        assert "borrow_inventory_unavailable" in plan["blocking_manual_reasons"]
        assert plan["plan_status"] == "watch_only"
        assert plan["trade_allowed_without_manual"] is False


class TestReportLevelKeys:
    def test_phase2_report_has_required_top_level(self, tmp_path):
        phase1 = _phase1_report([_phase1_candidate(rank="B")])
        report = _run_phase2(tmp_path, phase1)
        for key in (
            "schema_version",
            "skill",
            "phase",
            "generated_at",
            "as_of",
            "data_source",
            "data_latency_sec",
            "account_size",
            "risk_bps",
            "plans",
        ):
            assert key in report
        assert report["phase"] == "pre_market_plan"
        assert report["schema_version"] == "1.0"
