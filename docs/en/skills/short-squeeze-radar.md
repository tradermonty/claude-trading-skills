---
layout: default
title: "Short Squeeze Radar"
grand_parent: English
parent: Skill Guides
nav_order: 56
lang_peer: /ja/skills/short-squeeze-radar/
permalink: /en/skills/short-squeeze-radar/
generated: true
---

# Short Squeeze Radar
{: .no_toc }

Rank US equities by short-squeeze potential using FREE FINRA data (no API key). Use when the user asks about short squeezes, crowded shorts, short interest, days-to-cover, short-volume ratio, "who could squeeze", GME/AMC-style meme setups, or wants to screen a watchlist for squeeze-primed names. Fetches FINRA Reg SHO daily short-volume files and optional bi-monthly short-interest data, detects rising (piling-in) short-volume inflections, and flags crowded-short vs low-pressure names.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/short-squeeze-radar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/short-squeeze-radar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Rank US equities by short-squeeze potential from FREE, no-auth FINRA data. Two inputs drive the scan:

1. **FINRA Reg SHO daily short-sale volume files** — published every trading day, pipe-delimited, no auth. This is the raw input behind every "short volume %" product. `short_volume_ratio = (ShortVolume + ShortExemptVolume) / TotalVolume`. A daily executed short-flow proxy: a *rising* ratio means shorts are piling in.
2. **Bi-monthly Consolidated Short Interest** (optional but recommended) — reported shares short, average daily volume, and `days_to_cover = short_interest / avg_daily_volume`. Days-to-cover is the classic squeeze-pressure gauge. Supplied as a local CSV/JSON file so the skill stays free and offline.

The scanner builds a multi-day short-volume-ratio series per symbol to detect a rising inflection, ranks candidates by days-to-cover, classifies each as crowded-short / neutral / low-pressure, and flags squeeze-primed names.

---

## 2. When to Use

- User asks "which stocks could short squeeze?" or "screen my watchlist for squeeze setups"
- User mentions short interest, days-to-cover, crowded shorts, short-volume ratio, or dark-pool short volume
- User wants a free alternative to paid short-squeeze scanners
- User is evaluating a meme/high-short-interest name and wants the short-side picture

---

## 3. Prerequisites

- No API keys required. FINRA daily files are free and un-authenticated.
- Python 3.9+ (standard library only for parsing/analytics; `urllib` for fetch).
- Optional: a downloaded bi-monthly short-interest file (CSV or JSON) from FINRA, NASDAQ, or a broker to enable days-to-cover ranking.

---

## 4. Quick Start

```bash
# Ticker list, no short interest (short-volume-ratio ranking only)
python3 skills/short-squeeze-radar/scripts/scan_short_squeeze.py \
  --tickers GME,AMC,TSLA \
  --output-dir reports/

# Watchlist file + short interest for full days-to-cover ranking
python3 skills/short-squeeze-radar/scripts/scan_short_squeeze.py \
  --watchlist watchlist.txt \
  --short-interest-file short_interest.csv \
  --lookback-days 5 \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Gather Targets

Collect the symbols to scan. Accept a watchlist file (JSON array or newline/comma-delimited text) and/or a comma-separated `--tickers` string. Scanning is symbol-filtered — the FINRA daily file lists thousands of tickers, so always pass a target set.

### Step 2: Obtain Short-Interest Data (Optional but Recommended)

Days-to-cover ranking requires reported short interest, which is bi-monthly and not in the daily short-volume file. If the user has a short-interest export (FINRA/NASDAQ/broker), pass it via `--short-interest-file`. Expected fields per row: `ticker` (or `symbol`), `short_interest`, `avg_daily_volume`, and optionally `days_to_cover` (computed as `short_interest / avg_daily_volume` when absent) and `settlement_date`.

Without short interest, the scan still ranks on short-volume ratio and rising-inflection, but the composite score is capped at 60 and names are flagged "no short-interest data".

### Step 3: Run the Scanner

```bash
# Ticker list, no short interest (short-volume-ratio ranking only)
python3 skills/short-squeeze-radar/scripts/scan_short_squeeze.py \
  --tickers GME,AMC,TSLA \
  --output-dir reports/

# Watchlist file + short interest for full days-to-cover ranking
python3 skills/short-squeeze-radar/scripts/scan_short_squeeze.py \
  --watchlist watchlist.txt \
  --short-interest-file short_interest.csv \
  --lookback-days 5 \
  --output-dir reports/
```

Fetches are TTL-cached (default 6h) under the system temp dir; the daily file is immutable once published, so re-runs are cheap.

### Step 4: Load the Interpretation Reference

Read `references/squeeze_signals.md` for the mechanics of a short squeeze, how to read the short-volume ratio vs. short interest, the days-to-cover / crowded-short thresholds, and the important caveats (executed short volume is a flow proxy, not reported short interest; a squeeze needs a demand catalyst).

### Step 5: Interpret and Present

Present the ranked table and highlight squeeze-primed names (crowded short + rising short-volume ratio + hard-to-cover). For each primed name, state the days-to-cover, the short-volume-ratio trend, and the caveat that a squeeze requires a price/demand catalyst — the radar identifies *fuel*, not ignition. Route any position-sizing to the position-sizer skill and confirm borrow/availability before acting.

---

## 6. Resources

**References:**

- `skills/short-squeeze-radar/references/squeeze_signals.md`

**Scripts:**

- `skills/short-squeeze-radar/scripts/scan_short_squeeze.py`
