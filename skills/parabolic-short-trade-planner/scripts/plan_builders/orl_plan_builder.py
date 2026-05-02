"""5-min Opening Range Low (ORL) trigger plan.

The trader watches the first 5-minute bar, marks its low, and shorts on
a break of that low with 1.2x volume. Stop sits above the session HOD
plus a small ATR cushion.
"""

from __future__ import annotations

TRIGGER_TYPE = "orl_5min_break"


def build_orl_plan(
    *,
    plan_id: str,
    size_recipe: dict,
    reference_r_multiples: tuple[float, ...] = (1.0, 2.0, 3.0),
    stop_buffer_atr: float = 0.25,
) -> dict:
    """Build the ORL entry plan dict (Phase 2 schema entry)."""
    return {
        "plan_id": plan_id,
        "trigger_type": TRIGGER_TYPE,
        "condition": "5min ORL を出来高 1.2x 以上で下抜け",
        "entry_hint": "5min_orl_low - 0.05",
        "stop_hint": f"session_HOD + {stop_buffer_atr} * ATR",
        "structural_targets": ["dma_10", "dma_20"],
        "reference_r_multiples": list(reference_r_multiples),
        "size_recipe": dict(size_recipe),
        "wait_for_trigger": True,
    }
