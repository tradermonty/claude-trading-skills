---
layout: default
title: "Ibd Distribution Day Monitor"
grand_parent: English
parent: Skill Guides
nav_order: 32
lang_peer: /ja/skills/ibd-distribution-day-monitor/
permalink: /en/skills/ibd-distribution-day-monitor/
---

# Ibd Distribution Day Monitor
{: .no_toc }

Detect IBD-style Distribution Days for QQQ/SPY (close down at least 0.2% on higher volume), track 25-session expiration and 5% invalidation, count d5/d15/d25 clusters, classify market risk (NORMAL/CAUTION/HIGH/SEVERE), and emit TQQQ/QQQ exposure recommendations. Use after market close, before TQQQ exposure changes, or as input to FTD/market-state frameworks. Does not execute trades.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

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

# IBD Distribution Day Monitor

---

## 2. When to Use

Invoke this skill:
- Daily after the US market close.
- Before increasing TQQQ exposure or rebalancing leveraged positions.
- When evaluating whether an uptrend is becoming vulnerable to a correction.
- As an upstream input to FTD (Follow-Through Day) detection or other market-state frameworks.

Do NOT use this skill to:
- Execute trades or modify orders.
- Generate discretionary market predictions outside of the IBD ruleset.

---

## 3. Prerequisites

- **FMP API key** required (`FMP_API_KEY` environment variable)
- Financial Modeling Prep API
- Python 3.9+ recommended

---

## 4. Quick Start

1. Load OHLCV for the configured symbols via FMP (`get_historical_prices`).
2. Validate data quality; record skipped sessions in audit.
3. Rebase via `prepare_effective_history` so `effective_history[0]` is the evaluation session.
4. Detect raw Distribution Days; enrich with `high_since`, invalidation event, and status.
5. Count `d5` / `d15` / `d25` active records.
6. Compute 21EMA and 50SMA filters; flag `market_below_21ema_or_50ma` (None if data insufficient).
7. Classify each index, then combine using QQQ-weighted policy.
8. Generate portfolio action for the configured instrument.
9. Write JSON + Markdown reports to `--output-dir` with API keys redacted.

---

## 5. Workflow

1. Load OHLCV for the configured symbols via FMP (`get_historical_prices`).
2. Validate data quality; record skipped sessions in audit.
3. Rebase via `prepare_effective_history` so `effective_history[0]` is the evaluation session.
4. Detect raw Distribution Days; enrich with `high_since`, invalidation event, and status.
5. Count `d5` / `d15` / `d25` active records.
6. Compute 21EMA and 50SMA filters; flag `market_below_21ema_or_50ma` (None if data insufficient).
7. Classify each index, then combine using QQQ-weighted policy.
8. Generate portfolio action for the configured instrument.
9. Write JSON + Markdown reports to `--output-dir` with API keys redacted.

---

## 6. Resources

**References:**

- `skills/ibd-distribution-day-monitor/references/ibd_distribution_methodology.md`
- `skills/ibd-distribution-day-monitor/references/tqqq_exposure_policy.md`

**Scripts:**

- `skills/ibd-distribution-day-monitor/scripts/data_loader.py`
- `skills/ibd-distribution-day-monitor/scripts/distribution_day_tracker.py`
- `skills/ibd-distribution-day-monitor/scripts/exposure_policy.py`
- `skills/ibd-distribution-day-monitor/scripts/fmp_client.py`
- `skills/ibd-distribution-day-monitor/scripts/history_utils.py`
- `skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py`
- `skills/ibd-distribution-day-monitor/scripts/math_utils.py`
- `skills/ibd-distribution-day-monitor/scripts/models.py`
- `skills/ibd-distribution-day-monitor/scripts/report_generator.py`
- `skills/ibd-distribution-day-monitor/scripts/risk_classifier.py`
