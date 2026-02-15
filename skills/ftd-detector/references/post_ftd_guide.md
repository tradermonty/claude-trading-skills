# Post-FTD Monitoring Guide

## Overview

A confirmed Follow-Through Day (FTD) shifts the probability toward a new uptrend, but approximately 75% of FTDs ultimately fail. Post-FTD monitoring is essential for:
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

### Failure Rate by Distribution Timing

| Distribution Timing | Failure Rate | Quality Score Impact | Action |
|--------------------|-------------|---------------------|--------|
| **Day 1 after FTD** | ~85% fail | -30 points | Immediately reduce exposure |
| **Day 2 after FTD** | ~80% fail | -30 points | Reduce to defensive levels |
| **Day 3 after FTD** | ~65% fail | -15 points | Tighten stops significantly |
| **Day 4 after FTD** | ~50% fail | -5 points | Moderate caution |
| **Day 5 after FTD** | ~45% fail | -5 points | Normal monitoring |
| **No distribution (5 days)** | ~35% fail | +10 points | Increase conviction |

**Key Insight:** The earlier distribution appears after an FTD, the more likely the FTD will fail. Distribution within the first 2 days is a near-certain failure signal.

### Multiple Distribution Days
- 2+ distribution days within 5 days of FTD: ~90% failure rate
- Even if individual days are in the "moderate" timing zone (Day 4-5), accumulation of distribution is bearish

---

## FTD Invalidation

### Invalidation Criteria
An FTD is formally invalidated when:
- **Index closes below the FTD day's intraday low**
- This is a hard stop - the FTD signal is no longer valid

### What to Do After Invalidation
1. Reduce equity exposure to defensive levels (0-25%)
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

## Exposure Management After FTD

### Graduated Exposure Model

The O'Neil approach uses progressive exposure increase, not all-at-once buying:

**Phase 1: Initial (FTD Day)**
- Start at 25% of target exposure
- Buy 1-2 leading stocks breaking out of bases
- Use FTD day's low as initial stop reference

**Phase 2: Confirmation (Days 1-5 post-FTD)**
- If no distribution: increase to 50% exposure
- Add positions in additional leaders
- Tighten stops on initial positions to breakeven

**Phase 3: Acceleration (Days 5-15 post-FTD)**
- If trend confirms (clean action, breakouts working): increase to 75%
- Pyramid into winning positions
- Look for Power Trend development

**Phase 4: Full Exposure (2-4 weeks post-FTD)**
- If Power Trend develops: full 100% exposure
- Focus on strongest leaders
- Normal stop-loss management

### Exposure Reduction Triggers

| Trigger | Action |
|---------|--------|
| Distribution Day 1-2 post-FTD | Cut to 0-25% |
| Distribution Day 3 post-FTD | Cut to 25-50% |
| FTD invalidated | Cut to 0-25% |
| Breakouts failing (stocks reversing after breakout) | Reduce by 25% |
| No quality setups forming | Don't force increase |

---

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

## Historical Success Rate Context

Based on IBD historical analysis of FTDs since 1900:

- **Overall FTD success rate:** ~25% (1 in 4 leads to sustained uptrend)
- **FTDs with quality score 80+:** ~45-50% success rate
- **FTDs with quality score 60-79:** ~30-35% success rate
- **FTDs with quality score below 60:** ~10-15% success rate

The quality scoring system effectively filters the ~75% failure rate down to a more manageable ~50-55% for high-quality signals. Combined with proper stop-loss management, this creates a positive expected value system despite the sub-50% win rate, because winners significantly outperform losers when properly managed.
