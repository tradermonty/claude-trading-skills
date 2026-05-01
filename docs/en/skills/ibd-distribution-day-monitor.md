---
layout: default
title: IBD Distribution Day Monitor
grand_parent: English
parent: Skill Guides
nav_order: 11
lang_peer: /ja/skills/ibd-distribution-day-monitor/
permalink: /en/skills/ibd-distribution-day-monitor/
---

# IBD Distribution Day Monitor
{: .no_toc }

Detect IBD-style Distribution Days for QQQ/SPY, track 25-session expiration and 5% invalidation, classify market risk (NORMAL / CAUTION / HIGH / SEVERE), and emit TQQQ/QQQ exposure recommendations. Designed for daily post-market review.
{: .fs-6 .fw-300 }

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ibd-distribution-day-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ibd-distribution-day-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

IBD Distribution Day Monitor automates the single most actionable signal in William O'Neil's CAN SLIM framework: counting the days when institutions are quietly unloading positions. A cluster of Distribution Days has historically preceded most major market corrections, and this skill turns the rule into a reproducible daily workflow.

**What it solves:**
- Removes ambiguity from a rule that traders interpret differently in practice (e.g. "is 25 sessions inclusive?", "does the DD day's intraday high count for invalidation?").
- Produces a deterministic risk level (NORMAL / CAUTION / HIGH / SEVERE) and a TQQQ-aware exposure recommendation in one command.
- Replaces eyeballing with auditable JSON output, including the exact dates that contributed to the active count.
- Handles QQQ + SPY simultaneously and combines them with a TQQQ-weighted policy that escalates broad-market degradation.

**Key capabilities:**
- Distribution Day detection: close down at least 0.2% on higher volume, with explicit float epsilon at the boundary
- 25-session expiration AND 5% invalidation tracked separately, with `removal_reason` recorded as `expired_25_sessions` or `invalidated_5pct_gain`
- Display-vs-invalidation `high_since` separation: DD day's intraday high is shown but never used to invalidate the same DD
- Configurable `invalidation_price_source`: `high` (conservative, default) or `close` (closing-price only)
- Risk classification with configurable `RiskThresholds` and a 21EMA / 50SMA filter that escalates to SEVERE when the index is below both
- TQQQ-weighted multi-index combination: a HIGH on QQQ alone, or NORMAL+HIGH on (QQQ, SPY), both raise overall risk
- TQQQ exposure policy (100 / 75 / 50 / 25%) with progressively tighter trailing stops; QQQ uses a less aggressive variant
- UTF-8 output (`ensure_ascii=False`); API keys redacted automatically in audit snapshots

<span class="badge badge-api">FMP Required</span>

---

## 2. Prerequisites

- **API Key:** [Financial Modeling Prep (FMP)](https://site.financialmodelingprep.com/developer/docs) — free tier (250 calls/day) is sufficient for daily QQQ + SPY runs.
- **Python 3.9+:** Standard library plus `requests` (already installed) and `pyyaml` (already in `pyproject.toml` dependencies).
- **No pandas dependency:** All OHLCV is processed as `list[dict]` for portability and speed.

> Set the API key once via environment variable: `export FMP_API_KEY=your_key_here`. The skill's resolution order is `--api-key` flag > `data.api_key` in config > `FMP_API_KEY` env var, so a CLI override always wins.
{: .tip }

> The Distribution Day rule itself does not require any market structure assumptions, so the skill works on any liquid US equity ETF / index that FMP supports. Defaults are tuned for QQQ + SPY.
{: .note }

---

## 3. Quick Start

Run the script with default settings:

```bash
export FMP_API_KEY=your_key_here

python3 skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py \
  --symbols QQQ,SPY \
  --lookback-days 80 \
  --instrument TQQQ \
  --current-exposure 100 \
  --base-trailing-stop 10 \
  --output-dir reports/
```

The script fetches 80 sessions of OHLCV for each symbol, detects active Distribution Days, classifies risk, and writes a JSON + Markdown report pair to `reports/` named `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.{json,md}`.

You can also invoke it conversationally inside Claude Code: "Run the IBD Distribution Day monitor for today and tell me whether to keep my TQQQ exposure at 100%."

---

## 4. How It Works

```
+-----------------+   +-----------------------+   +-----------------------+
| 1. Fetch OHLCV  |-->| 2. as_of normalization|-->| 3. Detect DDs         |
|   (FMP per sym) |   |   prepare_effective_  |   |  pct_change <= -0.002 |
+-----------------+   |   history             |   |  AND volume up        |
                      +-----------------------+   +-----------+-----------+
                                                              |
+-----------------+   +-----------------------+   +-----------v-----------+
| 7. Combine risk |<--| 6. Classify per-index |<--| 4. Enrich records     |
|   QQQ-weighted  |   |   d5/d15/d25 + MA     |   |  high_since (display) |
+--------+--------+   +-----------------------+   |  invalidation event   |
         |                                         |  expiration / status  |
         v                                         +-----------+-----------+
+-----------------+   +-----------------------+               |
| 8. Exposure     |-->| 9. Write JSON + MD    |<--------------+
|   policy (TQQQ) |   |  with redaction       |
+-----------------+   +-----------------------+
```

1. **Fetch OHLCV** — Each symbol is requested with `lookback_days + 5` extra sessions so that the 50SMA filter has enough history. The `fmp_client.py` truncates correctly per Issue #64 fix.
2. **`as_of` normalization** — Either today (default) or the user-supplied `--as-of YYYY-MM-DD` is rebased so that `effective_history[0]` is always the evaluation session. No `as_of_index` is plumbed through downstream modules; this keeps tracker code simple.
3. **DD detection** — For each consecutive pair, `pct_change <= -0.002 + EPSILON` and volume up. Sessions with missing or non-positive close/volume are skipped and recorded as `skipped_sessions` in the audit.
4. **Enrichment** — Each raw DD becomes a full record:
    - `high_since` for display = `max(high in history[0:k+1])` (DD day's high included)
    - Invalidation scan = `history[0:k]` ∩ expiration window, using the configured `invalidation_price_source`
    - Status priority: `invalidated` > `expired` > `active`
    - 5% gain that occurs **after** 25 sessions is treated as `expired_25_sessions`, not invalidation.
5. **Counting** — `count_active_in_window(records, N)` returns the number of `active` records with `age_sessions <= N`. So `d25_count` includes ages 0..25 (26 sessions). Aligned with `expiration_sessions = 25`: an age=25 DD is still active and still counted; age=26 is expired and excluded.
6. **Per-index classification** — Thresholds (`d25 >= 6` or `d15 >= 4` for SEVERE, etc.) are loaded from config (`RiskThresholds`). The 21EMA / 50SMA filter only escalates to SEVERE when the close is below **both** moving averages and `d25 >= 5`. If MA cannot be computed due to insufficient data, the filter is `None` and SEVERE escalation is skipped.
7. **Combine** — The combined risk is QQQ-weighted: a SEVERE on either index, or a HIGH on QQQ, immediately escalates. `QQQ NORMAL + SPY HIGH` still raises to HIGH because broad-market deterioration historically spills into TQQQ. Otherwise the maximum risk wins.
8. **Exposure policy** — TQQQ targets {100, 75, 50, 25}% as risk rises and tightens the trailing stop accordingly. QQQ uses a less aggressive variant ({100, 100, 75, 50}%). The recommendation never **widens** the user's existing trailing stop — it can only tighten it.
9. **Output** — JSON is written with `ensure_ascii=False` so Japanese explanations survive round-trip. Sensitive keys (`api_key`, `fmp_api_key`, `token`, etc.) are redacted via lowercase comparison before either file is written.

---

## 5. Usage Examples

### Example 1: Daily Post-Market Check

**Prompt:**
```
Run the IBD Distribution Day monitor for today and report whether I should
adjust my TQQQ position.
```

**What happens:** The skill loads 80 sessions of QQQ + SPY data, detects active Distribution Days, and outputs the combined risk level plus a TQQQ-specific recommendation (target exposure %, trailing stop %).

**Why useful:** Replaces eyeballing index charts with a deterministic answer in seconds. The same input always produces the same output, which is exactly what you want for a risk-management rule.

---

### Example 2: Backtest a Past Top

**Prompt:**
```
What did the IBD distribution-day picture look like on 2025-04-04, the day
after the tariff-shock decline?
```

**What happens:** With `--as-of 2025-04-04 --lookback-days 80`, the skill rebases history so that 2025-04-04 is the evaluation session, and runs the full pipeline as if today were that date. The MA filter and 5% invalidation tracker honor the historical context.

**Why useful:** Validates whether the rule would have warned you ahead of the actual drawdown. If the audit shows `insufficient_lookback`, simply request more history with a larger `lookback-days`.

---

### Example 3: Adjust Risk Thresholds

**Prompt:**
```
I want a more conservative trigger. Change the HIGH threshold to d25 >= 4
and re-run today's analysis.
```

**What happens:** Edit `skills/ibd-distribution-day-monitor/config/default.yaml` (or pass a custom `--config` file) so `risk_thresholds.high.d25_count: 4`, then re-run. The skill loads the new threshold and reclassifies. Test changes against historical dates first via `--as-of`.

**Why useful:** Different traders prefer different sensitivity. The skill never hard-codes thresholds — they all live in YAML and can be tuned per portfolio.

---

### Example 4: Switch to Close-Source Invalidation

**Prompt:**
```
I want to invalidate Distribution Days only when the index closes 5%+ above
the DD close, not on intraday highs.
```

**What happens:** Set `distribution_day_rule.invalidation_price_source: close` in the config. The `_find_invalidation_event` scanner now compares `row["close"]` (instead of `row["high"]`) against `dd_close * 1.05`.

**Why useful:** Some practitioners prefer the strict closing-price interpretation. The skill supports both without code changes; the choice is documented in `audit.rule_evaluation.distribution_day_rule.invalidation_price_source`.

---

### Example 5: Pre-Trade Sanity Check Before Adding TQQQ

**Prompt:**
```
I'm thinking of adding 25% to my TQQQ position. Is the market environment
green-lit?
```

**What happens:** The skill runs and reports the current risk level. If NORMAL, the recommendation is `HOLD_OR_FOLLOW_BASE_STRATEGY`. If CAUTION, it advises `AVOID_NEW_ADDS`. If HIGH or SEVERE, it explicitly proposes reducing exposure.

**Why useful:** A 5-second sanity check before a leveraged add. Repeated additions during a HIGH-state market is one of the most common ways amateur TQQQ traders lose more than the index drops.

---

### Example 6: Combine with Position Sizer

**Prompt:**
```
The risk level is HIGH. Recalculate my TQQQ position size with a tighter
trailing stop based on the recommendation.
```

**What happens:** The IBD Monitor returns `trailing_stop_pct: 5` for HIGH state; you then pass that into the Position Sizer skill (`--atr-multiplier` or stop-based sizing) to compute the tighter share count.

**Why useful:** Risk management cascades. The Distribution Day signal informs the trailing stop; the trailing stop informs the share count. Both are deterministic, both are auditable.

---

## 6. Understanding the Output

The skill writes two files plus a console summary:

1. **JSON report** — Full schema with `market_distribution_state`, `portfolio_action`, `rule_evaluation`, and `audit` sections. UTF-8 with `ensure_ascii=False`.
2. **Markdown report** — Human-readable summary with the active DD table per index, recommended action, and audit flags.

### Risk Level Quick Reference

| Risk | Trigger (one of) | TQQQ Action | TQQQ Target | Trail Stop Cap |
|------|------------------|-------------|-------------|----------------|
| NORMAL | `d25 <= 2` | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base |
| CAUTION | `d25 >= 3` | AVOID_NEW_ADDS | 75% | 7% |
| HIGH | `d25 >= 5` OR `d15 >= 3` OR `d5 >= 2` | REDUCE_EXPOSURE | 50% | 5% |
| SEVERE | `d25 >= 6` OR `d15 >= 4` OR (close below 21EMA AND 50SMA AND `d25 >= 5`) | CLOSE_TQQQ_OR_HEDGE | 25% | 3% |

### Per-DD Record Fields

| Field | Meaning |
|-------|---------|
| `date` | Distribution Day date |
| `age_sessions` | Sessions elapsed since the DD (0 = today) |
| `expires_in_sessions` | `25 - age_sessions`, bounded at 0 |
| `pct_change` | DD-day decline (negative) |
| `volume_change_pct` | DD-day volume change vs prior session |
| `high_since` | Display max of intraday high from DD day to today (DD day **included**) |
| `invalidation_price` | `dd_close * 1.05` |
| `invalidation_date` | Date of first 5%+ trigger after DD (null if not triggered) |
| `invalidation_trigger_price` | The actual price that triggered (high or close depending on config) |
| `invalidation_trigger_source` | `"high"` or `"close"` per config |
| `status` | `active`, `expired`, or `invalidated` |
| `removal_reason` | `expired_25_sessions` or `invalidated_5pct_gain` (null when active) |

### Audit Flags

| Flag | Meaning |
|------|---------|
| `insufficient_lookback` | Loaded history is shorter than the required window (50SMA + 1 etc.) |
| `insufficient_data_for_moving_average` | 21EMA or 50SMA could not be computed; SEVERE escalation skipped |
| `data_quality_warnings` | At least one session was skipped due to missing or invalid OHLCV |
| `no_data_returned` | FMP returned no rows for one or more symbols |

---

## 7. Tips & Best Practices

- **Run after the close, not intraday.** The Distribution Day rule was designed for end-of-day data. Intraday volume estimates are unreliable, and an intraday "DD" can disappear if the close recovers.
- **Watch the cluster pattern, not just the count.** Two DDs in 5 sessions (`d5 >= 2`) is more dangerous than five DDs spread over 25 sessions even though both are HIGH. The skill captures both via the d5/d15/d25 buckets.
- **Use `--as-of` to validate the rule against history.** Before trusting any threshold change, run the modified config against 2008, 2018, 2020, 2022, and 2025-04 to confirm it would have triggered at the right moments.
- **Don't widen your trailing stop.** The skill's recommendation is always `min(your_base, policy_cap)`. If your existing trail is already tighter, the skill respects it. Manually widening on your own undermines the point of the rule.
- **The `market_below_21ema_or_50ma=None` case is real.** During the first 50 sessions of an IPO or a thinly-traded index, the 50SMA filter is unavailable. The skill correctly returns `None` and skips SEVERE escalation rather than guessing.
- **Combine with FTD Detector for full state.** Distribution Days warn you to defend; Follow-Through Days clear you to attack. Running both is the simplest two-pole framework for major-index timing.

---

## 8. Combining with Other Skills

| Workflow | How to Combine |
|----------|---------------|
| **Daily exposure review** | Run IBD Distribution Day Monitor for the risk level, then Market Breadth Analyzer for confirmation. Disagreement (e.g., DD HIGH but breadth Strong) deserves extra investigation |
| **Bottom-confirmation pair** | After a SEVERE → drawdown → recovery, run FTD Detector starting from the lowest close. The FTD signal counter-balances the distribution warning |
| **Position sizing** | Pass the trailing stop recommendation into Position Sizer for the leveraged ETF; tighter stops translate directly into smaller shares |
| **Top probability composite** | Feed the `risk_level` into Market Top Detector as one of multiple top-side inputs. Distribution clustering is one of six O'Neil tops components |
| **Backtest validation** | Loop `--as-of` over historical dates and feed the JSON results into Backtest Expert to evaluate whether the threshold + exposure policy improved drawdown vs buy-and-hold |
| **Kanchi-style dividend portfolio** | Use the risk level as an overlay: do not add to TQQQ in HIGH/SEVERE, but Kanchi-style dividend adds can continue if individual thesis-level T1-T5 triggers are clean |

---

## 9. Troubleshooting

### `FMP API key required` error

**Cause:** None of `--api-key`, `config.data.api_key`, or `FMP_API_KEY` env var is set.

**Fix:** Set `export FMP_API_KEY=your_key_here` in your shell, or pass `--api-key your_key_here` on the command line. The skill never reads the key from disk except via the explicit config path.

### `as_of YYYY-MM-DD not found in loaded history`

**Cause:** The date you passed is not a trading session in FMP's data, or it is older than `lookback_days` allows.

**Fix:** Verify the date is a US market session (no weekends, no holidays), then increase `--lookback-days` to ensure the date is within the loaded window. For dates more than 80 sessions back, set `--lookback-days 200` or more.

### `insufficient_lookback` audit flag

**Cause:** After `as_of` slicing, the remaining history has fewer rows than `required_min_sessions = max(lookback, 50, expiration_sessions + 2)`.

**Fix:** Increase `--lookback-days` so that the slice still has enough sessions. The analysis still runs, but the 50SMA may be `None` and SEVERE escalation will be skipped.

### `insufficient_data_for_moving_average` audit flag

**Cause:** Loaded history has fewer than 21 closes (for 21EMA) or 50 closes (for 50SMA).

**Fix:** Increase `--lookback-days` to at least 80. If you intentionally want shorter history, accept that SEVERE will only trigger via `d25 >= 6` or `d15 >= 4`, never via the MA condition.

### Risk level says HIGH but the headlines look fine

**Cause:** Distribution clusters often precede headline-driving sell-offs by days or weeks. Mid-2007, late-2021, and early-2022 all had HIGH-state DD counts before the actual collapse made headlines.

**Fix:** This is the intended behavior — leading indicators feel premature until they look obvious. Trust the rule, tighten the stop, avoid new adds. If you want to see why the level is HIGH, inspect the active DD table in the Markdown report.

### Recommended trailing stop is wider than my actual stop

**Cause:** The skill returns `min(your_base, policy_cap)`. If you passed `--base-trailing-stop 4` and the policy cap for HIGH is 5%, the recommendation correctly stays at 4%.

**Fix:** None — this is the intended behavior. The skill never widens an existing tighter stop.

---

## 10. Reference

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--symbols` | No | `QQQ,SPY` (from config) | Comma-separated symbols |
| `--lookback-days` | No | `80` | Trading sessions to load |
| `--instrument` | No | `TQQQ` (from config) | `TQQQ` or `QQQ` (controls exposure policy) |
| `--current-exposure` | No | `100` (from config) | Current exposure as integer percent |
| `--base-trailing-stop` | No | `10` (from config) | Base trailing-stop percent (skill never widens it) |
| `--as-of` | No | latest session | `YYYY-MM-DD` for backtest evaluation |
| `--config` | No | `config/default.yaml` | Custom YAML override path |
| `--api-key` | No | `FMP_API_KEY` env var | FMP API key |
| `--output-dir` | No | `reports/` | Output directory for JSON + MD pair |

### Default Configuration (`config/default.yaml`)

| Section | Key | Default |
|---------|-----|---------|
| `distribution_day_rule` | `min_decline_pct` | `-0.002` |
| `distribution_day_rule` | `expiration_sessions` | `25` |
| `distribution_day_rule` | `invalidation_gain_pct` | `0.05` |
| `distribution_day_rule` | `invalidation_price_source` | `high` |
| `risk_thresholds.caution` | `d25_count` | `3` |
| `risk_thresholds.high` | `d25_count` / `d15_count` / `d5_count` | `5 / 3 / 2` |
| `risk_thresholds.severe` | `d25_count` / `d15_count` / `severe_ma_d25` | `6 / 4 / 5` |
| `moving_average_filters` | `ema_periods` | `[21]` |
| `moving_average_filters` | `sma_periods` | `[50]` |
| `strategy_context` | `instrument` | `TQQQ` |
| `strategy_context` | `current_exposure_pct` | `100` |
| `strategy_context` | `base_trailing_stop_pct` | `10` |

### TQQQ vs QQQ Exposure Policy

| Risk | TQQQ Action | TQQQ Target | TQQQ Trail Cap | QQQ Action | QQQ Target | QQQ Trail Cap |
|------|-------------|-------------|----------------|-----------|------------|---------------|
| NORMAL | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base |
| CAUTION | AVOID_NEW_ADDS | 75% | 7% | AVOID_NEW_ADDS | 100% | 8% |
| HIGH | REDUCE_EXPOSURE | 50% | 5% | REDUCE_EXPOSURE | 75% | 6% |
| SEVERE | CLOSE_TQQQ_OR_HEDGE | 25% | 3% | REDUCE_EXPOSURE_OR_HEDGE | 50% | 5% |

### Output Files

| File | Description |
|------|-------------|
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json` | Full structured report (UTF-8, `ensure_ascii=False`, secrets redacted) |
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.md` | Human-readable summary + active DD table |
