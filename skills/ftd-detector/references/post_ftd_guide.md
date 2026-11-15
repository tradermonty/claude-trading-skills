# Post-FTD Monitoring Guide

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

A confirmed Follow-Through Day (FTD) shifts the probability toward a new uptrend, but does not guarantee an uptrend. Post-FTD monitoring is essential for:
1. Confirming the signal is working (exposure increase)
2. Detecting early failure (exposure reduction)
3. Identifying Power Trend confirmation (maximum conviction)

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
- 2+ distribution days within 5 days of FTD: ~90% failure rate
- Even if individual days are in the "moderate" timing zone (Day 4-5), accumulation of distribution is bearish

---

## FTD Invalidation

### Invalidation Criteria
An FTD is formally invalidated when:
- **A later intraday low strictly undercuts the recorded rally Day 1 low**
- This is a hard stop - the FTD signal is no longer valid

### What to Do After Invalidation
1. Reassess risk against portfolio limits; the tool does not prescribe a percentage
2. Do NOT try to average down or hold through
3. Wait for a new swing low and fresh rally attempt
4. The previous FTD failure provides no information about the next attempt

### Soft Warnings (Not Yet Invalidated)
- Close approaches but doesn't breach FTD low: heightened caution
- Intraday breach but close above: technically valid but weak
- Slow grinding decline toward FTD low: consider preemptive reduction

---

## Power Trend Confirmation

### Definition
A Power Trend is the strongest bullish condition in O'Neil's framework. It occurs when three conditions are simultaneously true:

1. **21-day EMA > 50-day SMA** (short-term momentum above medium-term trend)
2. **50-day SMA slope is positive** (rising over the last 5 trading days)
3. **Price above 21-day EMA** (current price confirming the trend)

### Significance
- Power Trend + FTD = highest conviction bottom signal
- Historically, markets in Power Trend have very low probability of immediate failure
- Power Trend typically develops 2-4 weeks after a successful FTD
- Not required for FTD validity, but serves as strong confirmation

### Power Trend Conditions Breakdown

| Conditions Met | Interpretation |
|---------------|---------------|
| 3/3 | Full Power Trend - maximum conviction |
| 2/3 | Developing trend - monitor for completion |
| 1/3 | No Power Trend - rely on other signals |
| 0/3 | Bearish structure - be cautious despite FTD |

---

## FTD Success vs Failure Patterns

### Characteristics of Successful FTDs

| Factor | Successful Pattern |
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

### Characteristics of Failed FTDs

| Factor | Failure Pattern |
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
1. Top Detector signals defensive posture
2. FTD Detector watches for bottom signals
3. When FTD confirms, begin transitioning from defensive to offensive

### During FTD Confirmed:
1. FTD Detector guides exposure increase
2. Top Detector should show declining score (improving conditions)
3. If Top Detector score remains high despite FTD, exercise extra caution

### Signal Conflict Resolution:
- FTD confirmed but Top Detector still 60+: proceed with caution, use smaller position sizes
- FTD confirmed and Top Detector below 40: higher conviction signal
- FTD invalidated: defer to Top Detector for defensive guidance

---

## Empirical limits

No universal FTD success/failure rate is asserted. A measured rate needs a
specified universe, sample period, failure reference and outcome horizon.
