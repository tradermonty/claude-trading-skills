---
layout: default
title: "Residual Edge Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 51
lang_peer: /ja/skills/residual-edge-analyzer/
permalink: /en/skills/residual-edge-analyzer/
generated: true
---

# Residual Edge Analyzer
{: .no_toc }

Separate a strategy return series into declared baseline exposure and residual edge with returns-based OLS attribution, HAC inference, rolling stability, alternate-baseline sensitivity, and regime breakdowns. Use when evaluating whether backtest, out-of-sample, or live returns contain independent alpha beyond market, equal-weight, momentum, sector, or user-supplied factor returns; when explaining whether a drawdown came from baseline exposure or strategy-specific behavior; or when a strategy needs an attribution quality gate after backtesting. Do not use for holdings-based Brinson attribution, feature-level Shapley explanations, or analysis from summary metrics without a dated return series.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/residual-edge-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/residual-edge-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Test whether a strategy's apparent performance survives explicit comparison with
predeclared baseline return series. Produce an auditable JSON artifact and a concise
Markdown report without fetching data or changing trading exposure.

Treat this as a falsification gate after `backtest-expert`, not as trade authorization.

---

## 2. Prerequisites

- Use Python 3.9+.
- Prepare one CSV containing an ISO date, strategy return, and every baseline return on
  the same row.
- Prepare a JSON specification following
  [references/input-contract.md](references/input-contract.md).
- Supply actual period returns. Do not substitute CAGR, Sharpe, cumulative P&L, or other
  summary metrics.

---

## 3. Quick Start

```bash
python3 skills/residual-edge-analyzer/scripts/analyze_residual_edge.py \
  --input reports/strategy_returns.csv \
  --config reports/residual_edge_config.json \
  --output-json reports/residual_edge_report.json \
  --output-markdown reports/residual_edge_report.md
```

---

## 4. Workflow

### 1. Define the question before inspecting results

State the claimed independent edge in one sentence. Select a primary baseline that is a
plausible simple copy of the strategy, then select at least one alternate baseline model.

Record these declarations in the config:

- `baseline_selection: predeclared`
- `strategy_return_basis` and `baseline_return_basis`: both `gross` or both `net`
- `analysis_scope`: `out_of_sample`, `live`, or `in_sample`
- `universe_data`: `point_in_time`, `current_constituents`, or `not_applicable`

Every declaration is mandatory for a decision-grade verdict. Omitting one is treated as
undeclared, not as benign, and drops the report to `REVIEW_REQUIRED`. `not_applicable`
exists so that a baseline with no universe membership can be declared explicitly rather
than left blank.

Do not choose a baseline because it gives the preferred residual result.

### 2. Validate the return-series contract

Require:

- unique ISO dates;
- finite numeric returns greater than -100%;
- identical frequency and cost basis across strategy and baselines;
- point-in-time membership for same-universe equal-weight or momentum baselines;
- regime labels defined independently of the loss periods being explained.

Stop if the input lacks a dated strategy return series. Report summary-only input as
insufficient rather than inventing observations.

### 3. Run the analyzer

```bash
python3 skills/residual-edge-analyzer/scripts/analyze_residual_edge.py \
  --input reports/strategy_returns.csv \
  --config reports/residual_edge_config.json \
  --output-json reports/residual_edge_report.json \
  --output-markdown reports/residual_edge_report.md
```

The script runs the predeclared primary model and all sensitivity models in one execution.
It uses an intercept OLS model and HAC/Newey-West standard errors. It reports the residual
edge ratio as annualized alpha divided by annualized residual volatility; do not calculate
a Sharpe ratio from raw OLS residual mean because an intercept makes that mean zero.

### 4. Interpret the evidence

Use the four statuses as diagnostic labels:

- `RESIDUAL_EDGE`: alpha, residual edge ratio, and rolling stability clear configured
  thresholds.
- `BASELINE_EXPLAINED`: baseline R-squared is high while residual evidence is weak.
- `RESIDUAL_FRAGILE`: results fail one or more robustness gates or change across declared
  baseline models. Also use this status when rolling analysis is disabled, unavailable,
  incomplete, or no sensitivity model was supplied.
- `INSUFFICIENT_EVIDENCE`: the sample is below the configured minimum.

Read `decision_eligibility` separately. A statistically interesting result remains
`REVIEW_REQUIRED` when critical provenance, cost-basis, sample, or multicollinearity
warnings exist, when rolling evidence is unavailable, or when no alternate baseline was
tested.

Inspect:

1. primary and sensitivity-model status;
2. annualized alpha and HAC t-stat;
3. residual edge ratio and residual autocorrelation;
4. rolling alpha stability;
5. VIF for multi-factor models;
6. active-return breakdown across predeclared regimes.

### 5. Hand off findings

- Send baseline-choice, OOS, and stability findings back to `backtest-expert`.
- Send recurring residual failure regimes to `signal-postmortem`.
- Pass only evidence and operating constraints to `trade-performance-coach`.
- Never change position size, exposure, or orders automatically.

---

## 5. Resources

**References:**

- `skills/residual-edge-analyzer/references/input-contract.md`
- `skills/residual-edge-analyzer/references/methodology.md`

**Scripts:**

- `skills/residual-edge-analyzer/scripts/analyze_residual_edge.py`
