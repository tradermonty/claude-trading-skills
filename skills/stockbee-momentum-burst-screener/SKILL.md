---
name: stockbee-momentum-burst-screener
description: Screen US stocks for Stockbee-style short-term Momentum Burst setups using 4% breakout, dollar breakout, range expansion, volume expansion, prior range contraction, close-location, failure filters, and risk-distance scoring. Use when the user asks for Stockbee, Pradeep Bonde, momentum burst, 4% breakout, range expansion, dollar breakout, short-term swing momentum candidates, or 3-5 day burst setup review.
---

# Stockbee Momentum Burst Screener

Screen US equities for Stockbee-style short-term Momentum Burst candidates. The skill is a candidate-generation and setup-quality workflow, not a signal service or an auto-execution system.

## When to Use

- User asks for Stockbee / Pradeep Bonde style Momentum Burst screening
- User wants 4% breakout, dollar breakout, or range expansion candidates
- User asks for short-term 3-5 day swing momentum setups
- User wants to review whether a daily breakout has A/B/C setup quality
- User provides a symbol list, universe file, or historical OHLCV JSON for screening
- User wants candidate outputs to feed into `technical-analyst`, `position-sizer`, or `trader-memory-core`

## Prerequisites

- FMP API key for live universe and historical OHLCV screening:
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- Install `requirements.txt`, including the pinned exchange-calendar dependency.
- Optional no-API path: provide `--prices-json` containing daily OHLCV bars by symbol; historical fixtures need an explicit completed `--as-of YYYY-MM-DD`.
- Run only after the market-regime workflow allows new swing risk, or mark output as manual-review-only.

## Workflow

### Step 1: Choose Input Mode

Use one of three modes:

**Mode A: FMP universe scan**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

**Mode B: Explicit symbols**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols NVDA SMCI PLTR TSLA \
  --output-dir reports/
```

**Mode C: Offline OHLCV JSON**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --as-of 2026-11-06 \
  --output-dir reports/
```

### Completed-session freshness gate

Every input mode must pass the same freshness gate before scoring. The default
cutoff is the most recently **completed NYSE session**, frozen before collection
using the New York exchange calendar. Before the close, today's unfinished bar is
excluded; weekends, holidays, DST and early closes follow the shared calendar.

- `--as-of YYYY-MM-DD` selects the last session on/before that date. It must not
  exceed the actual latest completed session, even if today was specified before
  the close. Historical dates only clip the available input window: live FMP
  requests do not guarantee that older data will be available or point-in-time.
- `--max-bar-age-sessions N` permits at most N subsequent exchange sessions
  (nonnegative integer; default **0**). A wider tolerance deliberately admits
  older observations; it does not make them current. Keep the default for Day 1
  screening.
- Bars after the cutoff are excluded. Missing/noncanonical dates anywhere in
  supplied rows produce `REJECTED` / `invalid_price_date`. In `--prices-json`,
  each row's `date` (or `timestamp`) must be exactly `YYYY-MM-DD`; values such as
  `2026-11-06 00:00:00` or `2026-11-06T00:00:00Z` are rejected. A latest eligible bar
  on a non-session day is also rejected. No eligible bar produces
  `no_completed_price_data`. Too-old bars produce `stale_price_data`, score 0 and
  a do-not-trade downstream action. Short usable history stays rejected.
- With `--max-bar-age-sessions` above 0, a setup on an older (but tolerated) bar is
  capped at `MANUAL_REVIEW` with a `stale_bar_tolerated` soft tag, never
  `ACTIONABLE_DAY1`. The cap changes only `state`; `rating` and `setup_score`
  keep their computed values, and the tag is added only when the cap applies.
  Treat `bar_age_sessions > 0` as the authoritative stale-bar signal, and do not
  route on `rating` alone. When every processed symbol is stale (typically FMP has not
  yet published today's EOD data), the report carries a top-level `warnings`
  entry and a `## Warnings` section in the markdown.
- Calendar failure exits 1 before reports are written; invalid flag syntax exits
  2. A future/uncompleted as-of exits 1 before any provider request. Neither path
  replaces existing reports. The FMP universe additionally requests active
  equities and discards rows explicitly marked inactive; absent flags never
  substitute for the bar freshness gate.

JSON candidates include `latest_bar_date` (null if unplaceable/no eligible bar),
`expected_session`, `bar_age_sessions` (null when unknown) and
`max_bar_age_sessions`. Report metadata includes the expected session, allowed age,
`latest_bar_dates` by symbol and `stale_price_data_count`. The Markdown summary
shows cutoff, tolerance and stale count even without `--include-rejected`.
Dates and freshness do not establish provider identity, completeness, adjustment
or historical availability, and this screen never authorizes an order.

### Step 2: Run the Screening Pass

The script detects these trigger families:

- **4% Breakout:** `close / previous_close >= 1.04`, volume above previous day, and volume above the liquidity floor
- **Dollar Breakout:** `close - open >= 0.90`, volume above the liquidity floor
- **Range Expansion:** current daily range exceeds the prior three daily ranges while the prior day was not already extended

It then scores setup quality using:

- Trigger strength
- Volume expansion
- Prior base / range contraction quality
- Close location near the high of day
- Risk distance to the trigger-day low
- Failure filters such as prior 3-day run-up or recent 4% breakdown
- Market gate alignment

### Step 3: Review Output

Read the generated JSON and Markdown reports. For each candidate, present:

- Trigger type and all matched trigger tags
- Day gain, dollar gain, volume ratio, and close-location percentage
- Prior base length and base width
- Entry reference, stop reference, and risk percentage to stop
- Setup score, rating, state, and reject reasons
- Suggested downstream action

### Step 4: Send Survivors to Trade Planning

Use the output conservatively:

- **A / A- candidates:** send to `technical-analyst` for manual chart validation, then `position-sizer`
- **B candidates:** watchlist or smaller-risk review only
- **Watch-only candidates:** keep in model book; do not plan a trade unless chart review upgrades the setup
- **Rejected candidates:** retain for post-analysis, not for execution

## Output

- `stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json` - Structured candidate list, metadata, thresholds, score components, and rejects
- `stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.md` - Human-readable report grouped by rating/state

## Resources

- `references/momentum_burst_methodology.md` - Stockbee-style method summary and implementation boundaries
- `references/scoring_system.md` - Component weights, state thresholds, and failure filters
- `references/entry_exit_rules.md` - Entry reference, stop, sizing handoff, and exit template

## Shared FMP client

Live FMP access uses the bundled generated `scripts/fmp_client.py`, loaded only
when an FMP run starts, so offline modes still work without `requests`. CLI
key/environment precedence, the API-call budget and successful output shapes are
preserved. Requests use stable endpoints only; a denied, empty or failed stable
request does not fall back to retired v3 URLs. The shared client masks raw and
URL-encoded key echoes, retries malformed JSON once, and retries a 429 at most once,
after a 60-second wait, before stopping on a repeated rate limit.
