# Weekly Digest — Metric Definitions

Definitions and formulas used by `generate_weekly_digest.py`. All headline metrics are
computed over **CLOSED theses only**, selected by `exit.actual_date` within the week.

## Win / loss classification

- A trade is a **winner** when `outcome.pnl_dollars > 0`, a **loser** when `< 0`, and
  **breakeven** when `== 0`.
- When `pnl_dollars` is absent, `pnl_pct` is used as a fallback signal of sign.

## Headline metrics

| Metric | Formula |
|---|---|
| Win rate | `winners / total_trades` |
| Expectancy | `mean(pnl_dollars)` across all closed trades (avg P&L per trade) |
| Profit factor | `gross_profit / abs(gross_loss)`; `null` when there are no losers (undefined) |
| Total realized P&L | `sum(pnl_dollars)` |
| Avg / largest winner | `mean` / `max` of winning `pnl_dollars` |
| Avg / largest loser | `mean` / `min` of losing `pnl_dollars` |
| Avg holding days (W/L) | `mean(holding_days)` for winners and losers separately |

`expectancy` can also be reasoned about as
`(avg_win × win_rate) + (avg_loss × loss_rate)`; the script computes it directly as the
mean P&L per trade, which is equivalent.

## R-multiple

```
R = pnl_dollars / initial_risk
initial_risk = (entry.actual_price − exit.stop_loss) × position.shares
```

- Stop-loss is read from **`exit.stop_loss`** (the real thesis schema location).
- `R` is `null` when any of `pnl_dollars`, `entry.actual_price`, `exit.stop_loss`, or
  `position.shares` is missing, or when initial risk is zero.
- `r_multiple_stdev` uses the sample standard deviation; it is `0.0` for a single trade.

## MAE / MFE

- **MAE** (Maximum Adverse Excursion, `outcome.mae_pct`) is the worst drawdown while the
  position was open. By convention it is **≤ 0** (adverse).
- **MFE** (Maximum Favorable Excursion, `outcome.mfe_pct`) is the best unrealized gain
  while open. By convention it is **≥ 0** (favorable).
- `trader-memory-core` does not clamp these fields, so an always-profitable trade can
  carry `mae_pct > 0` (and an always-underwater one `mfe_pct < 0`). The digest **clamps
  on read** to preserve the convention: MAE → `min(value, 0)`, MFE → `max(value, 0)`.
- The digest aggregates `avg_mae_pct` and `avg_mfe_pct` across closed trades. Large
  average MFE relative to realized P&L suggests trades are being exited too early; large
  average MAE relative to risk suggests stops are too wide or entries are mistimed.

## Pattern analysis

Each closed trade is bucketed across six dimensions, each reporting `{wins, losses,
total, win_rate}` (win_rate = wins / decided, where decided = wins + losses):

| Dimension | Source field |
|---|---|
| `by_source_skill` | `origin.skill` |
| `by_exit_reason` | `exit.exit_reason` |
| `by_thesis_type` | `thesis_type` |
| `by_sector` | `market_context.sector` |
| `by_mechanism_tag` | `mechanism_tag` |
| `by_screening_grade` | `origin.screening_grade` |

Missing values bucket as `unknown` rather than dropping the trade.

## Partial trims (informational only)

`partial_trims` scans `status_history[]` of **PARTIALLY_CLOSED** theses for entries with
a `realized_pnl` whose `at` date is in-week. These are realized gains/losses on still-open
positions; they are reported separately and **never** added to the headline totals or
win-rate, because a CLOSED thesis's `outcome.pnl_dollars` already includes its own trims
cumulatively (counting both would double-count).

## Luck vs. skill heuristics

- A small sample (few closed trades) makes win rate and expectancy noisy — treat a single
  week as directional, not conclusive; confirm patterns across multiple weeks.
- Consistent positive expectancy with R-multiple average ≥ 0 across many trades is the
  signal of an edge; a high win rate with negative expectancy means losers are too large.
