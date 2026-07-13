#!/usr/bin/env python3
"""Pure news-reaction-failure calculation module (Jason Shapiro contrarian
methodology, step 2: news failure).

No I/O, no network calls — every function takes plain dicts/lists/scalars and
returns plain values so it is trivially unit-testable. See
references/news-failure-patterns.md for the methodology this implements and
references/price-source-map.md for how the CLI (analyze_news_reaction.py)
fetches the price series this module consumes.

Design note (why drift-significance, not a naive failure-ratio): an earlier
design CONFIRMed "news failure" whenever fewer than half the relevant events
"responded" — but under pure noise, P(z < 0.5) ≈ 69% per event, so that rule
CONFIRMed on random noise 48-83% of the time depending on n. This module
instead requires the market to have moved *significantly against* the
crowd's favorable news (a drift-significance test with a Monte-Carlo-verified
null false-positive bound), not merely "not enough with it". See
TestMonteCarloNullBound / TestMonteCarloAr1CorrelatedNull in
tests/test_reaction_math.py for the regression guard on this design.
"""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# --- Thresholds (one block, with rationale + null-rate documentation) ------

# Per-event / per-cluster classification boundary on the direction-adjusted
# 3-day z-score. Symmetric around 0.
Z_THRESHOLD_DEFAULT = 0.5

# Verdict drift-significance threshold. drift_stat = sqrt(n) * mean(adjusted
# zscore_3d); under the iid-N(0,1) null, drift_stat ~ N(0,1). 1.45 was chosen
# (over 1.0/1.28/1.35, all rejected) so the combined null false-CONFIRMED
# rate (drift_stat <= -drift_z AND responded_ratio <= 0.25) stays under 8%
# for n in {3,4,5,8} with real margin (worst measured case ~7.28-7.30%, vs.
# 1.0 -> 13.4-15.8%, 1.28 -> ~9.7-10.0%, 1.35 -> 8.1-8.8%, all of which fail
# the <8% bound). Verified by a seeded >=50,000-trial Monte Carlo test per n
# (see TestMonteCarloNullBound).
#
# Robustness under correlated noise that slips past the clustering rule
# (see cluster_events()) is also verified: at rho=0.1 (lag-1 AR, a
# conservative-but-realistic residual-correlation stress), the null
# CONFIRMED rate stays under 10% (measured 8.08-9.00% across n in
# {3,4,5,8}, worst at n=8; hard-gated by TestMonteCarloAr1CorrelatedNull).
# At an intentionally extreme rho=0.3 stress, the rate rises to
# 10.84-13.11% across the same n -- this is measured and documented as a
# known v1 residual risk, not hard-gated, since it models correlation
# roughly 10x stronger than liquid-futures empirical signed-return
# autocorrelation. Raising --drift-z to 1.75 restores <10% even under the
# rho=0.3 stress, for users who want that margin. See
# references/news-failure-patterns.md for the full writeup.
DRIFT_Z_DEFAULT = 1.45

# Below this many usable relevant event clusters, the verdict is
# INSUFFICIENT_EVIDENCE rather than risking a statistically unsupported call.
MIN_EVENTS_DEFAULT = 3

# CONFIRMED-verdict confidence upgrades to HIGH at a stricter drift_stat
# threshold (98.75th percentile). This never affects the verdict itself.
CONFIDENCE_HIGH_DRIFT_Z = 1.645

# daily_stdev is computed from trailing daily returns ending the day before
# the event. 60 trading days (~3 months) is the intended lookback; if fewer
# than min_samples returns are available (thin history near a listing date,
# or a very small offline test fixture), the event is treated as unusable
# for z-scoring rather than computing a stdev on a handful of noisy points.
DAILY_STDEV_LOOKBACK_DEFAULT = 60
DAILY_STDEV_MIN_SAMPLES_DEFAULT = 20

# Event-clustering independence guard: relevant events whose 3-trading-day
# return windows [effective_date_index, effective_date_index + window - 1]
# share any trading day are collapsed into one cluster (counted once toward
# n). This defends the iid-N(0,1) null the verdict test assumes --
# overlapping windows would otherwise produce correlated z3 values that
# silently inflate n. The window matches compute_returns()'s return_3d span
# (window trading sessions starting at, and including, the effective date).
CLUSTER_WINDOW_DAYS = 3

# Market close cutoff (ET). An event at/after this wall-clock hour counts
# from the next trading day (it couldn't have moved that day's close).
MARKET_CLOSE_HOUR_ET = 16


# --- Price series helpers ---------------------------------------------------


def build_sorted_series(rows: list[dict]) -> list[tuple[str, float]]:
    """Convert raw FMP-shaped price rows into a sorted, deduped (date, close)
    series. Accepts either a `close` field (e.g. the full OHLCV endpoint) or
    a `price` field -- verified live: FMP's
    `stable/historical-price-eod/light` endpoint (used by this skill for
    all price symbols, futures and ETF alike) returns `price`, not `close`,
    despite "close" being the semantically correct name for a daily
    settlement value. Rows missing `date` or both price fields are dropped;
    duplicate dates keep the last occurrence (assumed to be the more
    recently fetched value)."""
    by_date: dict[str, float] = {}
    for row in rows:
        d = row.get("date")
        c = row.get("close", row.get("price"))
        if d is None or c is None:
            continue
        by_date[d] = c
    return sorted(by_date.items())


def find_date_index(series: list[tuple[str, float]], date_str: str) -> int | None:
    """Index of `date_str` in `series`, or None if not present."""
    for i, (d, _) in enumerate(series):
        if d == date_str:
            return i
    return None


# --- Effective-date snapping -------------------------------------------------


def compute_effective_date(event_time_iso: str, trading_dates: list[str]) -> str | None:
    """Snap an event's ISO8601 timestamp to its effective trading date.

    The effective date is the first date in `trading_dates` (any order; not
    required to be sorted) that is on/after the event's calendar date in ET,
    bumped to the next calendar day when the event lands at/after 16:00 ET
    (market close -- it couldn't have moved that day's closing price).
    Weekend/holiday gaps degrade naturally: whatever date isn't in
    `trading_dates` is simply skipped in favor of the next one that is.

    Raises ValueError for a naive (timezone-unaware) or unparsable
    `event_time_iso` -- callers should catch this and drop the event with a
    reason rather than guessing at an implicit timezone.
    """
    try:
        dt = datetime.fromisoformat(event_time_iso)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unparsable event_time {event_time_iso!r}: {exc}") from exc
    if dt.tzinfo is None:
        raise ValueError(
            f"event_time must be timezone-aware; got naive datetime {event_time_iso!r}. "
            "Use an explicit UTC offset, e.g. '...-04:00'."
        )
    et_dt = dt.astimezone(ET)
    target_date = et_dt.date()
    if et_dt.hour >= MARKET_CLOSE_HOUR_ET:
        target_date = target_date.fromordinal(target_date.toordinal() + 1)
    target_str = target_date.isoformat()
    candidates = sorted(d for d in trading_dates if d >= target_str)
    return candidates[0] if candidates else None


# --- Returns -----------------------------------------------------------------


def compute_returns(series: list[tuple[str, float]], effective_date: str) -> dict:
    """close(eff + k - 1 trading days) / close(eff - 1 trading day) - 1, for
    k in {1, 3}, as fractions (e.g. 0.02 for +2%) -- a true k-trading-session
    return: the k sessions starting at and including the effective date
    itself, against the close the day before. For k=1 that's just
    close(eff)/close(eff-1); for k=3 it's close(eff+2)/close(eff-1) (the
    3 sessions eff, eff+1, eff+2). Returns None for a horizon when the
    effective date isn't in the series, has no prior bar (it's the first
    row), or lacks enough forward bars for that horizon (return_1d never
    needs a forward bar, since its own session IS the effective date).
    """
    idx = find_date_index(series, effective_date)
    if idx is None or idx < 1:
        return {"return_1d": None, "return_3d": None}
    pre_close = series[idx - 1][1]
    result: dict = {}
    for k, key in ((1, "return_1d"), (3, "return_3d")):
        post_idx = idx + k - 1
        if post_idx >= len(series) or not pre_close:
            result[key] = None
        else:
            post_close = series[post_idx][1]
            result[key] = post_close / pre_close - 1
    return result


def compute_daily_stdev(
    series: list[tuple[str, float]],
    effective_date: str,
    lookback: int = DAILY_STDEV_LOOKBACK_DEFAULT,
    min_samples: int = DAILY_STDEV_MIN_SAMPLES_DEFAULT,
) -> float | None:
    """Sample stdev of trailing daily returns, ending the day before the
    event (i.e. using bars up to index eff-1). Returns None if the effective
    date isn't in the series or fewer than `min_samples` daily returns are
    available in the lookback window.
    """
    idx = find_date_index(series, effective_date)
    if idx is None or idx < 2:
        return None
    end_idx = idx - 1  # last bar included: the day before the event
    start_idx = max(1, end_idx - lookback + 1)
    daily_returns = []
    for i in range(start_idx, end_idx + 1):
        prev_close = series[i - 1][1]
        cur_close = series[i][1]
        if not prev_close:
            continue
        daily_returns.append(cur_close / prev_close - 1)
    if len(daily_returns) < min_samples:
        return None
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    return math.sqrt(variance)


# --- Z-scores ------------------------------------------------------------


def compute_zscore_1d(return_1d: float | None, daily_stdev: float | None) -> float | None:
    """zscore_1d = return_1d / daily_stdev. No horizon scaling."""
    if return_1d is None or not daily_stdev:
        return None
    return return_1d / daily_stdev


def compute_zscore_3d(return_3d: float | None, daily_stdev: float | None) -> float | None:
    """zscore_3d = return_3d / (daily_stdev * sqrt(3)). The sqrt(3) horizon
    scaling is mandatory (a 3-day return's noise scales with sqrt(horizon)
    under a random-walk assumption); see
    TestComputeZscores.test_zscore_3d_sqrt3_scaling_pinned for a
    hand-computed regression pin.
    """
    if return_3d is None or not daily_stdev:
        return None
    return return_3d / (daily_stdev * math.sqrt(3))


def direction_adjusted_zscore(zscore: float | None, direction: str) -> float | None:
    """Flip sign for CROWDED_SHORT so that a positive adjusted z-score
    always means "the market moved in the direction that rewards the
    crowd" -- for CROWDED_LONG that's a positive raw return (rally, sign
    unchanged); for CROWDED_SHORT that's a negative raw return (sell-off,
    sign flipped)."""
    if zscore is None:
        return None
    sign = 1.0 if direction == "CROWDED_LONG" else -1.0
    return zscore * sign


def expected_direction_for(direction: str) -> str:
    """CROWDED_LONG needs bullish news to reward the crowd; CROWDED_SHORT
    needs bearish news."""
    return "BULLISH" if direction == "CROWDED_LONG" else "BEARISH"


# --- Per-event / per-cluster classification --------------------------------


def classify_reaction(adjusted_zscore_3d: float, z_threshold: float = Z_THRESHOLD_DEFAULT) -> str:
    """Descriptive label for a direction-adjusted zscore_3d value.

    RESPONDED: the market moved far enough to reward the crowd (news
    "worked"). OPPOSITE: the market moved far enough against the crowd
    (evidence of news failure). FAILED_TO_RESPOND: neither, inside the
    threshold band. Boundaries are inclusive on both sides.
    """
    if adjusted_zscore_3d >= z_threshold:
        return "RESPONDED"
    if adjusted_zscore_3d <= -z_threshold:
        return "OPPOSITE"
    return "FAILED_TO_RESPOND"


# --- Event clustering (independence guard) ----------------------------------


def cluster_events(events: list[dict], window: int = CLUSTER_WINDOW_DAYS) -> list[dict]:
    """Collapse relevant events whose [effective_date_index,
    effective_date_index + window - 1] 3-trading-day return windows overlap
    into one cluster, counted once.

    `events`: list of dicts, each with at least `event_id` (str),
    `effective_date` (str), `effective_date_index` (int), and
    `zscore_3d_adjusted` (float, already direction-adjusted).

    Overlap is transitive: a chain of events each overlapping the next all
    collapse into a single cluster even if the first and last don't overlap
    each other directly (standard interval-merge semantics).

    Pinned rule: a cluster's z3 is the z3 already computed at the cluster's
    OWN effective date -- the earliest member's window z3. Member z3 values
    are never averaged into the cluster's contribution to drift_stat; they
    are only recorded (in `cluster_members`) for transparency. Averaging
    would mix z-scores computed over different, overlapping windows, which
    is a different (and not obviously more correct) statistic than "what
    happened in the window starting at the cluster's own effective date."

    Returns clusters sorted by earliest effective_date_index, each:
    {"effective_date_index", "effective_date" (of the earliest member),
     "zscore_3d_adjusted" (the earliest member's own z3, NOT averaged),
     "cluster_members": [{"event_id", "zscore_3d_adjusted"}, ...]}.
    """
    if not events:
        return []
    ordered = sorted(events, key=lambda e: e["effective_date_index"])
    clusters: list[list[dict]] = []
    current = [ordered[0]]
    current_end = ordered[0]["effective_date_index"] + window - 1
    for ev in ordered[1:]:
        if ev["effective_date_index"] <= current_end:
            current.append(ev)
            current_end = max(current_end, ev["effective_date_index"] + window - 1)
        else:
            clusters.append(current)
            current = [ev]
            current_end = ev["effective_date_index"] + window - 1
    clusters.append(current)
    return [_finalize_cluster(members) for members in clusters]


def _finalize_cluster(members: list[dict]) -> dict:
    earliest = min(members, key=lambda e: e["effective_date_index"])
    ordered_members = sorted(members, key=lambda e: e["effective_date_index"])
    return {
        "effective_date_index": earliest["effective_date_index"],
        "effective_date": earliest["effective_date"],
        # Pinned rule: the cluster's z3 is the earliest member's OWN window
        # z3 -- not a mean across members (see cluster_events() docstring).
        "zscore_3d_adjusted": earliest["zscore_3d_adjusted"],
        "cluster_members": [
            {"event_id": m["event_id"], "zscore_3d_adjusted": m["zscore_3d_adjusted"]}
            for m in ordered_members
        ],
    }


# --- Verdict synthesis -------------------------------------------------------


def synthesize_verdict(
    n: int,
    drift_stat: float | None,
    responded_ratio: float | None,
    min_events: int = MIN_EVENTS_DEFAULT,
    drift_z: float = DRIFT_Z_DEFAULT,
) -> tuple[str, str | None]:
    """Fail-closed 3-value verdict. Returns (verdict, reason); reason is
    None for CONFIRMED and for the INSUFFICIENT_EVIDENCE min-events case
    (the low n is self-explanatory), otherwise a short machine-readable tag.

    CONFIRMED and the explicit NOT_CONFIRMED condition below are mutually
    exclusive by construction (drift_z > 0 makes `drift_stat <= -drift_z`
    and `drift_stat >= +drift_z` disjoint; 0.25 < 0.5 makes the
    responded_ratio conditions disjoint too), so check order doesn't hide
    an ambiguous case.
    """
    if n < min_events:
        return "INSUFFICIENT_EVIDENCE", "insufficient_relevant_events"
    if drift_stat <= -drift_z and responded_ratio <= 0.25:
        return "CONFIRMED", None
    if drift_stat >= drift_z or responded_ratio >= 0.5:
        return "NOT_CONFIRMED", "market_rewarded_crowd"
    return "NOT_CONFIRMED", "mixed_reactions"


def compute_confidence(verdict: str, drift_stat: float | None, n: int, opposite_count: int) -> str:
    """HIGH iff verdict is CONFIRMED AND drift_stat <= -1.645 AND n >= 4 AND
    at least one clustered event classified OPPOSITE; MEDIUM otherwise. LOW
    is reserved for future use and is never emitted in v1."""
    if (
        verdict == "CONFIRMED"
        and drift_stat is not None
        and drift_stat <= -CONFIDENCE_HIGH_DRIFT_Z
        and n >= 4
        and opposite_count >= 1
    ):
        return "HIGH"
    return "MEDIUM"


def derive_actual_reaction(verdict: str, direction: str, responded_ratio: float | None) -> str:
    """Top-level `actual_reaction` field per the issue's output contract.

    CONFIRMED -> FAILED_TO_RALLY (long) / FAILED_TO_SELL_OFF (short).
    NOT_CONFIRMED with responded_ratio >= 0.5 -> RALLIED / SOLD_OFF (market
    clearly rewarded the crowd). Other NOT_CONFIRMED -> MIXED_REACTION.
    INSUFFICIENT_EVIDENCE -> NO_DATA regardless of direction.
    """
    if verdict == "INSUFFICIENT_EVIDENCE":
        return "NO_DATA"
    is_long = direction == "CROWDED_LONG"
    if verdict == "CONFIRMED":
        return "FAILED_TO_RALLY" if is_long else "FAILED_TO_SELL_OFF"
    if responded_ratio is not None and responded_ratio >= 0.5:
        return "RALLIED" if is_long else "SOLD_OFF"
    return "MIXED_REACTION"


# --- Top-level pure orchestrator --------------------------------------------


def synthesize_result(
    usable_events: list[dict],
    direction: str,
    min_events: int = MIN_EVENTS_DEFAULT,
    drift_z: float = DRIFT_Z_DEFAULT,
    z_threshold: float = Z_THRESHOLD_DEFAULT,
) -> dict:
    """Cluster usable relevant events and compute the full verdict, confidence,
    and actual_reaction. Pure: no I/O.

    `usable_events` must already be filtered to RELEVANT events
    (expected_impact == expected_direction_for(direction)) with usable price
    data; each needs `event_id`, `effective_date`, `effective_date_index`,
    `zscore_3d_adjusted` (direction-adjusted). Events with unusable price
    data must be dropped by the caller before this function is called.

    Returns: {clusters, n, mean_z3, drift_stat, responded_ratio, verdict,
    verdict_reason, confidence, actual_reaction}.
    """
    clusters = cluster_events(usable_events)
    n = len(clusters)
    if n == 0:
        mean_z3 = None
        drift_stat = None
        responded_ratio = None
        opposite_count = 0
    else:
        mean_z3 = sum(c["zscore_3d_adjusted"] for c in clusters) / n
        drift_stat = math.sqrt(n) * mean_z3
        cluster_classes = [
            classify_reaction(c["zscore_3d_adjusted"], z_threshold) for c in clusters
        ]
        responded_ratio = cluster_classes.count("RESPONDED") / n
        opposite_count = cluster_classes.count("OPPOSITE")

    verdict, reason = synthesize_verdict(n, drift_stat, responded_ratio, min_events, drift_z)
    confidence = compute_confidence(verdict, drift_stat, n, opposite_count)
    actual_reaction = derive_actual_reaction(verdict, direction, responded_ratio)

    return {
        "clusters": clusters,
        "n": n,
        "mean_z3": mean_z3,
        "drift_stat": drift_stat,
        "responded_ratio": responded_ratio,
        "verdict": verdict,
        "verdict_reason": reason,
        "confidence": confidence,
        "actual_reaction": actual_reaction,
    }
