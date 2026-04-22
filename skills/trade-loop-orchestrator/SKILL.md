---
name: trade-loop-orchestrator
description: Main automated trading loop. Every 5 minutes during US market hours, this skill (1) checks the kill-switch, (2) reads macro regime + exposure scale, (3) runs all configured screeners, (4) ranks/dedupes signals, (5) sizes positions via position-sizer, (6) submits bracket orders via alpaca-executor with full safety gates, and (7) writes a per-iteration audit log. Invoke when the user asks "run the loop", "execute the trader", "start the bot", "scan and place trades".
---

# Trade Loop Orchestrator

The conductor. Reads from every upstream skill, validates against every guard,
and submits bracket orders through alpaca-executor.

## Invariants

1. **Kill-switch first.** Pre-loop check is mandatory. If `TRIPPED` or `UNKNOWN`,
   the loop short-circuits with no orders submitted.
2. **Macro gate.** If `risk_on_score < cfg.global.macro_min_risk_on` (default 35),
   no new long entries. Existing positions are not touched.
3. **Exposure scale enforced.** Max new entries this loop = `floor(exposure_scale *
   max_positions) - current_positions`. If <=0, no new entries.
4. **Screener weights.** Signals from each screener are scored per
   `config/screener_weights.yaml`, then ranked by `composite_score = sum(weight_i *
   strategy_score_i) * confidence_multiplier`.
5. **Dedupe.** Same ticker, multiple screeners → highest composite wins; only one
   entry per ticker per loop.
6. **Idempotency.** Each candidate emits a stable `signal_id =
   sha1(ticker|date|primary_screener)[:16]`. Re-runs in the same day are no-ops.
7. **Dry-run by default.** Every entry path checks `TRADE_LOOP_DRY_RUN`; default
   true. Live submission requires explicit env flip + signed checklist.
8. **Audit trail.** Every iteration writes
   `state/loop/iter_<utc>_<status>.json` with all inputs and decisions.

## When to Use

- Scheduled by launchd `com.trade-analysis.trade-loop.plist` every 5 min,
  09:35-15:55 ET, weekdays.
- On demand by the user: "run the loop now", "what would the trader do right
  now?".
- Smoke test: `--mode plan` outputs would-be orders without invoking executor.

## Inputs

| Source | File / Endpoint | Purpose |
|--------|-----------------|---------|
| Kill-switch | `state/kill_switch_status.json` | Hard gate |
| Macro regime | `state/macro/dashboard_<date>.json` | risk_on_score, exposure_scale |
| Exposure coach | `state/exposure/recommendation_<date>.json` | per-strategy multipliers (optional) |
| Screener adapters | `reports/screeners/<screener>_<date>.json` | candidates list |
| Sector map | `config/sector_map.yaml` | enforce sector cap before submit |
| Trading params | `config/trading_params.yaml` | active profile + global guards |
| Screener weights | `config/screener_weights.yaml` | signal ranking |

## Workflow

```bash
# Plan-only (smoke test, no orders):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode plan --output state/loop/

# Live loop (still gated by TRADE_LOOP_DRY_RUN):
python3 skills/trade-loop-orchestrator/scripts/run_loop.py \
  --mode execute --output state/loop/
```

### Per-iteration sequence

1. Acquire file-lock at `state/loop/.lock` (prevents overlapping runs).
2. Pre-loop kill-switch check. If not OK, write `iter_<utc>_blocked.json`, exit 2.
3. Read macro state. If stale (>4h old) or missing, fall back to neutral
   (exposure_scale=0.5) and log a warning.
4. Load all screener outputs for today. Each adapter returns a uniform
   `Candidate` shape (see `references/candidate_schema.md`).
5. Rank + dedupe. Cap to `entries_allowed_this_loop`.
6. For each top candidate:
   - Resolve sector from `sector_map.yaml`
   - Skip if sector cap would be breached after this entry
   - Run position-sizer to compute `quantity` and `risk_amount`
   - Skip if quantity == 0 or risk > per-trade cap
   - Build payload and call `alpaca-executor/execute_trade.py`
7. Write iteration audit JSON with: macro snapshot, kill-switch status, all
   considered candidates, all decisions, all order results.

### Gates - in order, all must pass

| Gate | Source | Failure action |
|------|--------|----------------|
| Kill-switch OK | kill-switch | abort loop |
| Inside trading window | trading_params.yaml `global.trading_hours` | abort loop |
| Not a blackout date | trading_params.yaml `global.blackout_dates` | abort loop |
| risk_on_score >= macro_min_risk_on | macro-indicator-dashboard | skip new entries |
| current_positions < cap * exposure_scale | computed | skip new entries |
| Sector cap not breached by this entry | sector_map | skip this candidate |
| Per-trade risk within profile cap | position-sizer | skip this candidate |
| `validate_order` accepts | alpaca-executor | order refused, logged |

## State Files

`state/loop/iter_<utc>_<status>.json`:

```json
{
  "iteration_id": "loop_2026-04-21T14:35:00Z",
  "status": "executed",
  "kill_switch": {"status": "OK"},
  "macro": {"regime": "GOLDILOCKS", "risk_on_score": 72, "exposure_scale": 1.0},
  "candidates_considered": 14,
  "candidates_after_dedupe": 8,
  "entries_allowed": 3,
  "decisions": [
    {"ticker": "AAPL", "action": "submit", "alpaca_order_id": "abc-123"},
    {"ticker": "MSFT", "action": "skip_sector_cap", "reason": "Tech at 24%"}
  ],
  "duration_ms": 2843
}
```

## Combining with Other Skills

- **kill-switch**: pre-loop check (gate 1)
- **macro-indicator-dashboard**: regime + exposure_scale
- **exposure-coach**: per-strategy multipliers (optional refinement)
- **position-sizer**: shares-per-trade calculation
- **alpaca-executor**: actual order submission
- **eod-reconciliation**: consumes the iteration audit logs nightly
- **trader-memory-core**: each `submit` decision opens an ENTRY_READY thesis

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Loop completed (may have submitted 0 orders) |
| 1 | Hard error (config, env, lock acquisition failed) |
| 2 | Pre-loop check blocked (kill-switch, blackout, off-hours) |
| 3 | Partial: some orders failed but loop completed |
