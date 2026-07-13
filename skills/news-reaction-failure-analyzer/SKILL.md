---
name: news-reaction-failure-analyzer
description: Judge whether a market FAILED to react to news favorable to a crowded speculative position — step 2 of Jason Shapiro's COT contrarian process. Consumes a cot-contrarian-detector report (or an explicit direction) plus a Claude-curated events JSON, fetches the underlying price series with a documented fallback chain, and produces a fail-closed CONFIRMED / NOT_CONFIRMED / INSUFFICIENT_EVIDENCE verdict using a statistically validated drift-significance test (not a naive failure-ratio, which false-confirms on pure noise). Generic beyond COT — reusable for PEAD and macro-crowding news-failure checks. Use when the user asks to check news-failure confirmation, whether a crowded market "shrugged off" good/bad news, or wants to run Shapiro step 2 on a CROWDED_LONG/CROWDED_SHORT market.
---

# News Reaction Failure Analyzer

## Overview

Implements step 2 of Jason Shapiro's COT contrarian process: once a market
is flagged as crowded (`cot-contrarian-detector`, step 1), check whether it
FAILED to react to news that should have rewarded the crowd. A crowded-long
market that doesn't rally on genuinely bullish news, or a crowded-short
market that doesn't sell off on genuinely bearish news, is the core
behavioral tell that the crowd has run out of buying/selling power — this
is the confirmation step that turns "crowded" into a contrarian setup
candidate (steps 3-5, still manual: price-action confirmation, entry, exit).

**Why this isn't a naive failure-ratio check:** an earlier design flagged
"news failure" whenever fewer than half the relevant events "responded" —
but under pure noise, roughly 69% of individual events fail to respond by
chance, so that rule would CONFIRM on random noise 48-83% of the time
depending on sample size. This skill instead requires the market to have
moved *significantly against* the crowd's favorable news (a drift-
significance test with a Monte-Carlo-verified null false-positive bound),
never merely "didn't respond enough." See
`references/news-failure-patterns.md` for the full statistical rationale.

## When to Use This Skill

**English:**
- "Did the market shrug off [event] even though [asset] is crowded long/short?"
- "Run a news-failure check on [symbol]"
- "Is [symbol] confirmed for a Shapiro-style contrarian setup?"
- After `cot-contrarian-detector` flags a market CROWDED_LONG / CROWDED_SHORT
  and the user wants to move to step 2

**Japanese:**
- 「この市場は好材料に反応しなかった？」
- 「COTで偏っているこの銘柄のニュース失敗を確認して」

**Do NOT use when:**
- The market isn't crowded (NEUTRAL classification) — this skill refuses
  fail-closed without an explicit `--direction` override
- No curated events JSON exists yet — WebSearch must run first (Phase 2
  below); never fabricate events or URLs to get a verdict

## Prerequisites

- **FMP API Key:** Required. Set `FMP_API_KEY` or pass `--api-key`. Used
  for price data only (`stable/historical-price-eod/light`) — coverage
  varies by symbol; see `references/price-source-map.md`.
- **Python 3.9+** with `requests` installed.
- **WebSearch access** to curate the events JSON (Phase 2). Skill degrades
  gracefully without it (states the limitation; never fabricates events).
- **Optional:** a `cot-contrarian-detector` JSON report (`--detector-json`)
  to auto-resolve symbol + direction, or supply `--direction` explicitly.

## Workflow

### Phase 1: Obtain symbol + direction

From a `cot-contrarian-detector` report (`--detector-json`, symbol looked
up in `markets[]`) or directly from the user (`--symbol` + `--direction`).
A `NEUTRAL` classification, a symbol missing from the report, or a report
older than `--max-detector-age-days` (default 10) all refuse fail-closed
with a specific reason — only an explicit `--direction` overrides.

### Phase 2: Curate the events JSON via WebSearch

Search news in the evaluation window (`--window-days`, default 10) using
the 4-tier source hierarchy (issuer/primary → SEC/official stats → wire →
portal — see `references/news-failure-patterns.md`). Write findings into
an events JSON from `references/news-failure-patterns.md`'s template —
`event`, `event_time` (ISO8601 with explicit UTC offset), `source_url`,
`source_tier`, `expected_impact` (BULLISH/BEARISH) per event.

**Never fabricate events or URLs.** WebSearch unavailable → state it
explicitly; proceed without an events JSON only if the user accepts an
`INSUFFICIENT_EVIDENCE` result (reason `no_events_provided`) — the CLI
never raises an exception for a missing events file, it always exits 0
with a documented reason.

### Phase 3: Run the CLI

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json reports/cot_crowding_2026-07-12.json \
  --events-json reports/nrf_events_B6_2026-07-12.json \
  --output-dir reports/
```

The script fetches the price series (documented fallback chain — futures
symbol first, ETF proxy if 402/restricted or `rows == 0`; see
`references/price-source-map.md`), computes effective dates / returns /
z-scores per event, clusters events whose 3-trading-day windows overlap
(independence guard), and synthesizes the verdict.

### Phase 4: Present verdict + handoff

Present the verdict, aggregate stats (`drift_stat`, `responded_ratio`), and
the evidence table (per-event returns/z-scores/reaction labels, with any
`dropped_events` reasons shown — never silently hidden). If a proxy
(`run_context.proxy_used`) was used, note the tracking-error caveat.

Emit a handoff block for `contrarian-setup-gate` (#241, not yet built):

```json
{"news_failure": {"verdict": "CONFIRMED", "confidence": "HIGH", "report_path": "reports/nrf_B6_2026-07-12.json"}}
```

## Output

- **JSON:** `reports/nrf_<symbol>_<as-of-date>.json` — `schema_version`,
  `symbol`, `direction`, `expected_direction`, `actual_reaction`
  (`FAILED_TO_RALLY`/`FAILED_TO_SELL_OFF`/`RALLIED`/`SOLD_OFF`/
  `MIXED_REACTION`/`NO_DATA`), `verdict`, `confidence`,
  `relevant_events_used`, `aggregate` (mean_z3/drift_stat/responded_ratio),
  `evidence[]`, `dropped_events[]`, `run_context`.
- **Markdown:** `reports/nrf_<symbol>_<as-of-date>.md` — human-readable
  verdict, aggregate stats, evidence table, dropped-events table, proxy
  caveat (if used), and methodology footnote.

## Guardrails

- **CONFIRMED is not a trade signal.** It confirms step 2 of 5 — price-
  action confirmation (step 3), entry (step 4), and exit (step 5) are still
  manual and still required before any position.
- **INSUFFICIENT_EVIDENCE never advances the pipeline.** Fewer than
  `--min-events` (default 3) usable relevant event *clusters*, a missing
  detector report, or a detector vintage (`data_date`) that's missing,
  unparsable, dated after `--as-of`, or older than
  `--max-detector-age-days` (stale), a `NEUTRAL` classification without an
  explicit override, or no working price source all produce this verdict
  — never a crash, never a forced call on inadequate data.
- **COT publication lag.** COT data is 3-9 days old by the time it's read
  (see `cot-contrarian-detector`); news-failure evidence should be read in
  that context, not as same-day confirmation.
- **Counter-direction events are context only** — shown in the evidence
  table but excluded from the verdict (only events whose `expected_impact`
  matches the crowd's `expected_direction` count).
- **Proxy-based prices are noted, not hidden.** When an ETF proxy was used
  (`run_context.proxy_used`), the report says so — tracking error, expense
  drag, and roll-timing differences make the reaction-direction read
  approximate, not exact.
- **Residual statistical risk under extreme correlation.** The verdict's
  null false-CONFIRMED rate is hard-verified under i.i.d. noise (<8%) and
  under a realistic residual-correlation stress (AR(1) ρ=0.1, <10%). Under
  an intentionally extreme correlation stress (lag-1 ρ=0.3 across
  non-clustered event windows — roughly 10x liquid-futures empirical
  autocorrelation), the measured null rate rises to ~11-13%. This is a
  documented v1 limitation, not a silent gap — see
  `references/news-failure-patterns.md` for the full numbers. Users who
  want the stricter <10% margin even under that stress can pass
  `--drift-z 1.75` (at the cost of missing some genuine news-failure
  signals, not just noise).
- **Not investment advice.** Research/educational purposes only.

## Resources

### `references/news-failure-patterns.md`
Full methodology: what qualifies as a relevant event, the 4-tier source
hierarchy, worked examples, the events-JSON curation guide + template, and
the verdict-threshold rationale (why drift-significance, not a naive
ratio; the Monte-Carlo-verified null bounds).

### `references/price-source-map.md`
Per-market price-source fallback chain, verified/402/0-rows status (live-
probed at implementation time), ETF-proxy caveats, and markets with no
viable source (documented `no_price_source` cases: VX, ZQ, HO, all agri on
this key).

### When to Load References
- **First use / explaining the methodology:** Load
  `references/news-failure-patterns.md`
- **Explaining why a market has no verdict (no_price_source):** Load
  `references/price-source-map.md`
- **Regular execution:** References not needed for the CLI itself — needed
  for Phase 2 (events curation) and for explaining results to the user
