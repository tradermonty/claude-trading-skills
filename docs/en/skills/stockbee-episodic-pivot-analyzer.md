---
layout: default
title: "Stockbee Episodic Pivot Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 50
lang_peer: /ja/skills/stockbee-episodic-pivot-analyzer/
permalink: /en/skills/stockbee-episodic-pivot-analyzer/
generated: true
---

# Stockbee Episodic Pivot Analyzer
{: .no_toc }

Analyze Stockbee-style Day 1 Episodic Pivot candidates from earnings, guidance raises, M&A, FDA/regulatory approvals, analyst actions, major contracts, product launches, short-squeeze catalysts, or theme/story events. Scores catalyst quality together with gap/range expansion, volume shock, neglect/revaluation context, liquidity, and risk to the EP-day low. Use when the user asks for EP candidates, episodic pivots, Day 1 catalyst trades, game-changing news reactions, delayed EP watchlists, or handoffs into PEAD monitoring.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-episodic-pivot-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-episodic-pivot-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Stockbee Episodic Pivot Analyzer

---

## 2. When to Use

- The user asks for Pradeep Bonde / Stockbee style EP candidates
- The user provides earnings, guidance, M&A, FDA, analyst, contract, product, short-squeeze, or theme/news events
- The user wants to separate `ACTIONABLE_DAY1` candidates from `DELAYED_EP_WATCH` names
- The user wants to hand strong earnings/guidance EPs into `pead-screener`
- The user wants to combine catalyst analysis with `stockbee-momentum-burst-screener` price/volume output

---

## 3. Prerequisites

- Python 3.10+
- Optional: FMP API key for OHLCV/profile enrichment
- One of:
  - Catalyst/events JSON
  - `earnings-trade-analyzer` JSON output
  - Catalyst JSON plus `stockbee-momentum-burst-screener` JSON enrichment
- This skill does not fetch or discover news by itself. If the catalyst is not supplied, first gather the event/news context using the user's preferred news or research process.

---

## 4. Quick Start

```bash
**Mode B — Earnings pipeline:**

Use the JSON produced by `earnings-trade-analyzer`.

**Mode C — Price/volume enrichment:**

Pass a `stockbee-momentum-burst-screener` JSON report to reuse day-gain, volume, close-location, and risk-distance fields.

### Step 2: Run the Analyzer
```

---

## 5. Workflow

### Step 1: Prepare Candidate Inputs

Use one or more of these input modes.

**Mode A — Catalyst/event JSON:**

```json
{
  "events": [
    {
      "symbol": "ABC",
      "event_date": "2026-04-25",
      "catalyst_type": "guidance_raise",
      "headline": "ABC raises FY guidance after record demand",
      "summary": "Management raised revenue and EPS guidance."
    }
  ]
}
```

**Mode B — Earnings pipeline:**

Use the JSON produced by `earnings-trade-analyzer`.

**Mode C — Price/volume enrichment:**

Pass a `stockbee-momentum-burst-screener` JSON report to reuse day-gain, volume, close-location, and risk-distance fields.

### Step 2: Run the Analyzer

```bash
# Catalyst JSON + offline OHLCV
python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py \
  --events-json data/catalysts.json \
  --prices-json data/daily_ohlcv.json \
  --output-dir reports/

# Earnings pipeline input
python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py \
  --earnings-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --output-dir reports/

# Catalyst JSON + Stockbee momentum enrichment
python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py \
  --events-json data/catalysts.json \
  --momentum-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --output-dir reports/
```

Optional FMP enrichment:

```bash
export FMP_API_KEY=your_key
python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py \
  --events-json data/catalysts.json \
  --max-api-calls 200 \
  --output-dir reports/
```

### Step 3: Review the Output

For each candidate, present:

- `state`: `ACTIONABLE_DAY1`, `DAY1_WATCH`, `DELAYED_EP_WATCH`, `CATALYST_WATCH`, or `REJECT`
- `ep_type`: `EARNINGS_EP`, `GUIDANCE_EP`, `FDA_EP`, `M_AND_A_EP`, `STORY_EP`, etc.
- Catalyst quality score and reasons
- Price/range expansion, volume shock, and close-location quality
- Risk to EP-day low
- `pead_handoff` and `delayed_ep_watch` flags

### Step 4: Handoff Rules

- `ACTIONABLE_DAY1`: Send to `technical-analyst` and `position-sizer` before any trade decision.
- `DAY1_WATCH`: Keep on the intraday/next-day watchlist; require chart confirmation.
- `DELAYED_EP_WATCH`: Do not chase Day 1; monitor for a controlled pullback or new range.
- `CATALYST_WATCH`: Catalyst may be important, but price/volume confirmation is not yet sufficient.
- `REJECT`: Do not trade from this candidate source.
- Earnings/guidance EPs with `pead_handoff=true` can be sent to `pead-screener` for weekly red-candle / delayed reaction monitoring.

---

## 6. Resources

**References:**

- `skills/stockbee-episodic-pivot-analyzer/references/catalyst_quality.md`
- `skills/stockbee-episodic-pivot-analyzer/references/ep_methodology.md`
- `skills/stockbee-episodic-pivot-analyzer/references/handoff_rules.md`

**Scripts:**

- `skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py`
