---
name: us-market-bubble-detector
description: "Evaluates market bubble risk through quantitative data-driven analysis using the revised Minsky/Kindleberger framework v2.1. Prioritizes objective metrics (Put/Call, VIX, margin debt, breadth, IPO data) over subjective impressions. Features strict qualitative adjustment criteria with confirmation bias prevention. Supports practical investment decisions with mandatory data collection and mechanical scoring. Use when user asks about bubble risk, valuation concerns, or profit-taking timing."
---

# US Market Bubble Detection Skill (v2.1)

## When to Use This Skill

Use this skill when:

**English:**
- User asks "Is the market in a bubble?" or "Are we in a bubble?"
- User seeks advice on profit-taking, new entry timing, or short-selling decisions
- User reports social phenomena (non-investors entering, media frenzy, IPO flood)
- User mentions narratives like "this time is different" or "revolutionary technology" becoming mainstream
- User consults about risk management for existing positions

**Japanese:**
- ユーザーが「今の相場はバブルか?」と尋ねる
- 投資の利確・新規参入・空売りのタイミング判断を求める
- 社会現象(非投資家の参入、メディア過熱、IPO氾濫)を観察し懸念を表明
- 「今回は違う」「革命的技術」などの物語が主流化している状況を報告
- 保有ポジションのリスク管理方法を相談

---

## Evaluation Process (Strict Order)

### Phase 1: Mandatory Quantitative Data Collection

**CRITICAL: Always collect the following data before starting evaluation**

#### 1.1 Market Structure Data (Highest Priority)
```
□ Put/Call Ratio (CBOE Equity P/C)
  - Source: CBOE DataShop or web_search "CBOE put call ratio"
  - Collect: 5-day moving average

□ VIX (Fear Index)
  - Source: Yahoo Finance ^VIX or web_search "VIX current"
  - Collect: Current value + percentile over past 3 months

□ Volatility Indicators
  - 21-day realized volatility
  - Historical position of VIX (determine if in bottom 10th percentile)
```

#### 1.2 Leverage & Positioning Data
```
□ FINRA Margin Debt Balance
  - Source: web_search "FINRA margin debt latest"
  - Collect: Latest month + Year-over-Year % change

□ Breadth (Market Participation)
  - % of S&P 500 stocks above 50-day MA
  - Source: web_search "S&P 500 breadth 50 day moving average"
```

#### 1.3 IPO & New Issuance Data
```
□ IPO Count & First-Day Performance
  - Source: Renaissance Capital IPO or web_search "IPO market 2025"
  - Collect: Quarterly count + median first-day return
```

**Do NOT proceed with evaluation without Phase 1 data collection.**

---

### Phase 2: Quantitative Scoring

Score mechanically based on collected data. **Phase 2 Total: 0-12 points.**

| Indicator | 2 points | 1 point | 0 points |
|-----------|----------|---------|----------|
| **Put/Call Ratio** | P/C < 0.70 | P/C 0.70-0.85 | P/C > 0.85 |
| **VIX + Highs** | VIX < 12 AND within 5% of 52-week high | VIX 12-15 AND near highs | VIX > 15 OR >10% from highs |
| **Margin Debt** | YoY +20%+ AND all-time high | YoY +10-20% | YoY +10% or less / negative |
| **IPO Overheating** | Quarterly count >2x 5yr avg AND median 1st-day return +20%+ | Count >1.5x 5yr avg | Normal levels |
| **Breadth Anomaly** | New high AND <45% above 50DMA | 45-60% above 50DMA | >60% above 50DMA |
| **Price Acceleration** | 3-month return >95th percentile (10yr) | 85-95th percentile | Below 85th percentile |

---

### Phase 3: Qualitative Adjustment (max +3 points)

**Confirmation bias prevention -- before adding ANY qualitative points:**
```
□ Do I have concrete, measurable data? (not impressions)
□ Would an independent observer reach the same conclusion?
□ Am I avoiding double-counting with Phase 2 scores?
□ Have I documented specific evidence with sources?
```

#### Adjustment A: Social Penetration (0-1 points)
```
+1 point: ALL THREE criteria must be met:
  ✓ Direct user report of non-investor recommendations
  ✓ Specific examples with names/dates/conversations
  ✓ Multiple independent sources (minimum 3)

+0 points: Any criteria missing

✅ VALID: "My barber asked about NVDA (Nov 1), dentist mentioned AI stocks (Nov 2),
Uber driver discussed crypto (Nov 3)"
❌ INVALID: "Everyone is talking about stocks" (vague, unverified)
```

#### Adjustment B: Media/Search Trends (0-1 points)
```
+1 point: BOTH criteria must be met:
  ✓ Google Trends showing 5x+ YoY increase (measured)
  ✓ Mainstream coverage confirmed (Time covers, TV specials with dates)

+0 points: Search trends <5x OR no mainstream coverage

✅ VALID: "Google Trends: 'AI stocks' at 780 (baseline 150 = 5.2x).
Time cover 'AI Revolution' (Oct 15, 2025)."
❌ INVALID: "AI/technology narrative seems elevated" (unmeasurable)
```

#### Adjustment C: Valuation Disconnect (0-1 points)
```
+1 point: ALL criteria must be met:
  ✓ P/E >25 (if NOT already counted in Phase 2)
  ✓ Fundamentals explicitly ignored in mainstream discourse
  ✓ "This time is different" documented in major media

+0 points: P/E <25 OR fundamentals support valuations

Self-check (if ANY is YES, score = 0):
- Is P/E already in Phase 2 scoring?
- Do companies have real earnings supporting valuations?
- Is the narrative backed by fundamental improvements?
```

---

### Phase 4: Final Judgment

```
Final Score = Phase 2 (0-12) + Phase 3 (0 to +3) = 0 to 15 points

| Score   | Phase          | Risk Budget | Short-Selling            |
|---------|----------------|-------------|--------------------------|
| 0-4     | Normal         | 100%        | Not allowed              |
| 5-7     | Caution        | 70-80%      | Not recommended          |
| 8-9     | Elevated Risk  | 50-70%      | Consider cautiously      |
| 10-12   | Euphoria       | 40-50%      | Active consideration     |
| 13-15   | Critical       | 20-30%      | Recommended              |
```

---

## Recommended Actions by Bubble Stage

### Normal (0-4 points) -- Risk Budget: 100%
- Continue normal investment strategy
- Set ATR 2.0x trailing stop
- Apply stair-step profit-taking rule (+20% take 25%)

### Caution (5-7 points) -- Risk Budget: 70-80%
- Begin partial profit-taking (20-30% reduction)
- Tighten ATR to 1.8x
- Reduce new position sizing by 50%

### Elevated Risk (8-9 points) -- Risk Budget: 50-70%
- Increase profit-taking (30-50% reduction)
- Tighten ATR to 1.6x
- New positions: highly selective, quality only
- Begin building cash reserves
- Short-selling: only after 2/7 composite conditions met, small positions (10-15% of normal), strict stop-loss (ATR 2.0x)

### Euphoria (10-12 points) -- Risk Budget: 40-50%
- Accelerate stair-step profit-taking (50-60% reduction)
- Tighten ATR to 1.5x
- No new long positions except on major pullbacks
- Short-selling: after 3/7 composite conditions, small positions (20-25%), defined risk only (options, tight stops)

### Critical (13-15 points) -- Risk Budget: 20-30%
- Major profit-taking or full hedge implementation
- ATR 1.2x or fixed stop-loss
- Cash preservation mode
- Short-selling: after 5/7 composite conditions, scale in with pyramiding, consider put options

---

## Composite Conditions for Short-Selling (7 Items)

```
1. Weekly chart shows lower highs
2. Volume peaks out
3. Leverage indicators drop sharply (margin debt decline)
4. Media/search trends peak out
5. Weak stocks start to break down first
6. VIX surges (spike above 20)
7. Fed/policy shift signals
```

---

## Output Format

```markdown
# [Market Name] Bubble Evaluation Report

## Overall Assessment
- Final Score: X/15 points
- Phase: [Normal/Caution/Elevated Risk/Euphoria/Critical]
- Risk Level: [Low/Medium/Medium-High/High/Extremely High]
- Evaluation Date: YYYY-MM-DD

## Quantitative Evaluation (Phase 2)

| Indicator | Measured Value | Score | Rationale |
|-----------|----------------|-------|-----------|
| Put/Call | [value] | [0-2] | [reason] |
| VIX + Highs | [value] | [0-2] | [reason] |
| Margin YoY | [value] | [0-2] | [reason] |
| IPO Heat | [value] | [0-2] | [reason] |
| Breadth | [value] | [0-2] | [reason] |
| Price Accel | [value] | [0-2] | [reason] |

**Phase 2 Total: X/12 points**

## Qualitative Adjustment (Phase 3)
- [ ] Confirmation bias checklist completed
- A. Social Penetration: [+0 or +1] -- [evidence]
- B. Media/Search Trends: [+0 or +1] -- [evidence]
- C. Valuation Disconnect: [+0 or +1] -- [evidence]

**Phase 3 Total: +X/3 points**

## Recommended Actions
**Risk Budget: X%** (Phase: [phase name])
- [action 1]
- [action 2]
- [action 3]

**Short-Selling:** [status] -- Composite conditions: X/7 met
```

---

## Data Sources

| Data | US Source | Japanese Source |
|------|----------|----------------|
| Put/Call | [CBOE](https://www.cboe.com/tradable_products/vix/) | [Barchart Nikkei](https://www.barchart.com/futures/quotes/NO*0/options) |
| VIX | [Yahoo ^VIX](https://finance.yahoo.com/) / [CBOE](https://www.cboe.com/) | [JNIVE](https://www.investing.com/indices/nikkei-volatility-historical-data) |
| Margin Debt | [FINRA](https://www.finra.org/investors/learn-to-invest/advanced-investing/margin-statistics) | JSF Monthly Report |
| Breadth | [Barchart S&P](https://www.barchart.com/stocks/indices/sp/sp500?viewName=advanced) | [MacroMicro](https://en.macromicro.me/series/31841/japan-topix-index-200ma-breadth) |
| IPO | [Renaissance Capital](https://www.renaissancecapital.com/IPO-Center/Stats) | [PwC IPO Watch](https://www.pwc.co.uk/services/audit/insights/global-ipo-watch.html) |

---

## Core Principles

1. **Data > Impressions**: Ignore "many news reports" or "experts are cautious" without quantitative data
2. **Strict Order**: Phase 1 (Data) -> Phase 2 (Quantitative) -> Phase 3 (Qualitative) -- never skip or reorder
3. **Qualitative Ceiling**: +3 points maximum -- qualitative cannot override quantitative evaluation
4. **Social Penetration Standard**: Require direct, dated, specific non-investor reports -- not vague claims

---

## Reference Documents

Load references selectively based on need:

- **`references/implementation_guide.md`** (English) -- First use, detailed guidance, common failure patterns, self-check criteria
- **`references/bubble_framework.md`** (Japanese) -- Minsky/Kindleberger theory, behavioral psychology
- **`references/historical_cases.md`** (Japanese) -- Dotcom, Crypto, Pandemic bubble case studies
- **`references/quick_reference.md`** / **`quick_reference_en.md`** -- Daily checklist, emergency 3-question assessment, quick scoring
