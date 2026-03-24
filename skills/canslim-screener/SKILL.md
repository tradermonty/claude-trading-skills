---
name: canslim-screener
description: "Screen US stocks using William O'Neil's CANSLIM growth stock methodology. Analyze current earnings growth, annual EPS CAGR, new highs and breakouts, supply/demand volume patterns, relative strength leadership, institutional sponsorship, and market direction. Use when user requests CANSLIM stock screening, growth stock analysis, momentum stock identification, multi-bagger candidates, or wants to find stocks with strong earnings and price momentum following O'Neil's investment system."
---

# CANSLIM Stock Screener

Screen US stocks across all 7 CANSLIM components (**C**urrent Earnings, **A**nnual Growth, **N**ewness/New Highs, **S**upply/Demand, **L**eadership/RS Rank, **I**nstitutional Sponsorship, **M**arket Direction) using a two-stage approach:

1. **Stage 1**: Fetch and score each stock via FMP API + Finviz fallback
2. **Stage 2**: Rank by weighted composite score (0-100) and generate reports

**Component Weights (Original O'Neil):** C 15% | A 20% | N 15% | S 15% | L 20% | I 10% | M 5%

**Rating Bands:** Exceptional+ (90-100) | Exceptional (80-89) | Strong (70-79) | Above Average (60-69)

---

## When to Use

- User asks to find CANSLIM stocks, screen growth stocks, or identify momentum candidates
- User wants stocks near 52-week highs with accelerating earnings
- User needs a ranked list using O'Neil's criteria or systematic growth stock selection

**When NOT to Use:**
- Value investing focus → use value-dividend-screener
- Income/dividend focus → use dividend-growth-pullback-screener

---

## Prerequisites

- **FMP API key**: Set `export FMP_API_KEY=your_key_here` (sign up at https://site.financialmodelingprep.com/developer/docs)
  - Free tier: 250 calls/day (sufficient for 35 stocks); Starter $29.99/mo for 40+
- **Python 3.7+** with: `pip install requests beautifulsoup4 lxml`

---

## Workflow

### Step 1: Verify Environment

```bash
echo $FMP_API_KEY
python3 -c "import requests, bs4, lxml; print('Dependencies OK')"
```

**Checkpoint:** If API key is empty, guide user to sign up at FMP. If imports fail, run `pip install requests beautifulsoup4 lxml`. Do not proceed until both pass.

### Step 2: Determine Stock Universe

```bash
# Default: top 40 S&P 500 by market cap
python3 skills/canslim-screener/scripts/screen_canslim.py --api-key $FMP_API_KEY

# Custom symbols
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --api-key $FMP_API_KEY --universe AAPL MSFT GOOGL AMZN NVDA META TSLA

# Free tier budget: use --max-candidates 35 (35 x 7 + 3 = 248 FMP calls)
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --api-key $FMP_API_KEY --max-candidates 35
```

**API Budget:** 7 FMP calls/stock (profile, quote, income x2, historical_90d, historical_365d, institutional) + 3 market calls. Finviz fallback for institutional data is free and automatic.

### Step 3: Execute Screening

```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --api-key $FMP_API_KEY \
  --max-candidates 40 \
  --top 20 \
  --output-dir reports/
```

The script:
1. Fetches **M** (Market Direction): S&P 500 vs 50-day EMA. If bear market (M=0), warns to raise cash.
2. For each stock, calculates **C** (quarterly EPS/revenue YoY), **A** (3-year EPS CAGR), **N** (distance from 52-week high + breakout), **S** (up/down volume ratio), **L** (52-week RS vs S&P 500), **I** (holder count + ownership % with Finviz fallback).
3. Computes weighted composite, ranks, and generates JSON + Markdown reports.

**Checkpoint:** Verify output files exist before proceeding:
```bash
ls -lt reports/canslim_screener_*.md | head -1
```

**Execution time:** ~2 minutes for 40 stocks. Finviz fallback adds ~2s/stock but improves I component from 35/100 to 60-100/100.

### Step 4: Analyze Results

Read the latest Markdown report and consult reference documents:
- `references/interpretation_guide.md` - Rating bands, portfolio sizing, entry/exit
- `references/canslim_methodology.md` - Component details and historical examples
- `references/scoring_system.md` - Scoring formulas and thresholds

**Analysis by rating:**

| Rating | Score | Action | Position Size |
|--------|-------|--------|---------------|
| Exceptional+ | 90-100 | Immediate buy | 15-20% |
| Exceptional | 80-89 | Strong buy | 10-15% |
| Strong | 70-79 | Buy, standard | 8-12% |
| Above Average | 60-69 | Buy on pullback | 5-8% |

**Bear Market Override:** If M=0, do NOT buy regardless of other scores. CANSLIM does not work in bear markets (3 of 4 stocks follow the market trend). Raise 80-100% cash.

### Step 5: Generate User Report

Present a concise summary including:
- **Market condition** (M score, trend, any bear market warning)
- **Top candidates** ranked by composite score with per-component breakdown (C, A, N, S, L, I, M)
- **Actionable tiers**: Immediate buy, strong buy, and watchlist
- **Risk factors**: Quality warnings, market conditions, sector concentration, data source notes
- **Next steps**: Fundamental deep-dive on top 3, check earnings calendar, review charts for entry timing

---

## Output

**Directory:** `reports/` (default) or custom via `--output-dir`

**Files generated:**
- `canslim_screener_YYYY-MM-DD_HHMMSS.json` - Structured data
- `canslim_screener_YYYY-MM-DD_HHMMSS.md` - Human-readable report with market summary, ranked candidates, component breakdowns, and rating distribution

---

## Resources

### Scripts (`scripts/`)
- `screen_canslim.py` - Main orchestrator: `python3 screen_canslim.py --api-key KEY [--max-candidates N] [--top N] [--output-dir DIR]`
- `fmp_client.py` - FMP API client with rate limiting (0.3s) and 429 retry
- `finviz_stock_client.py` - Finviz scraper for institutional ownership fallback (2.0s rate limit)
- `calculators/earnings_calculator.py` - C component (quarterly EPS/revenue YoY)
- `calculators/growth_calculator.py` - A component (3-year EPS CAGR + stability)
- `calculators/new_highs_calculator.py` - N component (52-week high distance + breakout)
- `calculators/supply_demand_calculator.py` - S component (up/down volume ratio, 60-day)
- `calculators/leadership_calculator.py` - L component (52-week RS vs S&P 500)
- `calculators/institutional_calculator.py` - I component (holders + ownership + superinvestor detection)
- `calculators/market_calculator.py` - M component (S&P 500 vs 50-day EMA, VIX-adjusted)
- `scorer.py` - Weighted composite calculation and rating interpretation
- `report_generator.py` - JSON + Markdown output generation

### References (`references/`)
- `canslim_methodology.md` - Complete CANSLIM explanation with O'Neil thresholds and historical examples
- `scoring_system.md` - Scoring formulas, weights, interpretation bands, minimum thresholds
- `fmp_api_endpoints.md` - API endpoints, Finviz fallback strategy, rate limiting, cost analysis
- `interpretation_guide.md` - Portfolio construction, position sizing, entry/exit, bear market rules

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `429 Too Many Requests` | Exceeded FMP daily limit | Wait (auto-retries 60s), reduce `--max-candidates`, or upgrade to Starter tier |
| `required libraries not found` | Missing Python deps | `pip install requests beautifulsoup4 lxml` |
| Slow execution (~2.5min) | Finviz fallback rate limiting | Normal with fallback; improves I component accuracy significantly |
| Finviz 403 errors | Scraping blocked | Script degrades gracefully to FMP-only (I score capped at 70). Wait and retry. |
| All scores below 60 | Bear market or wrong universe | Check M component; expand universe or wait for bull market conditions |
| Data quality warnings | Buyback distortion or data source switch | Not errors; review component details, cross-check fundamentals |

---

## Important Notes

- **Data sources:** FMP API (primary), Finviz (institutional fallback), methodology from O'Neil's "How to Make Money in Stocks" (4th ed.), scoring adapted from IBD MarketSmith
- **Finviz fallback** activates automatically when FMP lacks `sharesOutstanding`. Priority: FMP > Finviz > partial data (50% penalty).
- **Disclaimer:** For educational/informational purposes only. Not investment advice. Past performance does not guarantee future results. Consult a financial advisor before investing.
