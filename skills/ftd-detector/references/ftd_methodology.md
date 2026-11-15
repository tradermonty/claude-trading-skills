# Follow-Through Day (FTD) Methodology

## Current implementation contract (#765)

Default Nasdaq evidence is ^IXIC; --nasdaq-symbol QQQ explicitly selects a
Nasdaq-100 ETF proxy. Never conflate the two series' prices or volumes. The Day
4–10 window is this model's bounded choice. Day 1 low is an explicit failure
anchor, potentially stricter than the generic IBD downtrend-low description;
these are not claimed identical. Missing reference/low data is unavailable.
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
The swing low is a qualifying closing-price minimum used to search for Day 1. It is not this model's intraday rally-failure reference:

- Must be preceded by 3%+ decline from a recent high (within 40 trading days)
- Must have at least 3 down days between the high and the low
- Must be a local minimum (adjacent days have higher closes)
- Multiple swing lows can occur; use the most recent qualifying one

**Important:** The swing low is determined by *closing price*, not intraday low.

---

## Step 2: Rally Attempt and Day 1 Reference

### Day 1 Detection
Day 1 marks the beginning of a rally attempt. It occurs on the **first qualifying up day** after the swing low:

**Primary criterion:** Close > Previous day's close (up day)

**Alternative criterion:** Close in the top 50% of the day's price range
- Formula: (Close - Low) / (High - Low) >= 0.50
- This captures days where the market recovers significantly from intraday lows even if it doesn't close above the prior day's close

### Integrity Check: Every Session After Day 1

- Every subsequent session's **intraday low** must hold the recorded Day 1 low, including sessions after FTD confirmation.
- A strict intraday breach fails the rally even if the close recovers above that reference. Equality holds.
- This rule is not limited to Day 2–3. Missing low/reference evidence makes the state unavailable.
- The FTD candle low is a different reference: a close below it warns but does not itself fail the rally.

### Rally Invalidation (Reset)
A later intraday low strictly below the recorded Day 1 low fails this implementation's rally. The failed event remains in the evidence.

Separately, a close below the FTD candle low warns, but does not itself fail or reset the rally.

When a rally resets, the new lower price may become the new swing low, and the cycle begins again.

---

## Step 3: FTD Window (Day 4-10)

### FTD Qualification Criteria
A Follow-Through Day must satisfy ALL of these conditions:

1. **Day 4-10** of the rally attempt (Day 4-7 is the prime window; Day 8-10 still valid)
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
- Outside this implementation's bounded qualification window; not a universal IBD upper limit
- Rally without FTD by Day 10 is a warning sign
- A later rally may still develop; no reliability estimate is supplied

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

## Common Mistakes

1. **Buying before FTD confirmation:** Acting on Day 1-3 before FTD is confirmed
2. **Ignoring volume:** A large gain without volume increase is NOT an FTD
3. **Counting wrong:** Including non-trading days or resetting day count incorrectly
4. **Single vs. dual index:** Treating single-index FTD as equivalent to dual-index
5. **Ignoring post-FTD distribution:** Not monitoring for early distribution days
6. **FTD ≠ all clear:** Treating FTD as guarantee rather than probability shift
