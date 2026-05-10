---
layout: default
title: ワークフロー
parent: 日本語
nav_order: 4
lang_peer: /en/workflows/
permalink: /ja/workflows/
---

# ワークフロー
{: .no_toc }

> _このページは `scripts/generate_workflow_docs.py` によって自動生成されます。手動編集しないでください。_

個人トレーダー OS の運用ワークフロー manifest 群です。各ワークフローは使用するスキル・判断ゲート・artifact の流れを順番通りに記述しています。[`workflows/`](https://github.com/tradermonty/claude-trading-skills/tree/main/workflows) 以下の manifest が正本で、本ページはそこから自動生成されます。

---

## ワークフロー一覧

| ワークフロー | 頻度 | 目安(分) | API プロファイル | 難易度 |
|---|---|---|---|---|
| [`core-portfolio-weekly`](#core-portfolio-weekly) — Core Portfolio Weekly | weekly | 60 | mixed | beginner |
| [`market-regime-daily`](#market-regime-daily) — Market Regime Daily | daily | 15 | no-api-basic | beginner |
| [`monthly-performance-review`](#monthly-performance-review) — Monthly Performance Review | monthly | 90 | no-api-basic | intermediate |
| [`swing-opportunity-daily`](#swing-opportunity-daily) — Swing Opportunity Daily | daily | 30 | fmp-required | intermediate |
| [`trade-memory-loop`](#trade-memory-loop) — Trade Memory Loop | ad-hoc | 30 | no-api-basic | beginner |

---

## Core Portfolio Weekly {#core-portfolio-weekly}

**`core-portfolio-weekly`** · weekly · ~60 min · mixed · beginner

**実行タイミング:** Once per week, typically on Saturday or Sunday before next week's market open. Reviews long-term holdings, dividend positions, and overall allocation.

**実行してはいけないとき:** Do not run as a daily routine. Daily portfolio churn defeats the long-term framing of this workflow.

**必須スキル:** `portfolio-manager`, `trader-memory-core`

**任意スキル:** `kanchi-dividend-review-monitor`, `value-dividend-screener`, `kanchi-dividend-us-tax-accounting`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `holdings_snapshot` | 1 | あり | `monthly-performance-review` |
| `allocation_report` | 2 | あり | — |
| `dividend_review_findings` | 3 | なし | — |
| `rebalance_actions` | 4 | あり | — |
| `weekly_journal_entry` | 5 | あり | — |

**ステップ:**

**ステップ 1: Fetch holdings snapshot** → `portfolio-manager`

- produces: `holdings_snapshot`

**ステップ 2: Review allocation and concentration** （判断ゲート） → `portfolio-manager`

- consumes: `holdings_snapshot`
- produces: `allocation_report`
- **判断:** Are sector and single-name concentrations within target bands? If not, what specific reallocation does the trader propose?

**ステップ 3: Check dividend health (T1-T5 anomaly check)** （任意） → `kanchi-dividend-review-monitor`

- consumes: `holdings_snapshot`
- produces: `dividend_review_findings`

**ステップ 4: Decide rebalance actions** （判断ゲート） → `portfolio-manager`

- consumes: `allocation_report`, `dividend_review_findings`
- produces: `rebalance_actions`
- **判断:** Which rebalance actions (if any) will be executed next week? Confirm explicit buy / sell / hold list with sizing.

**ステップ 5: Journal the weekly review** → `trader-memory-core`

- consumes: `rebalance_actions`
- produces: `weekly_journal_entry`

**手動レビュー:**

- Confirm holdings snapshot reflects the actual brokerage state (Alpaca or CSV).
- Confirm rebalance actions are entered manually at the broker, not auto-executed.
- If dividend_review_findings flags T1-T5 issues, defer additional buys until resolved.

**Journal 出力先:** `trader-memory-core`

---

## Market Regime Daily {#market-regime-daily}

**`market-regime-daily`** · daily · ~15 min · no-api-basic · beginner

**実行タイミング:** Before considering new swing-trade risk for the day. Run before market open or in the first 30 minutes after.

**実行してはいけないとき:** Do not use this output as a standalone buy/sell signal. The exposure_decision is a posture (allow / restrict / cash-priority), not a directive.

**必須スキル:** `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach`

**任意スキル:** `market-top-detector`, `macro-regime-detector`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `market_breadth_report` | 1 | あり | `swing-opportunity-daily`, `monthly-performance-review` |
| `uptrend_report` | 2 | あり | — |
| `top_risk_report` | 3 | なし | — |
| `exposure_decision` | 4 | あり | `swing-opportunity-daily` |

**ステップ:**

**ステップ 1: Analyze market breadth** → `market-breadth-analyzer`

- produces: `market_breadth_report`

**ステップ 2: Analyze uptrend participation** → `uptrend-analyzer`

- produces: `uptrend_report`

**ステップ 3: Check market top risk** （任意） → `market-top-detector`

- produces: `top_risk_report`

**ステップ 4: Decide exposure posture** （判断ゲート） → `exposure-coach`

- consumes: `market_breadth_report`, `uptrend_report`, `top_risk_report`
- produces: `exposure_decision`
- **判断:** Given today's breadth, uptrend participation, and top risk, is new swing trade risk allowed, restricted, or cash-priority?

**手動レビュー:**

- Confirm output is not used as a buy/sell signal.
- Confirm whether exposure should be reduced, unchanged, or increased.
- If exposure_decision is restrictive, defer running swing-opportunity-daily.

**Journal 出力先:** `trader-memory-core`

---

## Monthly Performance Review {#monthly-performance-review}

**`monthly-performance-review`** · monthly · ~90 min · no-api-basic · intermediate

**実行タイミング:** First weekend of each month, reviewing the prior month's closed positions, open thesis health, and process improvements. Closes the Plan -> Trade -> Record -> Review -> Improve loop.

**実行してはいけないとき:** Do not skip this review even in losing months — that is when it matters most. Do not run weekly; the monthly cadence is intentional to filter noise.

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**任意スキル:** `backtest-expert`, `dual-axis-skill-reviewer`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `monthly_aggregate` | 1 | あり | — |
| `aggregate_postmortem` | 2 | あり | — |
| `hypothesis_revalidation` | 3 | なし | — |
| `skill_review_findings` | 4 | なし | — |
| `monthly_decision_log` | 5 | あり | — |
| `rule_changes_for_next_month` | 5 | あり | — |
| `skill_improvement_backlog` | 5 | なし | — |

**ステップ:**

**ステップ 1: Aggregate the month's trades and theses** → `trader-memory-core`

- produces: `monthly_aggregate`

**ステップ 2: Pattern-level postmortem across the month** （判断ゲート） → `signal-postmortem`

- consumes: `monthly_aggregate`
- produces: `aggregate_postmortem`
- **判断:** What recurring patterns appear across the month's outcomes? Classify by thesis quality, execution, market environment, and randomness.

**ステップ 3: Re-validate hypotheses via backtest** （任意） → `backtest-expert`

- consumes: `aggregate_postmortem`
- produces: `hypothesis_revalidation`

**ステップ 4: Review which skills helped or hurt** （任意） → `dual-axis-skill-reviewer`

- consumes: `aggregate_postmortem`
- produces: `skill_review_findings`

**ステップ 5: Produce decision log and rule changes** （判断ゲート） → `trader-memory-core`

- consumes: `aggregate_postmortem`, `hypothesis_revalidation`, `skill_review_findings`
- produces: `monthly_decision_log`, `rule_changes_for_next_month`, `skill_improvement_backlog`
- **判断:** Based on this month's evidence, what specific rules will change next month? Trade-side rules vs repo-side improvements should stay separate.

**手動レビュー:**

- Distinguish process improvements (rule changes) from outcome accidents (randomness).
- Trade-side rule changes apply to the trader's behavior next month.
- Skill-side improvements are repo-improvement candidates and may or may not be acted on.
- Be willing to delete or downgrade rules that aren't working — not just add new ones.

**最終出力:**

- `monthly_decision_log` — What trades worked / what did not, by category
- `rule_changes_for_next_month` — Adjustments to position sizing, entry rules, regime gates
- `skill_improvement_backlog` — Optional feedback into repo improvement loop (skills / workflows)

**Journal 出力先:** `trader-memory-core`

---

## Swing Opportunity Daily {#swing-opportunity-daily}

**`swing-opportunity-daily`** · daily · ~30 min · fmp-required · intermediate

**実行タイミング:** Only after market-regime-daily has produced a non-restrictive exposure decision. Identifies swing trade candidates and builds entry plans.

**実行してはいけないとき:** Do not run when the latest market-regime-daily exposure_decision is cash-priority or restrictive. Do not use as a standalone screener without the regime gate.

**必須スキル:** `vcp-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**任意スキル:** `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — New swing trade risk requires a non-restrictive exposure decision. Skip this workflow on cash-priority or restrictive days.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `vcp_candidates` | 1 | あり | — |
| `canslim_candidates` | 2 | なし | — |
| `theme_candidates` | 3 | なし | — |
| `validated_setups` | 4 | あり | — |
| `position_sizing` | 5 | あり | — |
| `trade_plans` | 6 | なし | `trade-memory-loop` |
| `candidate_journal_entry` | 7 | あり | `trade-memory-loop` |

**ステップ:**

**ステップ 1: Run VCP screener** → `vcp-screener`

- produces: `vcp_candidates`

**ステップ 2: Run CANSLIM screener** （任意） → `canslim-screener`

- produces: `canslim_candidates`

**ステップ 3: Theme detection cross-check** （任意） → `theme-detector`

- produces: `theme_candidates`

**ステップ 4: Validate setups on weekly chart** （判断ゲート） → `technical-analyst`

- consumes: `vcp_candidates`, `canslim_candidates`, `theme_candidates`
- produces: `validated_setups`
- **判断:** Which candidates have a clean weekly setup (Stage 2 uptrend, tight base) and pass the manual chart review? Reject candidates that don't.

**ステップ 5: Calculate position size** → `position-sizer`

- consumes: `validated_setups`
- produces: `position_sizing`

**ステップ 6: Build entry plan** （任意） → `breakout-trade-planner`

- consumes: `validated_setups`, `position_sizing`
- produces: `trade_plans`

**ステップ 7: Register thesis in journal** （判断ゲート） → `trader-memory-core`

- consumes: `position_sizing`, `trade_plans`
- produces: `candidate_journal_entry`
- **判断:** For each candidate that survived validation, register the thesis with entry / stop / target. Confirm risk per trade matches position-sizer output and total portfolio heat is within budget.

**手動レビュー:**

- Confirm market-regime-daily exposure_decision allows new risk before acting.
- Reject any candidate where weekly setup is unclear, even if screener passed.
- Verify total portfolio heat is within budget before placing any order.
- All orders are placed manually at the broker; no auto-execution.

**Journal 出力先:** `trader-memory-core`

---

## Trade Memory Loop {#trade-memory-loop}

**`trade-memory-loop`** · ad-hoc · ~30 min · no-api-basic · beginner

**実行タイミング:** Every time a position is closed (full or partial exit). Records the outcome, generates a postmortem, and (optionally) re-validates the original hypothesis via backtest.

**実行してはいけないとき:** Do not run before a position is closed — use trader-memory-core directly to update an open thesis instead. Do not skip this loop after a closed trade, even on winners.

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**任意スキル:** `backtest-expert`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `closed_thesis_record` | 1 | あり | — |
| `postmortem_findings` | 2 | あり | `monthly-performance-review` |
| `backtest_validation` | 3 | なし | — |
| `lessons_log_entry` | 4 | あり | `monthly-performance-review` |

**ステップ:**

**ステップ 1: Record closed trade outcome** → `trader-memory-core`

- produces: `closed_thesis_record`

**ステップ 2: Generate postmortem** （判断ゲート） → `signal-postmortem`

- consumes: `closed_thesis_record`
- produces: `postmortem_findings`
- **判断:** What was the root cause of the outcome — thesis quality, execution, market environment, or randomness? Classify and document.

**ステップ 3: Re-validate hypothesis via backtest** （任意） → `backtest-expert`

- consumes: `postmortem_findings`
- produces: `backtest_validation`

**ステップ 4: Append lessons to journal** → `trader-memory-core`

- consumes: `postmortem_findings`, `backtest_validation`
- produces: `lessons_log_entry`

**手動レビュー:**

- Be honest about whether the win was thesis-driven or lucky.
- Be honest about whether the loss was thesis-flawed or executed poorly.
- Don't rationalize randomness as either skill or failure.

**Journal 出力先:** `trader-memory-core`

---
