#!/usr/bin/env python3
"""
FTD Detector - Rally Tracker (stateful forward replay)

Replays the supplied history oldest to newest, one session at a time, carrying
state. State changes only on defined events, so a bar's meaning never depends
on how many sessions happen to be in a window, and a confirmed FTD stays
confirmed until a defined event ends it.

Phases (reported through the unchanged ``MarketState`` values):
  uptrend_or_none -> NO_SIGNAL      no qualifying correction known
  correction      -> CORRECTION, or RALLY_FAILED / FTD_INVALIDATED when the
                     correction was (re-)entered by that event; the label lasts
                     until the next Day 1 (only an FTD leaves the correction)
  rally           -> RALLY_ATTEMPT (day 1-3) or FTD_WINDOW (day 4 onward)
  confirmed       -> FTD_CONFIRMED (additive ``cycle.uptrend_status``)

Rules (O'Neil / IBD):
- Correction: close >= 3% below the highest close with 3+ down closes since it.
- Day 1: first up close (or a close in the top 50% of a valid high-low range,
  including on a session that sets a new closing low).
- Rally failure: an intraday low strictly below the attempt's reference low,
  the lowest intraday low of the pullback segment the attempt started from
  (frozen on Day 1, Day 1 bar included). A segment starts at the correction
  entry and restarts at a rally failure and an FTD invalidation. Equality holds.
- FTD: Day 4 or later, gain >= 1.25% vs the previous close, volume above the
  previous session. Day 4-10 is the normal window; there is no upper limit,
  and a later FTD is flagged ``late``. An attempt ends only by an undercut of
  its reference low (rally failure) or by an FTD; a failed attempt may be
  restarted in the same correction.
- A confirmed uptrend goes under pressure at 5+ active distribution days, a
  close below the 50-session SMA or the first close below the FTD-day low. It
  ends with a new correction measured from the post-FTD peak on 6+ active
  distribution days with a close below the 21-session EMA, or on a 10% drawdown
  from that peak, or with FTD_INVALIDATED if the rally low breaks.

Data gaps (issue #655): a missing or non-finite close/volume/low is never read
as 0 and bars are never dropped (the replay compares positionally adjacent
sessions, so dropping a bar can fabricate an FTD). When bad bars exist, only
the clean suffix after the last bad bar is replayed, and only if it holds at
least MIN_REPLAY_SESSIONS bars; otherwise the result is NO_SIGNAL with
``data_gap: True`` and an ``error`` naming the gap.
"""

import copy
from enum import Enum

from _price_bars import find_bar_gaps, read_price
from ftd_lifecycle import assess_lifecycle


class MarketState(Enum):
    NO_SIGNAL = "NO_SIGNAL"
    CORRECTION = "CORRECTION"
    RALLY_ATTEMPT = "RALLY_ATTEMPT"
    FTD_WINDOW = "FTD_WINDOW"
    FTD_CONFIRMED = "FTD_CONFIRMED"
    RALLY_FAILED = "RALLY_FAILED"
    FTD_INVALIDATED = "FTD_INVALIDATED"


# Minimum correction depth to qualify
MIN_CORRECTION_PCT = 3.0
# Minimum down days during correction
MIN_DOWN_DAYS = 3
# FTD window bounds (inclusive)
FTD_DAY_START = 4
FTD_DAY_END = 10
# Minimum FTD gain thresholds
FTD_GAIN_MINIMUM = 1.25
FTD_GAIN_RECOMMENDED = 1.5
FTD_GAIN_STRONG = 2.0

# Confirmed uptrend -> under pressure -> correction. The distribution-day
# definition matches ibd-distribution-day-monitor. The counts, averages and the
# drawdown below are uncalibrated model choices, not verified IBD rules.
DD_MIN_DECLINE_PCT = 0.2
DD_EXPIRY_SESSIONS = 25
DD_RALLY_EXPIRY_PCT = 5.0
DD_PRESSURE_COUNT = 5  # active distribution days that put the uptrend under pressure
DD_CORRECTION_COUNT = 6  # active distribution days that, with a close < EMA, end it
PRESSURE_SMA = 50  # session count of the simple moving average of closes
CORRECTION_EMA = 21  # session count of the exponential moving average of closes
DEEP_CORRECTION_PCT = 10.0  # drawdown from the post-FTD peak close that ends it

# Display window for lookback_high / correction_depth_pct, and the minimum
# clean replay length once a data gap forces a restart.
ANALYSIS_LOOKBACK = 60
MIN_REPLAY_SESSIONS = 60
CLOSE_VOLUME = ("close", "volume")
REPLAY_FIELDS = ("close", "volume", "low")
REFERENCE_BASIS = "intraday low below the rally low"


def bar_gaps(bars: list[dict], required: tuple = CLOSE_VOLUME) -> dict:
    """Gap report for a chronological slice.

    Volume 0 is invalid here: for the indices this skill reads (^GSPC, QQQ) a
    zero session volume is provider missing data, and treating it as real can
    hide a distribution day or an invalidated FTD.
    """
    return find_bar_gaps(bars, required, order="chronological")


def gap_reason(gaps: dict, where: str) -> str:
    """Human-readable data-gap reason for a find_bar_gaps report."""
    return (
        f"Data gap: {gaps['bad_bars']} bar(s) with missing or invalid "
        f"{'/'.join(gaps['required'])} {where} (latest bad: {gaps['latest_bad']})"
    )


def window_quality(gaps: dict) -> dict:
    """Compact data-quality summary of a find_bar_gaps report for the JSON output."""
    return {
        "window_sessions": gaps["checked_bars"],
        "bad_bars": gaps["bad_bars"],
        "bad_dates": gaps["bad_dates"],
        "latest_bad": gaps["latest_bad"],
        "required": gaps["required"],
    }


# Float tolerance for inclusive percentage thresholds: 104.00 -> 105.30 is
# exactly +1.25% but computes as 1.2499999999999973.
_PCT_EPS = 1e-9


def _at_least(value: float, threshold: float) -> bool:
    """Inclusive threshold test that ignores float representation noise."""
    return value >= threshold - _PCT_EPS


def _upper_half(bar: dict) -> bool:
    """Close in the top 50% of a valid high-low range (needs a real high and low)."""
    high = read_price(bar, "high")
    low = read_price(bar, "low")
    if high is None or low is None or high - low <= 0:
        return False
    return (bar["close"] - low) / (high - low) >= 0.5


def _empty_ftd() -> dict:
    return {
        "ftd_detected": False,
        "ftd_day_number": None,
        "late": False,
        "ftd_date": None,
        "ftd_price": None,
        "ftd_low": None,
        "gain_pct": None,
        "volume": None,
        "prev_day_volume": None,
        "volume_above_avg": None,
        "gain_tier": None,
        "_ftd_idx": None,
    }


def _round4(value):
    return None if value is None else round(value, 4)


def _public(ftd: dict) -> dict:
    return {key: value for key, value in ftd.items() if not key.startswith("_")}


class _Replay:
    """Forward replay of one chronological, gap-free bar sequence."""

    def __init__(self, history: list[dict], start: int):
        self.h = history
        self.start = start
        self.phase = "uptrend_or_none"
        self.label = None  # CORRECTION / RALLY_FAILED / FTD_INVALIDATED in correction
        self.peak_close = history[start]["close"]
        self.peak_idx = start
        self.down_count = 0
        self.low_close = None
        self.low_idx = None
        self.seg_low = None  # lowest intraday low since the segment start
        self.seg_low_idx = None
        self.ref_low = None  # the attempt's rally-failure reference, frozen on Day 1
        self.ref_low_idx = None
        self.attempt = None
        self.failures = 0
        self.prior_events = []
        self.day = 0
        self.ftd = None
        self.ftd_idx = None
        self.ftd_ref_low = None
        self.ftd_ref_low_idx = None
        self.ftd_low_close = None
        self.ftd_low_idx = None
        self.pre_ftd_peak = None
        self.pre_ftd_peak_idx = None
        self.dds = []
        self.previous_ftd = None
        self.last_transition = None
        self.status = None
        self.pressure_reasons = []
        self.ftd_low_breached = False
        self.regained_sma = False  # closed above the 50-session SMA since the FTD bar
        self.ema = self._ema_series()

    # -- helpers ---------------------------------------------------------
    def _date(self, idx):
        return self.h[idx].get("date", "N/A")

    def _ema_series(self):
        """EMA of closes seeded with the SMA of the first CORRECTION_EMA replay closes.

        Each value uses closes up to its own bar only (point in time); ``None``
        until CORRECTION_EMA bars exist since the replay start.
        """
        out = [None] * len(self.h)
        first = self.start + CORRECTION_EMA - 1
        if first >= len(self.h):
            return out
        k = 2 / (CORRECTION_EMA + 1)
        value = sum(self.h[i]["close"] for i in range(self.start, first + 1)) / CORRECTION_EMA
        out[first] = value
        for i in range(first + 1, len(self.h)):
            value = self.h[i]["close"] * k + value * (1 - k)
            out[i] = value
        return out

    def sma(self, t):
        """SMA of the last PRESSURE_SMA closes ending at t, or None if too few bars."""
        if t - self.start + 1 < PRESSURE_SMA:
            return None
        return sum(self.h[i]["close"] for i in range(t - PRESSURE_SMA + 1, t + 1)) / PRESSURE_SMA

    def _transition(self, t, new_phase, reason):
        self.last_transition = {
            "date": self._date(t),
            "from": self.phase,
            "to": new_phase,
            "reason": reason,
        }
        self.phase = new_phase

    def run(self, on_bar=None):
        """Replay every bar; ``on_bar(replay, idx)`` sees the state after each one."""
        if on_bar:
            on_bar(self, self.start)
        for t in range(self.start + 1, len(self.h)):
            getattr(self, f"_step_{self.phase.split('_')[0]}")(t)
            if on_bar:
                on_bar(self, t)
        return self

    # -- uptrend_or_none ---------------------------------------------------
    def _step_uptrend(self, t):
        close = self.h[t]["close"]
        if close > self.peak_close:
            self.peak_close, self.peak_idx, self.down_count = close, t, 0
        elif close < self.h[t - 1]["close"]:
            self.down_count += 1
        if self._qualifies(close):
            self._enter_correction(t, "correction qualified")

    def _qualifies(self, close):
        return (
            close <= self.peak_close * (1 - MIN_CORRECTION_PCT / 100)
            and self.down_count >= MIN_DOWN_DAYS
        )

    def _enter_correction(self, t, reason, allow_day1=True):
        self.low_close = self.seg_low = None
        self.ref_low = self.ref_low_idx = None
        for k in range(self.peak_idx, t + 1):
            bar = self.h[k]
            if self.low_close is None or bar["close"] < self.low_close:
                self.low_close, self.low_idx = bar["close"], k
            if self.seg_low is None or bar["low"] < self.seg_low:
                self.seg_low, self.seg_low_idx = bar["low"], k
        self._transition(t, "correction", reason)
        self.label = MarketState.CORRECTION.value
        self.attempt = None
        self.failures = 0
        self.prior_events = []
        self.ftd = None
        self.status = None
        # A session that sets the closing low may itself be Day 1 (upper-half close),
        # except the bar that ends a confirmed uptrend: like a failure bar, never Day 1.
        if allow_day1 and self.low_idx == t and _upper_half(self.h[t]):
            self._start_day1(t)

    # -- correction ----------------------------------------------------------
    def _step_correction(self, t):
        bar = self.h[t]
        close = bar["close"]
        if bar["low"] < self.seg_low:
            self.seg_low, self.seg_low_idx = bar["low"], t
        # Only an FTD leaves a correction: a rise above the old peak does not.
        if close < self.low_close:
            self.low_close, self.low_idx = close, t
            if _upper_half(bar):
                self._start_day1(t)
            return
        if close > self.h[t - 1]["close"] or _upper_half(bar):
            self._start_day1(t)

    def _start_day1(self, t):
        bar = self.h[t]
        self._transition(t, "rally", "Day 1")
        self.ftd = None
        self.day = 1
        # Freeze the attempt's reference: the low of the pullback it started from,
        # including the Day 1 bar. It never changes while the attempt is active.
        self.ref_low, self.ref_low_idx = self.seg_low, self.seg_low_idx
        self.attempt = {
            "day1_idx": t,
            "day1_date": self._date(t),
            "day1_low": bar["low"],
            "current_day_count": 1,
            "rally_days": [
                {
                    "day": 1,
                    "idx": t,
                    "date": self._date(t),
                    "close": bar["close"],
                    "volume": bar["volume"],
                }
            ],
            "invalidated": False,
            "invalidation_reason": None,
            "reset_count": self.failures,
            "prior_ftd_events": list(self.prior_events),
        }

    # -- rally -----------------------------------------------------------------
    def _step_rally(self, t):
        bar, prev = self.h[t], self.h[t - 1]
        close = bar["close"]
        self.day += 1
        self.attempt["current_day_count"] = self.day
        if bar["low"] < self.ref_low:
            self.attempt.update(
                invalidated=True,
                invalidation_reason=(
                    f"Intraday low ${bar['low']:.2f} below rally low "
                    f"${self.ref_low:.2f} on {self._date(t)}"
                ),
            )
            self._fail(t, MarketState.RALLY_FAILED, "rally failed: rally low undercut")
            return
        if close < self.low_close:  # a lower close that holds the reference moves the closing low
            self.low_close, self.low_idx = close, t
        gain = (close - prev["close"]) / prev["close"] * 100
        change_pct = round(gain, 2)
        self.attempt["rally_days"].append(
            {
                "day": self.day,
                "idx": t,
                "date": self._date(t),
                "close": close,
                "volume": bar["volume"],
                "change_pct": change_pct,
                "volume_vs_prev": (
                    round((bar["volume"] / prev["volume"] - 1) * 100, 1)
                    if prev["volume"] > 0
                    else 0
                ),
            }
        )
        # No upper day limit: the attempt lasts until the rally low is undercut or an
        # FTD confirms. Day 4-10 is the normal window; a later FTD is flagged late.
        if (
            self.day >= FTD_DAY_START
            and _at_least(gain, FTD_GAIN_MINIMUM)
            and bar["volume"] > prev["volume"] > 0
        ):
            self._confirm(t, gain)

    def _fail(self, t, label, reason):
        """Re-enter the correction phase after an undercut; the bar is never Day 1."""
        self.failures += 1
        self._restart_segment(t)
        self._transition(t, "correction", reason)
        self.label = label.value

    def _restart_segment(self, t):
        """A new pullback segment starts at bar t (inclusive): rally failure or FTD invalidation."""
        bar = self.h[t]
        self.seg_low, self.seg_low_idx = bar["low"], t
        self.low_close, self.low_idx = bar["close"], t

    def _confirm(self, t, gain):
        bar = self.h[t]
        change_pct = round(gain, 2)
        lookback = [read_price(b, "volume") for b in self.h[max(self.start, t - 50) : t]]
        lookback = [v for v in lookback if v is not None]
        pit_avg = sum(lookback) / len(lookback) if lookback else 0
        if _at_least(gain, FTD_GAIN_STRONG):
            tier = "strong"
        elif _at_least(gain, FTD_GAIN_RECOMMENDED):
            tier = "recommended"
        else:
            tier = "minimum"
        self.ftd = {
            "ftd_detected": True,
            "ftd_day_number": self.day,
            "late": self.day > FTD_DAY_END,
            "ftd_date": self._date(t),
            "ftd_price": bar["close"],
            "ftd_low": bar["low"],
            "gain_pct": change_pct,
            "volume": bar["volume"],
            "prev_day_volume": self.h[t - 1]["volume"],
            "volume_above_avg": bar["volume"] > pit_avg if pit_avg > 0 else None,
            "gain_tier": tier,
            "_ftd_idx": t,
        }
        self.ftd_idx = t
        self.ftd_ref_low, self.ftd_ref_low_idx = self.ref_low, self.ref_low_idx
        self.ftd_low_close, self.ftd_low_idx = self.low_close, self.low_idx
        self.pre_ftd_peak, self.pre_ftd_peak_idx = self.peak_close, self.peak_idx
        self.peak_close, self.peak_idx = bar["close"], t
        self.dds = []
        self.status = "confirmed"
        self.pressure_reasons = []
        self.ftd_low_breached = False
        self.regained_sma = False  # closed above the 50-session SMA since the FTD bar
        self._transition(t, "confirmed", f"FTD on Day {self.day}")
        self._update_status(t)

    # -- confirmed -------------------------------------------------------------
    def _step_confirmed(self, t):
        bar, prev = self.h[t], self.h[t - 1]
        close = bar["close"]
        if bar["low"] < self.ref_low:  # (b) wins when several triggers apply
            if close > self.peak_close:
                self.peak_close, self.peak_idx = close, t
            self._invalidate_ftd(t)
            return
        if close > self.peak_close:
            self.peak_close, self.peak_idx = close, t
        high = read_price(bar, "high") or close
        for dd in self.dds:
            if dd["active"] and (
                t - dd["idx"] > DD_EXPIRY_SESSIONS
                or high >= dd["close"] * (1 + DD_RALLY_EXPIRY_PCT / 100)
            ):
                dd["active"] = False
        if (
            close <= prev["close"] * (1 - DD_MIN_DECLINE_PCT / 100)
            and bar["volume"] > prev["volume"]
        ):
            self.dds.append(
                {
                    "idx": t,
                    "date": self._date(t),
                    "close": close,
                    "change_pct": round((close / prev["close"] - 1) * 100, 2),
                    "active": True,
                }
            )
        active = len(self.active_dds())
        ema = self.ema[t]
        if active >= DD_CORRECTION_COUNT and ema is not None and close < ema:
            self._end_uptrend(t, "distribution")
        elif close <= self.peak_close * (1 - DEEP_CORRECTION_PCT / 100):
            self._end_uptrend(t, "deep_drawdown")
        else:
            self._update_status(t)

    def _update_status(self, t):
        """confirmed <-> under_pressure.

        Pressure causes: 5+ active distribution days, a close below the 50-session
        SMA (only once the index has closed above it since the FTD bar, that bar
        included), and the first close below the FTD-day low (a warning only, #765).
        The return needs <= 4 active distribution days and a close above the SMA; the
        FTD-day-low breach alone does not keep the status under pressure.
        """
        close = self.h[t]["close"]
        active = len(self.active_dds())
        sma = self.sma(t)
        if sma is not None and close > sma:
            self.regained_sma = True
        causes = []
        if active >= DD_PRESSURE_COUNT:
            causes.append("distribution")
        if self.regained_sma and sma is not None and close < sma:
            causes.append("below_50sma")
        if not self.ftd_low_breached and close < self.ftd["ftd_low"]:
            self.ftd_low_breached = True  # one-shot, like the lifecycle warning
            causes.append("ftd_low_close_breach")
        if self.status == "confirmed":
            if causes:
                self.status = "under_pressure"
                self.pressure_reasons = causes
        elif active < DD_PRESSURE_COUNT and sma is not None and close > sma:
            self.status = "confirmed"
            self.pressure_reasons = []
        else:
            kept = [r for r in self.pressure_reasons if r == "ftd_low_close_breach"]
            self.pressure_reasons = causes + [r for r in kept if r not in causes]
            if not self.pressure_reasons:
                self.pressure_reasons = ["awaiting_recovery"]  # causes cleared, return test not met

    def _end_uptrend(self, t, reason):
        self.previous_ftd = {
            "ftd": _public(self.ftd),
            "end_reason": reason,
            "end_date": self._date(t),
        }
        self._enter_correction(t, f"confirmed uptrend ended: {reason}", allow_day1=False)
        self.dds = []

    def active_dds(self):
        return [dd for dd in self.dds if dd["active"]]

    def _invalidate_ftd(self, t):
        bar = self.h[t]
        self.prior_events.append(
            {
                "ftd": _public(self.ftd),
                "status": "FTD_INVALIDATED",
                "day1_date": self.attempt["day1_date"],
                "day1_low": self.attempt["day1_low"],
                "failure_date": self._date(t),
                "reason": REFERENCE_BASIS,
            }
        )
        self.attempt.update(
            invalidated=True,
            invalidation_reason=(
                f"Intraday low ${bar['low']:.2f} below rally low "
                f"${self.ref_low:.2f} on {self._date(t)}"
            ),
        )
        if self.pre_ftd_peak >= self.peak_close:
            self.peak_close, self.peak_idx = self.pre_ftd_peak, self.pre_ftd_peak_idx
        self._fail(t, MarketState.FTD_INVALIDATED, "FTD invalidated: rally low undercut")
        self.status = None
        self.dds = []

    # -- output ----------------------------------------------------------------
    def state(self) -> MarketState:
        if self.phase == "uptrend_or_none":
            return MarketState.NO_SIGNAL
        if self.phase == "confirmed":
            return MarketState.FTD_CONFIRMED
        if self.phase == "rally":
            if self.attempt["current_day_count"] < FTD_DAY_START:
                return MarketState.RALLY_ATTEMPT
            return MarketState.FTD_WINDOW
        return MarketState(self.label)

    def market_status(self):
        """IBD tier: confirmed_uptrend, uptrend_under_pressure, market_in_correction, None."""
        if self.phase == "confirmed":
            return "confirmed_uptrend" if self.status == "confirmed" else "uptrend_under_pressure"
        if self.phase == "uptrend_or_none":
            return None  # warm-up: no qualifying correction since the replay start
        return "market_in_correction"

    def swing_low(self):
        if self.phase == "uptrend_or_none":
            return None
        h = self.h
        if self.ftd is not None:  # confirmed or FTD_INVALIDATED: the low the FTD rallied from
            high_close, high_idx = self.pre_ftd_peak, self.pre_ftd_peak_idx
            low_close, low_idx = self.ftd_low_close, self.ftd_low_idx
        else:
            high_close, high_idx = self.peak_close, self.peak_idx
            low_close, low_idx = self.low_close, self.low_idx
        down_days = sum(
            1 for k in range(high_idx + 1, low_idx + 1) if h[k]["close"] < h[k - 1]["close"]
        )
        return {
            "swing_low_idx": low_idx,
            "swing_low_price": low_close,
            "swing_low_date": self._date(low_idx),
            "swing_low_low": h[low_idx]["low"],
            "recent_high_price": high_close,
            "recent_high_idx": high_idx,
            "recent_high_date": self._date(high_idx),
            "decline_pct": round((low_close - high_close) / high_close * 100, 2),
            "down_days": down_days,
        }

    def rally_attempt(self, state: MarketState):
        attempt = copy.deepcopy(
            self.attempt
            or {
                "day1_idx": None,
                "day1_date": None,
                "day1_low": None,
                "current_day_count": 0,
                "rally_days": [],
                "invalidated": False,
                "invalidation_reason": None,
                "reset_count": self.failures,
                "prior_ftd_events": list(self.prior_events),
            }
        )
        if self.phase == "correction":
            attempt["reset_count"] = self.failures
            attempt["prior_ftd_events"] = list(self.prior_events)
        if state in (MarketState.FTD_CONFIRMED, MarketState.FTD_INVALIDATED):
            ref, ref_idx = self.ftd_ref_low, self.ftd_ref_low_idx
        elif self.ref_low is not None:
            ref, ref_idx = self.ref_low, self.ref_low_idx
        else:  # correction without an attempt: the low of the current pullback so far
            ref, ref_idx = self.seg_low, self.seg_low_idx
        attempt["reference_low"] = ref
        attempt["reference_low_date"] = self._date(ref_idx) if ref_idx is not None else None
        attempt["reference_basis"] = REFERENCE_BASIS
        return attempt

    def cycle(self, replay_sessions, restarted):
        confirmed = self.phase == "confirmed"
        return {
            "phase": self.phase,
            "uptrend_status": self.status if confirmed else None,
            "pressure_reasons": list(self.pressure_reasons) if confirmed else [],
            "regained_50sma_since_ftd": self.regained_sma if confirmed else None,
            "active_distribution_days": [
                {"date": d["date"], "close": d["close"], "change_pct": d["change_pct"]}
                for d in self.active_dds()
            ]
            if confirmed
            else [],
            "post_ftd_peak_close": self.peak_close if confirmed else None,
            "post_ftd_peak_date": self._date(self.peak_idx) if confirmed else None,
            "last_transition": self.last_transition,
            "previous_ftd": copy.deepcopy(self.previous_ftd),
            "indicators": {
                "sma50": _round4(self.sma(len(self.h) - 1)),
                "sma50_available": self.sma(len(self.h) - 1) is not None,
                "ema21": _round4(self.ema[-1]),
                "ema21_available": self.ema[-1] is not None,
            },
            "replay_start_date": self._date(self.start),
            "replay_sessions": replay_sessions,
            "restarted_after_gap": restarted,
        }


def analyze_single_index(history: list[dict], index_name: str) -> dict:
    """
    Run full FTD analysis for a single index by replaying its whole history.

    Args:
        history: Daily OHLCV in chronological order (oldest first)
        index_name: Label (e.g., "S&P 500", "NASDAQ")

    Returns:
        Complete analysis dict for this index. ``data_quality`` summarizes the
        close/volume check of the last 60 sessions. If a bar has a missing or
        invalid close, volume or low, only the clean suffix after the last bad
        bar is replayed (``cycle.restarted_after_gap``). When that suffix has
        fewer than MIN_REPLAY_SESSIONS bars the result is the early-exit shape
        (``NO_SIGNAL``, prices ``None``) with ``data_gap: True`` and an
        ``error`` naming the gap; no rally or FTD logic runs.
    """
    result = {
        "index": index_name,
        "state": MarketState.NO_SIGNAL.value,
        "swing_low": None,
        "rally_attempt": None,
        "ftd": None,
        "current_price": None,
        "lookback_high": None,
        "correction_depth_pct": None,
        "market_status": None,
    }

    history = history or []
    lookback = min(ANALYSIS_LOOKBACK, len(history))
    analysis_window = history[-lookback:] if lookback else []
    window_gaps = bar_gaps(analysis_window)
    result["data_quality"] = window_quality(window_gaps)

    gaps = find_bar_gaps(history, REPLAY_FIELDS, order="chronological")
    if len(history) < 10:
        if gaps["bad_bars"]:  # too short to restart past a bad bar: unavailable, not "no data"
            report = window_gaps if window_gaps["bad_bars"] else bar_gaps(analysis_window, ("low",))
            result["error"] = gap_reason(report, f"in the last {lookback} sessions")
            result["data_gap"] = True
        else:
            result["error"] = "Insufficient data"
        return result

    start = gaps["bad_indices"][-1] + 1 if gaps["bad_bars"] else 0
    replay_sessions = len(history) - start
    if gaps["bad_bars"] and replay_sessions < MIN_REPLAY_SESSIONS:
        report = window_gaps if window_gaps["bad_bars"] else bar_gaps(analysis_window, ("low",))
        result["error"] = gap_reason(report, f"in the last {lookback} sessions")
        result["data_gap"] = True
        return result

    result["current_price"] = analysis_window[-1]["close"]
    max_close = max(d["close"] for d in analysis_window)
    result["lookback_high"] = max_close
    if max_close > 0 and result["current_price"] > 0:
        result["correction_depth_pct"] = round(
            (result["current_price"] - max_close) / max_close * 100, 2
        )

    replay = _Replay(history, start).run()
    state = replay.state()
    result["state"] = state.value
    result["market_status"] = replay.market_status()
    result["swing_low"] = replay.swing_low()
    result["cycle"] = replay.cycle(replay_sessions, bool(gaps["bad_bars"]))
    if replay.phase == "uptrend_or_none":
        if gaps["bad_bars"]:
            # The restarted replay has not seen a qualifying correction yet, so it cannot
            # say whether an earlier FTD or correction still stands: unavailable, not a state.
            bad_date = history[gaps["bad_indices"][-1]].get("date", "N/A")
            result["data_gap"] = True
            result["error"] = (
                f"Data gap: replay restarted after a bad bar on {bad_date} and has not "
                "yet seen a qualifying correction"
            )
        return result
    result["rally_attempt"] = replay.rally_attempt(state)

    if state == MarketState.FTD_WINDOW:
        result["ftd"] = _empty_ftd()
    elif state in (MarketState.FTD_CONFIRMED, MarketState.FTD_INVALIDATED):
        result["ftd"] = dict(replay.ftd)
        lifecycle = assess_lifecycle(history, replay.ftd_idx, replay.ftd_ref_low)
        result["ftd_lifecycle"] = lifecycle
        if lifecycle.get("data_gap"):
            result.update(
                state=MarketState.NO_SIGNAL.value, data_gap=True, error=lifecycle["reason"]
            )
    return result


def _combined_market_status(combined_state, data_gap, *analyses):
    """IBD sets one status from either major index: the better confirmed status wins."""
    if data_gap:
        return None
    statuses = [a.get("market_status") for a in analyses]
    if combined_state == MarketState.FTD_CONFIRMED.value:
        if "confirmed_uptrend" in statuses:
            return "confirmed_uptrend"
        return "uptrend_under_pressure"
    if "market_in_correction" in statuses:
        return "market_in_correction"
    return None


def get_market_state(
    sp500_history: list[dict], nasdaq_history: list[dict], nasdaq_label="NASDAQ"
) -> dict:
    """
    Analyze both indices and produce a merged market state assessment.

    Priority logic:
    - If either index has FTD_CONFIRMED → overall FTD (single sufficient)
    - If both have FTD_CONFIRMED → strong FTD (dual confirmation)
    - Otherwise, use the more advanced state

    Args:
        sp500_history: S&P 500 daily OHLCV, most recent first (API format)
        nasdaq_history: NASDAQ Composite or explicit ETF proxy daily OHLCV, most recent first (API format)

    Returns:
        Combined market state with both index analyses
    """
    # Convert to chronological order (oldest first)
    sp500_chrono = list(reversed(sp500_history)) if sp500_history else []
    nasdaq_chrono = list(reversed(nasdaq_history)) if nasdaq_history else []

    sp500_analysis = analyze_single_index(sp500_chrono, "S&P 500")
    nasdaq_analysis = analyze_single_index(nasdaq_chrono, nasdaq_label)

    sp500_state = MarketState(sp500_analysis["state"])
    nasdaq_state = MarketState(nasdaq_analysis["state"])

    # Determine combined state
    sp500_ftd = sp500_state == MarketState.FTD_CONFIRMED
    nasdaq_ftd = nasdaq_state == MarketState.FTD_CONFIRMED

    if sp500_ftd and nasdaq_ftd:
        combined_state = MarketState.FTD_CONFIRMED.value
        dual_confirmation = True
    elif sp500_ftd or nasdaq_ftd:
        combined_state = MarketState.FTD_CONFIRMED.value
        dual_confirmation = False
    else:
        # Use the more advanced (hopeful) state
        # FTD_INVALIDATED above CORRECTION: more informative than bare correction
        state_priority = [
            MarketState.FTD_WINDOW,
            MarketState.RALLY_ATTEMPT,
            MarketState.FTD_INVALIDATED,
            MarketState.CORRECTION,
            MarketState.RALLY_FAILED,
            MarketState.NO_SIGNAL,
        ]
        combined_state = MarketState.NO_SIGNAL.value
        for state in state_priority:
            if sp500_state == state or nasdaq_state == state:
                combined_state = state.value
                break
        dual_confirmation = False

    # Determine which index triggered FTD (confirmed or invalidated)
    ftd_index = None
    if sp500_ftd:
        ftd_index = "S&P 500"
    if nasdaq_ftd:
        ftd_index = nasdaq_label if ftd_index is None else "Both"

    # Also track invalidated FTD index for reporting
    if ftd_index is None and combined_state == MarketState.FTD_INVALIDATED.value:
        for label, analysis in [("S&P 500", sp500_analysis), (nasdaq_label, nasdaq_analysis)]:
            if analysis.get("state") == MarketState.FTD_INVALIDATED.value:
                ftd_index = label
                break

    # True when either index replay hit a missing/invalid bar it could not restart past
    data_gap = bool(sp500_analysis.get("data_gap") or nasdaq_analysis.get("data_gap"))
    if data_gap:
        # A gapped index drops its own FTD context, so promoting the other
        # index could report a state more bullish than the healed data (e.g. an
        # invalidated S&P FTD hidden behind a NASDAQ confirmation). The combined
        # state is therefore unavailable: NO_SIGNAL with data_gap, no FTD source.
        # Each index's own analysis stays in the output for transparency.
        combined_state = MarketState.NO_SIGNAL.value
        dual_confirmation = False
        ftd_index = None

    return {
        "combined_state": combined_state,
        "market_status": _combined_market_status(
            combined_state, data_gap, sp500_analysis, nasdaq_analysis
        ),
        "dual_confirmation": dual_confirmation,
        "ftd_index": ftd_index,
        "sp500": sp500_analysis,
        "nasdaq": nasdaq_analysis,
        "data_gap": data_gap,
    }
