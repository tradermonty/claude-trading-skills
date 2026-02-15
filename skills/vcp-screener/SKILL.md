---
name: vcp-screener
description: Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). Identifies Stage 2 uptrend stocks forming tight bases with contracting volatility near breakout pivot points. Use when user requests VCP screening, Minervini-style setups, tight base patterns, volatility contraction breakout candidates, or Stage 2 momentum stock scanning.
---

# VCP Screener - Minervini Volatility Contraction Pattern

Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP), identifying Stage 2 uptrend stocks with contracting volatility near breakout pivot points.

## When to Use

- User asks for VCP screening or Minervini-style setups
- User wants to find tight base / volatility contraction patterns
- User requests Stage 2 momentum stock scanning
- User asks for breakout candidates with defined risk

## Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
- Free tier (250 calls/day) is sufficient for default screening (top 100 candidates)
- Paid tier recommended for full S&P 500 screening (`--full-sp500`)

## Workflow

### Step 1: Prepare and Execute Screening

Run the VCP screener script:

```bash
# Default: S&P 500, top 100 candidates
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir skills/vcp-screener/scripts

# Custom universe
python3 skills/vcp-screener/scripts/screen_vcp.py --universe AAPL NVDA MSFT AMZN META --output-dir skills/vcp-screener/scripts

# Full S&P 500 (paid API tier)
python3 skills/vcp-screener/scripts/screen_vcp.py --full-sp500 --output-dir skills/vcp-screener/scripts
```

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/vcp_methodology.md` for pattern interpretation context
3. Load `references/scoring_system.md` for score threshold guidance

### Step 3: Present Analysis

For each top candidate, present:
- VCP composite score and rating
- Contraction details (T1/T2/T3 depths and ratios)
- Trade setup: pivot price, stop-loss, risk percentage
- Volume dry-up ratio
- Relative strength rank

### Step 4: Provide Actionable Guidance

Based on ratings:
- **Textbook VCP (90+):** Buy at pivot with aggressive sizing
- **Strong VCP (80-89):** Buy at pivot with standard sizing
- **Good VCP (70-79):** Buy on volume confirmation above pivot
- **Developing (60-69):** Add to watchlist, wait for tighter contraction
- **Weak/No VCP (<60):** Monitor only or skip

## 3-Phase Pipeline

1. **Pre-Filter** - Quote-based screening (price, volume, 52w position) ~101 API calls
2. **Trend Template** - 7-point Stage 2 filter with 260-day histories ~100 API calls
3. **VCP Detection** - Pattern analysis, scoring, report generation (no additional API calls)

## Output

- `vcp_screener_YYYY-MM-DD_HHMMSS.json` - Structured results
- `vcp_screener_YYYY-MM-DD_HHMMSS.md` - Human-readable report

## Resources

- `references/vcp_methodology.md` - VCP theory and Trend Template explanation
- `references/scoring_system.md` - Scoring thresholds and component weights
- `references/fmp_api_endpoints.md` - API endpoints and rate limits
