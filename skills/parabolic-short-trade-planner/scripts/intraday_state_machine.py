"""Phase 3 dispatcher: choose the right evaluator by trigger_type.

The Phase 3 idempotency contract requires the FSM be a pure function
of ``(plan, bars, atr_14)``. ``prior_state`` is **not** an input —
it's read by the CLI for diff/notification purposes only. Each
evaluator left-folds over the full bar list from session open.
"""

from __future__ import annotations

from intraday_evaluators import (
    first_red_evaluator,
    orl_evaluator,
    vwap_fail_evaluator,
)
from vwap import vwap_for_each_bar

_EVALUATORS = {
    "orl_5min_break": orl_evaluator.evaluate,
    "first_red_5min": first_red_evaluator.evaluate,
    "vwap_fail": vwap_fail_evaluator.evaluate,
}


def step_one_plan(
    plan: dict,
    bars: list[dict],
    *,
    atr_14: float | None,
    stop_buffer_atr: float = 0.25,
) -> dict:
    """Dispatch to the right FSM evaluator based on plan["trigger_type"].

    Computes session VWAP once for the bar list and shares it with any
    evaluator that needs it (ORL + VWAP fail), so a Phase 3 run that
    has all three trigger plans for the same ticker only computes
    VWAP once.
    """
    trigger_type = plan["trigger_type"]
    if trigger_type not in _EVALUATORS:
        raise ValueError(f"Unknown trigger_type: {trigger_type!r}")

    vwap_series = vwap_for_each_bar(bars) if bars else None

    if trigger_type == "orl_5min_break":
        return orl_evaluator.evaluate(
            plan,
            bars,
            atr_14=atr_14,
            vwap_series=vwap_series,
            stop_buffer_atr=stop_buffer_atr,
        )
    if trigger_type == "first_red_5min":
        return first_red_evaluator.evaluate(plan, bars, atr_14=atr_14, vwap_series=vwap_series)
    # vwap_fail
    return vwap_fail_evaluator.evaluate(plan, bars, atr_14=atr_14, vwap_series=vwap_series)
