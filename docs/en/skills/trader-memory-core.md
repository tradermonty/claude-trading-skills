---
layout: default
title: "Trader Memory Core"
grand_parent: English
parent: Skill Guides
nav_order: 45
lang_peer: /ja/skills/trader-memory-core/
permalink: /en/skills/trader-memory-core/
---

# Trader Memory Core
{: .no_toc }

Persistent state layer that tracks investment theses from screening idea to closed position with postmortem. Bundles screener, analysis, position sizing, and portfolio management outputs into a single thesis object per trade idea.
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP Optional</span>

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

Trader Memory Core answers the question: "What did I think, what happened, and what did I learn?" It provides a persistent, file-based state layer that follows each investment thesis through its entire lifecycle:

```
Screener Output → IDEA → ENTRY_READY → ACTIVE → CLOSED
                    │          │            │
                    └──────────┴────────────┴──→ INVALIDATED
```

**What it solves:**
- Eliminates the gap between screening and execution tracking
- Provides a single source of truth for each trade idea across conversations
- Enforces disciplined state transitions (no skipping steps)
- Generates structured postmortem reports with P&L and MAE/MFE metrics
- Schedules periodic reviews so no position is forgotten

**Key capabilities:**
- 7 screener adapters: kanchi-dividend-sop, earnings-trade-analyzer, vcp-screener, pead-screener, canslim-screener, edge-candidate-agent, edge-concept-synthesizer
- Forward-only state machine with 5 statuses
- Fingerprint-based deduplication (same screener output never registers twice)
- Position sizing attachment from Position Sizer skill
- Review scheduling with escalation ladder (OK → WARN → REVIEW)
- Postmortem generation with optional MAE/MFE via FMP API

**Phase 1 scope:** Single-ticker theses only. Pair trades and options strategies are planned for Phase 2.

---

## 2. When to Use

- After a screener produces candidates and you want to **track them persistently**
- When you want to **transition a thesis** from idea to entry-ready to active position
- When **attaching position-sizer output** to size the trade
- When checking **which theses are due for review**
- When **closing a position** and generating a postmortem with lessons learned
- When you want a **trading journal** with structured P&L statistics

**Trigger phrases:** "register thesis", "track this idea", "thesis status", "review due", "close position", "postmortem", "trading journal"

---

## 3. Prerequisites

- **Python 3.9+** with `pyyaml` and `jsonschema` (both in project dependencies)
- **FMP API key:** Optional -- only needed for MAE/MFE calculation in postmortem reports. Core features (register, transition, close, review) work completely offline
- **State directory:** `state/theses/` is created automatically on first use

> FMP API is only used for fetching daily price history to compute Maximum Adverse Excursion (MAE) and Maximum Favorable Excursion (MFE) during postmortem. If no API key is set, postmortem reports are still generated with all other fields.
{: .tip }

---

## 4. Quick Start

```bash
# Step 1: Register screener output as thesis
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# Step 2: Query your theses
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ list --status IDEA

# Step 3: Generate summary statistics
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ summary
```

---

## 5. Workflow

### Step 1: Register -- Ingest screener output

Run the ingest script with the source screener name and its JSON output file:

```bash
# From kanchi-dividend-sop
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# From earnings-trade-analyzer
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source earnings-trade-analyzer \
  --input reports/earnings_trade_scored_2026-03-14.json \
  --state-dir state/theses/
```

Each candidate in the JSON becomes an `IDEA` thesis. Registration is **idempotent** -- running the same input twice produces no duplicates (fingerprint-based dedup).

**Supported sources:** `kanchi-dividend-sop`, `earnings-trade-analyzer`, `vcp-screener`, `pead-screener`, `canslim-screener`, `edge-candidate-agent`

### Step 2: Link analysis reports

After performing deeper analysis (US Stock Analysis, Technical Analyst, etc.), link the report to the thesis:

```python
from skills.trader_memory_core.scripts.thesis_store import link_report

link_report(state_dir, thesis_id,
            skill="us-stock-analysis",
            file="reports/us_stock_AAPL_2026-03-15.md",
            date="2026-03-15")
```

### Step 3: Transition IDEA to ENTRY_READY

After validating the thesis with analysis, promote it:

```python
from skills.trader_memory_core.scripts.thesis_store import transition

transition(state_dir, thesis_id, "ENTRY_READY",
           reason="Technical confirmation: above 200-day MA with volume")
```

> `transition()` only allows IDEA → ENTRY_READY. All other transitions use dedicated functions.
{: .warning }

### Step 4: Open position (ENTRY_READY to ACTIVE)

When you execute the trade, record the actual entry:

```python
from skills.trader_memory_core.scripts.thesis_store import open_position

open_position(state_dir, thesis_id,
              actual_price=155.50,
              actual_date="2026-03-16T10:30:00-04:00")
```

This is the **only path to ACTIVE status**. Requires both `actual_price` and `actual_date` (RFC 3339 format with timezone).

### Step 5: Attach position sizing

Link the Position Sizer output to record how many shares and the risk parameters:

```python
from skills.trader_memory_core.scripts.thesis_store import attach_position

attach_position(state_dir, thesis_id,
                report_path="reports/position_sizer_AAPL_2026-03-16.json")
```

The report must have `mode: "shares"` (budget mode is rejected).

### Step 6: Periodic review

Check which theses need attention:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ review-due --as-of 2026-04-15
```

Record a review with escalation support:

```python
from skills.trader_memory_core.scripts.thesis_store import mark_reviewed

mark_reviewed(state_dir, thesis_id,
              review_date="2026-04-15",
              outcome="OK")  # OK, WARN, or REVIEW
```

The `next_review_date` is automatically advanced based on the review interval.

### Step 7: Close and postmortem

When you exit the position:

```python
from skills.trader_memory_core.scripts.thesis_store import close

close(state_dir, thesis_id,
      exit_reason="target_reached",
      exit_price=172.00,
      exit_date="2026-05-01T15:45:00-04:00")
```

Then generate the postmortem:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1
```

The postmortem includes P&L, holding days, and (with FMP API key) MAE/MFE metrics. Output is saved to `state/journal/pm_{thesis_id}.md`.

---

## 6. Understanding Output

### Thesis YAML file

Each thesis is stored as a YAML file in `state/theses/`:

| Section | Key Fields | Description |
|---------|-----------|-------------|
| Identity | `thesis_id`, `ticker`, `created_at` | Unique ID with ticker and hash |
| Classification | `thesis_type`, `setup_type`, `catalyst` | e.g., `dividend_income`, `earnings_drift` |
| Status | `status`, `status_history` | Current state + full transition log with timestamps |
| Entry | `entry.target_price`, `entry.actual_price`, `entry.actual_date` | Planned vs actual entry |
| Exit | `exit.stop_loss`, `exit.target_price`, `exit.actual_price` | Planned vs actual exit |
| Position | `position.shares`, `position.risk_dollars` | From Position Sizer attachment |
| Monitoring | `next_review_date`, `review_history` | Review schedule and past reviews |
| Origin | `origin.source_skill`, `origin.screening_grade` | Which screener and what score |
| Outcome | `outcome.pnl_pct`, `outcome.holding_days` | Computed on close |

### Index file

`state/theses/_index.json` provides a lightweight lookup for fast queries without loading individual YAML files. It is rebuilt automatically and can be regenerated with `rebuild_index()`.

### Postmortem journal

`state/journal/pm_{thesis_id}.md` contains a structured markdown report with entry/exit summary, P&L analysis, MAE/MFE metrics (if available), and space for lessons learned.

---

## 7. Tips & Best Practices

- **Register early, decide later.** Ingest all screener output as IDEAs. You can invalidate what you don't pursue.
- **Idempotency is your friend.** Running the same ingest command twice is safe -- fingerprints prevent duplicates.
- **Use RFC 3339 dates.** All date-time fields require timezone (e.g., `2026-03-16T10:30:00-04:00`). Naive datetimes and space separators are rejected.
- **Invalidate rather than delete.** Use `terminate(thesis_id, "INVALIDATED", ...)` instead of manually removing YAML files. This preserves the audit trail.
- **Review schedule matters.** Default review interval is 7 days. Overdue theses surface via `review-due`, preventing forgotten positions.
- **Escalation ladder.** Reviews go OK → WARN → REVIEW. Consecutive WARN outcomes escalate automatically.
- **Link reports generously.** The more analysis you cross-reference, the richer the postmortem.
- **Git-track state/.** The `state/` directory is designed to be committed, giving you a full audit trail with `git log` and `git blame`.
- **Postmortem without FMP.** MAE/MFE are nice-to-have. P&L, holding days, and lessons learned work without any API.

---

## 8. Combining with Other Skills

| Skill | Integration Point | How |
|-------|------------------|-----|
| **kanchi-dividend-sop** | Register | `thesis_ingest.py --source kanchi-dividend-sop` |
| **earnings-trade-analyzer** | Register | `thesis_ingest.py --source earnings-trade-analyzer` |
| **vcp-screener** | Register | `thesis_ingest.py --source vcp-screener` |
| **pead-screener** | Register | `thesis_ingest.py --source pead-screener` |
| **canslim-screener** | Register | `thesis_ingest.py --source canslim-screener` |
| **edge-candidate-agent** | Register | `thesis_ingest.py --source edge-candidate-agent` |
| **US Stock Analysis** | Link report | `link_report(thesis_id, skill="us-stock-analysis", ...)` |
| **Technical Analyst** | Link report | `link_report(thesis_id, skill="technical-analyst", ...)` |
| **Position Sizer** | Attach sizing | `attach_position(thesis_id, report_path)` |
| **Portfolio Manager** | Execute trades | Open/close positions, then update thesis |
| **kanchi-dividend-review-monitor** | Review triggers | T1-T5 anomaly detection feeds `mark_reviewed()` |

---

## 9. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `ValidationError: ... is not a 'date-time'` | Date field missing timezone or using space separator | Use RFC 3339 format: `2026-03-16T10:30:00-04:00` |
| `ValueError: Cannot transition from terminal status CLOSED` | Attempting to modify a closed/invalidated thesis | Terminal statuses are permanent. Create a new thesis if needed. |
| `ValueError: Use open_position() to transition to ACTIVE` | Called `transition()` with `ACTIVE` target | Use `open_position(thesis_id, actual_price, actual_date)` instead |
| `ValueError: Budget mode not supported` | Position sizer report has `mode: "budget"` | Re-run Position Sizer with `--entry` and `--stop` to get shares mode |
| `ValueError: Missing required field: ticker` | Screener JSON missing expected fields | Check that the input matches the source adapter's expected format |
| Duplicate thesis not created | Fingerprint matches existing thesis | This is intentional (idempotency). The existing thesis_id is returned. |

---

## 10. Resources

**References:**
- `skills/trader-memory-core/references/thesis_lifecycle.md` -- Status states and valid transitions
- `skills/trader-memory-core/references/field_mapping.md` -- Source skill to canonical field mapping

**Scripts:**
- `skills/trader-memory-core/scripts/thesis_ingest.py` -- Screener adapter registry and CLI
- `skills/trader-memory-core/scripts/thesis_store.py` -- CRUD, transitions, and state management
- `skills/trader-memory-core/scripts/thesis_review.py` -- Postmortem generation and summary statistics
- `skills/trader-memory-core/scripts/fmp_price_adapter.py` -- FMP API integration for MAE/MFE

**Schema:**
- `skills/trader-memory-core/schemas/thesis.schema.json` -- JSON Schema for thesis validation

**Worked example:**
- `examples/workflows/trade-memory-loop/sample-run-full-path/` -- End-to-end Plan -> Trade -> Record -> Postmortem -> Backtest -> Journal sample run
