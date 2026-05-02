"""First Red 5-min evaluator (Phase 3).

Pure function. State machine:

    armed → red_marked            on the first bar where close < open
    red_marked → triggered        on a later bar whose low < red_low
                                  (intra-bar trigger; playbook says
                                  "prints below")
    red_marked → invalidated      on a later bar whose high > red_high
    triggered → invalidated       on a post-trigger bar whose high
                                  > red_high (rare but the contract
                                  says triggered is NOT terminal)
    invalidated → (terminal)      no further transitions

Same-bar tie-break (v0.5b contract): when a single bar prints both
``high > red_high`` (would invalidate) AND ``low < red_low`` (would
trigger), invalidation wins. Rationale: a bar that swept both sides
of the prior structure is a failed setup, not a clean breakdown.
"""

from __future__ import annotations

TRIGGER_TYPE = "first_red_5min"
ENTRY_OFFSET_BELOW_RED_LOW = 0.05  # entry hint: "first_red_5min_low - 0.05"


def _empty_state(plan: dict) -> dict:
    return {
        "plan_id": plan["plan_id"],
        "ticker": plan["ticker"],
        "trigger_type": TRIGGER_TYPE,
        "state": "armed",
        "evaluation_status": "evaluated",
        "skip_reason": None,
        "armed_at": None,
        "red_marked_at": None,
        "triggered_at": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "entry_actual": None,
        "stop_actual": None,
        "session_high": None,
        "session_low": None,
        "red_low": None,
        "red_high": None,
        "last_bar_ts": None,
    }


def evaluate(
    plan: dict,
    bars: list[dict],
    *,
    atr_14: float | None = None,
    vwap_series: list[float] | None = None,
) -> dict:
    """Run the First Red FSM. ``atr_14`` is unused but accepted for
    signature parity with the other evaluators."""
    out = _empty_state(plan)
    if not bars:
        return out

    # Initialise with the open bar.
    out["armed_at"] = bars[0]["ts_et"]
    out["session_high"] = bars[0]["h"]
    out["session_low"] = bars[0]["l"]
    out["last_bar_ts"] = bars[0]["ts_et"]

    for i, bar in enumerate(bars):
        out["last_bar_ts"] = bar["ts_et"]
        out["session_high"] = max(out["session_high"], bar["h"])
        out["session_low"] = min(out["session_low"], bar["l"])

        if out["state"] == "invalidated":
            continue

        if out["state"] == "armed":
            # Mark first red bar.
            if bar["c"] < bar["o"]:
                out["state"] = "red_marked"
                out["red_marked_at"] = bar["ts_et"]
                out["red_low"] = bar["l"]
                out["red_high"] = bar["h"]
            continue

        # red_marked or triggered: evaluate invalidation FIRST so the
        # same-bar tie-break (invalidation wins) is honoured.
        invalidates = bar["h"] > out["red_high"]
        triggers = bar["l"] < out["red_low"]

        if out["state"] == "red_marked":
            if invalidates:
                # Tie-break: even if triggers also true on the same bar,
                # invalidation wins.
                out["state"] = "invalidated"
                out["invalidated_at"] = bar["ts_et"]
                out["invalidation_reason"] = "red_high_taken_out"
            elif triggers:
                out["state"] = "triggered"
                out["triggered_at"] = bar["ts_et"]
                out["entry_actual"] = round(out["red_low"] - ENTRY_OFFSET_BELOW_RED_LOW, 4)
                out["stop_actual"] = round(out["red_high"], 4)
            continue

        if out["state"] == "triggered":
            # Post-trigger invalidation: red_high taken out.
            if invalidates:
                out["state"] = "invalidated"
                out["invalidated_at"] = bar["ts_et"]
                out["invalidation_reason"] = "post_trigger_red_high_taken_out"
            continue

    return out
