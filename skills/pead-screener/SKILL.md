---
name: pead-screener
description: Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. Analyzes weekly candle formation to detect red candle pullbacks and breakout signals. Supports two input modes - FMP earnings calendar (Mode A) or earnings-trade-analyzer JSON output (Mode B). Use when user asks about PEAD screening, post-earnings drift, earnings gap follow-through, red candle breakout patterns, or weekly earnings momentum setups.
---

# PEAD Screener - Post-Earnings Announcement Drift

Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns using weekly candle analysis to detect red candle pullbacks and breakout signals.

## When to Use

- User asks for PEAD screening or post-earnings drift analysis
- User wants to find earnings gap-up stocks with follow-through potential
- User requests red candle breakout patterns after earnings
- User asks for weekly earnings momentum setups
- User provides earnings-trade-analyzer JSON output for further screening

## Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- Free tier (250 calls/day) is sufficient for default screening
- For Mode B: earnings-trade-analyzer JSON output file with schema_version "1.0"

## Workflow

### Step 1: Prepare and Execute Screening

Run the PEAD screener script in one of two modes:

**Mode A (FMP earnings calendar):**
```bash
# Default: last 14 days of earnings, 5-week monitoring window
python3 skills/pead-screener/scripts/screen_pead.py --output-dir reports/

# Custom parameters
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 21 \
  --watch-weeks 6 \
  --min-gap 5.0 \
  --min-market-cap 1000000000 \
  --output-dir reports/
```

**Mode B (earnings-trade-analyzer JSON input):**
```bash
# From earnings-trade-analyzer output
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B \
  --output-dir reports/
```

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/pead_strategy.md` for PEAD theory and pattern context
3. Load `references/entry_exit_rules.md` for trade management rules

### Step 3: Present Analysis

For each candidate, present:
- Stage classification (MONITORING, SIGNAL_READY, BREAKOUT, EXPIRED)
- Weekly candle pattern details (red candle location, breakout status)
- Composite score and rating
- Trade setup: entry, stop-loss, target, risk/reward ratio
- Liquidity metrics (ADV20, average volume)

### Step 4: Provide Actionable Guidance

Based on stages and ratings:
- **BREAKOUT + Strong Setup (85+):** High-conviction PEAD trade, full position size
- **BREAKOUT + Good Setup (70-84):** Solid PEAD setup, standard position size
- **SIGNAL_READY:** Red candle formed, set alert for breakout above red candle high
- **MONITORING:** Post-earnings, no red candle yet, add to watchlist
- **EXPIRED:** Beyond monitoring window, remove from watchlist

## Output

- `pead_screener_YYYY-MM-DD_HHMMSS.json` - Structured results with stage classification
- `pead_screener_YYYY-MM-DD_HHMMSS.md` - Human-readable report grouped by stage

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `screen_candidate` | `ScreenCandidate` | Screened stock with scoring rationale and action state |

Schema: `schemas/json/screen_candidate.json`

## Resources

- `references/pead_strategy.md` - PEAD theory and weekly candle approach
- `references/entry_exit_rules.md` - Entry, exit, and position sizing rules

## Data Gaps

Explicit behavior when required data is unavailable — do not substitute neutrals silently.

| Scenario | Severity | Behavior |
|----------|----------|----------|
| `FMP_API_KEY` env var missing | CRITICAL | Halt — exit 1; print setup instructions; do not write output |
| FMP returns HTTP error or empty list | HIGH | Halt — log `[DATA GAP HIGH]`; do not fabricate candidates |
| Individual ticker data unavailable | LOW | Skip ticker; list missing symbols in output under `data_gaps[]` |
| Fewer than 30 qualifying candidates | MEDIUM | Continue; note reduced sample; mark `confidence: LOW` in output |
| Data timestamp >1 trading day old | MEDIUM | Warn in output; proceed only with user confirmation |
