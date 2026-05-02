"""VWAP-fail trigger plan.

After a first crack from the open's high, price retests VWAP. A 5-min
close back below VWAP plus a lower-high break is the entry. Invalidates
on a VWAP reclaim (i.e. a 5-min close back above).
"""

from __future__ import annotations

TRIGGER_TYPE = "vwap_fail"


def build_vwap_fail_plan(
    *,
    plan_id: str,
    size_recipe: dict,
    reference_r_multiples: tuple[float, ...] = (1.0, 2.0, 3.0),
) -> dict:
    return {
        "plan_id": plan_id,
        "trigger_type": TRIGGER_TYPE,
        "condition": "First crack 後 VWAP retest で 5min 終値拒否 + lower-high 下抜け",
        "entry_hint": "lower_high_low - 0.05",
        "stop_hint": "vwap_reclaim_5min_close",
        "structural_targets": ["dma_10", "dma_20"],
        "reference_r_multiples": list(reference_r_multiples),
        "size_recipe": dict(size_recipe),
        "wait_for_trigger": True,
    }
