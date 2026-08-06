---
name: mt5-robot-tester
description: Select the best MetaTrader 5 trading robots (Expert Advisors) that have not been backtested yet, by running the MT5 Strategy Tester from the command line through a 3-round pipeline. Use when the user wants to batch-test MT5 bots/EAs, screen robots across all symbols, optimize EA parameters, or move candidate bots to finalists based on profit, drawdown, positive months/years and equity-curve criteria. Runs terminal64.exe headless; Windows + MetaTrader 5 required at run time.
---

# MT5 Robot Tester

## Overview

Select the best MetaTrader 5 robots (Expert Advisors) from a *candidates* folder
by driving the Strategy Tester from the command line through a **3-round
pipeline**, moving each bot between folders as it advances, and **learning across
runs** to improve selection each loop. The whole run is checkpointed and
resumable.

- **Round 1 — screening (all pairs):** backtest the EA on each symbol in the
  configured `common.symbols` list (one `Optimization=0` backtest per symbol —
  MT5 build 6061 leaves the `Optimization=3` XML empty, so per-symbol backtests
  are used). Gate: **≥5 symbols profitable AND best symbol ≥3× deposit**.
- **Round 2 — best-pair backtest:** single backtest on the best symbol; analyze
  net profit %, worst drawdown %, % positive months, all-years-positive, LR
  Correlation, months-to-new-high.
- **Round 3 — sequential parameter optimization:** optimize the 5–6 inputs after
  `MagicNumber`, one at a time, range ±50% step 5%; then a final backtest.
- **Finalist:** optimized result **improves** on Round 2 **and** profit **≥4×
  deposit** **and** worst drawdown **≤12%**.

Tested bots move to *in-testing*; finalists are also copied to *finalists* with
their optimized `.set`.

## When to Use

- "Prueba robots / bots / EAs en MetaTrader 5."
- Screen a folder of MT5 Expert Advisors and pick the best across all pairs.
- Optimize EA parameters and decide finalists by profit/drawdown/consistency.
- Resume an interrupted testing run.

## Prerequisites

- **Windows + MetaTrader 5** installed (the tester runs `terminal64.exe`).
- Broker **tick data** downloaded (default modeling is real ticks, `Model=4`).
- The three folders under `MQL5\Experts`: *candidates*, *in-testing*, *finalists*.
- **`common.symbols`** set in the config — the pairs Round 1 backtests (your
  Market Watch symbols).
- Optional per-bot `.set` files (config `sets_dir`) for the Round-2 baseline and
  Round-3 parameter optimization. Every input is fixed during optimization
  except the one parameter currently being searched; without a `.set`, Round 3
  is skipped and the verdict comes from Round 2.
- **Close MetaTrader 5 before running** — the tester needs exclusive use of the
  data folder.
- Python 3.9+ (standard library only). No paid API.

## Workflow

### Step 1 — Configure

Copy `assets/pipeline_config.template.json`, fill in the three folder paths and
(optionally) `terminal_path`. Never commit real personal paths — pass the config
at run time. Defaults already encode the agreed settings (2020.01.01→2026.06.30,
H1, Model=4, 10000 USD, 1:100, gates and thresholds).

### Step 2 — Dry-run (optional)

Verify the generated Round-1 INIs without launching MT5:

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --dry-run
```

### Step 3 — Run the pipeline

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline
```

Each bot flows R1 → R2 → R3 → finalist decision. Progress is written to
`state.json` and `run.log` after every step.

### Step 4 — Resume if interrupted

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --resume
```

`--resume` skips completed bots and reuses finished rounds only while the
execution config, EA binary, and input `.set` fingerprints still match. A
changed period, symbol list, binary, or `.set` restarts that bot safely.

### Optional — HTML control panel

Launch a local dashboard to see the bots in each folder, each bot's phase and
verdict, and a **Launch** button — no CLI needed after starting it:

```bash
python3 skills/mt5-robot-tester/scripts/dashboard.py \
  --config my_config.json --output-dir reports/mt5_pipeline
```

It serves `http://127.0.0.1:8765/` (opens automatically, localhost only). The
page auto-refreshes every 3 s: folder contents, per-bot phase (R1/R2/R3/done),
pass/fail verdicts, summary counts, and the live `run.log`. Start/stop requests
are limited to the exact local origin and require the per-server CSRF token.

### Step 5 — Read the results

- `leaderboard_<ts>.md` / `.json` — ranking with verdict and key metrics.
- `learnings.json` / `learnings.md` — what the skill learned this loop
  (parameter impact and symbol priors) under the configured output directory.
- `mt5_reports/` and `mt5_ini/` — raw MT5 reports and configs per bot/round.

## Round details

### Round 1 gate (both required)
1. `count_positive_profit(passes) ≥ round1_min_positive` (default 5).
2. `best_symbol_profit ≥ round1_min_profit_multiple × deposit` (default 3×).

Fail → bot rejected (moved to *in-testing*).

### Round 2 quality profile (reference thresholds)
Net profit ≥300%, worst DD <15% (larger of balance/equity %), positive months
>70%, all years positive, **LR Correlation ≥0.80**, months-to-new-high ≤3.
Reported per bot; the hard finalist gate is Round 3.

### Round 3 sequential optimization
For each of the 5–6 inputs after `MagicNumber` (learned order first), optimize
that single parameter over `[V×0.5, V×1.5]` step `V×0.05` (`Optimization=1`)
while fixing every other `.set` input, fix its best value, then continue. Run a
final backtest with the exact complete input set saved for a finalist.

### Finalist
`evaluate_finalist`: improved on Round 2 **and** profit ≥4× deposit **and** worst
DD ≤12%. → copied to *finalists* with `<bot>.set`.

## Self-learning across loops

`learnings.json` accumulates, per run: parameter average profit improvement
(reorders Round-3 optimization so the most impactful parameters are tried first),
symbol priors (how often each is a best pair), and per-bot verdicts. This makes
selection converge faster each loop. Deterministic — plain aggregate statistics.

## Output Format

- `leaderboard_<ts>.json` — list of `{name, verdict, best_symbol, r2_profit,
  final_profit, final_dd_pct, lr, reason}` sorted finalists-first by profit.
- `leaderboard_<ts>.md` — same as a table.
- `state.json` — resumable per-bot/per-round checkpoint.

## Resources

- `scripts/mt5_batch_tester.py` — pipeline orchestrator + INI builders (CLI).
- `scripts/parse_mt5_optimization.py` — optimization report (XML/HTML) parser +
  Round-1 gate.
- `scripts/parse_mt5_report.py` — backtest report parser + balance-series metrics.
- `scripts/mt5_learnings.py` — cross-run learning store.
- `scripts/mt5_common.py` — shared parsing helpers (EN/ES headers, numbers).
- `references/mt5-cli-reference.md` — MT5 `[Tester]`/`[TesterInputs]` keys, enums,
  report formats and caveats.
- `assets/pipeline_config.template.json` — config template with placeholders.

## Key Principles

1. **Never commit personal paths** — folders/terminal come from config/ENV/args.
2. **Relative `Report=` names** because build 6061 ignores absolute report paths;
   collect completed reports from the terminal data directory.
3. **Real ticks (`Model=4`)** need broker tick data; it is slow — expect long runs.
4. **Resumable**: every round checkpoints; `--resume` reuses only fingerprint-
   matching work and retries execution errors.
5. **Fail closed**: incomplete, timed-out, stale, or unparsable reports never
   reject, promote, or move a candidate. Every unique Round-1 symbol must finish.
6. **Single MT5 owner**: an OS lock is held for the process lifetime for each
   shared MT5 data folder. If child termination cannot be confirmed, the whole
   run stops and writes a `.blocked` marker; verify the recorded PID/process tree
   has exited before removing that marker manually.
7. **Full-period metrics**: months without deals at the start, end, or across a
   full year remain part of the configured test period.
8. **Learn each loop**: parameter/symbol statistics bias future runs toward wins.
9. **Verify against your build**: report layout (esp. the deals table) and the
   32 ms delay mapping can differ — see the reference's *(verify)* notes.
