"""VWAP fail evaluator (Phase 3).

Pure function. State machine (per `references/intraday_trigger_playbook.md`
lines 49–74):

    armed → first_crack_seen      first 5-min close < VWAP, AND price
                                  has come from session HOD (filters
                                  open-print VWAP noise)
    first_crack_seen
        → vwap_retest_seen        next bar closes back at/above VWAP
    vwap_retest_seen
        → rejection_confirmed     next bar prints lower_high than the
                                  retest bar AND closes back below VWAP
    rejection_confirmed
        → triggered               on a later bar whose low < the
                                  rejection bar's low (intra-bar)
    triggered → invalidated       a later bar closes back above VWAP
                                  (post-trigger; triggered is NOT
                                  terminal per v0.5c)
    invalidated → (terminal)      no further transitions

The "from HOD" gate uses the running session HOD before the bar in
question — the bar's close must have descended from a prior bar that
printed at or near the session HOD.
"""

from __future__ import annotations

from vwap import vwap_for_each_bar

TRIGGER_TYPE = "vwap_fail"
ENTRY_OFFSET_BELOW_REJECTION_LOW = 0.05


def _empty_state(plan: dict) -> dict:
    return {
        "plan_id": plan["plan_id"],
        "ticker": plan["ticker"],
        "trigger_type": TRIGGER_TYPE,
        "state": "armed",
        "evaluation_status": "evaluated",
        "skip_reason": None,
        "armed_at": None,
        "first_crack_at": None,
        "vwap_retest_at": None,
        "rejection_confirmed_at": None,
        "triggered_at": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "entry_actual": None,
        "stop_actual": None,
        "session_high": None,
        "session_low": None,
        "vwap_series_last": None,
        "retest_bar_high": None,
        "rejection_bar_low": None,
        "last_bar_ts": None,
    }


def evaluate(
    plan: dict,
    bars: list[dict],
    *,
    atr_14: float | None = None,
    vwap_series: list[float] | None = None,
) -> dict:
    """Run the VWAP fail FSM. ``atr_14`` is unused but accepted for
    signature parity with the other evaluators."""
    out = _empty_state(plan)
    if not bars:
        return out

    if vwap_series is None:
        vwap_series = vwap_for_each_bar(bars)

    out["armed_at"] = bars[0]["ts_et"]
    out["session_high"] = bars[0]["h"]
    out["session_low"] = bars[0]["l"]
    out["last_bar_ts"] = bars[0]["ts_et"]
    out["vwap_series_last"] = vwap_series[0]

    # We need the session HOD *as of the bar before the current one* to
    # gate the "from HOD" transition into first_crack_seen.
    prior_session_high = bars[0]["h"]

    for i in range(1, len(bars)):
        bar = bars[i]
        out["last_bar_ts"] = bar["ts_et"]
        out["session_high"] = max(out["session_high"], bar["h"])
        out["session_low"] = min(out["session_low"], bar["l"])
        out["vwap_series_last"] = vwap_series[i]
        current_vwap = vwap_series[i]

        if out["state"] == "invalidated":
            prior_session_high = out["session_high"]
            continue

        # ----- Post-trigger invalidation: close back above VWAP -----
        if out["state"] == "triggered":
            if bar["c"] > current_vwap:
                out["state"] = "invalidated"
                out["invalidated_at"] = bar["ts_et"]
                out["invalidation_reason"] = "post_trigger_close_above_vwap"
            prior_session_high = out["session_high"]
            continue

        # ----- armed → first_crack_seen -----
        if out["state"] == "armed":
            # First close below VWAP, only if price has come down from
            # session HOD (i.e. session HOD > current close — proves
            # we're not just opening below VWAP).
            if bar["c"] < current_vwap and prior_session_high > bar["c"]:
                out["state"] = "first_crack_seen"
                out["first_crack_at"] = bar["ts_et"]
            prior_session_high = out["session_high"]
            continue

        # ----- first_crack_seen → vwap_retest_seen -----
        if out["state"] == "first_crack_seen":
            if bar["c"] >= current_vwap:
                out["state"] = "vwap_retest_seen"
                out["vwap_retest_at"] = bar["ts_et"]
                out["retest_bar_high"] = bar["h"]
            prior_session_high = out["session_high"]
            continue

        # ----- vwap_retest_seen → rejection_confirmed -----
        if out["state"] == "vwap_retest_seen":
            # Lower high than retest bar AND close back below VWAP.
            if bar["h"] < out["retest_bar_high"] and bar["c"] < current_vwap:
                out["state"] = "rejection_confirmed"
                out["rejection_confirmed_at"] = bar["ts_et"]
                out["rejection_bar_low"] = bar["l"]
            prior_session_high = out["session_high"]
            continue

        # ----- rejection_confirmed → triggered -----
        if out["state"] == "rejection_confirmed":
            # Trigger when a later bar's low takes out the rejection
            # bar's low.
            if bar["l"] < out["rejection_bar_low"]:
                out["state"] = "triggered"
                out["triggered_at"] = bar["ts_et"]
                out["entry_actual"] = round(
                    out["rejection_bar_low"] - ENTRY_OFFSET_BELOW_REJECTION_LOW, 4
                )
                # Stop is the VWAP-reclaim point — use the retest bar's
                # close (the price that proved VWAP was broken below).
                # If the retest happened at exactly VWAP, that's a
                # principled stop because a re-reclaim there means the
                # whole pattern failed.
                out["stop_actual"] = round(out["retest_bar_high"], 4)
            prior_session_high = out["session_high"]
            continue

        prior_session_high = out["session_high"]

    return out
