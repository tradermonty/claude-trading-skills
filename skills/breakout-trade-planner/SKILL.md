---
name: breakout-trade-planner
description: Generate Minervini-style breakout trade plans from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates (stop-limit bracket for pre-placement, limit bracket for post-confirmation). Use when user has VCP screener results and wants actionable trade plans with entry/stop/target levels and position sizing.
---

# Breakout Trade Planner

Generate trade plans from VCP screener output following Mark Minervini's breakout methodology. Calculate position sizes using worst-case entry prices, enforce portfolio risk limits, and output Alpaca API-compatible order templates.

## When to Use

- User has VCP screener JSON output and wants trade plans
- User asks for breakout entry/stop/target calculation
- User wants Alpaca order templates for VCP breakout candidates
- User needs position sizing with portfolio heat management

## Prerequisites

- VCP screener JSON output with `schema_version: "1.0"`
- No API keys required (works with local JSON files)
- No external skill dependencies (position sizing is built-in)

## Workflow

### Step 1: Generate Trade Plans

Run the planner with VCP screener output:

```bash
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_YYYY-MM-DD.json \
  --account-size 100000 \
  --risk-pct 0.5 \
  --output-dir reports/
```

### Step 2: Review Output

Read the generated JSON and Markdown reports. Present:

1. **Actionable Orders** — Pre-breakout candidates with order templates
2. **Revalidation** — Breakout-state candidates needing live confirmation
3. **Watchlist** — Developing VCP candidates to monitor
4. **Rejected/Deferred/Constrained** — Candidates filtered by Gate or portfolio limits
### Step 3: Explain Trade Plans

For each actionable order, explain:
- Entry levels (signal vs worst-case) and stop-loss placement
- R-multiple targets and reward-risk ratio
- Two execution modes: pre_place (stop-limit) vs post_confirm (limit after 5min confirmation)
- Portfolio risk contribution and cumulative heat
- Broker and intraday constraints: these templates are planning artifacts, not broker permission. If the plan could create same-day round trips or use margin, confirm the user's broker-specific intraday/day-trading controls. FINRA replaced the old pattern-day-trader day-count and $25,000 minimum-equity requirements with intraday margin standards effective 2026-06-04, with broker phase-in allowed through 2027-10-20.

## Minervini Gate (Filtering Criteria)

Candidates must pass ALL conditions:

| Condition | Pre-breakout | Breakout |
|-----------|-------------|----------|
| valid_vcp | True | True |
| rating_band | good/strong/textbook | good/strong/textbook |
| risk_pct_worst | <= 8.0% | <= 8.0% |
| breakout_volume | — | True |
| distance_from_pivot | — | <= max_chase_pct |
| current_price | — | <= worst_entry |

## CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| --account-size | (required) | Account equity in dollars |
| --risk-pct | 0.5 | Base risk % per trade |
| --max-position-pct | 10.0 | Max single position % |
| --max-sector-pct | 30.0 | Max sector exposure % |
| --max-portfolio-heat-pct | 6.0 | Max total open risk % |
| --target-r-multiple | 2.0 | Take-profit R-multiple |
| --stop-buffer-pct | 1.0 | Stop buffer below contraction low |
| --max-chase-pct | 2.0 | Max chase above pivot |
| --pivot-buffer-pct | 0.1 | Pivot buffer for buy-stop trigger |
| --current-exposure-json | None | Existing portfolio exposure |

## Output

- `breakout_trade_plan_YYYY-MM-DD_HHMMSS.json` — Structured plans with order templates
- `breakout_trade_plan_YYYY-MM-DD_HHMMSS.md` — Human-readable report

## Resources

- `references/minervini_entry_rules.md` — Entry methodology and rules
