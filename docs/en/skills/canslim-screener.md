---
layout: default
title: CANSLIM Screener
grand_parent: English
parent: Skill Guides
nav_order: 2
lang_peer: /ja/skills/canslim-screener/
permalink: /en/skills/canslim-screener/
---

# CANSLIM Screener
{: .no_toc }

Screen US stocks using William O'Neil's proven CANSLIM growth stock methodology. Phase 3 implements all 7 components for 100% methodology coverage.
{: .fs-6 .fw-300 }

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

The CANSLIM Screener applies William O'Neil's growth stock selection system -- developed from studying every major stock winner from 1953 to the present. The methodology identifies 7 common traits that multi-bagger stocks exhibit before their major price advances.

**What it solves:**
- Systematically scores stocks across the 7 CANSLIM dimensions instead of relying on subjective judgment
- Provides composite ratings (0-100) with clear interpretation bands
- Protects against buying in bear markets (M component gates all recommendations)
- Automates the labor-intensive process of analyzing earnings, growth, momentum, institutional activity, and market conditions

**Phase 3 implements all 7 components:**

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| **C** - Current Earnings | 15% | Quarterly EPS and revenue growth (YoY) |
| **A** - Annual Growth | 20% | 3-year EPS CAGR and stability |
| **N** - Newness | 15% | Distance from 52-week high, breakout detection |
| **S** - Supply/Demand | 15% | Volume-based accumulation/distribution |
| **L** - Leadership | 20% | Multi-period RS (3m/6m/12m vs configurable benchmark, default ^GSPC) |
| **I** - Institutional | 10% | Holder count + ownership % (with Finviz fallback) |
| **M** - Market Direction | 5% | S&P 500 trend vs 50-day EMA |

---

## 2. Prerequisites

> FMP API key is required. The free tier (250 calls/day) supports up to 35 stocks per run. Use `--max-candidates 35` to stay within the limit.
{: .api_required }

**API Requirements:**
- **FMP API key** -- Free tier: 250 calls/day. Starter tier ($29.99/mo): 750 calls/day for full 40-stock screening.
- Sign up: [https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

**Python Dependencies:**
- Python 3.7+
- `requests` (FMP API calls)
- `beautifulsoup4` (Finviz web scraping for I component fallback)
- `lxml` (HTML parsing)

```bash
pip install requests beautifulsoup4 lxml
```

**API Budget (Phase 3):**
- 40 stocks x 7 FMP calls/stock = 280 FMP calls
- Market data (S&P 500 quote, VIX, 52-week history): 3 calls
- Total: ~283 FMP calls per run (exceeds 250 free tier)
- **Recommendation:** Use `--max-candidates 35` for free tier (248 calls), or upgrade to Starter

---

## 3. Quick Start

```bash
# Set your API key
export FMP_API_KEY=your_key_here

# Run with default S&P 500 universe (top 40 by market cap)
python3 skills/canslim-screener/scripts/screen_canslim.py --output-dir reports/

# Free tier optimization (35 stocks max)
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --output-dir reports/
```

Or simply tell Claude:

```
Run a CANSLIM screen on the top 35 S&P 500 stocks
```

---

## 4. How It Works

The screener operates in a two-stage pipeline:

**Stage 1 -- Data Collection & Scoring (FMP API + Finviz):**
1. Fetch S&P 500 historical data for M component (market direction) and L component (relative strength benchmark)
2. For each stock, make 7 FMP API calls: profile, quote, income statement (2 periods), 90-day history, 365-day history, institutional holders
3. Calculate all 7 component scores using dedicated calculator modules
4. When FMP institutional data is incomplete, automatically fall back to Finviz web scraping for ownership percentage

**Stage 2 -- Ranking & Reporting:**
1. Calculate composite weighted score: C(15%) + A(20%) + N(15%) + S(15%) + L(20%) + I(10%) + M(5%)
2. Rank all stocks by composite score (highest first)
3. Generate JSON output for programmatic use and Markdown report for human review

**Finviz fallback behavior:**
- Triggers automatically when FMP `sharesOutstanding` is unavailable
- Scrapes institutional ownership % from Finviz.com (free, no API key needed)
- Rate-limited at 2.0 seconds per request
- Improves I component accuracy from 35/100 (partial data) to 60-100/100 (full data)

---

## 5. Usage Examples

### Example 1: Default S&P 500 Screening

**Prompt:**
```
Screen the S&P 500 for CANSLIM stocks
```

**What happens:** Claude runs the screener against the default universe of 40 stocks (top S&P 500 by market cap). Takes approximately 2 minutes. Generates a ranked report with composite scores and component breakdowns.

**Why useful:** The quickest way to identify the strongest growth stocks in the large-cap universe using a proven methodology.

---

### Example 2: Semiconductor Sector Focus

**Command:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --universe NVDA AMD QCOM AVGO TXN INTC MU MRVL AMAT LRCX \
  --output-dir reports/
```

**Why useful:** Narrows the analysis to a single high-growth sector. Useful when you already have a sector thesis and want to rank the best candidates within it using CANSLIM criteria.

---

### Example 3: Free Tier Optimization

**Command:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --top 10 --output-dir reports/
```

**Why useful:** Stays within the FMP free tier limit (250 calls/day) while still analyzing a meaningful universe. The `--top 10` flag keeps the report focused on the strongest candidates.

---

### Example 4: Component Deep Dive

After running a screen, examine the component breakdown for a top-scoring stock:

```
Score: 92.3 / 100 (Exceptional+)
  C (Current Earnings): 100/100 - EPS +58% QoQ, Revenue +32%
  A (Annual Growth):     95/100 - 3yr EPS CAGR 42%, consistent growth
  N (Newness):           98/100 - Within 2% of 52-week high, volume breakout
  S (Supply/Demand):     85/100 - Up/Down Volume Ratio 1.65 (Accumulation)
  L (Leadership):        92/100 - 52wk: +45% (+22% vs S&P 500), RS 88
  I (Institutional):     90/100 - 6,199 holders, 68.3% ownership
  M (Market Direction): 100/100 - Strong uptrend, S&P above 50-day EMA
```

**Why useful:** Understanding which components drive the score helps you assess whether the stock's strength is broad-based or concentrated in one area. Stocks with high scores across all components are the most reliable.

---

### Example 5: Bear Market Scenario

When the M component detects a bear market (S&P 500 below 50-day EMA, VIX elevated):

```
Market Condition: BEAR MARKET DETECTED
M Score: 0/100

WARNING: CANSLIM methodology recommends raising 80-100% cash in bear markets.
3 out of 4 stocks follow the market trend. Do NOT initiate new positions.
```

**Why useful:** The M component acts as a circuit breaker. Even if individual stocks score 90+ on other components, CANSLIM's historical data shows that buying in confirmed bear markets has a poor win rate. This protects capital.

---

### Example 6: Interpreting Score Ranges

| Rating | Score | Guidance | Position Sizing |
|--------|-------|----------|----------------|
| Exceptional+ | 90-100 | All components near-perfect. Aggressive buy | 15-20% of portfolio |
| Exceptional | 80-89 | Outstanding fundamentals + momentum. Strong buy | 10-15% of portfolio |
| Strong | 70-79 | Solid across components, minor weaknesses. Standard buy | 8-12% of portfolio |
| Above Average | 60-69 | Meets thresholds with one weak component. Buy on pullback | 5-8% of portfolio |

**Why useful:** The interpretation bands translate abstract scores into concrete position sizing guidance, aligning risk exposure with conviction level.

---

## 6. Understanding the Output

The screener generates two files:
- `canslim_screener_YYYY-MM-DD_HHMMSS.json` -- Structured data for programmatic use
- `canslim_screener_YYYY-MM-DD_HHMMSS.md` -- Human-readable report

**Report sections:**
1. **Market Condition Summary** -- Current trend, M score, and warnings
2. **Top N CANSLIM Candidates** -- Ranked by composite score with:
   - Composite score and rating band
   - Individual component scores with explanatory details
   - Data source notes (e.g., "Institutional data from Finviz")
   - Weakest component identification
3. **Summary Statistics** -- Distribution of ratings (how many Exceptional+, Exceptional, Strong, etc.)
4. **Methodology Note** -- Phase 3: 7 components, 100% coverage

**Quality warnings to watch for:**
- "Revenue declining despite EPS growth" -- Possible buyback distortion
- "Using Finviz institutional ownership data" -- Data source switched (still accurate)
- "Bear market detected" -- M component = 0, do not buy

---

## 7. Tips & Best Practices

- **Always check the M component first.** If M = 0, the rest of the scores are irrelevant from a CANSLIM perspective. Raise cash and wait.
- **Look for broad strength.** A score of 85 with all components above 70 is more reliable than a score of 85 with one component at 100 and another at 40.
- **Use `--max-candidates 35` for free tier.** This is the sweet spot for the 250 calls/day FMP free tier limit.
- **Run weekly, not daily.** CANSLIM is a weekly screening methodology. Earnings data updates quarterly, and most components are stable week-to-week.
- **Cross-reference with charts.** CANSLIM identifies fundamentally strong stocks, but entry timing matters. Use the Technical Analyst skill for chart-based entry confirmation.
- **Finviz fallback is reliable.** Testing showed 100% success rate (39/39 stocks) with ~2.5 seconds per request. The data quality is equivalent to FMP.

---

## 8. Combining with Other Skills

| Workflow | Steps |
|----------|-------|
| **Full growth stock pipeline** | CANSLIM Screener (rank candidates) > Technical Analyst (confirm chart setup) > Position Sizer (calculate shares) |
| **CANSLIM + VCP** | Run CANSLIM to identify growth leaders, then check if top candidates also show VCP patterns via VCP Screener |
| **Pre-filter with FinViz** | Use FinViz Screener (`fa_epsqoq_o25,ta_sma200_pa,ta_highlow52w_b0to10h`) to build a custom universe, then pass those tickers to CANSLIM Screener with `--universe` |
| **Earnings confirmation** | After CANSLIM ranks candidates, check Earnings Calendar for upcoming report dates to avoid entering before volatile events |
| **Bear market protection** | When CANSLIM M = 0, switch to Market Environment Analysis and Breadth Chart Analyst to monitor for recovery signals |

---

## 9. Troubleshooting

### FMP API rate limit exceeded (429 error)

The script automatically retries after 60 seconds. If the error persists:
- Reduce the universe: `--max-candidates 30`
- Check daily usage: free tier resets at midnight UTC
- Upgrade to FMP Starter ($29.99/mo) for 750 calls/day

### Missing Python libraries

```
ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml
```

Install all dependencies:
```bash
pip install requests beautifulsoup4 lxml
```

### Finviz web scraping failure (403 error)

This occurs when Finviz blocks scraping requests. The script degrades gracefully:
- Falls back to FMP holder count only
- I component score is capped at 70/100 with a 50% penalty
- Wait a few minutes and retry, or verify your network access to finviz.com

### All stocks scoring below 60

This may indicate bear market conditions or a universe lacking growth stocks:
- Check the M component -- if M = 0, follow bear market protocol (raise cash)
- Try a different sector or expand the universe
- In weak markets, scores in the 55-65 range may still be the relative best available

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--api-key` | No | `$FMP_API_KEY` | FMP API key |
| `--max-candidates` | No | `40` | Max stocks to analyze (use 35 for free tier) |
| `--top` | No | `20` | Number of top results in the report |
| `--output-dir` | No | `.` | Output directory for JSON and Markdown reports |
| `--universe` | No | S&P 500 top 40 | Custom list of ticker symbols |
| `--rs-benchmark` | No | `^GSPC` | Benchmark symbol for L-component RS (e.g. SPY, QQQ, IWM). M component still uses ^GSPC for EMA scale consistency. |
| `--disable-rs` | No | `false` | Skip L component calculation. Saves the per-stock 365-day price fetch and the custom benchmark fetch (when applicable). L is fixed at neutral 50. |

### Default Universe

The default universe includes the top 40 S&P 500 stocks by market cap:

```
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, BRK.B, UNH, JNJ,
XOM, V, PG, JPM, MA, HD, CVX, MRK, ABBV, PEP, COST, AVGO, KO,
ADBE, LLY, TMO, WMT, MCD, CSCO, ACN, ORCL, ABT, NKE, CRM, DHR,
VZ, TXN, AMD, QCOM, INTC
```

### Scoring Formula

```
Composite = C x 0.15 + A x 0.20 + N x 0.15 + S x 0.15 + L x 0.20 + I x 0.10 + M x 0.05
```

### Weighted RS Calculation (Phase 3.1)

The L component now uses a multi-period weighted relative strength against a configurable
benchmark (default `^GSPC`):

```
Weighted RS = 0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m
```

- Periods: 3m = 63 trading bars, 6m = 126 bars, 12m = 252 bars.
- When some periods are missing (insufficient history), the weights are re-normalized
  over the available periods so they still sum to 1.0.
- **Fallback hierarchy** when full multi-period data is not available:
  1. **No benchmark** → score from the weighted absolute stock performance with a 20% penalty
     (preserves the legacy fallback behavior).
  2. **All multi-period windows missing but >=50 bars of price history available**
     (e.g. fewer than 63 trading bars but a longer-than-50-bar series) → fall back to
     the legacy 365-day full-window absolute return as the scoring input. The 20% penalty
     still applies when no benchmark is present.
  3. **<50 bars of price history** → score=0 with `error` set; no scoring is performed.
- Pass `--rs-benchmark SPY` (or QQQ, IWM, etc.) to swap the benchmark. The M component
  always uses `^GSPC` to keep its EMA calculation in scale.

### Output Schema (Phase 3.1)

The L-component sub-object adds the following fields. Existing fields are preserved for
backward compatibility.

| Field | Type | Description |
|-------|------|-------------|
| `rs_3m_return` / `rs_6m_return` / `rs_12m_return` | float \| null | Stock absolute return over 63 / 126 / 252 trading bars. |
| `benchmark_3m_return` / `benchmark_6m_return` / `benchmark_12m_return` | float \| null | Benchmark absolute return over the same windows. |
| `rel_3m` / `rel_6m` / `rel_12m` | float \| null | Stock minus benchmark (per period). Null when no benchmark. |
| `weighted_stock_performance` | float \| null | Weighted absolute return (used as scoring input when no benchmark). |
| `weighted_relative_performance` | float \| null | Weighted relative return (scoring input when benchmark available). |
| `benchmark_52w_performance` | float \| null | Symbol-neutral successor to `sp500_52w_performance`. |
| `rs_benchmark` | string | Benchmark symbol used (e.g. `^GSPC`, `SPY`). |
| `rs_benchmark_relative_return` | float \| null | Equal to `rel_12m` (252-bar relative). Note: this is **not** the same as legacy `relative_performance`, which uses the full 365-day window. |
| `rs_rating` | string | Short label derived from `rs_rank_percentile`: `Market Leader` / `Strong` / `Above Average` / `Average` / `Laggard` / `Weak`. |
| `rs_component_score` | int | Alias of `score` (0–100). |
| `rs_rank_percentile` | int \| null | **Estimated** percentile derived from relative-performance thresholds. **Not** a cross-sectional percentile within the screened universe. |

Deprecation notes:

- `sp500_52w_performance` is retained for backward compatibility. When `--rs-benchmark`
  is set to a non-`^GSPC` symbol, this field contains that benchmark's return (the field
  name lies). Prefer `benchmark_52w_performance`.
- `relative_performance` continues to mean the 365-day full-window stock − benchmark
  return. It differs from `rs_benchmark_relative_return` (252-bar) and from
  `weighted_relative_performance` (multi-period weighted).

### Rating Bands

| Band | Score | Interpretation |
|------|-------|---------------|
| Exceptional+ | 90-100 | All components near-perfect |
| Exceptional | 80-89 | Outstanding fundamentals + momentum |
| Strong | 70-79 | Solid across components |
| Above Average | 60-69 | Meets thresholds with minor weaknesses |
| Average | 50-59 | Mixed signals |
| Below Average | < 50 | Does not meet CANSLIM criteria |
