---
layout: default
title: "Kanchi Dividend Review Monitor"
grand_parent: English
parent: Skill Guides
nav_order: 26
lang_peer: /ja/skills/kanchi-dividend-review-monitor/
permalink: /en/skills/kanchi-dividend-review-monitor/
---

# Kanchi Dividend Review Monitor
{: .no_toc }

Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIEW states without auto-selling. Use when users ask for 減配検知, 8-Kガバナンス監視, 配当安全性モニタリング, REVIEWキュー自動化, or periodic dividend risk checks.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-review-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-review-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Detect abnormal dividend-risk signals and route them into a human review queue.
Treat automation as anomaly detection, not automated trade execution.

---

## 2. When to Use

Use this skill when the user needs:
- Daily/weekly/quarterly anomaly detection for dividend holdings.
- Forced review queueing for T1-T5 risk triggers.
- 8-K/governance keyword scans tied to portfolio tickers.
- Deterministic `OK/WARN/REVIEW` output before manual decision making.

---

## 3. Prerequisites

Provide normalized input JSON that follows:
- `references/input-schema.md`

If upstream data is unavailable, provide at least:
- `ticker`
- `instrument_type`
- `dividend.latest_regular`
- `dividend.prior_regular`

---

## 4. Quick Start

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

---

## 5. Workflow

### 1) Normalize input dataset

Collect per ticker fields in one JSON document:
- Dividend points (latest regular, prior regular, missing/zero flag).
- Coverage fields (FCF or FFO or NII, dividends paid, ratio history).
- Balance-sheet trend fields (net debt, interest coverage, buybacks/dividends).
- Filing text snippets (especially recent 8-K or equivalent alert text).
- Operations trend fields (revenue CAGR, margin trend, guidance trend).

Use `references/input-schema.md` for field definitions
and sample payload.

### 2) Run the rule engine

Run:

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

The script maps each ticker to `OK/WARN/REVIEW` based on T1-T5.
Output files are saved to the specified directory with dated filenames (e.g., `review_queue_20260227.json` and `.md`).

### 3) Prioritize and deduplicate

If multiple triggers fire:
- Keep all findings for audit trail.
- Escalate final state to highest severity only.
- Store trigger reasons as single-line evidence.

### 4) Generate human review tickets

For each `REVIEW` ticker, include:
- Trigger IDs and evidence.
- Suspected failure mode.
- Required manual checks for next decision.

Use `references/review-ticket-template.md` output format.

---

## 6. Resources

**References:**

- `skills/kanchi-dividend-review-monitor/references/input-schema.md`
- `skills/kanchi-dividend-review-monitor/references/review-ticket-template.md`
- `skills/kanchi-dividend-review-monitor/references/trigger-matrix.md`

**Scripts:**

- `skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py`
