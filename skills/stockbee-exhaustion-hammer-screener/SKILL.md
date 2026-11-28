---
name: stockbee-exhaustion-hammer-screener
description: Screen US stocks for Stockbee-style selling-exhaustion hammer setups using prior momentum, pullback depth, undercut/reclaim, long lower-wick geometry, close-location, volume confirmation, quality/liquidity gates, and risk-distance scoring. Use when the user asks for Stockbee, Pradeep Bonde, exhaustion setup, selling exhaustion, hammer reversal, undercut reclaim, near-close reversal candidates, or pullback entries in high-quality funds-owned stocks.
---

# Stockbee Exhaustion Hammer Screener

Screen US equities for Stockbee-style selling-exhaustion hammer candidates. The skill is a candidate-generation and setup-quality workflow, not a signal service or an auto-execution system.

## When to Use

- User asks for Stockbee / Pradeep Bonde style exhaustion setup screening
- User wants near-close hammer / long lower-wick reversal candidates
- User wants to scan strong, liquid stocks that pulled back and may be seeing selling exhaustion
- User wants undercut/reclaim candidates before the close or after the close
- User provides a symbol list, universe file, or historical / provisional OHLCV JSON for screening
- User wants candidate outputs to feed into `technical-analyst`, `position-sizer`, `trader-memory-core`, or `stockbee-setup-fluency-trainer`

## Prerequisites

- FMP API key for live universe and historical OHLCV screening. `--fmp-universe` calls the company screener, which the free FMP plan does not include (HTTP 402/403); use `--symbols`, `--universe-file` or `--prices-json` on the free plan, or a plan that includes the screener (see `docs/en/getting-started.md#fmp-plans`):
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- Optional no-API path: provide `--prices-json` containing daily OHLCV bars by symbol. For the intended near-close use case, the latest bar should be a provisional current-day bar captured near the close.
- Optional `--profiles-json` can add quality metadata such as `marketCap`, `mutualFundHolders`, `institutionalHolders`, or `institutionalOwnershipPct`.
- Run only after the market-regime workflow allows new swing risk, or mark output as manual-review-only.

## Workflow

### Step 1: Choose Input Mode

Use one of three modes:

**Mode A: FMP universe scan**
```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --max-symbols 300 \
  --market-gate allowed \
  --output-dir reports/
```

**Mode B: Explicit symbols**
```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --symbols APP ENPH NVDA TSLA \
  --market-gate allowed \
  --output-dir reports/
```

**Mode C: Offline / near-close OHLCV JSON**
```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --prices-json data/near_close_daily_ohlcv.json \
  --profiles-json data/quality_profiles.json \
  --market-gate allowed \
  --output-dir reports/
```

For a best-effort FMP near-close run, use quote override. This costs one additional quote call per symbol and depends on provider freshness:

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --use-quote-latest \
  --max-api-calls 700 \
  --market-gate allowed \
  --output-dir reports/
```

### Step 2: Run the Screening Pass

The script detects these setup families:

- **Selling exhaustion hammer:** long lower wick, small body, strong close-location, and recovery from the day low
- **Undercut/reclaim hammer:** current low undercuts the prior short-term low and the near-close price reclaims that level
- **Prior momentum pullback:** recent high formed within the configured lookback, followed by a controlled pullback rather than a long-term downtrend
- **High-quality / liquid context:** price, volume, 20-day average dollar volume, market-cap metadata, and optional holder metadata

It then scores setup quality using:

- Quality / liquidity
- Prior momentum
- Pullback and selling-exhaustion context
- Hammer candle geometry
- Risk distance to the day low plus buffer
- Market gate alignment

### Step 3: Review Output

Read the generated JSON and Markdown reports. For each candidate, present:

- Trigger type and all matched tags
- Pullback depth from recent high and days since that high
- Undercut/reclaim status and short-term prior low
- Hammer geometry: lower wick, body, upper wick, close location, recovery from low
- Volume ratios, average dollar volume, and quality metadata
- Entry reference, stop reference, and risk percentage to stop
- Setup score, rating, state, and reject reasons
- Suggested downstream action

### Step 4: Send Survivors to Trade Planning

Use the output conservatively:

- **A / A- candidates:** validate chart manually, check earnings/news risk, then send to `position-sizer`
- **B candidates:** manual review or next-day hammer-high confirmation
- **Watch candidates:** keep on watchlist / model book; wait for follow-through or tighter risk
- **Rejected candidates:** retain for post-analysis, not for execution

## Output

- `stockbee_exhaustion_hammer_YYYY-MM-DD_HHMMSS.json` - Structured candidate list, metadata, thresholds, score components, and rejects
- `stockbee_exhaustion_hammer_YYYY-MM-DD_HHMMSS.md` - Human-readable report grouped by rating/state

Both reports carry an `evaluation_coverage` block (`docs/dev/evaluation-coverage-contract.md`).
Read a zero-candidate result together with its `verdict`: only `complete` means
every requested symbol reached a screening decision. Short price histories and
fetch failures are listed under `not_evaluated_reasons`, not counted as
rejections. A run where nothing could be evaluated still writes both reports,
with verdict `not_evaluable` and exit 0.

## Resources

- `references/exhaustion_hammer_methodology.md` - Stockbee-style method summary and implementation boundaries
- `references/scoring_system.md` - Component weights, state thresholds, and failure filters
- `references/near_close_operations.md` - Near-close operational checklist and scheduling notes

## Shared FMP client

Live FMP access uses the bundled generated `scripts/fmp_client.py`, loaded only
when an FMP run starts, so offline modes still work without `requests`. CLI
key/environment precedence, the API-call budget and successful output shapes are
preserved. Requests use stable endpoints only; a denied, empty or failed stable
request does not fall back to retired v3 URLs. The shared client masks raw and
URL-encoded key echoes, retries malformed JSON once, and retries a 429 at most once,
after a 60-second wait, before stopping on a repeated rate limit.

The quote override reads stable `/quote`; its default bar date is the
America/New_York calendar date, matching the history window.
