# Bubble Detector Implementation Guide (Revised v2.0)

## Required Checklist Before Use

### Pre-verification
```
□ User is asking "Is it a bubble?"
□ Objective evaluation is requested (not impressions)
□ You have time to collect measured data
```

---

## Step-by-Step Evaluation Process

### Step 1: Identify Market and Verify Data Sources

**For US Market:**
```
Required Data Sources:
1. CBOE - Put/Call ratio, VIX
2. FINRA - Margin debt balance
3. Renaissance Capital - IPO statistics
4. Barchart/TradingView - Breadth indicators
```

**For Japanese Market:**
```
Required Data Sources:
1. Barchart - Nikkei Futures Options P/C
2. Investing.com - JNIVE (Nikkei VI)
3. JSF - Margin debt balance
4. MacroMicro - TOPIX Breadth
5. PwC - Global IPO Watch
```

### Step 2: Quantitative Data Collection (MANDATORY)

**Use web_search to collect the following in order:**

```python
# US Market Example
queries = [
    "CBOE put call ratio current",  # P/C ratio
    "VIX index current level",       # VIX
    "FINRA margin debt latest",      # Margin debt
    "S&P 500 breadth 50 day MA",     # Breadth
    "Renaissance IPO market 2025",   # IPO statistics
]

# Japanese Market Example
queries_japan = [
    "Nikkei 225 futures options put call ratio",
    "Nikkei Volatility Index JNIVE current",
    "JSF margin trading balance latest",
    "TOPIX constituent stocks 200 day moving average",
    "Japan IPO market 2025 statistics",
]
```

**Important: Collect specific numerical values for each search**
- ❌ "VIX is at low levels" → Insufficient
- ✅ "VIX is 15.3" → OK

### Step 3: Organize and Verify Data

Organize collected data in table format:

```markdown
| Indicator | Collected Value | Source | Collection Date |
|-----------|----------------|---------|----------------|
| Put/Call | 0.95 | CBOE | 2025-10-27 |
| VIX | 15.3 | Yahoo Finance | 2025-10-27 |
| Margin YoY | +8% | FINRA | 2025-09 |
| Breadth (50DMA) | 68% | Barchart | 2025-10-27 |
| IPO Count | 45/Q3 | Renaissance | 2025 Q3 |
```

**Verification Points:**
- □ All indicators have specific numerical values
- □ Sources are reliable
- □ Data is recent (within 1 week)

### Step 4: Mechanical Scoring

**Score mechanically by referring to threshold tables:**

```
Indicator 1: Put/Call = 0.95
  → 0.95 > 0.85 → 0 points

Indicator 2: VIX = 15.3 + near highs
  → VIX > 15 → 0 points

Indicator 3: Margin YoY = +8%
  → +8% < +10% → 0 points

Indicator 4: IPO = 45 count (5-year average 35)
  → 45/35 = 1.29x < 1.5x → 0 points

Indicator 5: Breadth = 68%
  → 68% > 60% → 0 points

Indicator 6: Price Acceleration (requires calculation)
  → Past 3 months +12%, 75th percentile in 10-year distribution → 0 points

Phase 2 Total: 0 points
```

### Step 5: Qualitative Adjustment (Upper limit +3 points, STRICT CRITERIA)

**⚠️ CRITICAL: Qualitative adjustments require MEASURABLE evidence. Subjective impressions are NOT allowed.**

**Confirmation Bias Prevention Checklist:**
```
Before adding any qualitative points, verify:
□ Do you have concrete, measurable data? (not impressions)
□ Would an independent observer reach the same conclusion?
□ Are you avoiding double-counting with Phase 2 quantitative scores?
□ Have you documented the specific evidence?
```

**A. Social Penetration (0-1 points):**
```
REQUIRED EVIDENCE (all three must be present for +1 point):
✓ Direct user report: "Non-investor asked me about [asset]"
✓ Specific examples: Names, dates, conversations
✓ Multiple independent sources (minimum 3)

Scoring:
+1 point: All three criteria met (taxi driver/barber investment advice)
+0 points: Any criteria missing

Example of VALID evidence:
"User reported: 'My barber asked me about NVDA stock on Nov 1.
My dentist mentioned AI stocks on Nov 2.
My Uber driver discussed crypto on Nov 3.'"

Example of INVALID evidence:
"AI narrative is prevalent" (too vague, unmeasurable)
```

**B. Media/Search Trends (0-1 points):**
```
REQUIRED EVIDENCE (measurable data only):
✓ Google Trends data showing 5x+ increase YoY
✓ Mainstream media coverage count (Time/Newsweek covers, TV specials)
✓ Web search data from multiple sources confirming saturation

Scoring:
+1 point: Search trends 5x+ baseline AND mainstream coverage confirmed
+0 points: Search trends <5x OR no mainstream coverage confirmation

⚠️ CRITICAL: "Elevated narrative" without data = +0 points

How to verify:
1. Use Google Trends API or web search for "[topic] search volume 2025"
2. Search for "[topic] Time magazine cover" or "[topic] CNBC special"
3. Document specific numbers and dates

Example of VALID evidence:
"Google Trends shows 'AI stocks' at 780 (baseline 150 = 5.2x).
Time Magazine cover 'The AI Revolution' (Oct 15, 2025).
CNBC aired 'AI Investment Special' (3 episodes in Oct 2025)."

Example of INVALID evidence:
"AI/technology narrative seems elevated" (unmeasurable)
```

**C. Valuation Disconnect (0-1 points):**
```
⚠️ WARNING: Avoid double-counting with Phase 2 quantitative scores

REQUIRED EVIDENCE:
✓ P/E ratio >25 (if not already counted in Phase 2)
✓ Narrative explicitly ignores fundamentals
✓ "This time is different" reasoning documented in mainstream media

Scoring:
+1 point: P/E >25 AND fundamentals actively ignored in public discourse
+0 points: High P/E but fundamentals support valuation

Self-check questions:
- Is this already captured in Phase 2 quantitative scoring? If yes, +0 points
- Do companies have real earnings supporting valuations? If yes, +0 points
- Is the narrative backed by fundamental improvements? If yes, +0 points

Example of VALID evidence for +1 point:
"S&P 500 P/E = 35x (vs. historical 18x).
Mainstream articles: 'Earnings don't matter in AI era' (CNBC, Oct 2025).
'Traditional valuation metrics obsolete' (Bloomberg, Nov 2025)."

Example of INVALID evidence:
"P/E 30.8 but AI has fundamental backing" (fundamentals support valuation = +0)
```

**Phase 3 Adjustment Calculation:**
```
Maximum possible: +3 points (1+1+1)

Common mistakes to avoid:
❌ Adding points based on "feeling" or "sense"
❌ Double-counting valuation already in Phase 2
❌ Accepting narrative claims without measuring data
✅ Require concrete, independently verifiable evidence
✅ Document specific sources and dates
✅ Apply strict interpretation standards
```

### Step 6: Final Judgment and Report

```markdown
# [Market Name] Bubble Evaluation Report (Revised v2.0)

## Overall Assessment
- Final Score: 0/16 points
- Phase: Normal
- Risk Level: Low
- Evaluation Date: 2025-10-27

## Quantitative Data (Phase 2)

| Indicator | Measured Value | Score | Rationale |
|-----------|----------------|-------|-----------|
| Put/Call | 0.95 | 0 pts | > 0.85 healthy |
| VIX + Highs | 15.3 | 0 pts | > 15 normal |
| Margin YoY | +8% | 0 pts | < +10% normal |
| IPO Heat | 1.29x | 0 pts | < 1.5x |
| Breadth | 68% | 0 pts | > 60% healthy |
| Price Accel | 75th %ile | 0 pts | < 85th %ile |

**Phase 2 Total: 0 points**

## Qualitative Adjustment (Phase 3)

- Social Penetration: No user reports (+0 pts)
- Media: Google Trends 1.8x (+0 pts)
- Valuation: P/E 21x (+0 pts)

**Phase 3 Adjustment: +0 points**

## Recommended Actions

**Risk Budget: 100%**
- Continue normal investment strategy
- Set ATR 2.0× trailing stop
- Apply stair-step profit-taking rule (+20% take 25%)

**Short-Selling: Not Allowed**
- Composite conditions: 0/7 met
```

---

## NG Examples vs OK Examples

### NG Example 1: No Data Collection

```
❌ Bad Evaluation:
"Many Takaichi Trade reports"
"Experts warn of overheating"
→ Media saturation 2 points

✅ Good Evaluation:
[web_search: "Google Trends Japan stocks Takaichi"]
Result: 1.8x year-over-year
→ Google Trends adjustment +0 points (below 3x)
```

### NG Example 2: Scoring Based on Impressions

```
❌ Bad Evaluation:
"VIX seems to be at low levels"
→ Volatility suppression 2 points

✅ Good Evaluation:
[web_search: "VIX current level"]
Result: VIX 15.8
→ VIX > 15 = 0 points
```

### NG Example 3: Emotional Reaction to Price Rise

```
❌ Bad Evaluation:
"2,100 yen rise in one day is abnormal"
→ Price acceleration 2 points

✅ Good Evaluation:
[Verify daily return distribution over past 10 years]
4.5% rise = 80th percentile over past 10 years (rare but not extreme)
→ Price acceleration 0 points
```

---

## Self-Check: Quality of Evaluation

After completing evaluation, verify the following:

```
□ Did you collect data for all indicators in Phase 1?
  - Put/Call: [  ]
  - VIX: [  ]
  - Margin: [  ]
  - Breadth: [  ]
  - IPO: [  ]
  - Price Distribution: [  ]

□ Does each score have measured value basis?
  - Have you excluded impressions like "many reports"?

□ Did you keep qualitative adjustment within +5 point limit?
  - Adjustment A: [  ] points
  - Adjustment B: [  ] points
  - Adjustment C: [  ] points
  - Total ≤ 5 points?

□ Is the final score reasonable?
  - Compare with other quantitative frameworks
  - Re-verify if there is a difference of 10+ points
```

---

## Evaluation Quality Judgment Criteria

### Level 1: Failed (Insufficient Data)
```
- Quantitative data collection for 3 or fewer of 6 indicators
- Scoring based on impressions
- No source documentation
```

### Level 2: Pass Minimum (Needs Improvement)
```
- Quantitative data collection for 4-5 of 6 indicators
- Some impression-based evaluation mixed in
- Source documentation present but incomplete
```

### Level 3: Good (Recommended Level)
```
- Quantitative data collection for all 6 indicators
- Mechanical scoring implemented
- Source and date for all data
- Qualitative adjustment is conservative (+2 points or less)
```

### Level 4: Excellent (Best Practice)
```
- Perfect quantitative data collection
- Comparative analysis with historical data
- Cross-check with multiple sources
- Consistency check with quantitative frameworks
- Explicit statement of uncertainties
```

---

## Evaluation Report Template

```markdown
# [Market Name] Bubble Evaluation Report v2.0

**Evaluation Date:** YYYY-MM-DD
**Evaluator Confidence:** [0-100]
**Data Completeness:** [0-100]%

---

## Executive Summary

**Conclusion:** [One-sentence conclusion]
**Score:** X/16 points ([Normal/Caution/Euphoria/Critical])
**Recommendation:** [Concise action]

---

## Quantitative Evaluation (Phase 2)

[Table of 6 indicators]

**Phase 2 Total:** X points

---

## Qualitative Adjustment (Phase 3)

[3 adjustment items]

**Phase 3 Adjustment:** +Y points

---

## Final Judgment

**Final Score:** X + Y = Z points
**Risk Budget:** [0-100]%
**Recommended Actions:**
1. [Specific action 1]
2. [Specific action 2]
3. [Specific action 3]

---

## Data Quality Notes

**Collected Data:**
- [Indicator name]: [value] ([source], [date])
- ...

**Limitations:**
- [Document if there are data constraints]

**Confidence Level:**
- Confidence in this evaluation: [reason]
```

---

## Red Flags During Review

If any of the following are observed, redo the evaluation:

```
🚩 "Many reports" → No numbers
🚩 "Experts are cautious" → No quantitative data
🚩 "Obviously too high" → Subjective judgment
🚩 Score 10+ points but Put/Call > 1.0
🚩 Score 10+ points but VIX > 20
🚩 Score 10+ points but Margin YoY < +15%
🚩 No data source documentation
🚩 No collection date documentation
```

---

## Reference Materials

### Data Analysis Principles
- "In God we trust; all others must bring data." - W. Edwards Deming
- "Without data, you're just another person with an opinion." - W. Edwards Deming

### Guarding Against Biases
- Confirmation bias: Collecting only information that supports your hypothesis
- Availability bias: Overweighting recently seen information
- Narrative fallacy: Oversimplifying causal relationships with stories

---

## Final Check

Before submitting evaluation:

```
□ All quantitative data have numerical values
□ All data have sources and dates
□ Excluded impressions and emotional expressions
□ Scored mechanically
□ Qualitative adjustment is conservative (+2 points or less recommended)
□ Consistency verified with other quantitative frameworks
□ Uncertainties explicitly stated
```

**If all of these are ✓, you are ready to report.**

---

**Last Updated:** 2025-10-27
**Next Review:** Reflect feedback after actual evaluation implementation
