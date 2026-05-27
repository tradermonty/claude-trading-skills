---
layout: default
title: "Trader Memory Core"
grand_parent: English
parent: Skill Guides
nav_order: 59
lang_peer: /ja/skills/trader-memory-core/
permalink: /en/skills/trader-memory-core/
---

# Trader Memory Core
{: .no_toc }

Track investment theses across their lifecycle — from screening idea to closed position with postmortem. Register theses from screener outputs, manage state transitions, attach position sizing, review due dates, and generate postmortem reports with P&L and MAE/MFE analysis. Trigger when user says "register thesis", "track this idea", "thesis status", "review due", "close position", "postmortem", or "trading journal".
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trader-memory-core.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trader-memory-core){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Persistent state layer that bundles screening → analysis → position sizing → portfolio management outputs into a single "thesis object" per investment idea. Tracks what you thought, what happened, and what you learned — across conversations.

Phase 1 supports single-ticker theses: dividend_income, growth_momentum, mean_reversion, earnings_drift, pivot_breakout.

---

## 2. When to Use

- After a screener (kanchi, earnings-trade-analyzer, vcp, pead, canslim, edge-candidate-agent) produces candidates
- When transitioning a thesis from IDEA → ENTRY_READY → ACTIVE → CLOSED
- When attaching position-sizer output to a thesis
- When checking which theses are due for review
- When closing a position and generating a postmortem with lessons learned

---

## 3. Prerequisites

- Python 3.10+
- `pyyaml` (already in project dependencies)
- FMP API key (optional, only for MAE/MFE calculation in postmortem)

---

## 4. Quick Start

```bash
# Register screener output as thesis
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# Query theses
python3 skills/trader-memory-core/scripts/thesis_store.py \
  --state-dir state/theses/ list --ticker AAPL --status ACTIVE

# Check review schedule
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ review-due --as-of 2026-04-15

# Generate postmortem
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1

# Summary statistics
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ summary
```

---

## 5. Workflow

### 1. Register — Ingest screener output as thesis

Read the screener's JSON output and convert to thesis using the appropriate adapter.

```bash
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/
```

Supported sources: `kanchi-dividend-sop`, `earnings-trade-analyzer`, `vcp-screener`, `pead-screener`, `canslim-screener`, `edge-candidate-agent`.

Each thesis starts in `IDEA` status.

### 2. Query — Search and list theses

```bash
python3 skills/trader-memory-core/scripts/thesis_store.py \
  --state-dir state/theses/ list --ticker AAPL --status ACTIVE
```

Filter by `--ticker`, `--status`, or `--type`.

### 3. Update — Transition, attach position, link reports

**State transition** (IDEA → ENTRY_READY only):

Use `thesis_store.transition(state_dir, thesis_id, "ENTRY_READY", reason)` from Python.

**Open position** (ENTRY_READY → ACTIVE):

Use `thesis_store.open_position(state_dir, thesis_id, actual_price, actual_date)` — the only path to ACTIVE. Accepts optional `shares` and `event_date` (for backfilling past trades).

**Close or invalidate** (→ CLOSED or INVALIDATED):

Use `thesis_store.terminate(state_dir, thesis_id, terminal_status, exit_reason, actual_price, actual_date)`. For CLOSED, delegates to `close()` which computes P&L. For INVALIDATED, P&L is computed if entry/exit prices are available.

**Record review** (any non-terminal):

Use `thesis_store.mark_reviewed(state_dir, thesis_id, review_date=..., outcome="OK"|"WARN"|"REVIEW")` to advance next_review_date and record alerts.

**Attach position-sizer output:**

Use `thesis_store.attach_position(state_dir, thesis_id, report_path)` to link position sizing data. Validates that the report mode is "shares" (not budget).

**Link related reports:**

Use `thesis_store.link_report(state_dir, thesis_id, skill, file, date)` to cross-reference analysis documents.

### 4. Review — Check due dates and monitoring status

```bash
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ review-due --as-of 2026-04-15
```

List theses with `next_review_date <= as_of`. Use with kanchi-dividend-review-monitor triggers (T1-T5) for systematic review.

### 5. Postmortem — Close and reflect

```bash
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1
```

Generate a structured postmortem in `state/journal/`. If FMP API key is available, includes MAE/MFE (Maximum Adverse/Favorable Excursion) metrics.

**Summary statistics:**

```bash
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ summary
```

Shows win rate, average P&L%, and per-type breakdown across all closed theses.

---

## 6. Resources

**References:**

- `skills/trader-memory-core/references/field_mapping.md`
- `skills/trader-memory-core/references/thesis_lifecycle.md`

**Scripts:**

- `skills/trader-memory-core/scripts/fmp_price_adapter.py`
- `skills/trader-memory-core/scripts/thesis_ingest.py`
- `skills/trader-memory-core/scripts/thesis_review.py`
- `skills/trader-memory-core/scripts/thesis_store.py`
