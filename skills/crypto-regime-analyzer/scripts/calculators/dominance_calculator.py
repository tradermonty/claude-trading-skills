#!/usr/bin/env python3
"""
Component 3: BTC Dominance Regime (Weight: 15%)

BTC dominance direction is only meaningful jointly with BTC's own trend:

  BTC trend UP  + dominance FALLING -> capital rotating out the risk curve
                                        (classic alt-season risk-on)      -> 90
  BTC trend UP  + dominance RISING  -> BTC-led market, alts lagging
                                        (constructive but narrow)         -> 65
  BTC trend DOWN + dominance RISING -> flight to relative safety inside
                                        crypto (defensive)                -> 30
  BTC trend DOWN + dominance FALLING-> indiscriminate de-risking or
                                        stable-rotation (worst regime)    -> 10

Extreme-dominance level modifier:
  dominance >= 62% -> +5 when BTC trend down (washout / max-fear zone often
                       precedes bottoms), no change when trend up
  dominance <= 40% -> -5 when BTC trend up (froth: alts historically
                       overextended at very low dominance)

Input: list of daily dominance percentages oldest -> newest (>= 31 obs),
plus btc_trend_up flag from Component 1.
"""

TREND_LOOKBACK = 30
HIGH_DOMINANCE = 62.0
LOW_DOMINANCE = 40.0
FLAT_BAND = 0.5  # dominance percentage-point change treated as flat


def calculate_dominance_regime(dominance_series: list, btc_trend_up: bool) -> dict:
    """
    Score BTC dominance regime jointly with BTC trend direction.

    Args:
        dominance_series: Daily BTC dominance %, oldest -> newest.
        btc_trend_up: True when Component 1 shows constructive BTC trend.

    Returns:
        Dict with score, signal, data_available, and dominance details.
    """
    if not dominance_series or len(dominance_series) < TREND_LOOKBACK + 1:
        return {
            "score": 50,
            "signal": f"NO DATA: Need >= {TREND_LOOKBACK + 1} daily dominance points",
            "data_available": False,
        }

    current = dominance_series[-1]
    prior = dominance_series[-(TREND_LOOKBACK + 1)]
    change = current - prior

    if change > FLAT_BAND:
        dom_direction = "rising"
    elif change < -FLAT_BAND:
        dom_direction = "falling"
    else:
        dom_direction = "flat"

    if btc_trend_up:
        if dom_direction == "falling":
            score, regime = 90, "ALT ROTATION (BTC up, dominance falling)"
        elif dom_direction == "rising":
            score, regime = 65, "BTC-LED (BTC up, dominance rising; alts lagging)"
        else:
            score, regime = 75, "BTC UP, dominance flat"
    else:
        if dom_direction == "rising":
            score, regime = 30, "DEFENSIVE (BTC down, dominance rising)"
        elif dom_direction == "falling":
            score, regime = 10, "DE-RISKING (BTC down, dominance falling)"
        else:
            score, regime = 25, "BTC DOWN, dominance flat"

    modifier = ""
    if current >= HIGH_DOMINANCE and not btc_trend_up:
        score += 5
        modifier = "; dominance at washout extreme (contrarian watch)"
    elif current <= LOW_DOMINANCE and btc_trend_up:
        score -= 5
        modifier = "; dominance at froth extreme (late-cycle caution)"
    score = max(0, min(100, score))

    return {
        "score": score,
        "signal": f"{regime}; dominance {current:.1f}% "
        f"({change:+.1f}pts / {TREND_LOOKBACK}d){modifier}",
        "data_available": True,
        "dominance_pct": round(current, 2),
        "dominance_change_30d": round(change, 2),
        "direction": dom_direction,
    }
