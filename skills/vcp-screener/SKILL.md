---
name: vcp-screener
description: Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP) and detect historical VCPs in a single ticker's price path. Identifies Stage 2 uptrend stocks forming tight bases with contracting volatility near breakout pivot points; in historical single-ticker mode walks a multi-year history and emits every VCP that formed with forward-outcome stats (breakout / stop-hit / timeout). Use when user requests VCP screening, Minervini-style setups, tight base patterns, volatility contraction breakout candidates, Stage 2 momentum stock scanning, or historical VCP pattern study on a specific ticker (e.g. FIX, TSLA).
---

# VCP Screener - Minervini Volatility Contraction Pattern

Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP), identifying Stage 2 uptrend stocks with contracting volatility near breakout pivot points.

## When to Use

- User asks for VCP screening or Minervini-style setups
- User wants to find tight base / volatility contraction patterns
- User requests Stage 2 momentum stock scanning
- User asks for breakout candidates with defined risk
- User asks "find every historical VCP in <TICKER>" or wants to study one ticker's
  past VCP setups with forward outcomes (`--history --ticker SYM`)

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

### Strict Mode (Minervini pure setup)

Only return stocks with `valid_vcp=True` AND `execution_state` in `(Pre-breakout, Breakout)`:

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py --strict --output-dir reports/
```

### Historical single-ticker mode

Walk one ticker's multi-year history, detect every VCP that ever formed, and
attach forward-outcome stats (breakout / stop-hit / timeout, days-to-outcome,
max gain, max loss) per detection. Useful for pattern study and backtesting
context — not a real-time screener.

```bash
# Default: scan ~5 years (1260 trading days), 5-day stride, 60-day outcome window
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --history --ticker FIX --output-dir reports/

# Custom scan length: 750 trading days (~3 years), 90-day outcome window
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --history 750 --ticker TSLA \
  --stride-days 5 --outcome-days 90 \
  --output-dir reports/

# Long scan: 10 years (2520 trading days)
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --history 2520 --ticker NVDA --output-dir reports/
```

Outputs (timestamped):
- `vcp_history_<SYM>_<YYYY-MM-DD_HHMMSS>.json` — timeline of detections with full
  analyzer payload + `forward_outcome` per detection + summary stats.
- `vcp_history_<SYM>_<YYYY-MM-DD_HHMMSS>.md` — human-readable timeline.

Mode-specific flags:

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `--history [DAYS]` | (off) / 1260 if bare | 100-5040 | Enable historical mode; optionally specify trading-day scan window (requires `--ticker`) |
| `--ticker SYM` | — | — | Ticker to scan |
| `--stride-days` | 5 | 1-60 | Trading-day step between as-of cursor positions |
| `--outcome-days` | 60 | 5-252 | Forward window evaluated per detection |

Notes:
- Two FMP API calls per scan (ticker + SPY history), not 100+ like the
  cross-sectional pipeline.
- `marketCap` and absolute RS percentile reflect the ticker in isolation,
  not against the live screening universe — use this report for pattern
  study, not portfolio sizing.
- Detections are deduplicated by `(T1_high_date, last_low_date, pivot)` so
  the same VCP isn't reported repeatedly as the cursor ages.

### Advanced Tuning (for backtesting)

Adjust VCP detection parameters for research and backtesting:

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --min-contractions 3 \
  --t1-depth-min 12.0 \
  --breakout-volume-ratio 2.0 \
  --trend-min-score 90 \
  --atr-multiplier 1.5 \
  --output-dir reports/
```

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `--min-contractions` | 2 | 2-4 | Higher = fewer but higher-quality patterns |
| `--t1-depth-min` | 10.0% | 1-50 | Higher = excludes shallow first corrections |
| `--breakout-volume-ratio` | 1.5x | 0.5-10 | Higher = stricter volume confirmation |
| `--trend-min-score` | 85 | 0-100 | Higher = stricter Stage 2 filter |
| `--atr-multiplier` | 1.5 | 0.5-5 | Lower = more sensitive swing detection |
| `--contraction-ratio` | 0.70 | 0.1-1 | Lower = requires tighter contractions |
| `--min-contraction-days` | 5 | 1-30 | Higher = longer minimum contraction |
| `--lookback-days` | 120 | 30-365 | Longer = finds older patterns |
| `--max-sma200-extension` | 50.0% | — | SMA200 distance threshold for Overextended state and penalty |
| `--wide-and-loose-threshold` | 15.0% | — | Final contraction depth above which wide-and-loose flag triggers |
| `--strict` | off | — | Minervini strict mode: only Pre-breakout or Breakout with valid VCP |

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/vcp_methodology.md` for pattern interpretation context
3. Load `references/scoring_system.md` for score threshold guidance

### Step 3: Present Analysis

For each top candidate, present:
- **Quality** (`composite_score` / rating) — how well-formed is the VCP pattern?
- **Execution State** (`execution_state`) — is it buyable now? (Pre-breakout / Breakout = actionable)
- **Pattern Type** (`pattern_type`) — Textbook VCP / VCP-adjacent / Post-breakout / Extended Leader / Damaged
- `★` marker if a State Cap was applied (raw score was downgraded)
- Contraction details (T1/T2/T3 depths and ratios)
- Trade setup: pivot price, stop-loss, risk percentage
- Volume dry-up ratio and breakout_volume_score
- Relative strength rank

### Step 4: Provide Actionable Guidance

**By Execution State (primary filter):**
- **Pre-breakout / Breakout:** Pattern is in the active entry window — apply rating-based sizing
- **Early-post-breakout:** Breakout underway but above ideal entry — reduced size or wait for pullback
- **Extended / Overextended:** Trade missed — add to watchlist for next base
- **Damaged / Invalid:** Setup invalidated — do not enter

**By Rating (secondary, after state confirms actionability):**
- **Textbook VCP (90+):** Buy at pivot with aggressive sizing (1.5-2x)
- **Strong VCP (80-89):** Buy at pivot with standard sizing (1x)
- **Good VCP (70-79):** Buy on volume confirmation above pivot (0.75x)
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
