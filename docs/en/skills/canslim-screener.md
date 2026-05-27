---
layout: default
title: "CANSLIM Screener"
grand_parent: English
parent: Skill Guides
nav_order: 14
lang_peer: /ja/skills/canslim-screener/
permalink: /en/skills/canslim-screener/
---

# CANSLIM Screener
{: .no_toc }

Screen US stocks using William O'Neil's CANSLIM growth stock methodology. Use when user requests CANSLIM stock screening, growth stock analysis, momentum stock identification, or wants to find stocks with strong earnings and price momentum following O'Neil's investment system.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/canslim-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/canslim-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill screens US stocks using William O'Neil's proven CANSLIM methodology, a systematic approach for identifying growth stocks with strong fundamentals and price momentum. CANSLIM analyzes 7 key components: **C**urrent Earnings, **A**nnual Growth, **N**ewness/New Highs, **S**upply/Demand, **L**eadership/RS Rank, **I**nstitutional Sponsorship, and **M**arket Direction.

**Phase 3** implements all 7 of 7 components (C, A, N, S, L, I, M), representing **100% of the full methodology**.

**Two-Stage Approach:**
1. **Stage 1 (FMP API + Finviz)**: Analyze stock universe with all 7 CANSLIM components
2. **Stage 2 (Reporting)**: Rank by composite score and generate actionable reports

**Key Features:**
- Composite scoring (0-100 scale) with weighted components
- **Finviz fallback** for institutional ownership data (automatic when FMP data incomplete)
- Progressive filtering to optimize API usage
- JSON + Markdown output formats
- Interpretation bands: Exceptional+ (90+), Exceptional (80-89), Strong (70-79), Above Average (60-69)
- Bear market protection (M component gating)

**Phase 3.1 Component Weights (Original O'Neil weights):**
- C (Current Earnings): 15%
- A (Annual Growth): 20%
- N (Newness): 15%
- S (Supply/Demand): 15%
- L (Leadership/RS Rank): 20% — multi-period weighted RS (3m/6m/12m vs configurable benchmark)
- I (Institutional): 10%
- M (Market Direction): 5%

**Weighted RS Formula:**
```
Weighted RS = 0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m
```
Available periods are re-normalized when some are missing. Default benchmark is `^GSPC`;
override with `--rs-benchmark SPY/QQQ/IWM/...`.

**Fallback hierarchy when multi-period data is incomplete:**
1. No benchmark → weighted absolute stock performance + 20% penalty.
2. All multi-period windows missing but >=50 bars of price history → fall back to the
   legacy 365-day full-window absolute return as the scoring input (20% penalty if no
   benchmark).
3. <50 bars of price history → score=0 with `error` set.

**Future Phases:**
- Phase 4: FINVIZ Elite integration → 10x faster execution

---

---

## 2. When to Use

**Explicit Triggers:**
- "Find CANSLIM stocks"
- "Screen for growth stocks using O'Neil's method"
- "Which stocks have strong earnings and momentum?"
- "Identify stocks near 52-week highs with accelerating earnings"
- "Run a CANSLIM screener on [sector/universe]"

**Implicit Triggers:**
- User wants to identify multi-bagger candidates
- User is looking for growth stocks with proven fundamentals
- User wants systematic stock selection based on historical winners
- User needs a ranked list of stocks meeting O'Neil's criteria

**When NOT to Use:**
- Value investing focus (use value-dividend-screener instead)
- Income/dividend focus (use dividend-growth-pullback-screener instead)
- Bear market conditions (M component will flag - consider raising cash)

---

---

## 3. Prerequisites

**API Requirements:**
- **FMP API key** (free tier: 250 calls/day, sufficient for 35 stocks; Starter tier $29.99/mo for 40+ stocks)
  - Sign up: https://site.financialmodelingprep.com/developer/docs
  - Set via environment variable: `export FMP_API_KEY=your_key_here`

**Python Dependencies:**
- Python 3.7+
- `requests` (FMP API calls)
- `beautifulsoup4` (Finviz web scraping)
- `lxml` (HTML parsing)

**Installation:**
```bash
pip install requests beautifulsoup4 lxml
```

---

---

## 4. Quick Start

```bash
# Check environment variable
echo $FMP_API_KEY

# If not set, prompt user to provide it
```

---

## 5. Workflow

### Step 1: Verify API Access and Requirements

Check if user has FMP API key configured:

```bash
# Check environment variable
echo $FMP_API_KEY

# If not set, prompt user to provide it
```

**Requirements:**
- **FMP API key** (free tier: 250 calls/day, sufficient for 40 stocks)
- **Python 3.7+** with required libraries:
  - `requests` (FMP API calls)
  - `beautifulsoup4` (Finviz web scraping)
  - `lxml` (HTML parsing)

**Installation:**
```bash
pip install requests beautifulsoup4 lxml
```

If API key is missing, guide user to:
1. Sign up at https://site.financialmodelingprep.com/developer/docs
2. Get free API key (250 calls/day)
3. Set environment variable: `export FMP_API_KEY=your_key_here`

### Step 2: Determine Stock Universe

**Option A: Default Universe (Recommended)**
Use top 40 S&P 500 stocks by market cap (predefined in script):

```bash
python3 skills/canslim-screener/scripts/screen_canslim.py
```

**Option B: Custom Universe**
User provides specific symbols or sector:

```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --universe AAPL MSFT GOOGL AMZN NVDA META TSLA
```

**Option C: Sector-Specific**
User can provide sector-focused list (Technology, Healthcare, etc.)

**API Budget Considerations (Phase 3):**
- 40 stocks × 7 FMP calls/stock = 280 API calls
  - FMP: 7 calls/stock (profile, quote, income×2, historical_90d, historical_365d, institutional)
  - Finviz: ~1.8 calls/stock (institutional ownership fallback, 2s rate limit, not counted in FMP budget)
- Market data (^GSPC quote, ^VIX quote, ^GSPC 52-week history): 3 FMP calls
- Total: ~283 FMP calls per screening run (exceeds 250 free tier)
- **Recommendation**: Use `--max-candidates 35` for free tier (35 × 7 + 3 = 248 calls), or upgrade to FMP Starter tier ($29.99/mo, 750 calls/day) for full 40-stock screening

### Step 3: Execute CANSLIM Screening Script

Run the main screening script with appropriate parameters:

```bash
cd skills/canslim-screener/scripts

# Basic run (40 stocks, top 20 in report)
python3 screen_canslim.py --api-key $FMP_API_KEY

# Custom parameters
python3 screen_canslim.py \
  --api-key $FMP_API_KEY \
  --max-candidates 40 \
  --top 20 \
  --output-dir ../../../

# Custom RS benchmark (Phase 3.1)
python3 screen_canslim.py --rs-benchmark SPY

# Disable L component (saves per-stock 365-day fetch; L fixed at neutral 50)
python3 screen_canslim.py --disable-rs
```

**Script Workflow (Phase 3 - Full CANSLIM):**
1. **Market Direction (M)**: Analyze S&P 500 trend vs 50-day EMA (using real historical data for accurate EMA)
   - If bear market detected (M=0), warn user to raise cash
2. **S&P 500 Historical Data**: Fetch 52-week data for M component EMA and L component RS calculation
3. **Stock Analysis**: For each stock, calculate:
   - **C Component**: Quarterly EPS/revenue growth (YoY)
   - **A Component**: 3-year EPS CAGR and stability
   - **N Component**: Distance from 52-week high, breakout detection
   - **S Component**: Volume-based accumulation/distribution (up-day vs down-day volume)
   - **L Component**: 52-week Relative Strength vs S&P 500
   - **I Component**: Institutional holder count + ownership % (with Finviz fallback)
4. **Composite Scoring**: Weighted average with all 7 component breakdown
5. **Ranking**: Sort by composite score (highest first)
6. **Reporting**: Generate JSON + Markdown outputs

**Expected Execution Time (Phase 3):**
- 40 stocks: **~2 minutes** (additional 52-week history fetch per stock for L component)
- Finviz fallback adds ~2 seconds per stock (rate limiting)
- L component requires 365-day historical data for each stock

**Finviz Fallback Behavior:**
- Triggers automatically when FMP `sharesOutstanding` unavailable
- Scrapes institutional ownership % from Finviz.com (free, no API key)
- Increases I component accuracy from 35/100 (partial data) to 60-100/100 (full data)
- User sees: `✅ Using Finviz institutional ownership for NVDA: 68.3%`

### Step 4: Read and Parse Screening Results

The script generates two output files:
- `canslim_screener_YYYY-MM-DD_HHMMSS.json` - Structured data
- `canslim_screener_YYYY-MM-DD_HHMMSS.md` - Human-readable report

Read the Markdown report to identify top candidates:

```bash
# Find the latest report
ls -lt canslim_screener_*.md | head -1

# Read the report
cat canslim_screener_YYYY-MM-DD_HHMMSS.md
```

**Report Structure (Phase 3 - Full CANSLIM):**
- Market Condition Summary (trend, M score, warnings)
- Top N CANSLIM Candidates (ranked, N = --top parameter)
- For each stock:
  - Composite Score and Rating (Exceptional+/Exceptional/Strong/etc.)
  - Component Breakdown (C, A, N, S, L, I, M scores with details)
  - Interpretation (rating description, guidance, weakest component)
  - Warnings (quality issues, market conditions, data source notes)
- Summary Statistics (rating distribution)
- Methodology note (Phase 3: 7 components, 100% coverage)

**Component Details in Report:**
- **S Component**: "Up/Down Volume Ratio: 1.06 ✓ Accumulation"
- **L Component (Phase 3.1)**: "3m/6m/12m: +12.4%/+18.7%/+44.1% (rel +5.2%/+8.3%/+22.0%) | RS: 88 (Strong)"
- **I Component**: "6199 holders, 68.3% ownership ⭐ Superinvestor"

A new **Summary Table** appears above the candidate list in Phase 3.1 reports, showing
rank, symbol, composite score, rating, RS rating, and RS percentile for quick scanning.

### Step 5: Analyze Top Candidates and Provide Recommendations

Review the top-ranked stocks and cross-reference with knowledge bases:

**Reference Documents to Consult:**
1. `references/interpretation_guide.md` - Understand rating bands and portfolio sizing
2. `references/canslim_methodology.md` - Deep dive into component meanings (now includes S and I)
3. `references/scoring_system.md` - Understand scoring formulas (Phase 3 weights)

**Analysis Framework:**

For **Exceptional+ stocks (90-100 points)**:
- All components near-perfect (C≥85, A≥85, N≥85, S≥80, L≥85, I≥80, M≥80)
- Guidance: Immediate buy, aggressive position sizing (15-20% of portfolio)
- Example: "NVDA scores 97.2 - explosive quarterly earnings (100), strong 3-year growth (95), at new highs (98), volume accumulation (85), RS leader (92), strong institutional support (90), uptrend market (100)"

For **Exceptional stocks (80-89 points)**:
- Outstanding fundamentals + strong momentum
- Guidance: Strong buy, standard sizing (10-15% of portfolio)

For **Strong stocks (70-79 points)**:
- Solid across all components, minor weaknesses
- Guidance: Buy, standard sizing (8-12% of portfolio)
- Phase 3 Example: "Stock scores 77.5 - strong earnings (85), solid growth (80), near high (70), accumulation (60), RS leader (75), good institutions (60), uptrend (90)"

For **Above Average stocks (60-69 points)**:
- Meets thresholds, one component weak
- Guidance: Buy on pullback, conservative sizing (5-8% of portfolio)

**Bear Market Override:**
- If M component = 0 (bear market detected), **do NOT buy** regardless of other scores
- Guidance: Raise 80-100% cash, wait for market recovery
- CANSLIM does not work in bear markets (3 out of 4 stocks follow market trend)

### Step 6: Generate User-Facing Report

Create a concise, actionable summary for the user:

**Report Format:**

```markdown
# CANSLIM Stock Screening Results (Phase 3 - Full CANSLIM)
**Date:** YYYY-MM-DD
**Market Condition:** [Trend] - M Score: [X]/100
**Stocks Analyzed:** [N]
**Components:** C, A, N, S, L, I, M (7 of 7, 100% coverage)

---

## 6. Resources

**References:**

- `skills/canslim-screener/references/canslim_methodology.md`
- `skills/canslim-screener/references/fmp_api_endpoints.md`
- `skills/canslim-screener/references/interpretation_guide.md`
- `skills/canslim-screener/references/scoring_system.md`

**Scripts:**

- `skills/canslim-screener/scripts/check_institutional_endpoint.py`
- `skills/canslim-screener/scripts/finviz_stock_client.py`
- `skills/canslim-screener/scripts/fmp_client.py`
- `skills/canslim-screener/scripts/report_generator.py`
- `skills/canslim-screener/scripts/scorer.py`
- `skills/canslim-screener/scripts/screen_canslim.py`
