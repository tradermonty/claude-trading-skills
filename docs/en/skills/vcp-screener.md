---
layout: default
title: VCP Screener
grand_parent: English
parent: Skill Guides
nav_order: 3
lang_peer: /ja/skills/vcp-screener/
permalink: /en/skills/vcp-screener/
---

# VCP Screener
{: .no_toc }

Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). Identifies Stage 2 uptrend stocks forming tight bases with contracting volatility near breakout pivot points.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/vcp-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/vcp-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

The VCP Screener automates detection of Mark Minervini's Volatility Contraction Pattern -- a technical base pattern that precedes many large stock advances. The pattern forms when a stock in a Stage 2 uptrend pulls back multiple times, with each successive correction getting shallower and the trading range getting tighter, indicating supply is being absorbed.

**What it solves:**
- Manually scanning hundreds of charts for VCP patterns is time-consuming and inconsistent
- The screener applies objective, quantitative criteria to identify patterns across the entire S&P 500
- Provides precise trade setups with pivot points, stop-loss levels, and risk percentages
- Separates entry-ready stocks from those still forming (developing patterns)

**3-Phase Pipeline:**
1. **Pre-Filter** -- Quote-based screening on price, volume, and 52-week position (~101 API calls)
2. **Trend Template** -- Minervini's 7-point Stage 2 filter using 260-day price histories (~100 API calls)
3. **VCP Detection** -- Pattern analysis, contraction scoring, pivot calculation (no additional API calls)

---

## 2. Prerequisites

> FMP API key is required. The free tier (250 calls/day) is sufficient for the default screening of top 100 candidates.
{: .api_required }

**API Requirements:**
- **FMP API key** -- Free tier: 250 calls/day (sufficient for default screening). Paid tier recommended for `--full-sp500`.
- Sign up: [https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

**Python Dependencies:**
- Python 3.7+
- `requests` (FMP API calls)

```bash
pip install requests
```

---

## 3. Quick Start

```bash
# Set your API key
export FMP_API_KEY=your_key_here

# Default: screen top 100 S&P 500 candidates
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/

# Or tell Claude:
# "Screen S&P 500 stocks for VCP patterns"
```

---

## 4. How It Works

**Phase 1 -- Pre-Filter (Quote-Based):**
- Fetches current quotes for S&P 500 stocks
- Filters by price (above minimum), average volume (sufficient liquidity), and 52-week position
- Reduces the universe from ~500 to ~100 candidates
- Cost: ~101 API calls (1 batch quote + individual quotes)

**Phase 2 -- Trend Template (Minervini's 7-Point Check):**
- Fetches 260-day price history for each pre-filtered stock
- Applies Minervini's Stage 2 trend template:
  - Price above 50-day and 150-day moving averages
  - 50-day MA above 150-day MA
  - 150-day MA above 200-day MA
  - 200-day MA trending up for at least 1 month
  - Price at least 30% above 52-week low
  - Price within 25% of 52-week high
  - Relative Strength Rank above 70
- Scores each stock (0-100) on trend template criteria
- Cost: ~100 API calls (1 per stock)

**Phase 3 -- VCP Detection (No Additional API Calls):**
- Analyzes price data for contraction patterns using ATR-based ZigZag swing detection
- Identifies successive tightening corrections (T1, T2, T3, etc.)
- Calculates: contraction depths, contraction ratios, volume dry-up, pivot price
- **Two-axis scoring** separates pattern quality (composite score) from execution readiness (execution state), preventing strong but extended stocks from receiving buy signals
- Composite scoring combines trend template score, VCP pattern quality, volume pattern, relative strength, and pivot proximity

---

## 5. Usage Examples

### Example 1: Default S&P 500 VCP Scan

**Prompt:**
```
Screen for VCP patterns in the S&P 500
```

**What happens:** The screener runs the full 3-phase pipeline against the top 100 S&P 500 candidates. Takes about 2-3 minutes. Results are split into two sections:
- **Section A (Entry Ready):** Stocks within 3% of their pivot point with acceptable risk
- **Section B (Extended / Developing):** Stocks with VCP patterns that are either above pivot (extended) or still forming

---

### Example 2: Custom Universe

**Command:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --universe AAPL NVDA MSFT AMZN META AVGO CRM ADBE \
  --output-dir reports/
```

**Why useful:** When you already have a watchlist from another source (e.g., CANSLIM Screener output) and want to check which stocks are forming actionable VCP setups.

---

### Example 3: Strict Quality Filter

**Command:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --min-contractions 3 \
  --breakout-volume-ratio 2.0 \
  --trend-min-score 90 \
  --output-dir reports/
```

**Why useful:** Tightens detection criteria for higher-quality patterns. Requiring 3+ contractions and 2x breakout volume produces fewer candidates but with more textbook VCP characteristics. Best for conservative traders who want only the clearest setups.

---

### Example 4: Reading Contraction Details

A typical VCP output shows contraction analysis:

```
VCP Pattern: 3 contractions detected
  T1: -18.5% (base correction)
  T2: -11.2% (ratio: 0.61 -- good contraction)
  T3: -5.8%  (ratio: 0.52 -- excellent tightening)
Volume Dry-Up: 0.45 (55% below average -- strong supply exhaustion)
Pivot Price: $185.20
```

**Interpretation:**
- T1 at -18.5% establishes the base depth (within Minervini's 10-35% typical range)
- T2/T1 ratio of 0.61 shows meaningful contraction (below the 0.75 threshold)
- T3/T2 ratio of 0.52 shows accelerating tightening -- a hallmark of institutional accumulation
- Volume dry-up at 0.45 means volume dropped to 45% of average, indicating supply is exhausted
- The tighter the last contraction and the lower the volume, the more explosive the potential breakout

---

### Example 5: Entry-Ready vs Extended Stocks

The report separates stocks into two categories:

**Section A -- Entry Ready:**
- Price is within `--max-above-pivot` (default 3%) of the pivot
- Risk to stop-loss is within `--max-risk` (default 15%)
- Valid VCP pattern confirmed (unless `--no-require-valid-vcp` is set)
- These are actionable now

**Section B -- Extended / Developing:**
- Stocks that passed trend template but are extended above pivot
- Developing patterns that have not yet completed enough contractions
- These go on the watchlist for future entry opportunities

---

### Example 6: Trade Setup

For an entry-ready candidate, the report provides a complete trade setup:

```
NVDA (Score: 92.1 - Textbook VCP)
  Pivot: $185.20
  Current: $183.50 (0.9% below pivot)
  Stop-Loss: $171.40 (T3 low)
  Risk: 6.6%
  Risk/Reward at 2R: 13.2% upside target = $207.70
```

**How to use this:**
1. Set a buy order at or just above the pivot price ($185.20)
2. Set your stop-loss at $171.40 (below the lowest point of the last contraction)
3. Your initial risk is 6.6% of position value
4. Use Position Sizer to calculate the exact number of shares based on your account size and risk tolerance

---

## 6. Understanding the Output

The screener generates:
- `vcp_screener_YYYY-MM-DD_HHMMSS.json` -- Structured results for programmatic use
- `vcp_screener_YYYY-MM-DD_HHMMSS.md` -- Human-readable report

**Report sections:**
1. **Executive Summary** -- Number of candidates screened, VCPs found, entry-ready count
2. **Section A -- Entry Ready** -- Stocks near pivot with trade setups
3. **Section B -- Extended / Developing** -- Watchlist candidates
4. **For each stock:**
   - Composite score and rating (Textbook VCP 90+, Strong 80-89, Good 70-79, Developing 60-69)
   - Trend Template score (7-point check)
   - VCP contraction details (T1/T2/T3 depths and ratios)
   - Volume pattern (dry-up ratio)
   - Relative strength rank
   - Pivot price, stop-loss, and risk percentage

**Two-axis output:**

Each stock receives both a **quality rating** (pattern strength) and an **execution state** (entry timing). The final rating is capped by the execution state -- a Textbook-quality pattern that is Overextended will not get a buy signal.

| Execution State | Meaning | Max Rating |
|-----------------|---------|------------|
| Pre-breakout | Below pivot (ideal entry zone) | No cap |
| Breakout | 0-3% above pivot + volume confirmed | No cap |
| Early-post-breakout | 3-5% above pivot, OR 0-3% without volume | Strong VCP |
| Extended | 5-10% above pivot | Developing VCP |
| Overextended | >10% above pivot or >50% above SMA200 | Weak VCP |
| Damaged | Below SMA50 or stop level | No VCP |
| Invalid | Price < SMA50 < SMA200 | No VCP |

**Quality rating bands (before state caps):**

| Rating | Score | Action |
|--------|-------|--------|
| Textbook VCP | 90+ | Buy at pivot with aggressive sizing |
| Strong VCP | 80-89 | Buy at pivot with standard sizing |
| Good VCP | 70-79 | Buy on volume confirmation above pivot |
| Developing | 60-69 | Watchlist -- wait for tighter contraction |
| Weak / No VCP | <60 | Monitor only or skip |

---

## 7. Tips & Best Practices

- **Volume confirmation is critical.** A breakout above the pivot on volume below average is suspicious. Look for breakout volume at least 1.5x the 50-day average (the default threshold).
- **Tighter is better.** The best VCPs show T3 (or final contraction) depth under 10%. When the stock barely moves despite market volatility, supply is truly exhausted.
- **Check the broader market.** VCP breakouts have the highest success rate in confirmed market uptrends. Combine with Market Environment Analysis or Breadth Chart Analyst to verify conditions.
- **Do not chase extended stocks.** If a stock is more than 5% above its pivot, the risk/reward ratio deteriorates significantly. Wait for a pullback to the pivot or for a new pattern to form.
- **Use prebreakout mode for focused output.** The `--mode prebreakout` flag shows only entry-ready candidates, filtering out noise from extended or developing patterns.
- **Adjust parameters for research.** The default parameters work well for most market conditions. Tighten `--min-contractions` and `--breakout-volume-ratio` in choppy markets; loosen them in strong uptrends.

---

## 8. Combining with Other Skills

| Workflow | Steps |
|----------|-------|
| **CANSLIM + VCP** | Run CANSLIM Screener to identify growth leaders with strong fundamentals, then check for VCP setups via VCP Screener. Stocks that score high on both are the strongest candidates |
| **VCP + Technical Analyst** | After VCP Screener identifies entry-ready candidates, use Technical Analyst for detailed chart confirmation -- support/resistance, volume profile, and broader pattern context |
| **VCP + Position Sizer** | Feed the pivot and stop-loss from VCP output directly into Position Sizer to calculate risk-based share count: `--entry 185.20 --stop 171.40 --account-size 100000 --risk-pct 1.0` |
| **Pre-filter with FinViz** | Use FinViz Screener to build a custom universe (e.g., `ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to10h,sh_relvol_o1.5`), then pass those tickers to VCP Screener with `--universe` |
| **Market timing** | Only trade VCP breakouts when Breadth Chart Analyst and Uptrend Analyzer confirm healthy market breadth. Avoid entries when distribution signals are active |

---

## 9. Troubleshooting

### Few or no VCPs found

**Possible causes:**
- Market is in a correction phase (most stocks are in Stage 1 or Stage 4, not Stage 2)
- Parameters are too strict for current conditions

**Fix:**
- Check market conditions with Breadth Chart Analyst -- VCPs form primarily in Stage 2 uptrends
- Try `--trend-min-score 80` (looser trend filter)
- Try `--min-contractions 2` (default) instead of 3
- Expand the universe with `--full-sp500` (requires paid API tier)

### API rate limit (429 error)

The 3-phase pipeline uses approximately 201 API calls for 100 candidates:
- Phase 1: ~101 calls (quotes)
- Phase 2: ~100 calls (historical prices)

The free tier (250 calls/day) accommodates this with headroom. If you hit limits from running multiple skills, wait until UTC midnight for reset or use `--max-candidates 50` to reduce calls.

### "Stale" stocks with ATR below threshold

Stocks with minimal price movement (average true range < 1% of price) are filtered out by the `--min-atr-pct` flag (default: 1.0%). These may include stocks being acquired, penny stocks, or low-liquidity names. This filter prevents false VCP detections in effectively dead stocks.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--api-key` | No | `$FMP_API_KEY` | FMP API key |
| `--max-candidates` | No | `100` | Max stocks for full VCP analysis after pre-filter |
| `--top` | No | `20` | Top results in report |
| `--output-dir` | No | `.` | Output directory |
| `--universe` | No | S&P 500 | Custom symbols to screen |
| `--full-sp500` | No | `false` | Screen all S&P 500 (requires paid API) |
| `--mode` | No | `all` | Output mode: `all` or `prebreakout` (entry-ready only) |
| `--max-above-pivot` | No | `3.0` | Max % above pivot for entry-ready classification |
| `--max-risk` | No | `15.0` | Max risk % for entry-ready |
| `--min-atr-pct` | No | `1.0` | Min avg daily range % to exclude stale stocks |
| `--min-contractions` | No | `2` | Minimum contractions for valid VCP (2-4) |
| `--t1-depth-min` | No | `8.0` | Minimum T1 correction depth % |
| `--breakout-volume-ratio` | No | `1.5` | Breakout volume vs 50d avg ratio |
| `--trend-min-score` | No | `85.0` | Minimum trend template score for Phase 2 |
| `--atr-multiplier` | No | `1.5` | ATR multiplier for ZigZag swing detection |
| `--contraction-ratio` | No | `0.75` | Max ratio for successive contractions |
| `--min-contraction-days` | No | `5` | Minimum days per contraction |
| `--lookback-days` | No | `120` | VCP pattern lookback window in days |
| `--ext-threshold` | No | `8.0` | SMA50 distance % where extended penalty starts |
| `--no-require-valid-vcp` | No | `false` | Do not require valid_vcp for entry-ready |
| `--max-sma200-extension` | No | `50.0` | Max % above SMA200 before Overextended state |
| `--wide-and-loose-threshold` | No | `15.0` | Final contraction depth % for wide-and-loose flag |
| `--strict` | No | `false` | Strict mode: requires 3+ contractions, 7+ days each, ratio 0.60 |

### Scoring Components

| Component | Weight | Description |
|-----------|--------|-------------|
| Trend Template | 25% | Minervini's 7-point Stage 2 check |
| VCP Pattern | 25% | Contraction quality, depth ratios, tightness |
| Volume Pattern | 20% | Dry-up ratio (lower = better supply exhaustion) |
| Pivot Proximity | 15% | Distance from calculated pivot point |
| Relative Strength | 15% | Minervini-weighted performance vs S&P 500 |
