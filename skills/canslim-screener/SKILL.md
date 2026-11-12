---
name: canslim-screener
description: Screen US stocks using William O'Neil's CANSLIM growth stock methodology. Use when user requests CANSLIM stock screening, growth stock analysis, momentum stock identification, or wants to find stocks with strong earnings and price momentum following O'Neil's investment system.
---

# CANSLIM Stock Screener - Phase 3 (Full CANSLIM)

## Overview

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

Read `references/scoring_overview.md` for the Phase 3.1 component weights, the weighted RS formula and the RS fallback hierarchy.

**Future Phases:**
- Phase 4: FINVIZ Elite integration → 10x faster execution

---

## When to Use This Skill

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

## Prerequisites

**API Requirements:**
- **FMP API key** (free tier: 250 calls/day, sufficient for 35 stocks; Starter tier $29.99/mo for 40+ stocks)
  - Sign up: https://site.financialmodelingprep.com/developer/docs
  - Set via environment variable: `export FMP_API_KEY=your_key_here`

**Python Dependencies:**
- Python 3.9+
- `requests` (FMP API calls)
- `beautifulsoup4` (Finviz web scraping)
- `lxml` (HTML parsing)

**Installation:**
```bash
pip install requests beautifulsoup4 lxml
```

---

## Output

**Output Directory:** `reports/` (default) or custom via `--output-dir`

**Generated Files:**
- `canslim_screener_YYYY-MM-DD_HHMMSS.json` - Structured data for programmatic use
- `canslim_screener_YYYY-MM-DD_HHMMSS.md` - Human-readable report

**Report Contents:**
- Market Condition Summary (trend, M score, warnings)
- Top N CANSLIM Candidates (ranked by composite score)
- Component Breakdown for each stock (C, A, N, S, L, I, M scores with details)
- Rating interpretation (Exceptional+/Exceptional/Strong/Above Average)
- Quality warnings and data source notes
- Summary statistics (rating distribution)

**Rating Bands:**
- **Exceptional+ (90-100):** All components near-perfect, aggressive buy
- **Exceptional (80-89):** Outstanding fundamentals + momentum, strong buy
- **Strong (70-79):** Solid across components, standard buy
- **Above Average (60-69):** Meets thresholds with minor weaknesses, buy on pullback

---

## Workflow

### Step 1: Verify API Access and Requirements

Check if user has FMP API key configured:

```bash
# Check environment variable
echo $FMP_API_KEY

# If not set, prompt user to provide it
```

**Requirements:**
- **FMP API key** (free tier: 250 calls/day, sufficient for 40 stocks)
- **Python 3.9+** with required libraries:
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

**Report Format:** Read `references/report_template.md` for the user-facing report template.

---

## Resources

### Scripts Directory (`scripts/`)

Read `references/script_inventory.md` for what each script, calculator and supporting module does.

### References Directory (`references/`)

**Knowledge Bases:**
- `references/canslim_methodology.md` (27KB) - Complete CANSLIM explanation
  - All 7 components with O'Neil's original thresholds
  - S component (Volume accumulation/distribution) detailed explanation
  - L component (Leadership/Relative Strength) detailed explanation
  - I component (Institutional sponsorship) detailed explanation
  - Historical examples (AAPL 2009, NFLX 2013, TSLA 2019, NVDA 2023)

- `references/scoring_system.md` (21KB) - Technical scoring specification (Phase 3)
  - Phase 3 component weights and formulas (all 7 components)
  - Interpretation bands (90-100, 80-89, etc.)
  - Minimum thresholds for all 7 components
  - Composite score calculation examples

- `references/fmp_api_endpoints.md` (18KB) - API integration guide (Phase 3)
  - Required endpoints for all 7 components
  - L component: 52-week historical prices endpoint
  - Institutional holder endpoint documentation
  - Finviz fallback strategy explanation
  - Rate limiting strategy
  - Cost analysis (Phase 3: ~283 FMP calls for 40 stocks, exceeds 250 free tier)

- `references/interpretation_guide.md` (18KB) - User guidance
  - Portfolio construction rules
  - Position sizing by rating
  - Entry/exit strategies
  - Bear market protection rules

**How to Use References:**
- Read `references/canslim_methodology.md` first to understand O'Neil's system (now includes S and I)
- Consult `references/interpretation_guide.md` when analyzing results
- Reference `references/scoring_system.md` if scores seem unexpected
- Check `references/fmp_api_endpoints.md` for API troubleshooting or Finviz fallback issues

---

## Troubleshooting

Read `references/troubleshooting.md` when a run fails or returns unexpected results. It covers rate limits, missing libraries, slow or failing Finviz fallback, no stocks meeting thresholds and data quality warnings.

---

## Important Notes

Read `references/implementation_notes.md` for Phase 3 implementation status, Finviz integration benefits, planned Phase 4 and data source attribution.

### Disclaimer

**This screener is for educational and informational purposes only.**
- Not investment advice
- Past performance does not guarantee future results
- CANSLIM methodology works best in bull markets (M component confirms)
- Conduct your own research and consult a financial advisor before making investment decisions
- O'Neil's historical winners include AAPL (2009: +1,200%), NFLX (2013: +800%), but many stocks fail to perform

---

**Version:** Phase 3.1 (multi-period RS)
**Last Updated:** 2026-05-03
**API Requirements:** FMP API (free tier: up to 35 stocks; Starter tier recommended for 40 stocks) + BeautifulSoup/requests/lxml for Finviz
**Execution Time:** ~2 minutes for 40 stocks
**Output Formats:** JSON + Markdown (now includes Summary Table and `schema_version: "3.1"`)
**Components Implemented:** C, A, N, S, L, I, M (7 of 7, 100% coverage)
**Phase 3.1 additions:** multi-period RS (3m/6m/12m), `--rs-benchmark`, `--disable-rs`,
new RS fields (`rs_rating`, `rs_rank_percentile`, `rs_3m_return`, `rs_6m_return`,
`rs_12m_return`, `rs_benchmark`, `rs_benchmark_relative_return`, `rs_component_score`,
`benchmark_52w_performance`).
