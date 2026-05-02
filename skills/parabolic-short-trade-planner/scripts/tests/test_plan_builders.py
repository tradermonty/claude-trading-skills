"""Tests for plan_builders/{orl,first_red,vwap_fail}_plan_builder."""

import sys
from pathlib import Path

PLAN_DIR = Path(__file__).resolve().parents[1] / "plan_builders"
if str(PLAN_DIR) not in sys.path:
    sys.path.insert(0, str(PLAN_DIR))

from first_red_plan_builder import build_first_red_plan  # noqa: E402
from orl_plan_builder import build_orl_plan  # noqa: E402
from vwap_fail_plan_builder import build_vwap_fail_plan  # noqa: E402

SIZE_RECIPE = {
    "risk_usd": 500,
    "max_position_value_usd": 5000,
    "shares_formula": "...",
    "sizing_rule_applied": "fixed_fractional",
    "max_short_exposure_check_passed": True,
}


class TestORLPlan:
    def test_basic_shape(self):
        plan = build_orl_plan(plan_id="XYZ-2026-04-30-ORL5", size_recipe=SIZE_RECIPE)
        assert plan["plan_id"] == "XYZ-2026-04-30-ORL5"
        assert plan["trigger_type"] == "orl_5min_break"
        assert plan["wait_for_trigger"] is True
        assert plan["structural_targets"] == ["dma_10", "dma_20"]
        assert plan["size_recipe"]["risk_usd"] == 500

    def test_atr_buffer_used_in_stop_hint(self):
        plan = build_orl_plan(plan_id="X", size_recipe=SIZE_RECIPE, stop_buffer_atr=0.5)
        assert "0.5" in plan["stop_hint"]

    def test_size_recipe_is_copied(self):
        original = dict(SIZE_RECIPE)
        plan = build_orl_plan(plan_id="X", size_recipe=original)
        plan["size_recipe"]["risk_usd"] = 9999
        assert original["risk_usd"] == 500  # caller's dict not mutated


class TestFirstRedPlan:
    def test_basic_shape(self):
        plan = build_first_red_plan(plan_id="X-FR5", size_recipe=SIZE_RECIPE)
        assert plan["trigger_type"] == "first_red_5min"
        assert plan["entry_hint"] == "first_red_5min_low - 0.05"
        assert plan["stop_hint"] == "first_red_5min_high"

    def test_reference_r_multiples_default(self):
        plan = build_first_red_plan(plan_id="X-FR5", size_recipe=SIZE_RECIPE)
        assert plan["reference_r_multiples"] == [1.0, 2.0, 3.0]

    def test_custom_reference_r_multiples(self):
        plan = build_first_red_plan(
            plan_id="X-FR5",
            size_recipe=SIZE_RECIPE,
            reference_r_multiples=(0.5, 1.5),
        )
        assert plan["reference_r_multiples"] == [0.5, 1.5]


class TestVWAPFailPlan:
    def test_basic_shape(self):
        plan = build_vwap_fail_plan(plan_id="X-VWF", size_recipe=SIZE_RECIPE)
        assert plan["trigger_type"] == "vwap_fail"
        assert "VWAP" in plan["condition"]
        assert plan["stop_hint"] == "vwap_reclaim_5min_close"

    def test_size_recipe_passed_through(self):
        plan = build_vwap_fail_plan(plan_id="X-VWF", size_recipe=SIZE_RECIPE)
        assert plan["size_recipe"]["max_position_value_usd"] == 5000


class TestPlanIdRequired:
    def test_orl_uses_supplied_id(self):
        plan = build_orl_plan(plan_id="ABCD", size_recipe=SIZE_RECIPE)
        assert plan["plan_id"] == "ABCD"
