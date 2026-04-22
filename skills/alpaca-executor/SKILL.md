---
name: alpaca-executor
description: Execute equity trades on Alpaca (paper or live) as bracket orders with idempotency keys, mandatory stop-loss, and target. Refuses to send live orders unless config/trading_params.yaml is in live mode AND LIVE_TRADING_CHECKLIST.md is signed AND TRADE_LOOP_DRY_RUN=false. Use when the trade-loop-orchestrator needs to place an order, when the user asks to "buy/sell X", "place a bracket order", "submit trade", or "execute". Also handles flatten-all and order cancellation.
---

# Alpaca Executor

Single point of order entry for the entire trader. Every order goes through this skill,
which enforces:

1. **Paper-by-default**: `ALPACA_PAPER=true` until user explicitly flips it.
2. **Dry-run gate**: `TRADE_LOOP_DRY_RUN=true` blocks ALL outbound orders, paper or live.
3. **Live trading lockout**: live mode requires `mode: live` in trading_params.yaml AND
   a signed `LIVE_TRADING_CHECKLIST.md` artifact at the configured path.
4. **Bracket-only**: every entry order ships with a stop-loss and target; no naked entries.
5. **Idempotency**: `client_order_id` derived from `(ticker, signal_id, date)` so accidental
   retries don't double-place.
6. **Risk validation**: compares the order size against trading_params.yaml `risk_per_trade_pct`
   and `max_position_size_pct` before submission.

## When to Use

- The trade-loop-orchestrator emits a SIGNAL_READY trade plan and needs to execute it.
- The user manually says "buy X shares of TICKER with stop at Y, target at Z".
- The kill-switch needs to flatten all positions.
- You need to cancel an open order or replace a stop.

## Prerequisites

- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER` env vars (loaded via `scripts/with_env.sh`)
- `pyyaml`, `requests`
- `config/trading_params.yaml` exists and validates
- For live mode: `LIVE_TRADING_CHECKLIST.md` exists and contains `signed: true` line

## Workflow: Place a Bracket Order

```bash
python3 skills/alpaca-executor/scripts/execute_trade.py \
  --ticker AAPL \
  --side buy \
  --quantity 50 \
  --entry-type market \
  --stop-loss 145.00 \
  --target 165.00 \
  --signal-id vcp-2026-04-21-aapl \
  --output reports/orders/aapl_2026-04-21.json
```

The script:
1. Loads trading_params.yaml.
2. Reads `ALPACA_PAPER`, `TRADE_LOOP_DRY_RUN`.
3. If global.mode == "live" and ALPACA_PAPER != "false": refuse.
4. If TRADE_LOOP_DRY_RUN == "true": log the order but do NOT call Alpaca; return a synthetic
   acknowledgement.
5. Validate position size against risk_per_trade_pct and max_position_size_pct.
6. Compute the client_order_id as `sha1(ticker|signal_id|date)`.
7. Call Alpaca's `/v2/orders` endpoint with bracket parameters.
8. Persist the response JSON to the output path.

## Workflow: Flatten All

```bash
python3 skills/alpaca-executor/scripts/flatten_all.py --reason "kill_switch_triggered"
```

Cancels every open order, then submits market sells for every open long. Refused unless
the caller passes `--confirm` or the config file's `kill_switch_active: true` flag is set
by the kill-switch service.

## Output Format

Successful order JSON:
```json
{
  "submitted_at": "2026-04-21T14:32:00Z",
  "ticker": "AAPL",
  "side": "buy",
  "quantity": 50,
  "client_order_id": "ace_4f3...e2",
  "alpaca_order_id": "abc-def-...",
  "status": "accepted",
  "entry_type": "market",
  "stop_loss": 145.00,
  "target": 165.00,
  "dry_run": false,
  "paper": true
}
```

Refused order JSON:
```json
{
  "submitted_at": "2026-04-21T14:32:00Z",
  "ticker": "AAPL",
  "status": "refused",
  "reason": "DRY_RUN=true",
  "would_have_sent": { ... }
}
```

## Combining with Other Skills

- **trade-loop-orchestrator**: primary caller.
- **kill-switch**: calls flatten_all on trigger.
- **portfolio-manager**: reconciles fills.
- **trader-memory-core**: registers ENTRY_READY -> ACTIVE transition with the order id.

## Safety Invariants

These are checked on every call. Violation = refuse with non-zero exit:

1. `mode` value in trading_params.yaml must match ALPACA_PAPER:
   - mode=paper => ALPACA_PAPER must be "true"
   - mode=live => ALPACA_PAPER must be "false"
2. `risk_per_trade_pct * 100` must be > 0 and the order's notional risk
   ((entry - stop) * qty) must be <= account_size_usd * risk_per_trade_pct/100
3. Order notional (qty * entry) must be <= account_size_usd * max_position_size_pct/100
4. Stop loss must be set (no naked entries).
5. Risk/reward must be >= global.min_rr_ratio.
6. If TRADE_LOOP_DRY_RUN=true: never call Alpaca at all.
7. If LIVE mode and checklist missing/unsigned: refuse with clear error.

## Troubleshooting

- `403 forbidden`: usually keys swapped between paper and live; check Alpaca dashboard.
- `Order rejected - insufficient buying power`: the orchestrator should have caught this; double-check max_positions and account_size_usd alignment.
- `Stop loss too close to entry`: Alpaca rejects stops < 0.01 from entry; the script
  validates a 1% minimum distance.
