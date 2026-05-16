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

Supported sources: `kanchi-dividend-sop`, `earnings-trade-analyzer`, `vcp-screener`, `pead-screener`, `canslim-screener`, `edge-candidate-agent`, `manual`.

Each thesis starts in `IDEA` status.

#### Manual brokerage entry (fractional shares)

For trades that did **not** come from a screener — e.g. fractional-share
brokers (IBKR, Robinhood, IBI Smart, Alpaca, eToro) or hand journaling — use
the `manual` source with a free-form JSON file (a single object or an array):

```json
{
  "ticker": "AMD",
  "thesis_statement": "AMD AI accelerator momentum, fractional IBI Smart position",
  "thesis_type": "growth_momentum",
  "entry_price": 142.10,
  "entry_date": "2026-05-02",
  "shares": 7.86,
  "stop_price": 128.00
}
```

```bash
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source manual --input amd.json --state-dir state/theses/
```

Required: `ticker`, `thesis_statement`, `thesis_type` (one of
`dividend_income`, `growth_momentum`, `mean_reversion`, `earnings_drift`,
`pivot_breakout`). `stop_price`/`stop_loss` and `target_price`/`take_profit`
map to `exit.stop_loss`/`exit.take_profit`; `entry_price`/`entry_date`/`shares`
are kept in `origin.raw_provenance` — the authoritative entry price/date and
share count are set when you open the position (below). `shares` may be
**fractional** (the schema accepts any positive number). Like every adapter,
manual ingest creates an `IDEA` thesis only — it never mutates status
directly.

To record an **already-open broker position**, run the explicit lifecycle
sequence (the `--event-date` flags backdate the history so it stays
chronological):

```bash
# 1. ingest → IDEA (stamped at entry_date)
python3 .../thesis_ingest.py --source manual --input amd.json --state-dir state/theses/
# 2. IDEA → ENTRY_READY (backdated)
python3 .../thesis_store.py --state-dir state/theses/ transition <id> ENTRY_READY \
  --reason "existing IBI Smart position" --event-date 2026-05-02
# 3. ENTRY_READY → ACTIVE (fractional shares, backdated)
python3 .../thesis_store.py --state-dir state/theses/ open-position <id> \
  --actual-price 142.10 --actual-date 2026-05-02 --shares 7.86 --event-date 2026-05-02
```

### 2. Query — Search and list theses

```bash
python3 skills/trader-memory-core/scripts/thesis_store.py \
  --state-dir state/theses/ list --ticker AAPL --status ACTIVE
```

Filter by `--ticker`, `--status`, or `--type`.

### 3. Update — Transition, attach position, link reports

Each lifecycle operation is available **both** as a Python function and as a
`thesis_store.py` CLI subcommand. `--event-date` / `--actual-date` accept a
plain `YYYY-MM-DD` (widened to midnight UTC) or a full ISO timestamp.

**State transition** (IDEA → ENTRY_READY only):

```bash
python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
  transition <id> ENTRY_READY --reason "validated" [--event-date YYYY-MM-DD]
```

`--event-date` backdates `status_history.at` (use it when backfilling an
existing position so the later backdated `open-position` stays chronological).
Python: `thesis_store.transition(state_dir, thesis_id, "ENTRY_READY", reason, event_date=...)`.

**Open position** (ENTRY_READY → ACTIVE — the only path to ACTIVE):

```bash
python3 .../thesis_store.py --state-dir state/theses/ open-position <id> \
  --actual-price 142.10 --actual-date 2026-05-02 [--shares 7.86] [--event-date 2026-05-02]
```

`--shares` accepts **fractional** quantities. Python:
`thesis_store.open_position(state_dir, thesis_id, actual_price, actual_date, shares=..., event_date=...)`.

**Trim — partial close** (ACTIVE/PARTIALLY_CLOSED → PARTIALLY_CLOSED, or →
CLOSED when the whole remainder is sold):

```bash
python3 .../thesis_store.py --state-dir state/theses/ trim <id> \
  --shares-sold 4 --price 120.00 --date 2026-05-10
```

`position.shares` is the **original** opened quantity (immutable);
`position.shares_remaining` tracks what is still open. Each trim appends a
`status_history` ledger entry (`shares_sold` / `price` / `proceeds` /
`realized_pnl`). `outcome.pnl_dollars` is the **cumulative** realized P&L
(Σ all trims + final close); `outcome.pnl_pct = pnl_dollars / (entry_price ×
original_shares) × 100`. A trim that sells the entire remainder closes the
thesis (default `exit_reason: manual`, overridable with `--exit-reason`).
`--date` is the ledger timestamp (override with `--event-date`). Python:
`thesis_store.trim(state_dir, thesis_id, shares_sold, price, date, ...)`.

Status invariants: `ACTIVE` ⇒ `shares_remaining == shares`;
`PARTIALLY_CLOSED` ⇒ `0 < shares_remaining < shares`; `CLOSED` ⇒
`shares_remaining == 0`. Legacy theses (no `shares_remaining`) are treated as
fully open at runtime.

**Close or invalidate** (→ CLOSED or INVALIDATED):

```bash
python3 .../thesis_store.py --state-dir state/theses/ close <id> \
  --exit-reason target_hit --actual-price 165.00 --actual-date 2026-06-01
python3 .../thesis_store.py --state-dir state/theses/ terminate <id> \
  --terminal-status INVALIDATED --exit-reason "thesis broke"
```

`close` accepts an `ACTIVE` **or** `PARTIALLY_CLOSED` thesis; from
PARTIALLY_CLOSED it adds the final leg and reports the cumulative outcome.

Python: `thesis_store.terminate(state_dir, thesis_id, terminal_status, exit_reason, actual_price, actual_date)`. For CLOSED, delegates to `close()` which computes P&L (fractional-share aware). For INVALIDATED, P&L is computed if entry/exit prices are available.

**Record review** (any non-terminal):

Use `thesis_store.mark_reviewed(state_dir, thesis_id, review_date=..., outcome="OK"|"WARN"|"REVIEW")` to advance next_review_date and record alerts.

**Attach position-sizer output:**

```bash
python3 .../thesis_store.py --state-dir state/theses/ attach-position <id> \
  --report reports/position_report.json
```

Python: `thesis_store.attach_position(state_dir, thesis_id, report_path)` to link position sizing data. Validates that the report mode is "shares" (not budget).

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
- Position: shares (fractional supported), value, risk (from position-sizer or `open-position --shares`)
- Monitoring: review dates, triggers, alerts
- Origin: source skill, screening grade, raw provenance
- Outcome: P&L, holding days, MAE/MFE, lessons learned

### Index (state/theses/_index.json)

Lightweight index for fast queries without loading full YAML files.

### Journal (state/journal/)

Postmortem markdown reports: `pm_{thesis_id}.md`.

## Key Principles

- **Forward-only transitions**: IDEA → ENTRY_READY → ACTIVE → CLOSED (no backtracking)
- **Raw provenance**: All original screener data preserved in `origin.raw_provenance`
- **Atomic writes**: All file operations use tempfile + os.replace
- **Git-tracked state**: `state/` directory is committed, providing audit trail
- **Phase 1 scope**: Single-ticker theses only (pair trades and options in Phase 2)

## Resources

- `references/thesis_lifecycle.md` — Status states and valid transitions
- `references/field_mapping.md` — Source skill → canonical field mapping
- `schemas/thesis.schema.json` — JSON Schema for thesis validation
