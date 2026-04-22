---
name: eod-reconciliation
description: End-of-day job that reconciles intraday loop decisions against actual Alpaca fills, updates trader-memory-core theses, generates a daily P&L attribution report, and triggers postmortem prompts for any closed positions. Run by launchd at 16:30 ET. Invoke when the user asks "run EOD", "reconcile today's trades", "what filled today", "daily P&L".
---

# End-of-Day Reconciliation

The bookkeeping pass. Connects intent (loop decisions) to outcome (Alpaca fills),
updates the thesis store, and produces a daily attribution report.

## When to Use

- Scheduled by `com.trade-analysis.eod-reconcile.plist` at 16:30 ET weekdays.
- On demand: "reconcile today", "what filled today", "give me today's P&L".

## Inputs

- `state/loop/iter_*.json` (today's loop iterations)
- Alpaca `/v2/orders?status=all&after=<sod>` (today's order activity)
- Alpaca `/v2/account` (EOD equity)
- Alpaca `/v2/positions` (current snapshot)
- `state/sod_<date>.json` (start-of-day equity)
- `state/theses/*.yaml` (open theses)

## Workflow

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

## Output Schema

```json
{
  "date": "2026-04-21",
  "sod_equity": 100000.00,
  "eod_equity": 100850.00,
  "day_pnl_usd": 850.00,
  "day_pnl_pct": 0.85,
  "iterations_count": 78,
  "submits_attempted": 4,
  "fills": {"filled": 3, "partial": 0, "canceled": 1, "rejected": 0},
  "by_strategy": {
    "vcp-screener": {"submits": 2, "fills": 2, "realized_pnl_usd": 0,
                     "open_positions": 2},
    "pead-screener": {"submits": 1, "fills": 1, "realized_pnl_usd": 320.00,
                      "open_positions": 0}
  },
  "closed_positions": [
    {"ticker": "AAPL", "thesis_id": "th_xxx",
     "realized_pnl_usd": 320, "r_multiple": 1.2,
     "postmortem_path": "state/theses/postmortems/aapl_2026-04-21.md"}
  ],
  "open_positions": 5,
  "warnings": []
}
```

## Combining with Other Skills

- **trade-loop-orchestrator**: consumes its iter_*.json
- **alpaca-executor**: cross-references its order JSON receipts
- **trader-memory-core**: closes theses, generates postmortems
- **kill-switch**: reads SOD snapshot
