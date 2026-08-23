# Metric Bridge Reference

`skills/backtest-expert/scripts/evaluate_backtest.py` takes eight inputs. This
page says where each one comes from and what goes wrong when you source it by
hand.

## The eight

| Evaluator input | Source | Conversion |
|-----------------|--------|------------|
| `--total-trades` | paired round trips | count of completed trips, not fills |
| `--win-rate` | paired round trips | percent of decided trips that made money net of fees |
| `--avg-win-pct` | paired round trips | mean net return of winners, percent of notional |
| `--avg-loss-pct` | paired round trips | mean net return of losers, absolute value |
| `--max-drawdown-pct` | engine metrics | `abs(max_drawdown) * 100` |
| `--years-tested` | config time range | `(end_ns - start_ns) / 365.25 days` |
| `--num-parameters` | spec | see `strategy_spec.md` |
| `--slippage-tested` | spec | set when fees or slippage are non-zero |

## The four traps

Each one produces a number that looks right and scores the strategy wrongly.
None raises an exception.

### Fills counted as trades

The engine's `trade_stats.total_trades` counts executions. A round trip needs
two, so the raw count runs at about double. The sample-size dimension scores 0
below 30 trades and 20 above 200, so a doubled count can carry a 90-trade
backtest into the top band it has not earned.

Use `round_trips`, which the engine also reports and which `pair_round_trips`
recomputes independently.

### Fills zipped in pairs

Taking rows two at a time assumes buy and sell alternate. That holds for one
shape: single symbol, long only, no scaling. Outside it:

- a sell can **open** a short, so `(exit - entry) / entry` reports the sign
  backwards for the whole short side
- scaling in leaves one exit answering several entries, so a pair reads
  `(buy, buy)` as a trip and drops the exit
- a universe interleaves fills across symbols, so pairs cross instruments

`pair_round_trips` tracks position per symbol and closes a trip when it crosses
back through flat. It accumulates entry / exit quantities and cash values over
the whole lifecycle, including a scale-out followed by a re-add. The weighted
average prices are for display; gross and net PnL are derived from those cash
flows so earlier exits never use the remaining position's cost basis.

### Gross percentages beside a net win rate

At 7 bps a side, a trade that gains 0.1% on price loses money. Count it as a
win and the win rate rises while the account falls.

The evaluator computes expectancy as `win_rate * avg_win - loss_rate * avg_loss`.
Feed it a gross win rate with net averages and the expectancy is wrong in a
direction that flatters the strategy. All percentages here are net of fees;
`gross_return_pct` stays on each trip for inspection.

`build_evaluation_inputs` compares its win rate against the engine's own and
warns when they differ by more than a point. A gap that large means one of the
two computations is wrong, and the numbers should not leave the machine until
you know which.

### Drawdown passed with its sign

The engine reports `max_drawdown` as a negative fraction: `-0.3846` for a 38.46%
fall. The evaluator wants a positive percent and scores worse as it grows. Pass
`-0.3846` and a near-catastrophic drawdown scores as a perfect one.

## Scratch trades

A trip that returns exactly zero is neither a win nor a loss. `summarize_round_trips`
counts it in `total_trades`, excludes it from the win rate, and reports it under
`scratches`. Folding scratches into losses depresses the win rate without any
trade having gone against the strategy.

## Warnings the bridge emits

| Warning | Why it matters |
|---------|----------------|
| no completed round trip | every percentage below it is undefined |
| fewer than 30 round trips | the sample-size dimension scores 0 |
| span under a year | the robustness dimension scores 0 |
| no friction modelled | execution realism scores 0 |
| `max_drawdown` absent | the risk dimension scores as if flawless |
| win rate gap over one point | the pairing and the engine disagree |

Read them before the numbers. Each one changes what the score means.
