# Follow-Through Day (FTD) Methodology

## Current implementation contract (#765)

Default Nasdaq evidence is ^IXIC; --nasdaq-symbol QQQ explicitly selects a
Nasdaq-100 ETF proxy. Never conflate the two series' prices or volumes. The Day
4–10 window is this model's FTD window (an attempt expires on Day 11 and a new count starts). Rally failure uses the rally low,
the low of the pullback the rally attempt started from (the lowest low of that pullback through Day 1, inclusive),
for the attempt and after an FTD alike; it is not the lowest low of the whole
correction. Day 1 low is informational. The model replays
the whole history oldest to newest with carried state (see "Why a forward
replay"). Missing low data is unavailable.
FTD-day-low close breach is pressure, not failure. Its published score is capped
at 59 so numerical consumers see the weakening; this cap is not calibrated.
Portfolio allocation is not assessed. Historical examples below are retained
illustrations, not newly verified data or statistical evidence.

## Overview

The Follow-Through Day (FTD) is an O'Neil-style technical signal of renewed demand after a correction. This implementation reports the event and its health, not a guaranteed bottom or a portfolio allocation.

**Key Insight:** An FTD is technical evidence, not a calibrated success probability or an allocation instruction.

---

## Step 1: Identify the Correction

### Qualifying Correction
A correction must meet these criteria before FTD analysis begins:

- **Decline magnitude:** Index closes 3% or more below its recent high
- **Duration:** At least 3 down days during the decline
- **Index scope:** S&P 500 and/or NASDAQ Composite (either suffices)

### Swing Low Definition
The swing low is the lowest *closing* price of the current pullback segment. The
intraday low of that segment is the separate rally-failure reference.

**Segments.** A segment starts at the correction entry (measured from the peak) and
restarts, inclusive of that bar, at a rally failure bar and an FTD invalidation bar. The segment's lowest intraday low becomes the
next attempt's reference on its Day 1; the segment's lowest close is the reported swing low.

- The correction is measured from the highest close; it qualifies once a close is 3%+ below it
  with at least 3 down closes since that high. There is no 40-bar search limit.
- It is a replay state, not a pattern re-selected on every run: a later, higher closing low
  inside the same segment never replaces it, and only a new lower close moves it.
- The latest bar is never a "confirmed" low: no right-hand bar is needed, and a down close
  that holds the reference does not reset an attempt.

**Important:** The swing low is determined by *closing price*, not intraday low.

---

## Step 2: Rally Attempt and Day 1 Reference

### Day 1 Detection
Day 1 marks the beginning of a rally attempt. It occurs on the **first qualifying up day** after the swing low:

**Primary criterion:** Close > Previous day's close (up day)

**Alternative criterion:** Close in the top 50% of the day's price range
- Formula: (Close - Low) / (High - Low) >= 0.50
- This captures days where the market recovers significantly from intraday lows even if it doesn't close above the prior day's close

### Day 1 on a new closing low
A session that sets a new closing low may be Day 1 if it closes in the top 50% of a valid
high-low range (the segment low then includes that session's intraday low). "New closing
low" means below the segment's lowest close. A new closing low in the lower half is not Day 1. A failure session is never Day 1: the earliest new Day 1
is the next session.

### Integrity Check: Every Session After Day 1

- Every subsequent session's **intraday low** must hold the attempt's **rally low** (the lowest
  intraday low of the segment it started from, frozen on Day 1 and never changed while the
  attempt is active), including sessions after FTD confirmation. A down close that holds it keeps
  counting, and a higher low never replaces it. In a clean decline into a single low (as in
  November 2026) the rally low and the whole-correction low coincide; they differ once an earlier
  attempt failed at a higher level, as in October 2019.
- A strict intraday breach fails the rally even if the close recovers. Equality holds.
- Trading below the Day 1 low alone does not fail the rally.
- Missing low evidence on any replayed bar makes the state unavailable.
- The FTD candle low is a different reference: a close below it warns but does not itself fail
  the rally and is never a correction trigger.

### Rally Invalidation (Reset)
An intraday low strictly below the rally low fails the attempt (RALLY_FAILED, or
FTD_INVALIDATED after an FTD). The failed event stays in the evidence. The failure bar starts a new
segment (its own low belongs to it) and is never Day 1; the next session can start a new Day 1.
**Expiry and re-count.** An FTD is valid on Day 4-10 only. With no FTD by Day 10 the attempt expires on the bar that would be Day 11 (RALLY_FAILED, "No follow-through day by Day 10"; market status stays market in correction) and a new segment starts at that bar, inclusive. The expiry bar is never Day 1. While the count is not armed a bar can only arm it (a down close arms it; the expiry bar itself can do so); the next up or upper-half close is then Day 1, never the arming bar. The new attempt's reference low is the lowest intraday low from the expiry bar through that Day 1, and Day 4-10 from there is the new window. `reset_count` counts expiries as well as failures; `rally_attempt.end_reason` is `expired` or `undercut`.

**Why the reference restarts at an expiry.** A version that kept the expired attempt's reference
for the next count lost the October 2019 Nasdaq FTD: the expired 9/19 attempt kept a June
reference, so the 10/2-10/3 pullback low never started a new count and the 10/11 follow-through
day fell on day 3 instead of day 7. That carried reference had been added only to stop repeated
small-dip failures in a 2013 Nasdaq replay, but the 50-day-line distribution trigger (see Market
status) already fixed that case, so the carry was removed.

---

## Step 3: FTD Window (Day 4-10)

### FTD Qualification Criteria
A Follow-Through Day must satisfy ALL of these conditions:

1. **Day 4-10** of the rally attempt (Day 4-7 is the prime window; Day 8-10 is the late window)
2. **Price gain >= 1.25%** (minimum threshold)
   - 1.25-1.49%: Minimum qualifying gain
   - 1.50-1.99%: Higher model gain tier (not a measured reliability estimate)
   - 2.00%+: Strong signal
3. **Volume > previous day's volume** (mandatory)
   - This confirms institutional participation
   - Volume does not need to exceed the 50-day average, though it's a positive if it does

### Day Counting Rules
- Day 1 = first qualifying up day after swing low
- Day 2, 3, etc. = every subsequent trading day (regardless of whether it's up or down)
- Days count continues as long as the rally is not invalidated
- The FTD itself must be an up day meeting the gain and volume requirements

### Prime vs Late Window

**Day 4-7 (Prime):**
- Preferred timing tier in this model; no measured success-rate advantage is asserted
- Base quality score: 60 points
- The weighting is heuristic, not evidence of institutional conviction

**Day 8-10 (Late):**
- Still qualifies; receives a lower heuristic base weight
- Base quality score: 50 points
- This weighting does not establish buyer intent

**After Day 10:**
- The attempt expires on the bar that would be Day 11 (RALLY_FAILED); a qualifying gain on that
  bar is not an FTD. The expiry bar starts a new segment: the next attempt's reference low is
  re-frozen from that bar through its own Day 1, and a new count can start after a down close (see above).
- IBD is reported to note that most FTDs come on days 4-7 and some come later (secondary report, IBD's official rule text not verified).
- A rally without an FTD by Day 10 is a warning sign. No reliability estimate is supplied

---

## Step 4: Dual-Index Confirmation

### Single-Index FTD
An FTD on either the S&P 500 or NASDAQ is sufficient to trigger the signal. A single-index event is reported, without prescribing a trade.

### Dual-Index FTD
When both S&P 500 and NASDAQ produce FTDs (within a few days of each other):
- Broader confirmation evidence; no calibrated reliability uplift is asserted
- Quality score bonus: +15 points
- Provides confirmation across the selected instruments
- Does not identify which investor groups are buying

### Index Discrepancy
When one index confirms FTD but the other is still in rally attempt or correction:
- FTD is still valid from the confirming index
- Monitor the lagging index for convergence or divergence
- Divergence (one fails while other holds) is a cautionary signal

---

## Quality Score Framework

### Score Components (0-100)

| Factor | Criteria | Points |
|--------|----------|--------|
| **Base (FTD Day)** | Day 4-7 | 60 |
| | Day 8-10 | 50 |
| **Price Gain** | >= 2.0% | +15 |
| | >= 1.5% | +10 |
| | >= 1.25% | +5 |
| **Volume vs 50-day Avg** | Above average | +10 |
| | Below average | +0 |
| **Dual Index Confirm** | Both S&P 500 + NASDAQ | +15 |
| | Single index | +0 |
| **Post-FTD Health** | No distribution (5 days) | +10 |
| | Distribution Day 4-5 | -5 |
| | Distribution Day 3 | -15 |
| | Distribution Day 1-2 | -30 |

### Interpretation

| Score | Signal | Portfolio sizing |
|---|---|---|
| 80–100 | Strong FTD | Not assessed |
| 60–79 | Moderate FTD | Not assessed |
| 40–59 | Weak FTD | Not assessed |
| below 40 | Very weak FTD (not automatically failed) | Not assessed |

A warning caps the published score at 59 (an explicit uncalibrated heuristic),
so score-only consumers do not treat pressure as strong confirmation. A true
reference breach returns failed quality; missing evidence returns unavailable.

---

## Historical FTD Examples

### March 2020 (COVID Crash)
- **Swing Low:** March 23, 2020 (S&P 500: ~2,237)
- **Day 1:** March 24, 2020 (+9.4%)
- **FTD:** April 2, 2020 (Day 8 of rally, +2.3% on higher volume)
- **Outcome:** Successful - began one of the strongest bull markets in history
- **Quality:** Moderate (Day 8 = late window, but strong gain and volume)
- **Note:** Multiple failed rally attempts preceded this successful one

### October 2022 (Bear Market Bottom)
- **Swing Low:** October 13, 2022 (S&P 500: ~3,491)
- **Day 1:** October 14, 2022 (+2.6%)
- **FTD:** October 21, 2022 (Day 6, +2.4% on higher volume)
- **Outcome:** Successful - confirmed the end of the 2022 bear market
- **Quality:** High (Day 6 = prime window, strong gain, above-avg volume)

### June 2022 (Failed FTD)
- **Swing Low:** June 17, 2022 (S&P 500: ~3,666)
- **FTD:** Late June 2022
- **Outcome:** Failed - market made new lows by September 2022
- **Lesson:** FTD occurred but distribution days followed quickly; market environment (rising rates, inflation) was hostile

### December 2018 (Christmas Eve Low)
- **Swing Low:** December 24, 2018 (S&P 500: ~2,351)
- **FTD:** January 4, 2019 (Day 6, +3.4% on higher volume)
- **Outcome:** Successful - powerful rally through 2019
- **Quality:** Very high (prime window, strong gain, Fed pivot as catalyst)

---

## Market status (IBD three tiers)

`market_status` is one of `confirmed_uptrend`, `uptrend_under_pressure`,
`market_in_correction`, or `null` when it cannot be determined (data gap, insufficient
data, warm-up before the first qualifying correction since the replay start). The legacy
`state` values are unchanged: both uptrend tiers are `FTD_CONFIRMED`; the rally attempt,
FTD window and day count are details inside `market_in_correction`.

**Rules (all indicators use bars up to the current bar only):**

- Correction to confirmed uptrend only on an FTD. A rise above the old peak, with or without
  a rally attempt that fails, stays `market_in_correction`; new attempts keep forming after a
  rally failure.
- Confirmed uptrend to under pressure: active distribution days >= 5, or a close below the
  50-session SMA of closes once the index has closed above that SMA at least once since the FTD
  bar (the FTD bar included; `cycle.regained_50sma_since_ftd`), or the first close below the
  FTD-day low. Until that first close above the SMA, being below it is not a cause, because an
  FTD normally comes from below the 50-day line. The FTD-day-low close
  breach stays a warning (#765): it is not a failure or a correction trigger, the lifecycle
  `warning` field is unchanged and the published quality score stays capped at 59.
- Under pressure back to confirmed: active distribution days <= 4 and close above the
  50-session SMA. No new FTD is required. The FTD-day-low breach alone does not keep the
  status under pressure once those two hold (it is a one-shot cause, like the warning).
  `cycle.pressure_reasons` lists the active causes: `distribution`, `below_50sma`,
  `ftd_low_close_breach`, or `awaiting_recovery` when the causes have cleared but the return
  test is not yet met.
- Either uptrend tier to correction, any of: (a) 6+ active distribution days and a close below
  the 50-day line (the 50-session SMA of closes; the new correction is measured from the post-FTD
  peak, `previous_ftd.end_reason` = `distribution`). This trigger does not depend on
  `regained_50sma_since_ftd`: it ends the uptrend even if the SMA was never regained. Secondary sources describe IBD's trigger variously (one cites the 21-day EMA); this model uses the 50-day line so that shallow pullbacks inside a rising market are not declared corrections, and the threshold is unverified.
  The earlier 21-session EMA trigger fired on shallow pullbacks (about half of the entries in a
  2000-2026 replay were less than 5% below the 60-day high) and left long stretches of a rising
  market in correction, because only an FTD ends a correction; (b) an intraday low below the rally low
  (FTD_INVALIDATED, as before); (c) a drawdown >= 10% from the post-FTD peak close
  (`end_reason` = `deep_drawdown`). (b) wins when several apply on one bar.
- Distribution day: close down >= 0.2% on volume above the previous session, counted after the
  FTD; it expires after 25 sessions or once a later high is >= 5% above its close (same
  defaults as ibd-distribution-day-monitor).
- An SMA that cannot be computed (fewer than 50 closes since the replay start) makes its
  condition false, in the pressure rule and in the distribution trigger;
  `cycle.indicators.sma50_available` says so. A close that is exactly on the average counts as
  neither above nor below.
- The status is evaluated on the FTD bar too. An FTD that closes below its 50-session SMA
  stays `confirmed_uptrend` until the index has closed above the SMA once; only distribution or
  the FTD-day-low breach can put it under pressure before that.
- IBD sets one status from either major index: if the combined state is `FTD_CONFIRMED`, the
  better confirmed index wins; any data gap gives `null`; otherwise `market_in_correction`
  if either index is in correction.

**Why:** IBD moves a correction to a confirmed uptrend only on a follow-through day, and
moves a confirmed uptrend to under pressure and then to correction as distribution
accumulates and key averages are lost. Under pressure returns to confirmed when distribution
ages off and the indexes regain the 50-day line, with no new FTD. Secondary sources (IBD's
official rule text was not verified):

- https://inkl.com/news/why-we-wait-for-a-follow-through-day-before-declaring-an-uptrend
- https://inkl.com/news/how-to-spot-a-stock-market-bottom-this-signal-marks-all-major-lows
- https://origin.williamoneil.com/tag/distribution-days/page/2

The numeric thresholds (5 and 6 distribution days, the 50-session SMA, the 10%
drawdown) are unverified, uncalibrated model choices.

## Why a forward replay

The state machine replays the whole supplied history oldest to newest and changes state only on
defined events. A longer stateless window (for example 250 sessions) was considered and
rejected: it only delays the problems. It keeps a bounded high search and re-selects swing
lows on every run, so the chosen low and the state still change as the window slides; a
confirmed FTD would still vanish when it leaves the window; and a long decline would still not be
recognized as one correction. The replay fixes all three, and the point-in-time
test checks that analyzing a prefix of the history gives the same result the full replay had at
that bar (no look-ahead).

When a bar has a missing close, volume or low, only the clean suffix after the last bad bar
is replayed, and only if it holds at least 60 sessions; otherwise the result is a data gap.

## Common Mistakes

1. **Buying before FTD confirmation:** Acting on Day 1-3 before FTD is confirmed
2. **Ignoring volume:** A large gain without volume increase is NOT an FTD
3. **Counting wrong:** Including non-trading days or resetting day count incorrectly
4. **Single vs. dual index:** Treating single-index FTD as equivalent to dual-index
5. **Ignoring post-FTD distribution:** Not monitoring for early distribution days
6. **FTD ≠ all clear:** Treating FTD as guarantee rather than probability shift
