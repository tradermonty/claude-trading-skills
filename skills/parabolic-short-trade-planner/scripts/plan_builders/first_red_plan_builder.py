"""First Red 5-minute candle trigger plan.

For ramps that print only green bars off the open, wait for the first
red 5-min and short on a break of *its* low. Stop above that bar's high.
This is the lowest-risk variant when the open gaps into resistance.
"""

from __future__ import annotations

TRIGGER_TYPE = "first_red_5min"


def build_first_red_plan(
    *,
    plan_id: str,
    size_recipe: dict,
    reference_r_multiples: tuple[float, ...] = (1.0, 2.0, 3.0),
) -> dict:
    return {
        "plan_id": plan_id,
        "trigger_type": TRIGGER_TYPE,
        "condition": "寄付後最初の赤 5min の安値割れ",
        "entry_hint": "first_red_5min_low - 0.05",
        "stop_hint": "first_red_5min_high",
        "structural_targets": ["dma_10", "dma_20"],
        "reference_r_multiples": list(reference_r_multiples),
        "size_recipe": dict(size_recipe),
        "wait_for_trigger": True,
    }
