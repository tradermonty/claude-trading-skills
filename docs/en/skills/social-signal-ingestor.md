---
layout: default
title: "Social Signal Ingestor"
grand_parent: English
parent: Skill Guides
nav_order: 61
lang_peer: /ja/skills/social-signal-ingestor/
permalink: /en/skills/social-signal-ingestor/
generated: true
---

# Social Signal Ingestor
{: .no_toc }

Ingest trading signals from YouTube channels — fetch video transcripts via yt-dlp, then extract one structured signal note per ticker (direction, price levels, sources) into a local vault. Use when mining social/video commentary for tradeable tickers, sentiment, and catalysts to feed the edge pipeline. YouTube is v1; X/Reddit plug in later via Agent-Reach.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/social-signal-ingestor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/social-signal-ingestor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Mine trading YouTube channels for tradeable signals. A deterministic fetch step
(`ingest_youtube.py`, wrapping the `yt-dlp` binary) stores immutable raw artifacts
and writes a source stub per new video; this skill then reads each transcript and
extracts **one signal note per ticker** into a vault; a deterministic index build
(`build_signal_index.py`) emits `signals/index.json`, which `edge-social-aggregator`
consumes. No video/audio is downloaded — metadata + subtitles only.

Storage is namespaced by agent: `data/<agent>/{raw,vault,state}` (default agent `social`).

---

## 2. When to Use

- Mining YouTube trading commentary for tickers, sentiment, price levels, and catalysts.
- Producing social signals to merge (low-weight) into `edge-signal-aggregator`.
- NOT for fundamentals/technicals on a known ticker (use `us-stock-analysis`), and not
  for delivery/messaging (that is Hermes territory).

---

## 3. Prerequisites

- `yt-dlp` on PATH (`pip install yt-dlp`). Public subtitles only — no API key.
- `pyyaml` (already a repo dependency).
- A channel list (`assets/channels.yaml` by default; override with `--config`).

---

## 4. Quick Start

```bash
python3 skills/social-signal-ingestor/scripts/ingest_youtube.py \
  --agent social --config skills/social-signal-ingestor/assets/channels.yaml
```

---

## 5. Workflow

### Step 1 — Fetch new videos (deterministic)

```bash
python3 skills/social-signal-ingestor/scripts/ingest_youtube.py \
  --agent social --config skills/social-signal-ingestor/assets/channels.yaml
```

Writes raw artifacts to `data/social/raw/youtube/<channel>/<video_id>/`
(`metadata.json`, `transcript .clean.txt`), a source stub in
`data/social/vault/current/sources/youtube/`, updates `state/youtube_state.json`
(idempotent — seen videos are skipped), and prints a JSON report listing
`new_videos` (each with `clean_transcript_paths` and `source_stub`).

### Step 2 — Extract signal notes (the analysis step)

For every entry in the report's `new_videos`:

1. Read the `clean_transcript_paths` and the `source_stub`.
2. Fill in the source stub's summary + trading-relevant claims.
3. Create **one signal note per real, quotable ticker** in
   `data/<agent>/vault/current/signals/` named `YYYY-MM-DD_TICKER_short-slug.md`,
   following `references/signal-schema.md`. Required frontmatter: `title`, `type: signal`,
   `ticker` (one symbol), `direction` (long/short/watch), `time_horizon`,
   `claim_date`, `sources` (wikilinks to the source note).
4. Add a `watch` block only when the source gives clean numeric trigger/invalidation
   levels. Conviction is computed downstream from recency and corroboration, so there
   is no confidence field to set — just be accurate about `claim_date` and `sources`.
5. If the video calls an **options** trade, set `instrument: option`, name the
   `option_strategy` (e.g. `long_call`, `put_credit_spread`), and add one `option_legs`
   entry per leg (`{side, right, strike, expiry, ratio}`); set `net_premium` only when the
   source states the trade's cost. Plain stock picks need none of these — `instrument`
   defaults to `stock`. Capture only what the source actually states; never invent strikes,
   expiries, or premiums.
6. Never invent a ticker for a theme with no instrument; never join symbols
   (`STRL/POWL`) into one note.

### Step 3 — Rebuild the machine index (deterministic)

```bash
python3 skills/social-signal-ingestor/scripts/build_signal_index.py --agent social
```

Scans the signal notes and writes two files, reporting any parse errors or multi-symbol
ticker warnings. Run this AFTER Step 2.

- `signals/index.json` — the full week's signals (cumulative; notes accumulate in the vault
  until the weekly reset). Consumed by `edge-social-aggregator` and for tracking.
- `signals/index_last.json` — only the records new since the previous `index.json` (this run's
  delta), overwritten each run. Consumed by `robinhood-trade-executor` so it buys only the fresh
  picks, not the whole week's accumulation. Same schema as `index.json`.

---

## 6. Resources

**References:**

- `skills/social-signal-ingestor/references/signal-schema.md`

**Scripts:**

- `skills/social-signal-ingestor/scripts/build_signal_index.py`
- `skills/social-signal-ingestor/scripts/clean_transcript.py`
- `skills/social-signal-ingestor/scripts/ingest_youtube.py`
- `skills/social-signal-ingestor/scripts/reset_weekly_vault.py`
