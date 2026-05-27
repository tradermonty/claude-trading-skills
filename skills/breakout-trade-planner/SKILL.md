---
name: breakout-trade-planner
description: Generate Minervini-style breakout trade plan templates from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates for manual entry (stop-limit bracket for pre-placement, limit bracket for post-confirmation). All plans require manual review and broker entry — no orders are placed automatically. Use when user has VCP screener results and wants decision-support trade plans with entry/stop/target levels and position sizing.
---

# Breakout Trade Planner

Generate trade plan templates from VCP screener output following Mark Minervini's breakout methodology.
Calculate position sizes using worst-case entry prices, enforce portfolio risk limits, and output
Alpaca-compatible order templates for **manual entry at the broker**.

> **Decision-support only.** This skill produces structured plan templates — no orders are placed
> automatically. All output requires manual review and explicit trader approval before any order
> is entered at a brokerage. `manual_review_required: true` in all output artifacts.

## When to Use

- User has VCP screener JSON output and wants trade plans
- User asks for breakout entry/stop/target calculation
- User wants Alpaca-compatible order templates for manual entry of VCP breakout candidates
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

1. **Evaluation Candidates** — Pre-breakout candidates with order templates for manual broker entry
2. **Revalidation** — Breakout-state candidates needing live confirmation
3. **Watchlist** — Developing VCP candidates to monitor
4. **Rejected/Deferred/Constrained** — Candidates filtered by Gate or portfolio limits
### Step 3: Explain Trade Plans

For each evaluation candidate, explain:
- Entry levels (signal vs worst-case) and stop-loss placement
- R-multiple targets and reward-risk ratio
- Two execution modes: pre_place (stop-limit) vs post_confirm (limit after 5min confirmation)
- Portfolio risk contribution and cumulative heat

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

## Manual Review Gate

Before acting on any plan output, the trader must confirm all of the following outside this repo:

1. Market-regime-daily `exposure_decision` is non-restrictive (not cash-priority)
2. Weekly chart review passes the trader's own chart criteria
3. Total portfolio heat after this trade remains within the trader's personal risk budget
4. Order parameters reviewed against live quote at the broker before placement
5. All orders entered manually — this skill does not place orders

## Data Gaps

| Scenario | Severity | Behavior |
|----------|----------|----------|
| VCP screener JSON missing or unreadable | CRITICAL | Halt — cannot generate plan without screener input |
| Account size not provided | CRITICAL | Halt — cannot size positions without account equity |
| Market regime not confirmed | HIGH | Note in output; mark plan as UNVALIDATED |
| Fewer than 1 candidate passes Minervini Gate | LOW | Output empty plan with explanation; do not fabricate candidates |

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `trade_plan` | `TradePlan` | Entry/stop/target plan — manual_review_required: true always |

Schema: `schemas/json/trade_plan.json`

## Resources

- `references/minervini_entry_rules.md` — Entry methodology and rules
