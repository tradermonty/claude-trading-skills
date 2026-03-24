# Universe Builder Design

## Goal

Maintain a rolling watchlist of 50–100 quality stocks for the VCP screener, built up gradually each evening to stay within FMP's 250 API call/day free tier limit.

## Problem

The VCP screener currently scans the full S&P 500 (~500 stocks), requiring ~1,008 FMP API calls per run — 4× the free tier daily limit. This means the VCP screener cannot run on the free tier at all.

## Solution Overview

A two-phase pipeline:

1. **FINVIZ pre-filter** (Sunday evening, no API calls) — scrapes FINVIZ free public screener to produce a ranked queue of ~150 candidates
2. **Nightly FMP batch scan** (Mon–Fri 16:30 ET, ~20 stocks/night) — scans the next batch from the queue using FMP, building up the universe over the week

The VCP screener reads its symbol list from `cache/vcp-universe.json` instead of fetching S&P 500 constituents, reducing daily FMP usage from ~1,008 to ~60–120 calls.

---

## Architecture

### Components

**`universe_builder.py`** — main module (replaces the existing stub)
- `UniverseBuilder` class with methods:
  - `build_queue()` — FINVIZ scrape + Finnhub sentiment scoring → writes `cache/universe-queue.json`
  - `run_nightly_batch()` — FMP scan of next 30 from queue + re-check weakening stocks → updates `cache/vcp-universe.json`

**`config.py`** — pass `--universe` arg to VCP screener from `cache/vcp-universe.json`

**`scheduler.py`** — add two new jobs:
- Sunday 18:00 ET: `build_queue()`
- Mon–Fri 16:30 ET: `run_nightly_batch()`

---

## Data Flow

```
Sunday 18:00
FINVIZ free screener (scrape, no API key)
  + Finnhub sentiment per stock (FINNHUB_API_KEY)
  → cache/universe-queue.json   (ranked list of ~150 candidates)
  → cache/universe-news-sentiment.json  (sentiment scores for news page)

Mon–Fri 16:30
Re-check weakening stocks from cache/vcp-universe.json  (~10 calls)
  + Scan next 20 from universe-queue.json  (~42 calls)
  → cache/vcp-universe.json   (active universe, 50–100 stocks)

Daily 09:32
VCP screener reads cache/vcp-universe.json
  → uses --universe flag with symbol list
  → ~60–120 FMP calls/day (fits in 250 free tier)
```

---

## FINVIZ Pre-filter Criteria

Stocks must meet all of the following to enter the queue:

- Price above 50-day MA
- Price above 200-day MA
- Average daily volume > 500,000
- Stock up > 5% over last 3 months

Stocks are then ranked by Finnhub news sentiment score (last 7 days). Positive sentiment → higher priority in queue.

---

## Universe Status Tracking

Each stock in `vcp-universe.json` has a `status` field:

| Status | Meaning |
|--------|---------|
| `active` | Passes all criteria |
| `weakening` | Failed one nightly re-check — kept in universe, flagged |
| removed | Failed two consecutive re-checks — dropped from universe |

On each nightly batch run, weakening stocks are re-checked first before scanning new candidates from the queue.

---

## Cache Files

| File | Written by | Read by |
|------|-----------|---------|
| `cache/universe-queue.json` | `build_queue()` | `run_nightly_batch()` |
| `cache/vcp-universe.json` | `run_nightly_batch()` | VCP screener, pivot monitor |
| `cache/universe-news-sentiment.json` | `build_queue()` | market-news-analyst page |

---

## API Usage

| Phase | Calls | Fits in 250/day? |
|-------|-------|-----------------|
| Sunday queue build | 0 FMP (FINVIZ scrape + Finnhub) | ✅ |
| Nightly batch (20 stocks) | ~42 FMP | ✅ |
| VCP screener daily run (50–100 stocks) | ~102–202 FMP | ✅ |
| **Total worst case** | **~244** | ✅ |

---

## Schedule

| Time (ET) | Job | What it does |
|-----------|-----|-------------|
| Sunday 18:00 | `build_queue` | FINVIZ scrape + Finnhub sentiment → queue |
| Mon–Fri 16:30 | `run_nightly_batch` | Re-check weakening + scan next 20 → universe |

---

## Out of Scope

- No UI changes required — VCP screener output already displays on the dashboard
- No new API keys required — uses existing FINVIZ (free, no key) and Finnhub (already configured)
- The Finnhub sentiment data fed to `universe-news-sentiment.json` can be surfaced on the news page in a future improvement
