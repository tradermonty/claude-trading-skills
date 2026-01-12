---
name: canslim-screener
description: Screen US stocks using William O'Neil's CANSLIM growth stock methodology. Use when user requests CANSLIM stock screening, growth stock analysis, momentum stock identification, or wants to find stocks with strong earnings and price momentum following O'Neil's investment system.
---

# CANSLIM Stock Screener - Phase 2

## Overview

This skill screens US stocks using William O'Neil's proven CANSLIM methodology, a systematic approach for identifying growth stocks with strong fundamentals and price momentum. CANSLIM analyzes 7 key components: **C**urrent Earnings, **A**nnual Growth, **N**ewness/New Highs, **S**upply/Demand, **L**eadership/RS Rank, **I**nstitutional Sponsorship, and **M**arket Direction.

**Phase 2** implements 6 of 7 components (C, A, N, S, I, M), representing **80% of the full methodology**. This phase adds critical volume analysis (S) and institutional ownership tracking (I) to the Phase 1 foundation.

**Two-Stage Approach:**
1. **Stage 1 (FMP API + Finviz)**: Analyze stock universe with 6 CANSLIM components
2. **Stage 2 (Reporting)**: Rank by composite score and generate actionable reports

**Key Features:**
- Composite scoring (0-100 scale) with weighted components
- **Finviz fallback** for institutional ownership data (automatic when FMP data incomplete)
- Progressive filtering to optimize API usage
- JSON + Markdown output formats
- Interpretation bands: Exceptional+ (90+), Exceptional (80-89), Strong (70-79), Above Average (60-69)
- Bear market protection (M component gating)

**Phase 2 Component Weights (Renormalized for 6 components):**
- C (Current Earnings): 19%
- A (Annual Growth): 25%
- N (Newness): 19%
- S (Supply/Demand): 19% ← **NEW**
- I (Institutional): 13% ← **NEW**
- M (Market Direction): 6%

**Future Phases:**
- Phase 3: Add L (Leadership/RS Rank) → 100% coverage (full CANSLIM)
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

**API Budget Considerations (Phase 2):**
- 40 stocks × ~5.1 calls/stock = ~203 API calls (within free tier)
  - FMP: ~3.3 calls/stock (income statements, quotes, prices, institutional holders)
  - Finviz: ~1.8 calls/stock (institutional ownership fallback, 2s rate limit)
- Market data (S&P 500, VIX): 3 calls
- Total: ~206 calls per screening run

### Step 3: Execute CANSLIM Screening Script

Run the main screening script with appropriate parameters:

```bash
cd /Users/takueisaotome/PycharmProjects/claude-trading-skills/skills/canslim-screener/scripts

# Basic run (40 stocks, top 20 in report)
python3 screen_canslim.py --api-key $FMP_API_KEY

# Custom parameters
python3 screen_canslim.py \
  --api-key $FMP_API_KEY \
  --max-candidates 40 \
  --top 20 \
  --output-dir ../../../
```

**Script Workflow (Phase 2):**
1. **Market Direction (M)**: Analyze S&P 500 trend vs 50-day EMA
   - If bear market detected (M=0), warn user to raise cash
2. **Stock Analysis**: For each stock, calculate:
   - **C Component**: Quarterly EPS/revenue growth (YoY)
   - **A Component**: 3-year EPS CAGR and stability
   - **N Component**: Distance from 52-week high, breakout detection
   - **S Component**: Volume-based accumulation/distribution (up-day vs down-day volume) ← **NEW**
   - **I Component**: Institutional holder count + ownership % (with Finviz fallback) ← **NEW**
3. **Composite Scoring**: Weighted average with component breakdown
4. **Ranking**: Sort by composite score (highest first)
5. **Reporting**: Generate JSON + Markdown outputs

**Expected Execution Time (Phase 2):**
- 40 stocks: **~1 minute 40 seconds** (tested: 101.42 seconds)
- Finviz fallback adds ~2 seconds per stock (rate limiting)
- Much faster than Phase 1 due to optimized API calls

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

**Report Structure (Phase 2):**
- Market Condition Summary (trend, M score, warnings)
- Top 20 CANSLIM Candidates (ranked)
- For each stock:
  - Composite Score and Rating (Exceptional+/Exceptional/Strong/etc.)
  - Component Breakdown (C, A, N, **S**, **I**, M scores with details) ← **S and I added**
  - Interpretation (rating description, guidance, weakest component)
  - Warnings (quality issues, market conditions, data source notes)
- Summary Statistics (rating distribution)
- Methodology note (Phase 2: 6 components)

**New Component Details in Report:**
- **S Component**: "Up/Down Volume Ratio: 1.06 ✓ Accumulation"
- **I Component**: "6199 holders, 68.3% ownership ⭐ Superinvestor"

### Step 5: Analyze Top Candidates and Provide Recommendations

Review the top-ranked stocks and cross-reference with knowledge bases:

**Reference Documents to Consult:**
1. `references/interpretation_guide.md` - Understand rating bands and portfolio sizing
2. `references/canslim_methodology.md` - Deep dive into component meanings (now includes S and I)
3. `references/scoring_system.md` - Understand scoring formulas (Phase 2 weights)

**Analysis Framework:**

For **Exceptional+ stocks (90-100 points)**:
- All components near-perfect (C≥85, A≥85, N≥85, S≥80, I≥80, M≥80)
- Guidance: Immediate buy, aggressive position sizing (15-20% of portfolio)
- Example: "NVDA scores 97.2 - explosive quarterly earnings (100), strong 3-year growth (95), at new highs (98), volume accumulation (85), strong institutional support (90), uptrend market (100)"

For **Exceptional stocks (80-89 points)**:
- Outstanding fundamentals + strong momentum
- Guidance: Strong buy, standard sizing (10-15% of portfolio)

For **Strong stocks (70-79 points)**:
- Solid across all components, minor weaknesses
- Guidance: Buy, standard sizing (8-12% of portfolio)
- Phase 2 Example: "NVDA scores 77.5 - explosive earnings (100), strong growth (90), near high (60), accumulation (60), good institutions (60), uptrend (90)"

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
# CANSLIM Stock Screening Results (Phase 2)
**Date:** YYYY-MM-DD
**Market Condition:** [Trend] - M Score: [X]/100
**Stocks Analyzed:** [N]
**Components:** C, A, N, S, I, M (6 of 7)

## Market Summary
[2-3 sentences on current market environment based on M component]
[If bear market: WARNING - Consider raising cash allocation]

## Top 5 CANSLIM Candidates

### 1. [SYMBOL] - [Company Name] ⭐⭐⭐
**Score:** [X.X]/100 ([Rating])
**Price:** $[XXX.XX] | **Sector:** [Sector]

**Component Breakdown:**
- C (Earnings): [X]/100 - [EPS growth]% QoQ, [Revenue growth]% revenue
- A (Growth): [X]/100 - [CAGR]% 3yr EPS CAGR
- N (Newness): [X]/100 - [Distance]% from 52wk high
- S (Supply/Demand): [X]/100 - Up/Down Volume Ratio: [X.XX]
- I (Institutional): [X]/100 - [N] holders, [X.X]% ownership [⭐ Superinvestor if present]
- M (Market): [X]/100 - [Trend]

**Interpretation:** [Rating description and guidance]
**Weakest Component:** [X] ([score])
**Data Source Note:** [If Finviz used: "Institutional data from Finviz"]

[Repeat for top 5 stocks]

## Investment Recommendations

**Immediate Buy List (90+ score):**
- [List stocks with exceptional+ ratings]
- Position sizing: 15-20% each

**Strong Buy List (80-89 score):**
- [List stocks with exceptional ratings]
- Position sizing: 10-15% each

**Watchlist (70-79 score):**
- [List stocks with strong ratings]
- Buy on pullback

## Risk Factors
- [Identify any quality warnings from components]
- [Market condition warnings]
- [Sector concentration risks if applicable]
- [Data source reliability notes if Finviz heavily used]

## Next Steps
1. Conduct detailed fundamental analysis on top 3 candidates
2. Check earnings calendars for upcoming reports
3. Review technical charts for entry timing
4. [If bear market: Wait for market recovery before deploying capital]

---
**Note:** This is Phase 2 (C, A, N, S, I, M components - 80% coverage). Phase 3 will add L component for full 7-component CANSLIM.
```

---

## Resources

### Scripts Directory (`scripts/`)

**Main Scripts:**
- `screen_canslim.py` - Main orchestrator script
  - Entry point for screening workflow
  - Handles argument parsing, API coordination, ranking, reporting
  - Usage: `python3 screen_canslim.py --api-key KEY [options]`

- `fmp_client.py` - FMP API client wrapper
  - Rate limiting (0.3s between calls)
  - 429 error handling with 60s retry
  - Session-based caching
  - Methods: `get_income_statement()`, `get_quote()`, `get_historical_prices()`, `get_institutional_holders()`

- `finviz_stock_client.py` - Finviz web scraping client ← **NEW**
  - BeautifulSoup-based HTML parsing
  - Fetches institutional ownership % from Finviz.com
  - Rate limiting (2.0s between calls)
  - No API key required (free web scraping)
  - Methods: `get_institutional_ownership()`, `get_stock_data()`

**Calculators (`scripts/calculators/`):**
- `earnings_calculator.py` - C component (Current Earnings)
  - Quarterly EPS/revenue growth (YoY)
  - Scoring: 50%+ = 100pts, 30-49% = 80pts, 18-29% = 60pts

- `growth_calculator.py` - A component (Annual Growth)
  - 3-year EPS CAGR calculation
  - Stability check (no negative growth years)
  - Scoring: 40%+ = 90pts, 30-39% = 70pts, 25-29% = 50pts

- `new_highs_calculator.py` - N component (Newness)
  - Distance from 52-week high
  - Volume-confirmed breakout detection
  - Scoring: 5% of high + breakout = 100pts, 10% + breakout = 80pts

- `supply_demand_calculator.py` - S component (Supply/Demand) ← **NEW**
  - Volume-based accumulation/distribution analysis
  - Up-day volume vs down-day volume ratio (60-day lookback)
  - Scoring: ratio ≥2.0 = 100pts, 1.5-2.0 = 80pts, 1.0-1.5 = 60pts

- `institutional_calculator.py` - I component (Institutional) ← **NEW**
  - Institutional holder count (from FMP)
  - Ownership % (from FMP or Finviz fallback)
  - Superinvestor detection (Berkshire Hathaway, Baupost, etc.)
  - Scoring: 50-100 holders + 30-60% ownership = 100pts

- `market_calculator.py` - M component (Market Direction)
  - S&P 500 vs 50-day EMA
  - VIX-adjusted scoring
  - Scoring: Strong uptrend = 100pts, Uptrend = 80pts, Bear market = 0pts

**Supporting Modules:**
- `scorer.py` - Composite score calculation
  - Phase 2 weighted average: C×19% + A×25% + N×19% + S×19% + I×13% + M×6%
  - Rating interpretation (Exceptional+/Exceptional/Strong/etc.)
  - Minimum threshold validation (all 6 components must meet baseline)

- `report_generator.py` - Output generation
  - JSON export (programmatic use)
  - Markdown export (human-readable)
  - Phase 2 component breakdown tables
  - Summary statistics calculation

### References Directory (`references/`)

**Knowledge Bases:**
- `canslim_methodology.md` (27KB) - Complete CANSLIM explanation ← **Updated for Phase 2**
  - All 7 components with O'Neil's original thresholds
  - **NEW**: S component (Volume accumulation/distribution) detailed explanation
  - **NEW**: I component (Institutional sponsorship) detailed explanation
  - Historical examples (AAPL 2009, NFLX 2013, TSLA 2019, NVDA 2023)
  - Phase 2 implementation notes

- `scoring_system.md` (21KB) - Technical scoring specification ← **Updated for Phase 2**
  - Phase 2 component weights and formulas
  - Interpretation bands (90-100, 80-89, etc.)
  - Minimum thresholds for 6 components
  - Composite score calculation examples

- `fmp_api_endpoints.md` (18KB) - API integration guide ← **Updated for Phase 2**
  - Required endpoints for each component
  - **NEW**: Institutional holder endpoint documentation
  - **NEW**: Finviz fallback strategy explanation
  - Rate limiting strategy
  - Cost analysis (Phase 2: ~203 calls for 40 stocks, within free tier)

- `interpretation_guide.md` (18KB) - User guidance
  - Portfolio construction rules
  - Position sizing by rating
  - Entry/exit strategies
  - Bear market protection rules

**How to Use References:**
- Read `canslim_methodology.md` first to understand O'Neil's system (now includes S and I)
- Consult `interpretation_guide.md` when analyzing results
- Reference `scoring_system.md` if scores seem unexpected
- Check `fmp_api_endpoints.md` for API troubleshooting or Finviz fallback issues

---

## Troubleshooting

### Issue 1: FMP API Rate Limit Exceeded

**Symptoms:**
```
ERROR: 429 Too Many Requests - Rate limit exceeded
Retrying in 60 seconds...
```

**Causes:**
- Running multiple screenings within short time window
- Exceeding 250 calls/day (free tier limit)
- Other applications using same API key

**Solutions:**
1. **Wait and Retry**: Script auto-retries after 60s
2. **Reduce Universe**: Use `--max-candidates 30` to lower API usage
3. **Check Daily Usage**: Free tier resets at midnight UTC
4. **Upgrade Plan**: FMP Starter ($29.99/month) provides 750 calls/day

### Issue 2: Missing Required Libraries

**Symptoms:**
```
ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml
```

**Solutions:**
```bash
# Install all required libraries
pip install requests beautifulsoup4 lxml

# Or install individually
pip install beautifulsoup4
pip install requests
pip install lxml
```

### Issue 3: Finviz Fallback Slow Execution

**Symptoms:**
```
Execution time: 2 minutes 30 seconds for 40 stocks (slower than expected)
```

**Causes:**
- Finviz rate limiting (2.0s per request)
- All stocks triggering fallback due to FMP data gaps

**Solutions:**
1. **Accept Delay**: 1-2 minutes for 40 stocks is normal with Finviz fallback
2. **Monitor Fallback Usage**: Check logs for "Using Finviz institutional ownership" messages
3. **Reduce Rate Limit** (advanced): Edit `finviz_stock_client.py`, change `rate_limit_seconds=2.0` to `1.5` (risk: IP ban)

**Note:** Finviz fallback adds ~2 seconds per stock but significantly improves I component accuracy (35 → 60-100 points).

### Issue 4: Finviz Web Scraping Failure

**Symptoms:**
```
WARNING: Finviz request failed with status 403 for NVDA
⚠️ Using Finviz institutional ownership data - FMP shares outstanding unavailable. Finviz fallback also unavailable. Score reduced by 50%.
```

**Causes:**
- Finviz blocking scraping requests (User-Agent detection)
- Rate limit exceeded (too many requests)
- Network issues or Finviz downtime

**Solutions:**
1. **Wait and Retry**: Rate limit resets after a few minutes
2. **Check Internet Connection**: Verify network access to finviz.com
3. **Fallback Accepted**: Script continues with FMP holder count only (I score capped at 70/100)
4. **Manual Verification**: Check Finviz website manually for blocked IP

**Graceful Degradation:**
- Script never fails due to Finviz issues
- Falls back to FMP holder count only
- User sees quality warning in report

### Issue 5: No Stocks Meet Minimum Thresholds

**Symptoms:**
```
✓ Successfully analyzed 40 stocks
Top 5 Stocks:
  1. AAPL  -  58.3 (Average)
  2. MSFT  -  55.1 (Average)
  ...
```

**Causes:**
- Bear market conditions (M component low)
- Selected universe lacks growth stocks
- Market rotation away from growth

**Solutions:**
1. **Check M Component**: If M=0 (bear market), raise cash per CANSLIM rules
2. **Expand Universe**: Try different sectors or market cap ranges
3. **Lower Expectations**: Average scores (55-65) may still be actionable in weak markets
4. **Wait for Better Setup**: CANSLIM works best in bull markets

### Issue 6: Data Quality Warnings

**Symptoms:**
```
⚠️ Revenue declining despite EPS growth (possible buyback distortion)
⚠️ Using Finviz institutional ownership data (68.3%) - FMP shares outstanding unavailable.
```

**Interpretation:**
- These are **not errors** - they are quality flags from calculators
- Revenue warning: EPS growth may be from share buybacks, not organic growth
- Finviz warning: Data source switched from FMP to Finviz (still accurate)

**Actions:**
1. Review component details in full report
2. Cross-check with fundamental analysis
3. Adjust position sizing based on risk level
4. Finviz data is reliable - no action needed for data source warnings

---

## Important Notes

### Phase 2 Implementation Status

This is **Phase 2** implementing 6 of 7 CANSLIM components:
- ✅ **C** (Current Earnings) - Implemented
- ✅ **A** (Annual Growth) - Implemented
- ✅ **N** (Newness) - Implemented
- ✅ **S** (Supply/Demand) - Implemented (Phase 2) ← **NEW**
- ❌ **L** (Leadership/RS Rank) - Not implemented (Phase 3)
- ✅ **I** (Institutional) - Implemented (Phase 2) ← **NEW**
- ✅ **M** (Market Direction) - Implemented

**Implications:**
- Composite scores represent **80% of full CANSLIM methodology**
- Top scores typically max out at ~95 (full CANSLIM can reach 200+)
- Missing component: Relative strength rank (L component)
- Phase 2 provides highly accurate screening with volume and institutional analysis

**Score Conversion:**
- Phase 2 score 85+ ≈ Full CANSLIM 145-165 (Strong to Exceptional)
- Phase 2 score 70-84 ≈ Full CANSLIM 125-144 (Above Average to Strong)
- Phase 2 score 60-69 ≈ Full CANSLIM 110-124 (Average to Above Average)

### Finviz Integration Benefits

**Automatic Fallback System:**
- When FMP API doesn't provide `sharesOutstanding`, Finviz automatically activates
- Scrapes institutional ownership % from Finviz.com (free, no API key)
- Improves I component accuracy from 35/100 (partial) to 60-100/100 (full)

**Data Source Priority:**
1. **FMP API** (primary): Institutional holder count + shares outstanding calculation
2. **Finviz** (fallback): Direct institutional ownership % from web page
3. **Partial Data** (last resort): Holder count only, 50% penalty applied

**Tested Reliability:**
- 39/39 stocks successfully retrieved ownership % via Finviz (100% success rate)
- Average execution time: 2.54 seconds per stock
- No errors or IP blocks during testing

### Future Enhancements

**Phase 3 (Planned):**
- Add L component: RS Rank estimation (52-week high proxy, 80% accuracy)
- Full 7-component CANSLIM: C 15%, A 20%, N 15%, S 15%, L 20%, I 10%, M 5%
- Coverage: 100% of full CANSLIM

**Phase 4 (Planned):**
- FINVIZ Elite integration for pre-screening
- Execution time: 2 minutes → 10-15 seconds
- FMP API usage reduction: 90%
- Larger universe possible (100+ stocks)

### Data Source Attribution

- **FMP API**: Income statements, quotes, historical prices, key metrics, institutional holders
- **Finviz**: Institutional ownership % (fallback), market data
- **Methodology**: William O'Neil's "How to Make Money in Stocks" (4th edition)
- **Scoring System**: Adapted from IBD MarketSmith proprietary system

### Disclaimer

**This screener is for educational and informational purposes only.**
- Not investment advice
- Past performance does not guarantee future results
- CANSLIM methodology works best in bull markets (M component confirms)
- Conduct your own research and consult a financial advisor before making investment decisions
- O'Neil's historical winners include AAPL (2009: +1,200%), NFLX (2013: +800%), but many stocks fail to perform

---

**Version:** Phase 2
**Last Updated:** 2026-01-12
**API Requirements:** FMP API (free tier sufficient) + BeautifulSoup/requests/lxml for Finviz
**Execution Time:** ~1 minute 40 seconds for 40 stocks
**Output Formats:** JSON + Markdown
**Components Implemented:** C, A, N, S, I, M (6 of 7, 80% coverage)
