"""5-min Opening Range Low evaluator (Phase 3).

Pure function: ``evaluate(plan, bars, *, atr_14, vwap_series=None)``
returns the new state dict computed by left-folding over ``bars``.
No ``prior_state`` parameter — replay determinism (per the v0.5
idempotency contract) requires the FSM be a function of the bar list
alone.

State machine:
    armed → triggered           on bar that closes < ORL low AND
                                vol ≥ 1.2 × ORL bar's vol
    armed → (no transition)     on a pre-trigger reclaim (does not
                                invalidate; the plan stays armed)
    triggered → invalidated     on a post-trigger bar with close >
                                ORL low AND close > current VWAP
                                (BOTH must be reclaimed)
    invalidated → (terminal)    no further transitions

Inputs:
- ``plan["plan_id"]``, ``plan["ticker"]``, ``plan["trigger_type"]``
- ``atr_14`` (float | None) — daily 14-bar ATR from
  ``plans[i]["key_levels"]["atr_14"]``. When None or missing, the
  evaluator returns ``evaluation_status="skipped"`` +
  ``skip_reason="atr_14_unavailable"`` and leaves ``state="armed"``.
- ``vwap_series`` (list[float] | None) — pre-computed cumulative
  session VWAP per bar. When None, evaluator computes it.
- ``stop_buffer_atr`` (kwarg, default 0.25) — ORL stop cushion.
"""

from __future__ import annotations

from datetime import datetime

from vwap import vwap_for_each_bar

TRIGGER_TYPE = "orl_5min_break"
ORL_VOLUME_MULTIPLIER = 1.2
ENTRY_OFFSET_BELOW_ORL = 0.05  # entry hint string: "5min_orl_low - 0.05"
OPENING_BAR_HOUR = 9
OPENING_BAR_MINUTE = 30


def _empty_state(plan: dict) -> dict:
    """The starting / no-bars / skipped shell."""
    return {
        "plan_id": plan["plan_id"],
        "ticker": plan["ticker"],
        "trigger_type": TRIGGER_TYPE,
        "state": "armed",
        "evaluation_status": "evaluated",
        "skip_reason": None,
        "armed_at": None,
        "triggered_at": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "entry_actual": None,
        "stop_actual": None,
        "session_high": None,
        "session_low": None,
        "orl_low": None,
        "orl_high": None,
        "orl_volume": None,
        "vwap_series_last": None,
        "last_bar_ts": None,
    }


def evaluate(
    plan: dict,
    bars: list[dict],
    *,
    atr_14: float | None,
    vwap_series: list[float] | None = None,
    stop_buffer_atr: float = 0.25,
) -> dict:
    """Run the ORL FSM over the full bar list and return the new state."""
    out = _empty_state(plan)

    if not bars:
        return out  # state stays armed; CLI sets evaluation_status=no_bars

    if atr_14 is None:
        out["evaluation_status"] = "skipped"
        out["skip_reason"] = "atr_14_unavailable"
        return out

    # The first bar of the regular session MUST be the 09:30 ET bar
    # (which covers 09:30-09:35 with bar-open semantics). Alpaca skips
    # bars during halts or empty intervals, so bars[0] could be 09:35
    # or later if there were no trades in the opening 5 minutes — in
    # that rare case we cannot establish ORL low/high/volume and must
    # skip rather than mis-anchor on a later bar.
    first_bar_ts = datetime.fromisoformat(bars[0]["ts_et"])
    if (first_bar_ts.hour, first_bar_ts.minute) != (OPENING_BAR_HOUR, OPENING_BAR_MINUTE):
        out["evaluation_status"] = "skipped"
        out["skip_reason"] = "opening_range_bar_unavailable"
        return out

    if vwap_series is None:
        vwap_series = vwap_for_each_bar(bars)

    # First bar (09:30 → 09:35) is the Opening Range bar.
    orl = bars[0]
    out["armed_at"] = orl["ts_et"]
    out["orl_low"] = orl["l"]
    out["orl_high"] = orl["h"]
    out["orl_volume"] = orl["v"]
    out["session_high"] = orl["h"]
    out["session_low"] = orl["l"]
    out["last_bar_ts"] = orl["ts_et"]
    out["vwap_series_last"] = vwap_series[0]

    # Walk subsequent bars, updating session H/L and FSM state.
    for i in range(1, len(bars)):
        bar = bars[i]
        out["last_bar_ts"] = bar["ts_et"]
        out["session_high"] = max(out["session_high"], bar["h"])
        out["session_low"] = min(out["session_low"], bar["l"])
        out["vwap_series_last"] = vwap_series[i]

        if out["state"] == "invalidated":
            # Terminal: no further transitions.
            continue

        current_vwap = vwap_series[i]

        if out["state"] == "armed":
            # Trigger predicate: close < ORL low AND vol >= 1.2× ORL vol.
            if bar["c"] < out["orl_low"] and bar["v"] >= ORL_VOLUME_MULTIPLIER * out["orl_volume"]:
                out["state"] = "triggered"
                out["triggered_at"] = bar["ts_et"]
                out["entry_actual"] = round(bar["c"] - ENTRY_OFFSET_BELOW_ORL, 4)
                out["stop_actual"] = round(out["session_high"] + stop_buffer_atr * atr_14, 4)
            # Pre-trigger reclaims do NOT invalidate — plan stays armed.
            continue

        if out["state"] == "triggered":
            # Post-trigger invalidation: close > orl_low AND close > current_vwap.
            if bar["c"] > out["orl_low"] and bar["c"] > current_vwap:
                out["state"] = "invalidated"
                out["invalidated_at"] = bar["ts_et"]
                out["invalidation_reason"] = "post_trigger_close_reclaimed_orl_and_vwap"
            continue

    return out
