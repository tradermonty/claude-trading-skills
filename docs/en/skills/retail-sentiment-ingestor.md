---
layout: default
title: "Retail Sentiment Ingestor"
grand_parent: English
parent: Skill Guides
nav_order: 52
lang_peer: /ja/skills/retail-sentiment-ingestor/
permalink: /en/skills/retail-sentiment-ingestor/
generated: true
---

# Retail Sentiment Ingestor
{: .no_toc }

Ingest real-time retail sentiment for a list of tickers from StockTwits cashtag streams and Reddit (r/wallstreetbets, r/stocks, r/investing) with no API key, plus an optional X path, and emit one scored signal note per ticker into the shared social vault. Use when gauging retail crowd sentiment, spotting cross-source divergence, or flagging a >=90/10 StockTwits over-extension to feed the edge pipeline. Scoring is fully deterministic (data-in-prompt, no model tool-calling) so nothing is fabricated.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/retail-sentiment-ingestor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/retail-sentiment-ingestor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Score real-time retail crowd sentiment per ticker and write it into the SAME
vault schema `social-signal-ingestor` uses, so `build_signal_index.py` and
`edge-social-aggregator` consume it with no change. `ingest_retail_sentiment.py`
fetches StockTwits cashtag messages (with their user-applied Bullish/Bearish
labels) and Reddit posts keylessly, optionally sweeps X, then runs **pure,
deterministic scoring** — sentiment band + 0-10 score + confidence, a StockTwits
message-count base rate, engagement-weighted Reddit, cross-source divergence
detection, and a contrarian over-extension flag at a >=90/10 StockTwits lean.

Unlike the YouTube ingestor, there is **no LLM extraction step**: StockTwits
carries explicit labels and Reddit/X carry numeric engagement, so the whole
pipeline is fetch → score → write. This is the anti-fabrication win — the model
never free-forms over raw feeds, so it cannot invent tickers, levels, or
sentiment (the failure mode that forced TradingAgents to redesign its sentiment
analyst around data-in-prompt).

Storage is namespaced by agent: `data/<agent>/{raw,vault,state}` (default agent
`social`, shared with `social-signal-ingestor` so corroboration spans platforms).

---

## 2. When to Use

- Gauging retail sentiment on a watchlist of tickers before or alongside the
  edge pipeline.
- Detecting cross-source divergence (retail leaning one way, another crowd the
  other) or a crowded >=90/10 StockTwits over-extension.
- NOT for institutional/news framing (that is `market-news-analyst`), not for
  fundamentals/technicals on a known ticker (`us-stock-analysis`), and not for
  delivery/messaging (Hermes territory).

---

## 3. Prerequisites

- Python 3.9+ and `pyyaml` (already a repo dependency). No API key for the
  StockTwits + Reddit path.
- Network egress to `api.stocktwits.com` and `reddit.com`.
- Optional X path: an X API bearer token in `X_API_KEY` (or `--x-api-key`).
  Historical event-window search needs a paid full-archive X tier.

---

## 4. Quick Start

```bash
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py \
  --tickers "NVDA,AMD,TSLA" --agent social
```

---

## 5. Workflow

### Step 1 — Ingest + score (deterministic, one command)

```bash
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py \
  --tickers "NVDA,AMD,TSLA" --agent social
```

For each ticker the script fetches StockTwits + Reddit, scores every source,
combines them, and (unless `--dry-run`) writes raw artifacts, one source note
per platform, and one signal note per ticker into
`data/social/vault/current/`. It prints a JSON run report and also saves a
markdown+JSON summary to `reports/`.

Seed tickers from StockTwits trending instead of (or in addition to) a list:

```bash
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py --trending
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py \
  --watchlist watchlists/swing.txt --tickers "NVDA" --dry-run
```

Add the optional impression-ranked X sweep (needs `X_API_KEY`), or a historical
event-window sweep via full-archive search:

```bash
export X_API_KEY=...   # bearer token
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py \
  --tickers "NVDA" --use-x
python3 skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py \
  --tickers "TSLA" --use-x --x-start 2026-01-27T00:00:00Z --x-end 2026-01-31T00:00:00Z
```

### Step 2 — Rebuild the machine index (deterministic)

The index builder lives in `social-signal-ingestor` and scans the shared vault,
so it picks up these notes with no change:

```bash
python3 skills/social-signal-ingestor/scripts/build_signal_index.py --agent social
```

### Step 3 — Score into the edge pipeline

```bash
python3 skills/edge-social-aggregator/scripts/aggregate_social.py \
  --agent social --output-dir reports/
```

`edge-social-aggregator` deduplicates each ticker across platforms and scores
`recency × corroboration`; a retail-sentiment ticker that a YouTube video also
named unions to a higher `n_sources`.

---

## 6. Resources

**References:**

- `skills/retail-sentiment-ingestor/references/sentiment_scoring.md`

**Scripts:**

- `skills/retail-sentiment-ingestor/scripts/ingest_retail_sentiment.py`
