# Bubble Detection Quick Reference (English)

## Daily Checklist (5 minutes)

### Morning Routine (Before Market Open)

```
□ Step 1: Update Bubble-O-Meter (2 min)
   - Score 6 quantitative indicators (0-2) + 3 qualitative adjustments (0-1)
   - Check risk budget based on 0-15 total score

□ Step 2: Position Management (2 min)
   - Update ATR trailing stops
   - Check stair-step profit targets
   - Evaluate new entry eligibility

□ Step 3: Signal Check (1 min)
   - Media/Social trends (Google Trends, Twitter)
   - Major indices distance from 52-week highs
   - VIX & Put/Call ratio
```

---

## Emergency Assessment: 3 Questions

When uncertain about an investment decision, answer these 3 questions:

### Q1: "Are non-investors recommending it?"
- YES → Mass penetration complete, likely late stage
- NO → Still early to mid stage

### Q2: "Has the narrative become 'common sense'?"
- YES → Euphoria stage, contrarian views socially unacceptable
- NO → Healthy skepticism still functions

### Q3: "Is 'this time is different' the catchphrase?"
- YES → Classic historical bubble signal
- NO → Healthy caution still present

**All 3 YES → Critical zone, prioritize profit-taking/exit**

---

## Action Matrix by Bubble Phase

| Phase | Score | Risk Budget | Entry | Profit-Taking | Stop | Short |
|-------|-------|------------|-------|---------------|------|-------|
| **Normal** | 0-4 | 100% | Normal | At target | 2.0 ATR | No |
| **Caution** | 5-7 | 70-80% | 50% reduced | 25% at +20% | 1.8 ATR | No |
| **Elevated Risk** | 8-9 | 50-70% | Selective | 40% at +20% | 1.6 ATR | Consider |
| **Euphoria** | 10-12 | 40-50% | Stopped | 50% at +20% | 1.5 ATR | After confirm |
| **Critical** | 13-15 | 20-30% | Stopped | 75-100% now | 1.2 ATR | Recommended |

---

## v2.1 Quick Scoring: 6 Quantitative + 3 Qualitative

### Quantitative Indicators (0-2 each)

### 1. Put/Call Ratio
```
0 pts: P/C > 0.85
1 pt: P/C 0.70-0.85
2 pts: P/C < 0.70
```

### 2. Volatility Suppression + New Highs
```
0 pts: VIX > 15 or index more than 10% from highs
1 pt: VIX 12-15 and index near highs
2 pts: VIX < 12 and major index within 5% of 52-week high
```

### 3. Leverage
```
0 pts: Margin debt YoY <= +10% or negative
1 pt: Margin debt YoY +10-20%
2 pts: Margin debt YoY +20% or more and all-time high
```

### 4. IPO Market Overheating
```
0 pts: Normal levels
1 pt: Quarterly IPO count >1.5x five-year average
2 pts: Quarterly IPO count >2x five-year average and median first-day return +20%+
```

### 5. Breadth Anomaly
```
0 pts: >60% of S&P 500 stocks above 50DMA
1 pt: 45-60% above 50DMA
2 pts: New high and <45% above 50DMA
```

### 6. Price Acceleration
```
0 pts: Past 3-month return below 85th percentile
1 pt: Past 3-month return in 85-95th percentile
2 pts: Past 3-month return above 95th percentile
```

### Qualitative Adjustments (0-1 each; +3 max)

### A. Social Penetration
```
0 pts: Any required evidence missing
1 pt: Direct user report + specific examples + at least 3 independent sources
```

### B. Media/Search Trends
```
0 pts: Search trends <5x or no mainstream coverage confirmation
1 pt: Google Trends 5x+ YoY and mainstream coverage confirmed
```

### C. Valuation Disconnect
```
0 pts: P/E <25 or fundamentals support valuation
1 pt: P/E >25, fundamentals ignored, and "this time is different" documented
```

---

## Profit-Taking Strategy Templates

### Template 1: Stair-Step (Conservative)

```
Position: $10,000 initial investment
Targets: +20%, +40%, +60%, +80%

+20% ($12,000) → Sell 25% = $3,000 secured
+40% ($14,000) → Sell 25% = $3,500 secured
+60% ($16,000) → Sell 25% = $4,000 secured
+80% ($18,000) → Sell 25% = $4,500 secured

Total profit secured: $15,000 (+50% equivalent)
```

### Template 2: ATR Trailing (Aggressive)

```python
def calculate_trailing_stop(current_price, atr_20d, bubble_phase):
    """
    Calculate trailing stop based on bubble phase

    bubble_phase: 'normal', 'caution', 'elevated_risk', 'euphoria', 'critical'
    """
    multipliers = {
        'normal': 2.0,
        'caution': 1.8,
        'elevated_risk': 1.6,
        'euphoria': 1.5,
        'critical': 1.2
    }
    multiplier = multipliers.get(bubble_phase, 2.0)
    stop_price = current_price - (atr_20d * multiplier)
    return stop_price
```

### Template 3: Hybrid (Recommended)

```
Stage 1 (Boom):
  → Stair-step reduces 50% of position

Stage 2 (Euphoria):
  → Apply ATR trailing to remaining 50%, ride upside

Stage 3 (Panic signals):
  → Exit immediately when ATR stop hit
```

---

## Short-Selling Timing Decision (Critical)

### ❌ Absolutely Avoid: Early Contrarian

```
Reason: Often 2-3x further rise after "obviously too high"
Risk: "Markets can remain irrational longer than you can remain solvent"
```

### ✅ Recommended: After Composite Conditions Met

**Need at least 3 of 7 conditions before considering:**

1. □ Weekly chart shows clear lower highs
2. □ Volume peaked out (3 weeks declining)
3. □ Leverage metrics drop sharply (margin debt -20%+)
4. □ Media/search trends peaked out
5. □ Weak stocks in sector breaking down first
6. □ VIX spike (+30%+)
7. □ Fed or policy reversal signals

**Execution example:**

```
Conditions check:
[✓] 1. Weekly lower highs
[✓] 2. Volume declining 3 weeks
[×] 3. Margin debt still elevated
[✓] 4. Google trends -40%
[×] 5. Still broad rally
[✓] 6. VIX +35% spike
[×] 7. No policy change

→ 4/7 met, short consideration OK
→ Small size (25% of normal) test entry
```

---

## Common Failure Patterns & Solutions

### Failure 1: "Too late" mentality, perpetual waiting

**Psychology:** Regret aversion (FOMO about missing out)
**Solution:**
- Run Bubble-O-Meter when feeling too late
- If score <=7, small entry OK
- If score 8-9, enter only on exceptional setups with reduced size
- If score >=10, correct to wait

### Failure 2: Re-entry after taking profits (buying high)

**Psychology:** Hindsight bias ("I knew it would go up")
**Solution:**
- 72-hour re-entry ban after profit-taking
- Re-entry only after Bubble-O-Meter check

### Failure 3: "Still going up" paralysis on profit-taking

**Psychology:** Greed + Overconfidence
**Solution:**
- Automate stair-step (preset limit orders)
- Target "satisfaction" not "perfection"

### Failure 4: Premature short selling

**Psychology:** Subjective "obviously too high"
**Solution:**
- Mechanically check composite conditions
- Wait for minimum 3 conditions

---

## Emergency Response Flowchart

```
Market shock detected
    ↓
Q: Have positions?
    ↓YES
Q: Down -5%+ ?
    ↓YES
Q: ATR stop hit?
    ↓YES
→ Sell immediately (no debate)

    ↓NO (stop not hit)
Q: Bubble-O-Meter 13+?
    ↓YES
→ Consider 75%+ profit-taking

    ↓NO (score ≤12)
Q: VIX spike +30%+?
    ↓YES
→ Take 50% profits, tighten stops on rest

    ↓NO
→ Normal monitoring, stay calm
```

---

## Golden Rules (Post on Your Wall)

1. **Watch the process, not the price**

2. **When taxi drivers talk stocks, exit**

3. **"This time is different" is the same every time**

4. **Mechanical rules protect your psychology**

5. **Short after confirmation, take profits early**

6. **When skepticism hurts socially, the end begins**

7. **Aim for satisfaction, abandon perfection**

8. **Bubbles last longer than expected, crashes faster**

9. **Leverage is an express ticket to ruin**

10. **"Markets can remain irrational longer than you can remain solvent"**

---

## Key Data Sources

### Instantly Accessible Indicators

| Indicator | Source | URL Example |
|-----------|--------|-------------|
| Google Search Trends | Google Trends | trends.google.com |
| VIX (Fear Index) | CBOE | cboe.com/vix |
| Put/Call Ratio | CBOE | cboe.com/data |
| Margin Debt | FINRA | finra.org/data |
| Futures Positioning | CFTC COT | cftc.gov/reports |
| IPO Statistics | Renaissance IPO | renaissancecapital.com |

### API-Accessible for Automation

```python
# Example: Google Trends (pytrends)
from pytrends.request import TrendReq
pytrends = TrendReq()
pytrends.build_payload(['SPY', 'stock market'])
data = pytrends.interest_over_time()

# Example: VIX (yfinance)
import yfinance as yf
vix = yf.Ticker('^VIX')
current_vix = vix.history(period='1d')['Close'].iloc[-1]
```

---

## Further Learning

### Books
- "Manias, Panics, and Crashes" - Charles Kindleberger
- "Irrational Exuberance" - Robert Shiller
- "The Alchemy of Finance" - George Soros

### Research
- Hyman Minsky's Financial Instability Hypothesis
- Behavioral Finance classics

### Data & Tools
- TradingView: Charts & technical indicators
- FRED (Federal Reserve): Economic time series
- Finviz: Screening & heatmaps
- Google Trends: Social trends

---

**Last Updated:** 2025 Edition
**License:** Educational/personal use only
