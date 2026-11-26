# Post-FTD Monitoring Guide

## Current implementation contract (#765)

Default Nasdaq evidence is ^IXIC; --nasdaq-symbol QQQ explicitly selects a
Nasdaq-100 ETF proxy. Never conflate the two series' prices or volumes. The Day
4–10 window is this model's bounded choice. The rally-failure reference is the
correction (downtrend) low, the lowest intraday low since the correction peak;
Day 1 low is informational. Missing reference/low data is unavailable.
FTD-day-low close breach is pressure, not failure. Its published score is capped
at 59 so numerical consumers see the weakening; this cap is not calibrated.
Portfolio allocation is not assessed. Historical examples below are retained
illustrations, not newly verified data or statistical evidence.

## Overview

A confirmed Follow-Through Day (FTD) shifts the probability toward a new uptrend, but does not guarantee an uptrend. Post-FTD monitoring is essential for:
1. Tracking whether technical confirmation persists
2. Distinguishing pressure, rally failure and missing evidence
3. Reporting the three-condition Power Trend proxy as separate technical context

---

## Distribution Day Monitoring After FTD

### What Is a Post-FTD Distribution Day?
A distribution day after an FTD is defined as:
- Index declines >= 0.2% from the prior day's close
- Volume is higher than the previous day's volume
- Occurs within the first 5 trading days after the FTD

### Distribution timing (heuristic, not calibrated failure rates)

Early distributions reduce quality more than later ones: days 1–2 subtract 30,
day 3 subtracts 15, days 4–5 subtract 5, and a monitored clean period adds 10.
These are model weights, not measured failure probabilities.

### Multiple Distribution Days
- 2+ distribution days within 5 days of FTD receive an additional 20-point heuristic penalty; no failure probability is estimated
- Even if individual days are in the "moderate" timing zone (Day 4-5), accumulation of distribution is bearish

---

## FTD Invalidation

### Invalidation Criteria
An FTD is formally invalidated when:
- **A later intraday low strictly undercuts the correction low the FTD rallied from**
- This is a hard stop - the FTD signal is no longer valid

### What to Do After Invalidation
1. Reassess risk against portfolio limits; the tool does not prescribe a percentage
2. Keep any portfolio decision separate from this technical event classification
3. Wait for a fresh rally attempt and a new FTD; only an FTD ends a correction
4. A previous failure does not determine the outcome of the next attempt

### Soft Warnings (Not Yet Invalidated)
- A close below the **FTD candle low**, while holding the correction low, is pressure and caps published quality at 59. It also moves `market_status` to `uptrend_under_pressure` (`cycle.pressure_reasons` includes `ftd_low_close_breach`); the state stays FTD_CONFIRMED. The status returns to `confirmed_uptrend` once active distribution days are <= 4 and the close is above the 50-session SMA, without a new FTD.
- An intraday breach of the **FTD candle low** followed by a close above that candle low is not the close-breach warning; inspect the correction low separately.
- An intraday breach of the **correction low** is failure even when the close recovers.
- Distribution (5+ active distribution days) or a close below the 50-session average moves a confirmed uptrend to `uptrend_under_pressure`; see the market status rules in `ftd_methodology.md`.
- Approaching either level is technical context, not an instruction to change portfolio exposure.

---

## Power Trend Confirmation

### Definition
This tool's Power Trend proxy reports whether three technical conditions are simultaneously true; it is not a claim to implement every published Power Trend definition:

1. **21-day EMA > 50-day SMA** (short-term momentum above medium-term trend)
2. **50-day SMA slope is positive** (rising over the last 5 trading days)
3. **Price above 21-day EMA** (current price confirming the trend)

### Significance
- Power Trend and FTD are complementary technical observations
- No immediate-failure probability is calibrated for this proxy
- Observe whether the proxy develops after the FTD; no typical time-to-success is asserted
- Not required for FTD validity, but serves as strong confirmation

### Power Trend Conditions Breakdown

| Conditions Met | Interpretation |
|---------------|---------------|
| 3/3 | All three proxy conditions met; sizing not assessed |
| 2/3 | Developing trend - monitor for completion |
| 1/3 | No Power Trend - rely on other signals |
| 0/3 | Bearish structure - be cautious despite FTD |

---

## Qualitative Patterns to Inspect (Not Calibrated Outcome Predictors)

### Favorable Technical Context

| Factor | Favorable Observation |
|--------|--------------------|
| **Day Timing** | Day 4-7 (prime window) |
| **Gain** | 2.0%+ on heavy volume |
| **Volume** | Above 50-day average |
| **Dual Index** | Both S&P 500 and NASDAQ confirm |
| **Post-FTD** | Clean first 3-5 days (no distribution) |
| **Leading Stocks** | Many breakouts from proper bases |
| **Sector Breadth** | Multiple sectors participating |
| **Catalyst** | Identifiable positive catalyst (Fed pivot, earnings surprise) |
| **Power Trend** | Develops within 2-4 weeks |

### Adverse Technical Context

| Factor | Adverse Observation |
|--------|--------------------|
| **Day Timing** | Day 8-10 (late window) |
| **Gain** | Minimum qualifying (1.25-1.49%) |
| **Volume** | Below 50-day average |
| **Dual Index** | Only one index confirms |
| **Post-FTD** | Distribution within first 2 days |
| **Leading Stocks** | Few/no quality breakouts |
| **Sector Breadth** | Narrow participation (1-2 sectors) |
| **Catalyst** | No clear catalyst, or hostile macro backdrop |
| **Power Trend** | Never develops, 50 SMA continues declining |

---

## Exposure decisions after FTD

`exposure_range` is always `Not assessed`. Assess breadth, leadership, stock
setups and portfolio limits separately. FTD-candle-low pressure caps published
quality at 59, but keeps the historical event. That cap is a conservative model
choice, not empirical calibration or a buy/sell/position-sizing instruction.

## Interaction with Market Top Detector

The FTD Detector and Market Top Detector are complementary:

### During Correction (Top Detector score 60+):
1. Top Detector supplies its separate deterioration assessment
2. FTD Detector watches for a qualifying rally event
3. When FTD confirms, compare both technical assessments; do not automatically change portfolio posture

### During FTD Confirmed:
1. FTD Detector reports event validity, pressure, quality and missing evidence
2. Compare Top Detector's direction and risk evidence separately
3. If Top Detector score remains high despite FTD, exercise extra caution

### Signal Conflict Resolution:
- FTD confirmed but Top Detector still 60+: report conflicting technical evidence; portfolio sizing remains unassessed
- FTD confirmed and Top Detector below 40: report agreement between the technical models, not a portfolio percentage
- FTD invalidated: retain the failed event evidence and assess any new rally attempt separately

---

## Empirical limits

No universal FTD success/failure rate is asserted. A measured rate needs a
specified universe, sample period, failure reference and outcome horizon.
