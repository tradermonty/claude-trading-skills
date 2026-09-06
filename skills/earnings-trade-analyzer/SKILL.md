---
name: earnings-trade-analyzer
description: Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). Scores each stock 0-100 and assigns A/B/C/D grades. Use when user asks about earnings trade analysis, post-earnings momentum screening, earnings gap scoring, or finding best recent earnings reactions.
---

# Earnings Trade Analyzer - Post-Earnings 5-Factor Scoring

Analyze recent post-earnings stocks using a 5-factor weighted scoring system to identify the strongest earnings reactions for potential momentum trades.

## When to Use

- User asks for post-earnings trade analysis or earnings gap screening
- User wants to find the best recent earnings reactions
- User requests earnings momentum scoring or grading
- User asks about post-earnings accumulation day (PEAD) candidates

## Prerequisites

- FMP API key (set `FMP_API_KEY` environment variable or pass `--api-key`)
- Free tier (250 calls/day) is sufficient for default screening (lookback 2 days, top 20)
- Paid tier recommended for larger lookback windows or full screening

## Workflow

### Step 1: Run the Earnings Trade Analyzer

Execute the analyzer script:

```bash
# Default: last 2 days of earnings, top 20 results
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py --output-dir reports/

# Custom lookback and market cap filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 5 \
  --min-market-cap 1000000000 \
  --top 30 \
  --output-dir reports/

# With entry quality filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --apply-entry-filter \
  --output-dir reports/
```

#### Degraded endpoint / budget fallback for scheduled reviews

If the analyzer reports a 404, an implausible empty earnings calendar, or exhausts its API-call budget before producing scored candidates during a scheduled after-close/pre-market run, do not report "no earnings reactions" immediately.

1. First retry once with a narrower liquid-universe configuration so the full 5-factor scorer has a chance to complete, for example:

```bash
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 2 \
  --min-market-cap 5000000000 \
  --top 20 \
  --max-api-calls 600 \
  --output-dir reports/<routine-date>
```

2. If the scored run still returns no candidates or cannot complete, verify the same range through the stable endpoint used by the compatibility shim and clearly label the result as an ungraded fallback:

```bash
curl "https://financialmodelingprep.com/stable/earnings-calendar?from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=$FMP_API_KEY"
```

Then optionally enrich returned US tickers through the analyzer's stable-first FMP client or per-symbol `/stable/quote?symbol=<ticker>` calls to rank by same-day `changesPercentage`, market cap, and liquidity. Use legacy `/api/v3` quote calls only as a legacy-key fallback after stable has failed. Present these as **preliminary / ungraded reactions** because the 5-factor scorer did not run; do not assign A/B/C/D grades from the fallback alone.

**No-candidate output pitfall:** The analyzer may print `Candidates after filtering: 0` / `No candidates found matching criteria.` and exit successfully without writing an `earnings_trade_analyzer_*.json` file. In that case, do not try to run PEAD Mode B from a nonexistent candidate file. Say explicitly that no scored analyzer JSON was produced, run the endpoint/quote enrichment fallback above if the routine needs an earnings section, and label any names as manual-review only.

### Step 2: Review Results

1. Read the generated JSON and Markdown reports
2. Load `references/scoring_methodology.md` for scoring interpretation context
3. Focus on Grade A and B stocks for actionable setups

### Step 3: Present Analysis

For each top candidate, present:
- Composite score and letter grade (A/B/C/D)
- Earnings gap size and direction
- Pre-earnings 20-day trend
- Volume ratio (20-day vs 60-day average)
- Position relative to 200-day and 50-day moving averages
- Weakest and strongest scoring components

### Step 4: Provide Actionable Guidance

Based on grades:
- **Grade A (85+):** Strong earnings reaction with institutional accumulation - consider entry
- **Grade B (70-84):** Good earnings reaction worth monitoring - wait for pullback or confirmation
- **Grade C (55-69):** Mixed signals - use caution, additional analysis needed
- **Grade D (<55):** Weak setup - avoid or wait for better conditions

## Output

- `earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json` - Structured results with schema_version "1.0"
- `earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.md` - Human-readable report with tables

### Unknown earnings timing

FMP does not confirm a bmo/amc session for every earnings row; unconfirmed
rows report `earnings_timing: "unknown"` and the gap calculation assumes the
AMC window as a fallback. Both reports surface `timing_unknown_count` out of
`timing_candidates_total` so this assumption stays visible rather than
blending unnoticed into the scores.

## Resources

- `references/scoring_methodology.md` - 5-factor scoring system, grade thresholds, and entry quality filter rules
