---
layout: default
title: "Eod Reconciliation"
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/eod-reconciliation/
permalink: /en/skills/eod-reconciliation/
---

# Eod Reconciliation
{: .no_toc }

End-of-day job that reconciles intraday loop decisions against actual Alpaca fills, updates trader-memory-core theses, generates a daily P&L attribution report, and triggers postmortem prompts for any closed positions. Run by launchd at 16:30 ET. Invoke when the user asks "run EOD", "reconcile today's trades", "what filled today", "daily P&L".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/eod-reconciliation){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# End-of-Day Reconciliation

---

## 2. When to Use

- Scheduled by `com.trade-analysis.eod-reconcile.plist` at 16:30 ET weekdays.
- On demand: "reconcile today", "what filled today", "give me today's P&L".

---

## 3. Prerequisites

- **API Key:** None required
- **Python 3.9+** recommended

---

## 4. Quick Start

```bash
python3 skills/eod-reconciliation/scripts/run_eod.py \
  --output-dir reports/eod/
```

---

## 5. Workflow

```bash
python3 skills/eod-reconciliation/scripts/run_eod.py \
  --output-dir reports/eod/
```

### Steps

1. List today's iteration audit logs from `state/loop/`.
2. Pull today's orders + fills from Alpaca.
3. For each loop `submit` decision:
   - Match by `client_order_id` (the orchestrator-supplied COID)
   - Classify: filled, partially_filled, canceled, expired, rejected
   - Compute slippage = fill_price - intended_entry
4. For each closed position today, generate a postmortem prompt and call
   `trader-memory-core/thesis_review.py postmortem`.
5. Compute attribution:
   - Total day P&L = current_equity - sod_equity
   - Per-strategy contribution (group by primary_screener)
   - Win rate and average R for closed trades
6. Write `reports/eod/eod_<date>.md` and `eod_<date>.json`.

---

## 6. Resources

**Scripts:**

- `skills/eod-reconciliation/scripts/run_eod.py`
