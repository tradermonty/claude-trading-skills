# Bubble Detection Quick Reference

## Daily Checklist (Complete in 5 Minutes)

### Morning Routine (Before Market Open)

```
□ Step 1: Update Bubble-O-Meter (2 minutes)
   - Score 8 indicators on 0-2 scale
   - Confirm risk budget based on total score

□ Step 2: Position Management (2 minutes)
   - Update ATR trailing stops
   - Check if stair-step profit-taking targets reached
   - Determine new entry eligibility

□ Step 3: Signal Confirmation (1 minute)
   - Media/social media trends (Google Trends, Twitter)
   - Major indices' distance from 52-week highs
   - VIX & Put/Call ratio
```

---

## Emergency Assessment: 3 Questions

When uncertain about investment decisions, answer these 3 questions:

### Q1: "Are non-investors recommending?"
- YES → Mass penetration complete, likely late stage
- NO → Still early-to-mid stage

### Q2: "Has the narrative become 'common sense'?"
- YES → Euphoria stage, dissent socially unacceptable
- NO → Skeptical views still tolerated, healthy state

### Q3: "Is 'this time is different' the mantra?"
- YES → Historically typical bubble sign
- NO → Healthy caution still functioning

**All 3 YES → Critical zone, prioritize profit-taking/exit**

---

## Action Matrix by Bubble Stage (REVISED v2.1)

| Phase | Score | Risk Budget | Entry | Profit-Taking | Stop | Shorts |
|-------|-------|------------|-------|--------------|------|--------|
| **Normal** | 0-4 | 100% | Normal | At target | 2.0 ATR | No |
| **Caution** | 5-7 | 70-80% | 50% reduced | 25% at +20% | 1.8 ATR | No |
| **Elevated Risk** | 8-9 | 50-70% | Selective | 40% at +20% | 1.6 ATR | Consider |
| **Euphoria** | 10-12 | 40-50% | Stop | 50% at +20% | 1.5 ATR | After conditions |
| **Critical** | 13-15 | 20-30% | Stop | 75-100% immediate | 1.2 ATR | Recommended |

**Note**: Maximum score reduced from 16 to 15 points (Phase 2: max 12, Phase 3: max 3)

---

## Quick Scoring for 8 Indicators

### 1. Mass Penetration
```
0 points: Investors only
1 point: General awareness but investment still limited
2 points: Taxi drivers/family recommending
```

### 2. Media Saturation
```
0 points: Normal coverage level
1 point: Search trends 2-3x
2 points: TV specials/magazine covers, searches 5x+
```

### 3. New Entrants
```
0 points: Normal account opening pace
1 point: 50-100% YoY increase
2 points: 200%+ YoY, beginner flood
```

### 4. Issuance Flood
```
0 points: Normal IPO count
1 point: 50% increase in IPOs/related products
2 points: Low-quality IPOs, theme ETF proliferation
```

### 5. Leverage
```
0 points: Normal range
1 point: Margin balance 1.5x
2 points: All-time high, funding rates elevated
```

### 6. Price Acceleration
```
0 points: Near historical median
1 point: Exceeds 90th percentile
2 points: 95-99th percentile or accelerating
```

### 7. Valuation Disconnect
```
0 points: Explainable by fundamentals
1 point: High valuation but explained by growth expectations
2 points: Completely "narrative"-dependent, fundamentals ignored
```

### 8. Correlation & Breadth
```
0 points: Only some leaders rising
1 point: Sector-wide spread
2 points: Even low-quality/zombie companies rallying
```

---

## Key Data Sources

### Instantly Checkable Indicators

| Indicator | Source | Example URL |
|-----------|--------|------------|
| Google Search Trends | Google Trends | trends.google.com |
| VIX (Fear Index) | CBOE | cboe.com/vix |
| Put/Call Ratio | CBOE | cboe.com/data |
| Margin Balance | FINRA | finra.org/data |
| Futures Positions | CFTC COT | cftc.gov/reports |
| IPO Statistics | Renaissance IPO | renaissancecapital.com |

### API-Accessible Auto-Retrieval

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

## Profit-Taking Strategy Templates

### Template 1: Stair-Step Profit-Taking (Conservative)

```
Position: $10,000 initial investment
Targets:  +20%, +40%, +60%, +80%

+20% ($12,000) → Sell 25% = $3,000 secured
+40% ($14,000) → Sell 25% = $3,500 secured
+60% ($16,000) → Sell 25% = $4,000 secured
+80% ($18,000) → Sell 25% = $4,500 secured

Total profits: $15,000 (+50% equivalent)
```

### Template 2: ATR Trailing (Aggressive)

```python
def calculate_trailing_stop(current_price, atr_20d, bubble_phase):
    """
    Calculate trailing stop based on bubble stage

    bubble_phase: 'normal', 'caution', 'euphoria', 'critical'
    """
    multipliers = {
        'normal': 2.0,
        'caution': 1.8,
        'euphoria': 1.5,
        'critical': 1.2
    }
    multiplier = multipliers.get(bubble_phase, 2.0)
    stop_price = current_price - (atr_20d * multiplier)
    return stop_price

# Usage example
current_price = 450.0
atr_20d = 10.0  # Average True Range over 20 days
bubble_phase = 'euphoria'

stop = calculate_trailing_stop(current_price, atr_20d, bubble_phase)
print(f"Trailing Stop: ${stop:.2f}")
# Output: Trailing Stop: $435.00
```

### Template 3: Hybrid (Recommended)

```
Stage 1 (Boom period):
  → Reduce 50% of position via stair-step profit-taking

Stage 2 (Euphoria period):
  → Apply ATR trailing to remaining 50%, follow upside

Stage 3 (Panic signs):
  → Exit immediately when ATR stop hit
```

---

## Short-Selling Timing Assessment (Critical)

### ❌ Absolutely NG: Early Contrarian

```
Reason: Normal for prices to rise 2-3x more after feeling "too high"
Risk: "Markets can remain irrational longer than you can remain solvent"
```

### ✅ Recommended: After Composite Conditions Clear

**Consider starting when at least 3 apply:**

1. □ Weekly chart shows clear lower highs
2. □ Volume peaks out (3 consecutive weeks declining)
3. □ Sharp drop in leverage indicators (margin balance -20%+)
4. □ Media/search trends peak out
5. □ Weak stocks within sector start breaking down first
6. □ VIX surges (+30%+)
7. □ Fed/policy shift signals

**Execution Example:**

```
Condition Check:
[✓] 1. Weekly lower highs forming
[✓] 2. Volume declining 3 weeks straight
[×] 3. Margin balance still elevated
[✓] 4. Google search trends -40%
[×] 5. Still broad rally continuing
[✓] 6. VIX +35% surge
[×] 7. No policy changes

→ 4/7 met, shorts consideration OK
→ Small position (25% of normal) for test entry
```

---

## Common Failure Patterns & Solutions

### Failure 1: "Too late" paralysis, missing opportunities

**Psychology:** Regret aversion (fear of being late)
**Solution:**
- Conduct Bubble-O-Meter when feeling "too late"
- Score ≤8: Small position entry OK
- Score ≥9: Correct to stay out

### Failure 2: Re-entry after profit-taking (buying high)

**Psychology:** Hindsight bias ("knew it would go higher")
**Solution:**
- 72-hour no re-entry rule after profit-taking
- Re-entry decisions only after Bubble-O-Meter check

### Failure 3: Can't take profits due to "still rising"

**Psychology:** Greed + Overconfidence
**Solution:**
- Automate stair-step profit-taking (pre-set limit orders)
- Aim for "satisfaction," abandon "perfection"

### Failure 4: Too-early shorts

**Psychology:** Subjective "obviously too high" judgment
**Solution:**
- Mechanically verify composite conditions
- Wait for minimum 3 conditions to clear

---

## Emergency Response Flowchart

```
Detect market volatility
    ↓
Q: Have positions?
    ↓YES
Q: Down -5% or more?
    ↓YES
Q: ATR stop reached?
    ↓YES
→ Sell immediately (no debate)

    ↓NO (Stop not reached)
Q: Bubble-O-Meter score 13+?
    ↓YES
→ Consider 75%+ profit-taking

    ↓NO (Score ≤12)
Q: VIX surge +30%+?
    ↓YES
→ 50% profit-taking, tighten remaining stops

    ↓NO
→ Business as usual, continue calm observation
```

---

## Golden Rules (10 Commandments to Post on Wall)

1. **See process, not price**

2. **When taxi drivers talk stocks, exit**

3. **"This time is different" is always the same**

4. **Mechanical rules protect psychology**

5. **Short after confirmation, take profits early**

6. **When skepticism hurts, the end begins**

7. **Aim for satisfaction, abandon perfection**

8. **Bubbles last longer than expected, collapses are faster**

9. **Leverage is an express ticket to ruin**

10. **"Markets can remain irrational longer than you can remain solvent"**

---

## Resources for Further Learning

### Books
- **"Manias, Panics, and Crashes"** - Charles Kindleberger
- **"Irrational Exuberance"** - Robert Shiller
- **"The Alchemy of Finance"** - George Soros

### Research
- Hyman Minsky's Financial Instability Hypothesis
- Classic papers in Behavioral Finance

### Data & Tools
- **TradingView**: Charts and technical indicators
- **FRED (Federal Reserve)**: Economic indicator time series
- **Finviz**: Screening and heatmaps
- **Google Trends**: Social trends

---

**Last Updated:** 2025 Edition
**License:** Educational and personal use only, redistribution prohibited
