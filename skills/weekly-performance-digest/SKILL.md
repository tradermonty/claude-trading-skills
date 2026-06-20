---
name: weekly-performance-digest
description: Generate a weekly performance summary from closed trader-memory-core theses — win rate, expectancy, profit factor, R-multiple, MAE/MFE, and win/loss pattern analysis by source skill, exit reason, thesis type, sector, and mechanism. No API required; pure local calculation.
---

# Weekly Performance Digest

## Overview

Weekly Performance Digest aggregates the trades you closed during a week into a single
performance report. It reads CLOSED theses tracked by `trader-memory-core`
(`state/theses/th_*.yaml`), computes headline metrics (win rate, expectancy, profit
factor, R-multiple, MAE/MFE), breaks results down across several pattern dimensions
(source skill, exit reason, thesis type, sector, mechanism tag, screening grade), and
surfaces the week's biggest winners, losers, and lessons. Output is a JSON record plus
a human-readable Markdown report. Pure calculation — no API key required.

## When to Use

- At the end of a trading week to review aggregate realized performance
- To measure win rate and expectancy across all closed positions
- To see which source skills, exit reasons, sectors, or mechanisms drove wins vs losses
- To feed a month-end review (combine four weekly digests) or a postmortem
- For a quick "what worked / what didn't" snapshot grounded in real closed trades

## When Not to Use

- For a single-trade deep review — use `trade-performance-coach`
- For signal-level true/false-positive classification — use `signal-postmortem`
- For buy/sell recommendations or position sizing — this skill is descriptive only

## Prerequisites

- Python 3.9+ with `PyYAML` (already a repo dependency)
- A `trader-memory-core` state directory of thesis YAML files (`state/theses/`)
- No API key required

## Workflow

### Step 1: Run the digest for a week

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

Defaults: `--state-dir state/theses`, `--from-date` = 7 days before `--to-date`,
`--to-date` = today, `--output-dir reports/`. With no date flags it digests the
trailing 7 days.

### Step 2: Read the report

The run writes `reports/weekly_digest_<to-date>.json` and
`reports/weekly_digest_<to-date>.md`. Review the Markdown for the executive summary,
metrics table, pattern breakdowns, and top winners/losers; consume the JSON downstream.

### Step 3 (optional): Feed downstream

Combine several weekly JSON digests for a monthly review, or pass the JSON to a
postmortem/coach step. The skill is descriptive — act on its findings via your normal
review process.

## How It Works

- **Trade selection.** A trade counts in a week if its `exit.actual_date` falls in
  `[from-date, to-date]` and `status == CLOSED`.
- **Win/loss.** `outcome.pnl_dollars > 0` is a winner, `< 0` a loser, `== 0` breakeven;
  `win_rate = winners / total_trades`.
- **R-multiple.** `pnl_dollars / ((entry.actual_price − exit.stop_loss) × position.shares)`.
  (Stop-loss is read from `exit.stop_loss`, per the real thesis schema.)
- **Double-counting safeguard.** A CLOSED thesis's `outcome.pnl_dollars` is the
  *cumulative* realized P&L across all trims plus the final leg. Headline metrics use
  that cumulative value over CLOSED theses only. The separate `partial_trims` block
  scans `status_history[]` of **PARTIALLY_CLOSED theses only** (still open) and is
  reported for information — it is **never** added into the headline totals/win-rate.
  A position trimmed in week 1 then closed in week 2 therefore shows as a partial trim
  in week 1 and inside week 2's CLOSED headline; that is intended, not a duplicate.

## Output Format

### JSON (`weekly_digest_<to-date>.json`)

```json
{
  "schema_version": "1.0",
  "report_type": "weekly_performance_digest",
  "period": {"from": "2026-06-13", "to": "2026-06-20"},
  "generated_at": "2026-06-20T21:39:07Z",
  "summary": {
    "total_trades": 2, "winners": 1, "losers": 1, "breakeven": 0,
    "win_rate": 0.5, "expectancy": 25.0, "profit_factor": 2.0,
    "total_realized_pnl": 50.0, "total_realized_pnl_pct": 4.17
  },
  "metrics": {
    "avg_winner": 100.0, "avg_loser": -50.0,
    "largest_winner": 100.0, "largest_loser": -50.0,
    "avg_holding_days_winners": 9.0, "avg_holding_days_losers": 6.0,
    "r_multiple_avg": 0.25, "r_multiple_stdev": 1.06,
    "avg_mae_pct": -3.75, "avg_mfe_pct": 4.5
  },
  "pattern_analysis": {
    "by_source_skill": {"...": {"wins": 1, "losses": 0, "total": 1, "win_rate": 1.0}},
    "by_exit_reason": {}, "by_thesis_type": {}, "by_sector": {},
    "by_mechanism_tag": {}, "by_screening_grade": {}
  },
  "partial_trims": {"count": 0, "total_realized_pnl": 0.0, "trims": []},
  "lessons": {"top_wins": [], "top_losses": [], "process_improvements": []}
}
```

### Markdown (`weekly_digest_<to-date>.md`)

Sections: `# Weekly Performance Digest`, `## Executive Summary`,
`## Performance Metrics`, `## Pattern Analysis`, `## Lessons Learned`
(`### Top Winners` / `### Top Losers` / `### Process Improvements`).

An empty week still produces a valid report with zeroed metrics (exit code 0).

## Resources

- `scripts/generate_weekly_digest.py` — digest generator (JSON + Markdown)
- `references/weekly-digest-metrics.md` — metric formulas and interpretation

## Key Principles

1. **Closed trades only for headline numbers** — cumulative `outcome.*`, keyed on exit date.
2. **No double-counting** — partial trims are informational and excluded from totals.
3. **Pattern attribution** — every win/loss is attributed across multiple dimensions.
4. **Descriptive, not prescriptive** — the digest reports; you decide.
