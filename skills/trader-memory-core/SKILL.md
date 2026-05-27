---
name: trader-memory-core
description: Track investment theses across their lifecycle — from screening idea to closed position with postmortem. Register theses from screener outputs, manage state transitions, attach position sizing, review due dates, and generate postmortem reports with P&L and MAE/MFE analysis. Trigger when user says "register thesis", "track this idea", "thesis status", "review due", "close position", "postmortem", or "trading journal".
---

# Trader Memory Core

## Overview

Persistent state layer that bundles screening → analysis → position sizing → portfolio management outputs into a single "thesis object" per investment idea. Tracks what you thought, what happened, and what you learned — across conversations.

Phase 1 supports single-ticker theses: dividend_income, growth_momentum, mean_reversion, earnings_drift, pivot_breakout.

## When to Use

- After a screener (kanchi, earnings-trade-analyzer, vcp, pead, canslim, edge-candidate-agent) produces candidates
- When transitioning a thesis from IDEA → ENTRY_READY → ACTIVE → CLOSED
- When attaching position-sizer output to a thesis
- When checking which theses are due for review
- When closing a position and generating a postmortem with lessons learned

## Prerequisites

- Python 3.10+
- `pyyaml` (already in project dependencies)
- FMP API key (optional, only for MAE/MFE calculation in postmortem)

## Workflow

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

## Output Format

### Thesis YAML (state/theses/)

Each thesis is a YAML file with:
- Identity: thesis_id, ticker, created_at
- Classification: thesis_type, setup_type, catalyst
- Lifecycle: status, status_history
- Entry/Exit: target prices, actual prices, conditions
- Position: shares, value, risk (attached from position-sizer)
- Monitoring: review dates, triggers, alerts
- Origin: source skill, screening grade, raw provenance
- Outcome: P&L, holding days, MAE/MFE, lessons learned

### Index (state/theses/_index.json)

Lightweight index for fast queries without loading full YAML files.

### Journal (state/journal/)

Postmortem markdown reports: `pm_{thesis_id}.md`.

## Thesis Lifecycle States

All thesis records follow the canonical `ThesisLifecycle` state machine from `schemas/artifacts.py`.
No state may be skipped; only forward transitions are valid.

| State | Meaning | Who sets it |
|-------|---------|-------------|
| `IDEA` | Screener output registered; not yet validated | `thesis_ingest.py` |
| `CANDIDATE` | Chart review done; awaiting sizing | Trader via `transition()` |
| `PLANNED` | Position sized; entry plan ready for manual approval | Trader via `transition()` |
| `ENTERED` | Order placed manually at broker; confirmed fill | Trader via `open_position()` |
| `MANAGED` | Position open; periodic review due | Automatic on review-due check |
| `EXITED` | Position closed at broker | Trader via `close_position()` |
| `POSTMORTEM_DONE` | Postmortem written and classified | `thesis_review.py postmortem` |
| `ARCHIVED` | No further action required | Trader via `transition()` |

**No transition from `PLANNED` to `ENTERED` may occur without manual broker confirmation.**
This skill does not place orders — it tracks state.

## Manual Review Gate

Every thesis must pass through at least one decision gate before advancing to `ENTERED`:

1. Trader confirms entry criteria still met on live chart
2. Position size reviewed against current account equity (not the original plan)
3. Portfolio heat checked — total open risk within personal limit
4. Order placed manually at broker; actual fill price recorded back into thesis

## Key Principles

- **Forward-only transitions**: IDEA → CANDIDATE → PLANNED → ENTERED → MANAGED → EXITED → POSTMORTEM_DONE → ARCHIVED
- **Raw provenance**: All original screener data preserved in `origin.raw_provenance`
- **Atomic writes**: All file operations use tempfile + os.replace
- **Git-tracked state**: `state/` directory is committed, providing audit trail
- **Phase 1 scope**: Single-ticker theses only (pair trades and options in Phase 2)

## Data Gaps

| Scenario | Severity | Behavior |
|----------|----------|----------|
| Source screener JSON unreadable | CRITICAL | Halt — cannot register thesis without input |
| Thesis ID not found in state store | HIGH | Halt update — do not create phantom records |
| FMP API key missing for MAE/MFE | MEDIUM | Generate postmortem without MAE/MFE; note limitation |
| Exit price not yet available | MEDIUM | Keep thesis in `EXITED` without P&L; add when confirmed |

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `trade_thesis` | `TradeThesis` | Full trade thesis with ThesisLifecycle state and provenance |
| `journal_entry` | `JournalEntry` | Timestamped decision log entry for trader memory |
| `postmortem_report` | `PostmortemReport` | 2×2 process/outcome classification with lessons learned |

Schema: `schemas/json/trade_thesis.json` (and sibling files for additional types above)

## Resources

- `references/thesis_lifecycle.md` — Status states and valid transitions
- `references/field_mapping.md` — Source skill → canonical field mapping
- `schemas/thesis.schema.json` — JSON Schema for thesis validation
