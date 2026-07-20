#!/usr/bin/env python3
"""Pure weekly price-action confirmation module (Jason Shapiro contrarian
methodology, step 3: price-action confirmation of a crowded market).

No I/O, no network calls -- every function takes plain dicts/lists/scalars
and returns plain values so it is trivially unit-testable. See
references/contrarian-confirmation-checklist.md for the methodology this
implements (definitions mirrored word-for-word) and
scripts/check_weekly_price_action.py for the CLI that fetches real FMP OHLC
data and feeds it through this module.

Direction convention: fading CROWDED_LONG seeks BEARISH reversal evidence at
or after UPSIDE extremes (watch highs); CROWDED_SHORT is the exact mirror
(watch lows). Every comparison in this module is a STRICT inequality --
equal-to-prior-extreme never counts as a new extreme, and a close exactly
at a prior level never counts as a reversal/breakout/failure.

Window terminology: "prior swing-lookback weeks" / "prior extreme-lookback
weeks" NEVER include the week under evaluation -- they are the N completed
weeks strictly before it. Truncation is per-evaluated-week, not per-run:
when fewer completed weeks exist before an evaluated week than the
configured window, the window truncates to what is available, and the
ACTUAL size used is reported as `*_window_weeks_used` inside that check's
own result block.
"""

from __future__ import annotations

from datetime import date

SWING_LOOKBACK_WEEKS_DEFAULT = 13
EXTREME_LOOKBACK_WEEKS_DEFAULT = 52
SIGNAL_RECENCY_WEEKS_DEFAULT = 4
MIN_WEEKS_DEFAULT = 30

# The confidence-HIGH "full 52-week extreme" gate reads this constant, not
# extreme_lookback_weeks directly, so a caller running with a non-default
# extreme_lookback_weeks still gets a well-defined (if perhaps unreachable)
# gate rather than a moving target. In practice callers are expected to run
# with the default 52, matching this constant.
CONFIDENCE_HIGH_EXTREME_WEEKS = 52

# Maps a triggered check's dict key to the short verdict_reason token used
# in the output contract (plan §2).
CHECK_REASON_MAP = {
    "weekly_key_reversal": "key_reversal",
    "failed_extreme": "failed_extreme",
    "failed_breakout": "failed_breakout",
}

_TRIGGER_ORDER = ("weekly_key_reversal", "failed_extreme", "failed_breakout")


# --- Daily series helpers ----------------------------------------------------


def build_sorted_daily_series(rows: list[dict]) -> list[dict]:
    """Convert raw FMP-shaped daily OHLCV rows into a sorted, deduped list of
    {date, open, high, low, close, volume} dicts. Accepts either a `close`
    field (the full OHLC endpoint used by this skill) or a `price` field
    (the light endpoint's field name, accepted defensively per the #245
    field-name trap). Rows missing `date`, any of open/high/low, or both
    close/price fields are dropped; duplicate dates keep the last
    occurrence (assumed to be the more recently fetched value).
    """
    by_date: dict[str, dict] = {}
    for row in rows:
        d = row.get("date")
        o = row.get("open")
        h = row.get("high")
        low = row.get("low")
        c = row.get("close", row.get("price"))
        if d is None or o is None or h is None or low is None or c is None:
            continue
        by_date[d] = {
            "date": d,
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": row.get("volume", 0) or 0,
        }
    return [by_date[d] for d in sorted(by_date)]


def resample_weekly(daily_bars: list[dict], as_of: str) -> list[dict]:
    """Group daily bars into completed ISO calendar weeks (Mon-Sun).

    `as_of` is an INFORMATION CUTOFF applied to the DAILY bars BEFORE
    resampling: any bar dated after `as_of` is dropped first. The ISO week
    CONTAINING `as_of` is then always excluded from the output -- it is the
    in-progress week, whether or not it happens to have a full week of
    bars already (a week made partial by the cutoff is dropped as
    incomplete; a week that isn't the as_of week, even a holiday-shortened
    one, is a completed week and is resampled normally).

    Crypto/24-7 markets (e.g. BT) may include weekend bars; a bar's ISO
    week is taken directly from its own `date` (Sunday belongs to its own
    Mon-Sun week, never the following week) -- deterministic regardless of
    FMP's UTC-vs-ET day-boundary convention for crypto.

    Returns weekly bars sorted ascending, each:
    {week_of (Monday, ISO date str), open, high, low, close, volume}.
    """
    as_of_date = date.fromisoformat(as_of)
    current_key = as_of_date.isocalendar()[:2]

    groups: dict[tuple[int, int], list[dict]] = {}
    for bar in daily_bars:
        if bar["date"] > as_of:
            continue
        d = date.fromisoformat(bar["date"])
        key = d.isocalendar()[:2]
        groups.setdefault(key, []).append(bar)

    weekly: list[dict] = []
    for key in sorted(groups.keys()):
        if key == current_key:
            continue
        bars = sorted(groups[key], key=lambda b: b["date"])
        iso_year, iso_week = key
        week_of = date.fromisocalendar(iso_year, iso_week, 1).isoformat()
        weekly.append(
            {
                "week_of": week_of,
                "open": bars[0]["open"],
                "high": max(b["high"] for b in bars),
                "low": min(b["low"] for b in bars),
                "close": bars[-1]["close"],
                "volume": sum(b.get("volume", 0) or 0 for b in bars),
            }
        )
    return weekly


# --- Window helper -------------------------------------------------------


def compute_prior_window(
    weekly_bars: list[dict], idx: int, lookback_weeks: int
) -> tuple[list[dict], int]:
    """The up-to-`lookback_weeks` completed weeks strictly before `idx`
    (never including `idx` itself), truncated to whatever is available.
    Returns (window_bars, window_weeks_used)."""
    start = max(0, idx - lookback_weeks)
    window = weekly_bars[start:idx]
    return window, len(window)


# --- Detectors -------------------------------------------------------------


def detect_weekly_key_reversal(
    weekly_bars: list[dict],
    direction: str,
    swing_lookback_weeks: int = SWING_LOOKBACK_WEEKS_DEFAULT,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
    signal_recency_weeks: int = SIGNAL_RECENCY_WEEKS_DEFAULT,
) -> dict:
    """Bearish form (CROWDED_LONG): the week's high is a new swing-lookback
    high (STRICTLY greater than the max high of the prior swing-lookback
    completed weeks) AND the week's close is STRICTLY below the prior
    week's low. Bullish mirror (CROWDED_SHORT): new lookback low AND close
    above the prior week's high.

    Scans the signal-recency window (the most recent `signal_recency_weeks`
    completed weeks) for candidate weeks; if more than one qualifies, the
    MOST RECENT is reported (a single check reports one signal, never a
    list). Also computes `is_full_window_extreme`: whether the same new
    high/low ALSO beats the max/min of the (separate, larger)
    extreme-lookback window -- used only by the confidence-HIGH gate, never
    by the trigger condition itself.
    """
    n = len(weekly_bars)
    recency_start = max(0, n - signal_recency_weeks)
    best: dict | None = None

    for i in range(max(recency_start, 1), n):
        swing_window, swing_used = compute_prior_window(weekly_bars, i, swing_lookback_weeks)
        if not swing_window:
            continue
        bar = weekly_bars[i]
        prior_bar = weekly_bars[i - 1]

        if direction == "CROWDED_LONG":
            triggered = (
                bar["high"] > max(w["high"] for w in swing_window)
                and bar["close"] < prior_bar["low"]
            )
        else:
            triggered = (
                bar["low"] < min(w["low"] for w in swing_window)
                and bar["close"] > prior_bar["high"]
            )

        if not triggered:
            continue

        extreme_window, extreme_used = compute_prior_window(weekly_bars, i, extreme_lookback_weeks)
        if direction == "CROWDED_LONG":
            is_full_window_extreme = bool(extreme_window) and bar["high"] > max(
                w["high"] for w in extreme_window
            )
        else:
            is_full_window_extreme = bool(extreme_window) and bar["low"] < min(
                w["low"] for w in extreme_window
            )

        side = "high" if direction == "CROWDED_LONG" else "low"
        best = {
            "triggered": True,
            "week_of": bar["week_of"],
            "swing_window_weeks_used": swing_used,
            "extreme_window_weeks_used": extreme_used,
            "is_full_window_extreme": is_full_window_extreme,
            "detail": (
                f"week {bar['week_of']}: new {swing_used}-week {side} "
                f"({bar[side]}) followed by a close through the prior week's "
                f"{'low' if direction == 'CROWDED_LONG' else 'high'}"
            ),
        }

    if best is None:
        return {
            "triggered": False,
            "week_of": None,
            "swing_window_weeks_used": None,
            "extreme_window_weeks_used": None,
            "is_full_window_extreme": False,
            "detail": "no weekly key reversal within the signal-recency window",
        }
    return best


def detect_failed_extreme(
    weekly_bars: list[dict],
    direction: str,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
    signal_recency_weeks: int = SIGNAL_RECENCY_WEEKS_DEFAULT,
) -> dict:
    """Intraweek poke-and-fail: within the signal-recency window, a week
    traded STRICTLY above the prior extreme-lookback high but closed back
    BELOW that same prior high. Mirror for lows (CROWDED_SHORT)."""
    n = len(weekly_bars)
    recency_start = max(0, n - signal_recency_weeks)
    best: dict | None = None

    for i in range(recency_start, n):
        window, used = compute_prior_window(weekly_bars, i, extreme_lookback_weeks)
        if not window:
            continue
        bar = weekly_bars[i]

        if direction == "CROWDED_LONG":
            level = max(w["high"] for w in window)
            triggered = bar["high"] > level and bar["close"] < level
        else:
            level = min(w["low"] for w in window)
            triggered = bar["low"] < level and bar["close"] > level

        if triggered:
            best = {
                "triggered": True,
                "attempted_level": level,
                "week_of": bar["week_of"],
                "window_weeks_used": used,
                "detail": (
                    f"week {bar['week_of']}: intraweek poke through {level} "
                    f"({used}-week prior extreme), closed back through it"
                ),
            }

    if best is None:
        return {
            "triggered": False,
            "attempted_level": None,
            "week_of": None,
            "window_weeks_used": None,
            "detail": "no failed extreme within the signal-recency window",
        }
    return best


def detect_failed_breakout(
    weekly_bars: list[dict],
    direction: str,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
    signal_recency_weeks: int = SIGNAL_RECENCY_WEEKS_DEFAULT,
) -> dict:
    """Confirmed-then-rejected: a weekly CLOSE above the prior
    extreme-lookback high (a closing breakout) at week B, followed within
    <=3 subsequent completed weeks by a weekly close back below the
    breakout level (the prior extreme high itself). Mirror down for
    CROWDED_SHORT. `week_of` on the returned block is the FAILURE week
    (the close back through the level), never the breakout week -- the
    breakout week is recorded only inside `detail`. Only the FIRST close
    back through the level after a given breakout counts as that
    breakout's failure (a later close back through is not a second,
    independent failure of the same breakout).

    The breakout week B itself may fall outside the signal-recency window
    -- only the failure week (this check's `week_of`) must be recent;
    B is, by construction, always strictly older than the failure week, so
    it can never later self-veto via the continuation check.
    """
    n = len(weekly_bars)
    recency_start = max(0, n - signal_recency_weeks)
    # B can be up to 3 weeks before the recency window's start and still
    # produce a failure week inside the recency window.
    b_start = max(0, recency_start - 3)
    best: tuple[int, int, float, int] | None = None  # (f_idx, b_idx, level, window_used)

    for b in range(b_start, n - 1):
        window, used = compute_prior_window(weekly_bars, b, extreme_lookback_weeks)
        if not window:
            continue
        bar_b = weekly_bars[b]

        if direction == "CROWDED_LONG":
            level = max(w["high"] for w in window)
            is_breakout = bar_b["close"] > level
        else:
            level = min(w["low"] for w in window)
            is_breakout = bar_b["close"] < level

        if not is_breakout:
            continue

        for f in range(b + 1, min(b + 3, n - 1) + 1):
            bar_f = weekly_bars[f]
            if direction == "CROWDED_LONG":
                failed = bar_f["close"] < level
            else:
                failed = bar_f["close"] > level
            if failed:
                if f >= recency_start and (best is None or f > best[0]):
                    best = (f, b, level, used)
                break  # only the FIRST close-back-through after this breakout counts

    if best is None:
        return {
            "triggered": False,
            "breakout_level": None,
            "week_of": None,
            "window_weeks_used": None,
            "detail": "no failed breakout within the signal-recency window",
        }

    f_idx, b_idx, level, used = best
    # Direction-aware wording (P3 regression, user re-review of PR #247):
    # a CROWDED_LONG breakout is a CLOSE strictly ABOVE the prior extreme
    # high; the CROWDED_SHORT mirror is a CLOSE strictly BELOW the prior
    # extreme low -- the detail text must say which one actually happened,
    # never a hardcoded "above" regardless of direction.
    breakout_word = "above" if direction == "CROWDED_LONG" else "below"
    return {
        "triggered": True,
        "breakout_level": level,
        "week_of": weekly_bars[f_idx]["week_of"],
        "window_weeks_used": used,
        "detail": (
            f"closing breakout {breakout_word} {level} at week {weekly_bars[b_idx]['week_of']}, "
            f"failed (closed back through) at week {weekly_bars[f_idx]['week_of']}"
        ),
    }


def detect_continuation(
    weekly_bars: list[dict],
    direction: str,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
    signal_recency_weeks: int = SIGNAL_RECENCY_WEEKS_DEFAULT,
    newest_signal_idx: int | None = None,
) -> dict:
    """Whether the market set a new CLOSING extreme in the crowd's
    direction (a new highest close for CROWDED_LONG, lowest close for
    CROWDED_SHORT, relative to each evaluated week's own prior
    extreme-lookback window of CLOSES) strictly more recently than the
    newest triggered reversal/failure signal.

    If a signal exists (`newest_signal_idx` is not None), the scan starts
    the week AFTER it -- so the signal week (and anything before it,
    including a failed_breakout's own breakout week, which is always
    older) can never self-veto. If no signal exists at all, the scan
    covers the full signal-recency window instead.

    Reports the EARLIEST qualifying week (the moment continuation
    resumed), not the most recent -- the verdict only needs to know
    whether continuation happened at all after the signal.
    """
    n = len(weekly_bars)
    recency_start = max(0, n - signal_recency_weeks)
    scan_start = max(0, (newest_signal_idx + 1) if newest_signal_idx is not None else recency_start)

    for i in range(scan_start, n):
        window, used = compute_prior_window(weekly_bars, i, extreme_lookback_weeks)
        if not window:
            continue
        bar = weekly_bars[i]

        if direction == "CROWDED_LONG":
            prior_close_extreme = max(w["close"] for w in window)
            new_extreme = bar["close"] > prior_close_extreme
        else:
            prior_close_extreme = min(w["close"] for w in window)
            new_extreme = bar["close"] < prior_close_extreme

        if new_extreme:
            return {
                "new_closing_extreme_with_crowd": True,
                "week_of": bar["week_of"],
                "window_weeks_used": used,
            }

    return {"new_closing_extreme_with_crowd": False, "week_of": None, "window_weeks_used": None}


# --- Swing levels (fractal pivots) ------------------------------------------


def compute_swing_levels(
    weekly_bars: list[dict],
    direction: str,
    swing_lookback_weeks: int = SWING_LOOKBACK_WEEKS_DEFAULT,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
) -> dict:
    """Swing high = a completed week whose high is STRICTLY greater than
    the highs of the 2 completed weeks on each side (a 5-week fractal).
    Swing low mirrors on lows. `nearest` = the most recent such pivot
    within the extreme-lookback window. Fallback when no pivot exists in
    that window: the max high (min low) of the swing-lookback window,
    flagged `fallback: true`. `stop_reference` follows the fade direction:
    fading a crowded LONG (going short) references the nearest swing HIGH;
    fading a crowded SHORT (going long) references the nearest swing LOW.
    """
    n = len(weekly_bars)
    nearest_swing_high = None
    nearest_swing_low = None

    # A pivot at index i needs 2 completed weeks on each side, i.e.
    # i-2 >= 0 and i+2 <= n-1 -- the most recent possible pivot is 2 weeks
    # before the last completed week.
    search_end = n - 3
    if search_end >= 2:
        search_start = max(2, search_end - extreme_lookback_weeks + 1)
        for i in range(search_end, search_start - 1, -1):
            bar = weekly_bars[i]
            if nearest_swing_high is None:
                neighbor_highs = [weekly_bars[j]["high"] for j in (i - 2, i - 1, i + 1, i + 2)]
                if bar["high"] > max(neighbor_highs):
                    nearest_swing_high = {
                        "price": bar["high"],
                        "week_of": bar["week_of"],
                        "fallback": False,
                    }
            if nearest_swing_low is None:
                neighbor_lows = [weekly_bars[j]["low"] for j in (i - 2, i - 1, i + 1, i + 2)]
                if bar["low"] < min(neighbor_lows):
                    nearest_swing_low = {
                        "price": bar["low"],
                        "week_of": bar["week_of"],
                        "fallback": False,
                    }
            if nearest_swing_high is not None and nearest_swing_low is not None:
                break

    fb_start = max(0, n - swing_lookback_weeks)
    fb_window = weekly_bars[fb_start:n]
    if nearest_swing_high is None and fb_window:
        best = max(fb_window, key=lambda w: w["high"])
        nearest_swing_high = {"price": best["high"], "week_of": best["week_of"], "fallback": True}
    if nearest_swing_low is None and fb_window:
        best = min(fb_window, key=lambda w: w["low"])
        nearest_swing_low = {"price": best["low"], "week_of": best["week_of"], "fallback": True}

    stop_reference = None
    if direction == "CROWDED_LONG" and nearest_swing_high is not None:
        stop_reference = nearest_swing_high["price"]
    elif direction == "CROWDED_SHORT" and nearest_swing_low is not None:
        stop_reference = nearest_swing_low["price"]

    return {
        "nearest_swing_high": nearest_swing_high,
        "nearest_swing_low": nearest_swing_low,
        "stop_reference": stop_reference,
    }


# --- Verdict synthesis -------------------------------------------------------


def _newest_triggered(
    checks: dict, week_of_to_idx: dict[str, int]
) -> tuple[str | None, int | None]:
    """The name + index of whichever of the 3 signal detectors triggered
    the MOST RECENT week_of. Ties (two detectors triggering the same week)
    break by _TRIGGER_ORDER (weekly_key_reversal first) -- arbitrary but
    deterministic."""
    best_name: str | None = None
    best_idx: int | None = None
    for name in _TRIGGER_ORDER:
        check = checks[name]
        if not check["triggered"]:
            continue
        idx = week_of_to_idx[check["week_of"]]
        if best_idx is None or idx > best_idx:
            best_idx = idx
            best_name = name
    return best_name, best_idx


def synthesize_verdict(checks: dict, newest_signal_name: str | None) -> tuple[str, str | None]:
    """Fail-closed verdict synthesis (assumes the min-weeks / price-source
    gates have already passed -- callers handle INSUFFICIENT_DATA before
    reaching here).

    - continuation.new_closing_extreme_with_crowd -> NOT_CONFIRMED
      (continuation_intact), regardless of whether a signal also triggered
      (the veto always wins: either no signal existed at all within
      recency, or a signal existed but continuation resumed strictly more
      recently than it -- both cases mean the crowd is still being
      rewarded as of the last completed week).
    - else, any of the 3 signal detectors triggered -> CONFIRMED, with
      verdict_reason naming whichever detector produced the newest
      triggered signal.
    - else -> NOT_CONFIRMED (no_reversal_evidence): absence of evidence
      never confirms.
    """
    if checks["continuation"]["new_closing_extreme_with_crowd"]:
        return "NOT_CONFIRMED", "continuation_intact"
    if newest_signal_name is not None:
        return "CONFIRMED", CHECK_REASON_MAP[newest_signal_name]
    return "NOT_CONFIRMED", "no_reversal_evidence"


def compute_confidence(checks: dict) -> str:
    """HIGH iff >=2 DISTINCT detector types triggered within recency (the
    same detector firing in only one week -- this module never reports
    more than one trigger per detector -- counts once by construction), OR
    a triggered weekly_key_reversal whose new high/low is ALSO an extreme
    of a full (untruncated, >=52-week) extreme-lookback window. Else
    MEDIUM. LOW is reserved, never emitted."""
    distinct_triggered = sum(1 for name in _TRIGGER_ORDER if checks[name]["triggered"])
    if distinct_triggered >= 2:
        return "HIGH"

    kr = checks["weekly_key_reversal"]
    if (
        kr["triggered"]
        and kr.get("is_full_window_extreme")
        and (kr.get("extreme_window_weeks_used") or 0) >= CONFIDENCE_HIGH_EXTREME_WEEKS
    ):
        return "HIGH"
    return "MEDIUM"


# --- Top-level pure orchestrator --------------------------------------------


def run_weekly_price_action(
    daily_bars: list[dict],
    direction: str,
    as_of: str,
    swing_lookback_weeks: int = SWING_LOOKBACK_WEEKS_DEFAULT,
    extreme_lookback_weeks: int = EXTREME_LOOKBACK_WEEKS_DEFAULT,
    signal_recency_weeks: int = SIGNAL_RECENCY_WEEKS_DEFAULT,
    min_weeks: int = MIN_WEEKS_DEFAULT,
) -> dict:
    """Resample, run all 4 checks, and synthesize verdict + confidence +
    swing levels. Pure: no I/O. Callers (the CLI) are responsible for the
    no-price-source INSUFFICIENT_DATA path -- this function assumes
    `daily_bars` already represents a successfully fetched price series (it
    may still be too short, which IS handled here via `min_weeks`).

    Returns: {verdict, verdict_reason, confidence, checks, swing_levels,
    weekly_bars_used, last_completed_week}.

    Invariant: `checks` (and `swing_levels`) is ALWAYS None whenever
    `verdict == "INSUFFICIENT_DATA"` -- never a placeholder dict of
    all-False checks. A downstream consumer (contrarian-setup-gate, #241)
    can rely on this single shape without branching on the specific
    INSUFFICIENT_DATA reason; the CLI's own early-exit INSUFFICIENT_DATA
    paths (no_price_source, detector-json refusal, etc.) follow the same
    rule.
    """
    weekly_bars = resample_weekly(daily_bars, as_of)
    n = len(weekly_bars)
    last_completed_week = weekly_bars[-1]["week_of"] if weekly_bars else None

    if n < min_weeks:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "verdict_reason": "insufficient_weekly_bars",
            "confidence": "MEDIUM",
            "checks": None,
            "swing_levels": None,
            "weekly_bars_used": n,
            "last_completed_week": last_completed_week,
        }

    kr = detect_weekly_key_reversal(
        weekly_bars, direction, swing_lookback_weeks, extreme_lookback_weeks, signal_recency_weeks
    )
    fe = detect_failed_extreme(weekly_bars, direction, extreme_lookback_weeks, signal_recency_weeks)
    fb = detect_failed_breakout(
        weekly_bars, direction, extreme_lookback_weeks, signal_recency_weeks
    )

    week_of_to_idx = {bar["week_of"]: i for i, bar in enumerate(weekly_bars)}
    partial_checks = {"weekly_key_reversal": kr, "failed_extreme": fe, "failed_breakout": fb}
    newest_signal_name, newest_signal_idx = _newest_triggered(partial_checks, week_of_to_idx)

    cont = detect_continuation(
        weekly_bars, direction, extreme_lookback_weeks, signal_recency_weeks, newest_signal_idx
    )

    checks = {**partial_checks, "continuation": cont}

    verdict, reason = synthesize_verdict(checks, newest_signal_name)
    confidence = compute_confidence(checks) if verdict == "CONFIRMED" else "MEDIUM"
    swing_levels = compute_swing_levels(
        weekly_bars, direction, swing_lookback_weeks, extreme_lookback_weeks
    )

    return {
        "verdict": verdict,
        "verdict_reason": reason,
        "confidence": confidence,
        "checks": checks,
        "swing_levels": swing_levels,
        "weekly_bars_used": n,
        "last_completed_week": last_completed_week,
    }
