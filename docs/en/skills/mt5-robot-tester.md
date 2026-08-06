---
layout: default
title: "Mt5 Robot Tester"
grand_parent: English
parent: Skill Guides
nav_order: 43
lang_peer: /ja/skills/mt5-robot-tester/
permalink: /en/skills/mt5-robot-tester/
generated: true
---

# Mt5 Robot Tester
{: .no_toc }

Select the best MetaTrader 5 trading robots (Expert Advisors) that have not been backtested yet, by running the MT5 Strategy Tester from the command line through a 3-round pipeline. Use when the user wants to batch-test MT5 bots/EAs, screen robots across all symbols, optimize EA parameters, or move candidate bots to finalists based on profit, drawdown, positive months/years and equity-curve criteria. Runs terminal64.exe headless; Windows + MetaTrader 5 required at run time.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/mt5-robot-tester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/mt5-robot-tester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

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

---

## 2. When to Use

- "Prueba robots / bots / EAs en MetaTrader 5."
- Screen a folder of MT5 Expert Advisors and pick the best across all pairs.
- Optimize EA parameters and decide finalists by profit/drawdown/consistency.
- Resume an interrupted testing run.

---

## 3. Prerequisites

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

---

## 4. Quick Start

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --dry-run
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/mt5-robot-tester/references/mt5-cli-reference.md`

**Scripts:**

- `skills/mt5-robot-tester/scripts/dashboard.py`
- `skills/mt5-robot-tester/scripts/mt5_batch_tester.py`
- `skills/mt5-robot-tester/scripts/mt5_common.py`
- `skills/mt5-robot-tester/scripts/mt5_learnings.py`
- `skills/mt5-robot-tester/scripts/parse_mt5_optimization.py`
- `skills/mt5-robot-tester/scripts/parse_mt5_report.py`
