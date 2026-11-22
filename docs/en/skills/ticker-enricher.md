---
layout: default
title: "Ticker Enricher"
grand_parent: English
parent: Skill Guides
nav_order: 71
lang_peer: /ja/skills/ticker-enricher/
permalink: /en/skills/ticker-enricher/
generated: true
---

# Ticker Enricher
{: .no_toc }

Enrich ticker signals with company metadata (name, sector, industry) and prices (recommendation-date price, current price) from Yahoo Finance. Reads the social-signal vault index and emits a records file ready for a generic writer (e.g. write-supabase); the dashboard derives gain % and days held from the stored prices/dates. Reusable by any producer that has tickers.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ticker-enricher.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ticker-enricher){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Turns ticker signals into enriched, dashboard-ready records. For each ticker in the social-signal
vault index it looks up company name / sector / industry and the recommendation-date + current
price (Yahoo Finance), resolves the recommendation source (the YouTube channel from the source
note), and emits `reports/enriched_records_*.json`. Gain % and age are derived later by the UI
from `price_at_recommendation`, `current_price`, and `date_recommended` — not stored here.

It does **only** enrichment + record shaping — persisting the records is a separate, generic
concern (`write-supabase`). That separation makes both halves reusable: any producer with tickers
can enrich them here, and the records can be written to any table.

---

## 2. When to Use

- After social-signal-ingestor has produced/refreshed the signal index, to attach company +
  price data to each ticker.
- Before `write-supabase` (which uploads the emitted records file to a table).
- NOT for trade lifecycle / MAE-MFE (that's `trader-memory-core`).

---

## 3. Prerequisites

- A populated `data/<agent>/vault/current/signals/index.json`.
- `yfinance` (already a repo dependency) for company metadata + prices.

---

## 4. Quick Start

```bash
python3 skills/ticker-enricher/scripts/enrich_tickers.py --agent social --output-dir reports/
```

---

## 5. Workflow

```bash
python3 skills/ticker-enricher/scripts/enrich_tickers.py --agent social --output-dir reports/
```

Groups index signals by **(ticker, channel)** — one row per channel that cited the ticker —
sets `date_recommended` = earliest `claim_date`, `price_at_recommendation` = Yahoo close on
that date, `current_price` = latest, `recommendation_source` = that channel's name, and writes
`reports/enriched_records_<ts>.json`:

```json
{ "table_hint": "recommendations",
  "conflict_hint": "ticker,recommendation_source,date_recommended",
  "records": [ { "ticker": "SOFI", "company_name": "...", "sector": "...", "current_price": 17.1, ... } ] }
```

Then hand the file to `write-supabase` (the `*_hint` keys are documentation; the writer takes
table + conflict from its own CLI). See `references/ledger-schema.md` for the full record shape.

---

## 6. Resources

**References:**

- `skills/ticker-enricher/references/ledger-schema.md`

**Scripts:**

- `skills/ticker-enricher/scripts/enrich_tickers.py`
