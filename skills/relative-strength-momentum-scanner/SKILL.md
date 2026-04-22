---
name: relative-strength-momentum-scanner
description: IBD-style relative strength screener. Ranks tickers by composite 3/6/9/12-month returns vs a benchmark, filters for trend quality (above MA50 and MA200), and emits a pullback-to-MA20 entry plan. Produces the same Candidate schema as vcp-screener, canslim-screener, and pead-screener so it plugs straight into the trade-loop orchestrator. Invoke with "run momentum screen", "RS rating scan", "find leading stocks", "pullback momentum candidates".
---

# Relative Strength Momentum Scanner

Ranks a universe of tickers by composite 3/6/9/12-month relative strength
vs a benchmark (default SPY), filters for trend quality, and emits pullback
entries on leaders. Output is a JSON + markdown report consumable by
`trade-loop-orchestrator` as a first-class screener.

## When to Use

- Daily leaderboard generation (runs premarket as part of the screener fan-out)
- Ad-hoc "what's leading the market right now" query
- Sector-rotation scan (group leaders by GICS sector)

## Universe

Accepts a ticker list via `--tickers AAPL,MSFT,...` or `--tickers-file
path/to/universe.txt`. The `universe.txt` format is one ticker per line,
optional `#` comments. Defaults to S&P 500 if no list is provided (via the
bundled `references/sp500.txt`).

## Metrics

For each ticker the scanner computes, using local OHLCV bars:

1. **Return over N trading days** for N ∈ {63, 126, 189, 252} (≈ 3, 6, 9, 12 months).
2. **Relative return** = ticker_return - benchmark_return for each window.
3. **Composite RS score** (0–99), IBD-style:
   ```
   composite = 0.40 * rel_ret_63  + 0.20 * rel_ret_126
             + 0.20 * rel_ret_189 + 0.20 * rel_ret_252
   ```
   then percentile-ranked across the screened universe and scaled to 1–99.
4. **Trend filters** (hard gates):
   - `close > MA50` AND `close > MA200`
   - `MA50 > MA200`
   - `close` within `[0.90 × 52w_high, 1.00 × 52w_high]`
5. **Pullback trigger** (soft signal):
   - Today's close within 2% of MA20, AND
   - `MA20 > MA50`
6. **Entry / stop / target**:
   - `entry_price = close` (market-on-open next session)
   - `stop_loss = min(MA50, recent_swing_low_20d) * 0.99`
   - `target = entry + 2 × (entry - stop_loss)`  (2R target)

Candidates failing any hard gate are excluded. Candidates failing only the
soft pullback trigger appear in the report but are flagged as
`status: watchlist` rather than `status: entry_ready`.

## Output

Writes `reports/rsm_scanner_<date>.json` with this shape:

```json
{
  "as_of": "2026-04-21",
  "benchmark": "SPY",
  "universe_size": 500,
  "candidates": [
    {
      "ticker": "AAPL",
      "rs_score": 92,
      "rel_ret_63": 12.4,
      "rel_ret_252": 38.1,
      "ma20": 184.2, "ma50": 178.9, "ma200": 162.1,
      "close": 185.4,
      "entry_price": 185.4,
      "stop_loss": 175.3,
      "target": 205.6,
      "r_multiple_to_52w_high": 1.6,
      "status": "entry_ready",
      "sector": "Technology",
      "side": "buy",
      "entry_type": "market",
      "primary_screener": "rsm-scanner",
      "supporting_screeners": [],
      "strategy_score": 92,
      "confidence": 0.78,
      "notes": "RS 92 leader at MA20 pullback"
    }
  ]
}
```

A markdown companion is written at `reports/rsm_scanner_<date>.md`.

## Workflow

1. Load the ticker universe (CLI flag or default).
2. Load local OHLCV CSV bars from `--bars-dir` (same format as
   paper-replay-harness: `<TICKER>.csv` with columns
   `date,open,high,low,close,volume`).
3. Skip tickers with fewer than 252 trading days of history.
4. Compute returns, moving averages, 52-week high, trend filters.
5. Percentile-rank the composite RS across surviving tickers.
6. Apply pullback trigger to assign `entry_ready` vs `watchlist` status.
7. Compute entry/stop/target and package into candidate dicts.
8. Sort descending by `rs_score`.
9. Write JSON + markdown to `--output-dir` (default `reports/`).

## Combining with Other Skills

- **trade-loop-orchestrator**: `screener_adapters.adapt_rsm_scanner` reads
  `rsm_scanner_<date>.json` and normalizes it into the Candidate schema.
- **paper-replay-harness**: emit candidates on historical days to simulate
  momentum-strategy backtests.
- **edge-pipeline-orchestrator**: consume RS-leader lists as an input layer
  for strategy concept generation.

## CLI

```bash
# Default S&P 500 universe, SPY benchmark, today's report
python3 skills/relative-strength-momentum-scanner/scripts/scan_rsm.py \
    --bars-dir data/bars/ --output-dir reports/

# Custom universe + narrower date (re-run for a past session)
python3 skills/relative-strength-momentum-scanner/scripts/scan_rsm.py \
    --tickers-file universes/tech200.txt \
    --bars-dir data/bars/ \
    --benchmark QQQ \
    --as-of 2026-03-31 \
    --output-dir reports/replay_screens/
```

## Determinism

Pure-function scanner: same CSV bars + same universe + same `as_of` →
byte-identical JSON output. No clock reads, no network calls.
