---
name: institutional-flow-tracker
description: "Use this skill to parse 13F SEC filings, compare quarter-over-quarter institutional position changes, and generate top holders reports. Use when the user asks about institutional ownership, 13F filings, hedge fund activity, mutual fund positions, smart money flows, accumulation or distribution patterns, or wants to track where institutional investors are deploying capital. Screens stocks by institutional ownership change, analyzes single-stock holder composition, and assigns data reliability grades to filter unreliable filings data."
---

# Institutional Flow Tracker

## Overview

Analyze quarterly 13F filing changes to discover institutional accumulation before price moves or distribution signaling risk.

## Prerequisites

- **FMP API Key:** Set `FMP_API_KEY` environment variable or pass `--api-key` to scripts
- **Python 3.8+:** Required for running analysis scripts
- **Dependencies:** `pip install requests` (scripts handle missing dependencies gracefully)

**Limitations:** 45-day reporting lag; not suitable for micro-caps (<$100M) or short-term signals (<3 months). See `references/13f_filings_guide.md` for full details.

## Data Sources & Requirements

### Required: FMP API Key

```bash
# Set environment variable (preferred)
export FMP_API_KEY=your_key_here

# Or provide when running scripts
python3 scripts/track_institutional_flow.py --api-key YOUR_KEY
```

Free tier (250 requests/day) is sufficient for analyzing 20-30 stocks quarterly.

## Analysis Workflow

### Step 1: Screen for Significant Institutional Changes

Run the screening script. Verify output contains results before proceeding to Step 2.

```bash
# Quick scan (top 50 by institutional change)
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

```bash
# Sector-focused scan
python3 scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

```bash
# Custom screening with JSON output
python3 scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_flow_results.json
```

**Checkpoint:** Verify output contains results and all stocks have Grade A or B reliability. Grade C stocks are auto-excluded.

### Step 2: Deep Dive on Specific Stocks

For each candidate from Step 1, run single-stock analysis. Verify the reliability grade before acting on results.

```bash
python3 scripts/analyze_single_stock.py AAPL
```

**Generates:** 8-quarter ownership trend, all holders with position changes, concentration analysis (top 10 holders' %), new/increased/decreased positions, and reliability grade.

**Checkpoint:** Confirm reliability grade is A or B. If Grade C, discard and move to next candidate.

### Step 3: Track Specific Institutional Investors

> **Note:** `track_institution_portfolio.py` is **not yet implemented**. FMP API organizes
> institutional holder data by stock (not by institution), making full portfolio reconstruction
> impractical via this API alone.

**Alternative approach — use `analyze_single_stock.py` to check if a specific institution holds a stock:**
```bash
# Analyze a stock and look for a specific institution in the output
python3 institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
# Then search the report for "Berkshire" or "ARK" in the Top 20 holders table
```

**For full institution-level portfolio tracking, use these external resources:**
1. **WhaleWisdom:** https://whalewisdom.com (free tier available, 13F portfolio viewer)
2. **SEC EDGAR:** https://www.sec.gov/cgi-bin/browse-edgar (official 13F filings)
3. **DataRoma:** https://www.dataroma.com (superinvestor portfolio tracker)

### Step 4: Interpret Signal Strength

Read `references/interpretation_framework.md` for detailed guidance. Use this table to classify signals:

| Signal | Ownership QoQ | Institution Count | Key Indicators |
|--------|--------------|-------------------|----------------|
| **Strong Bullish** | >+15% | >+10% | Quality investors adding, low ownership (<40%), multi-quarter accumulation |
| **Moderate Bullish** | +5–15% | Net positive | Mix of buyers/sellers, ownership 40–70% |
| **Neutral** | <±5% | Balanced | Stable base, minimal change |
| **Moderate Bearish** | -5–15% | Net negative | More sellers, high ownership (>80%) |
| **Strong Bearish** | >-15% | >-10% | Quality investors exiting, multi-quarter distribution, concentration risk |

**Checkpoint:** Classify each candidate's signal strength. Only proceed to portfolio application with Moderate Bullish or stronger signals.

### Step 5: Portfolio Application

- **New positions:** Run institutional analysis on candidates. Strong bullish = higher conviction. Strong bearish = reconsider or reduce size.
- **Existing holdings:** Re-run quarterly after 13F deadlines. Flag distribution as early warning. Re-evaluate thesis if institutions exiting.
- **Screening integration:** Use other screeners (Value Dividend, etc.) to find candidates, then validate with institutional flow. Prioritize accumulation, avoid distribution.

## Output Format

All analysis generates structured markdown reports saved to repository root:

**Filename convention:** `institutional_flow_analysis_<TICKER/THEME>_<DATE>.md`

**Report sections:**
1. Executive Summary (key findings)
2. Institutional Ownership Trend (current vs historical)
3. Top Holders and Changes
4. New Buyers vs Sellers
5. Concentration Analysis
6. Interpretation and Recommendations
7. Data Sources and Timestamp

## Data Reliability Grades

All analysis includes a reliability grade based on data quality:

- **Grade A:** Coverage ratio < 3x, match ratio >= 50%, genuine holder ratio >= 70%. Safe for investment decisions.
- **Grade B:** Genuine holder ratio >= 30%. Reference only — use with caution.
- **Grade C:** Genuine holder ratio < 30%. UNRELIABLE — automatically excluded from screening results.

The data quality module filters to "genuine" holders (present in both quarters) to avoid misleading metrics from quarter-to-quarter holder count variance.

## Advanced Use Cases

**Insider + Institutional Combo:**
- Look for stocks where both insiders AND institutions are buying
- Particularly powerful signal when aligned

**Sector Rotation Detection:**
- Track aggregate institutional flows by sector
- Identify early rotation trends before they appear in price

**Contrarian Plays:**
- Find quality stocks institutions are selling (potential value)
- Requires strong fundamental conviction

**Smart Money Validation:**
- Before major position, check if smart money agrees
- Gain confidence or find overlooked risks

## References

- `references/13f_filings_guide.md` — 13F reporting requirements and data quality considerations
- `references/institutional_investor_types.md` — Investor types, strategies, and how to interpret their moves
- `references/interpretation_framework.md` — Signal quality assessment and integration with other analysis

## Script Parameters

### track_institutional_flow.py

Main screening script for finding stocks with significant institutional changes.

**Required:**
- `--api-key`: FMP API key (or set FMP_API_KEY environment variable)

**Optional:**
- `--top N`: Return top N stocks by institutional change (default: 50)
- `--min-change-percent X`: Minimum % change in institutional ownership (default: 10)
- `--min-market-cap X`: Minimum market cap in dollars (default: 1B)
- `--sector NAME`: Filter by specific sector
- `--min-institutions N`: Minimum number of institutional holders (default: 10)
- `--limit N`: Number of stocks to fetch from screener (default: 100). Lower values save API calls.
- `--output FILE`: Output JSON file path
- `--output-dir DIR`: Output directory for reports (default: reports/)
- `--sort-by FIELD`: Sort by 'ownership_change' or 'institution_count_change'

### analyze_single_stock.py

Deep dive analysis on a specific stock's institutional ownership.

**Required:**
- Ticker symbol (positional argument)
- `--api-key`: FMP API key (or set FMP_API_KEY environment variable)

**Optional:**
- `--quarters N`: Number of quarters to analyze (default: 8, i.e., 2 years)
- `--output FILE`: Output markdown report path
- `--output-dir DIR`: Output directory for reports (default: reports/)
- `--compare-to TICKER`: Compare institutional ownership to another stock (future feature)

### Data Quality Module (data_quality.py)

Shared utility module used by both `track_institutional_flow.py` and `analyze_single_stock.py`:

- **classify_holder():** Classifies holders as genuine/new_full/exited/unknown
- **calculate_filtered_metrics():** Computes metrics using genuine holders only
- **reliability_grade():** Assigns A/B/C grade based on data quality
- **is_tradable_stock():** Filters out ETFs, funds, and inactive stocks
- **deduplicate_share_classes():** Removes BRK-A/B, GOOG/GOOGL duplicates

## Integration with Other Skills

- **Value Dividend Screener:** Screen candidates first, then validate with institutional flow
- **US Stock Analysis:** Run fundamentals, then confirm with ownership trends
- **Portfolio Manager:** Fetch holdings via Alpaca, flag positions with deteriorating institutional support
- **Technical Analyst:** Confirm technical setups with institutional buying for higher conviction

## External Resources

- FMP API Docs: https://financialmodelingprep.com/developer/docs
- SEC 13F Database: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F
- WhaleWisdom: https://whalewisdom.com
