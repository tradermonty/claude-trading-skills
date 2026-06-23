---
layout: default
title: 工作流
parent: 简体中文
nav_order: 4
lang_peer: /en/workflows/
permalink: /zh/workflows/
---

# 工作流
{: .no_toc }

> _本页由 `scripts/generate_workflow_docs.py` 自动生成。请勿手动编辑。_

面向个人交易者 OS 的运营工作流 manifest 群。每条工作流按顺序列出所用技能、判断关卡与 artifact。[`workflows/`](https://github.com/tradermonty/claude-trading-skills/tree/main/workflows) 下的 manifest 为正本，本页由其自动生成。

**翻译方针：** 本页仅将标题标签中文化。manifest 正文（`when_to_run` / `decision_question` / `manual_review` 等）按英文正本原样显示。正文的中文化为后续计划（拟在 manifest 中增加 `*_zh` 字段，或设置单独的本地化层）。

---

## 工作流一览

| 工作流 | 频率 | 预计(分) | API 配置 | 难度 |
|---|---|---|---|---|
| [`core-portfolio-weekly`](#core-portfolio-weekly) — Core Portfolio Weekly | weekly | 60 | mixed | beginner |
| [`market-regime-daily`](#market-regime-daily) — Market Regime Daily | daily | 15 | no-api-basic | beginner |
| [`monthly-performance-review`](#monthly-performance-review) — Monthly Performance Review | monthly | 90 | no-api-basic | intermediate |
| [`multi-asset-opportunity-daily`](#multi-asset-opportunity-daily) — Multi-Asset Opportunity Daily | daily | 45 | mixed | intermediate |
| [`swing-opportunity-daily`](#swing-opportunity-daily) — Swing Opportunity Daily | daily | 35 | fmp-required | intermediate |
| [`trade-memory-loop`](#trade-memory-loop) — Trade Memory Loop | ad-hoc | 30 | no-api-basic | beginner |

---

## Core Portfolio Weekly {#core-portfolio-weekly}

**`core-portfolio-weekly`** · weekly · ~60 min · mixed · beginner

**何时运行:** Once per week, typically on Saturday or Sunday before next week's market open. Reviews long-term holdings, dividend positions, and overall allocation.

**何时不要运行:** Do not run as a daily routine. Daily portfolio churn defeats the long-term framing of this workflow.

**必需技能:** `portfolio-manager`, `trader-memory-core`

**可选技能:** `kanchi-dividend-review-monitor`, `value-dividend-screener`, `kanchi-dividend-us-tax-accounting`

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `holdings_snapshot` | 1 | 是 | `monthly-performance-review` |
| `allocation_report` | 2 | 是 | — |
| `dividend_review_findings` | 3 | 否 | — |
| `rebalance_actions` | 4 | 是 | — |
| `weekly_journal_entry` | 5 | 是 | — |

**步骤:**

**步骤 1: Fetch holdings snapshot** → `portfolio-manager`

- produces: `holdings_snapshot`

**步骤 2: Review allocation and concentration** （判断关卡） → `portfolio-manager`

- consumes: `holdings_snapshot`
- produces: `allocation_report`
- **判断:** Are sector and single-name concentrations within target bands? If not, what specific reallocation does the trader propose?

**步骤 3: Check dividend health (T1-T5 anomaly check)** （可选） → `kanchi-dividend-review-monitor`

- consumes: `holdings_snapshot`
- produces: `dividend_review_findings`

**步骤 4: Decide rebalance actions** （判断关卡） → `portfolio-manager`

- consumes: `allocation_report`, `dividend_review_findings`
- produces: `rebalance_actions`
- **判断:** Which rebalance actions (if any) will be executed next week? Confirm explicit buy / sell / hold list with sizing.

**步骤 5: Journal the weekly review** → `trader-memory-core`

- consumes: `rebalance_actions`
- produces: `weekly_journal_entry`

**人工复核:**

- Confirm holdings snapshot reflects the actual brokerage state (Alpaca or CSV).
- Confirm rebalance actions are entered manually at the broker, not auto-executed.
- If dividend_review_findings flags T1-T5 issues, defer additional buys until resolved.

**Journal 输出位置:** `trader-memory-core`

---

## Market Regime Daily {#market-regime-daily}

**`market-regime-daily`** · daily · ~15 min · no-api-basic · beginner

**何时运行:** Before considering new swing-trade risk for the day. Run before market open or in the first 30 minutes after.

**何时不要运行:** Do not use this output as a standalone buy/sell signal. The exposure_decision is a posture (allow / restrict / cash-priority), not a directive.

**必需技能:** `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach`

**可选技能:** `market-top-detector`, `macro-regime-detector`

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `market_breadth_report` | 1 | 是 | `swing-opportunity-daily`, `monthly-performance-review` |
| `uptrend_report` | 2 | 是 | — |
| `top_risk_report` | 3 | 否 | — |
| `exposure_decision` | 4 | 是 | `swing-opportunity-daily` |

**步骤:**

**步骤 1: Analyze market breadth** → `market-breadth-analyzer`

- produces: `market_breadth_report`

**步骤 2: Analyze uptrend participation** → `uptrend-analyzer`

- produces: `uptrend_report`

**步骤 3: Check market top risk** （可选） → `market-top-detector`

- produces: `top_risk_report`

**步骤 4: Decide exposure posture** （判断关卡） → `exposure-coach`

- consumes: `market_breadth_report`, `uptrend_report`, `top_risk_report`
- produces: `exposure_decision`
- **判断:** Given today's breadth, uptrend participation, and top risk, is new swing trade risk allowed, restricted, or cash-priority?

**人工复核:**

- Confirm output is not used as a buy/sell signal.
- Confirm whether exposure should be reduced, unchanged, or increased.
- If exposure_decision is restrictive, defer running swing-opportunity-daily.

**Journal 输出位置:** `trader-memory-core`

---

## Monthly Performance Review {#monthly-performance-review}

**`monthly-performance-review`** · monthly · ~90 min · no-api-basic · intermediate

**何时运行:** First weekend of each month, reviewing the prior month's closed positions, open thesis health, and process improvements. Closes the Plan -> Trade -> Record -> Review -> Improve loop.

**何时不要运行:** Do not skip this review even in losing months — that is when it matters most. Do not run weekly; the monthly cadence is intentional to filter noise.

**必需技能:** `trader-memory-core`, `signal-postmortem`

**可选技能:** `trade-performance-coach`, `backtest-expert`, `dual-axis-skill-reviewer`

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `monthly_aggregate` | 1 | 是 | — |
| `aggregate_postmortem` | 2 | 是 | — |
| `monthly_performance_coach_report` | 3 | 否 | — |
| `monthly_behavior_patterns` | 3 | 否 | — |
| `next_month_operating_rules` | 3 | 否 | — |
| `hypothesis_revalidation` | 4 | 否 | — |
| `skill_review_findings` | 5 | 否 | — |
| `monthly_decision_log` | 6 | 是 | — |
| `rule_changes_for_next_month` | 6 | 是 | — |
| `skill_improvement_backlog` | 6 | 否 | — |

**步骤:**

**步骤 1: Aggregate the month's trades and theses** → `trader-memory-core`

- produces: `monthly_aggregate`

**步骤 2: Pattern-level postmortem across the month** （判断关卡） → `signal-postmortem`

- consumes: `monthly_aggregate`
- produces: `aggregate_postmortem`
- **判断:** What recurring patterns appear across the month's outcomes? Classify by thesis quality, execution, market environment, and randomness.

**步骤 3: Coach monthly process, risk, and behavior patterns** （可选） （判断关卡） → `trade-performance-coach`

- consumes: `monthly_aggregate`, `aggregate_postmortem`
- produces: `monthly_performance_coach_report`, `monthly_behavior_patterns`, `next_month_operating_rules`
- **判断:** Which next-month operating rules should be accepted, modified, deferred, or journaled only?

**步骤 4: Re-validate hypotheses via backtest** （可选） → `backtest-expert`

- consumes: `aggregate_postmortem`
- produces: `hypothesis_revalidation`

**步骤 5: Review which skills helped or hurt** （可选） → `dual-axis-skill-reviewer`

- consumes: `aggregate_postmortem`
- produces: `skill_review_findings`

**步骤 6: Produce decision log and rule changes** （判断关卡） → `trader-memory-core`

- consumes: `aggregate_postmortem`, `hypothesis_revalidation`, `skill_review_findings`
- produces: `monthly_decision_log`, `rule_changes_for_next_month`, `skill_improvement_backlog`
- **判断:** Based on this month's evidence, what specific rules will change next month? Trade-side rules vs repo-side improvements should stay separate.

**人工复核:**

- Distinguish process improvements (rule changes) from outcome accidents (randomness).
- Trade-side rule changes apply to the trader's behavior next month.
- Skill-side improvements are repo-improvement candidates and may or may not be acted on.
- Be willing to delete or downgrade rules that aren't working — not just add new ones.

**最终输出:**

- `monthly_decision_log` — What trades worked / what did not, by category
- `rule_changes_for_next_month` — Adjustments to position sizing, entry rules, regime gates
- `skill_improvement_backlog` — Optional feedback into repo improvement loop (skills / workflows)

**Journal 输出位置:** `trader-memory-core`

---

## Multi-Asset Opportunity Daily {#multi-asset-opportunity-daily}

**`multi-asset-opportunity-daily`** · daily · ~45 min · mixed · intermediate

**何时运行:** Only after market-regime-daily has produced a non-restrictive exposure decision. Sweeps macro + themes + news to surface multi-asset ideas (equities, commodities-via-equity-proxies, options expressions) and synthesizes them into ranked hypothesis cards.

**何时不要运行:** Do not run when the latest market-regime-daily exposure_decision is cash-priority. Do not treat hypothesis cards as buy/sell signals — they carry manual_review_required and must pass human sign-off before any capital moves. Forex output is research-only; never feed it into a broker.

**必需技能:** `macro-regime-detector`, `theme-detector`, `trade-hypothesis-ideator`, `position-sizer`, `trader-memory-core`

**可选技能:** `market-news-analyst`, `market-environment-analysis`, `sector-analyst`, `scenario-analyzer`, `stanley-druckenmiller-investment`

**前置工作流（informational）:**

- `market-regime-daily` 所需的 artifact `exposure_decision` — Multi-asset opportunity scanning requires a non-restrictive exposure posture. Skip on cash-priority days; reduce scope on restrict days.

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `macro_regime_brief` | 1 | 是 | `swing-opportunity-daily`, `monthly-performance-review` |
| `hot_themes` | 2 | 是 | `swing-opportunity-daily` |
| `catalyst_news_brief` | 3 | 否 | — |
| `hypothesis_cards` | 4 | 是 | `swing-opportunity-daily`, `trade-memory-loop` |
| `sized_hypotheses` | 5 | 是 | — |
| `opportunity_journal_entries` | 6 | 是 | `trade-memory-loop`, `monthly-performance-review` |

**步骤:**

**步骤 1: Refresh macro regime context** → `macro-regime-detector`

- produces: `macro_regime_brief`

**步骤 2: Detect hot themes + sector rotation** → `theme-detector`

- consumes: `macro_regime_brief`
- produces: `hot_themes`

**步骤 3: Scan news + catalyst landscape** （可选） → `market-news-analyst`

- consumes: `hot_themes`
- produces: `catalyst_news_brief`

**步骤 4: Synthesize ranked hypothesis cards** （判断关卡） → `trade-hypothesis-ideator`

- consumes: `macro_regime_brief`, `hot_themes`, `catalyst_news_brief`
- produces: `hypothesis_cards`
- **判断:** For each hypothesis, does layer 1 (macro) align with layer 2 (theme) and is what-is-priced-in still favorable? Reject any card where the gap to consensus is unclear or already closed.

**步骤 5: Apply risk-based sizing to hypothesis cards** → `position-sizer`

- consumes: `hypothesis_cards`
- produces: `sized_hypotheses`

**步骤 6: Persist as IDEA / ENTRY_READY entries** （判断关卡） → `trader-memory-core`

- consumes: `hypothesis_cards`, `sized_hypotheses`
- produces: `opportunity_journal_entries`
- **判断:** Which hypotheses should be promoted from IDEA to ENTRY_READY, which stay as IDEA pending more confirmation, and which are rejected?

**人工复核:**

- Confirm the regime brief does not contradict the exposure_decision from market-regime-daily.
- Confirm each hypothesis has a written thesis AND a kill criterion.
- Confirm position sizing respects portfolio risk caps (per-position and per-sector).
- For forex-related output, confirm research_only=true; never wire to a broker.
- Confirm IDEA → ENTRY_READY transitions are explicit and reviewed.

**Journal 输出位置:** `trader-memory-core`

---

## Swing Opportunity Daily {#swing-opportunity-daily}

**`swing-opportunity-daily`** · daily · ~35 min · fmp-required · intermediate

**何时运行:** Only after market-regime-daily has produced a non-restrictive exposure decision. Identifies swing trade candidates and builds entry plans.

**何时不要运行:** Do not run when the latest market-regime-daily exposure_decision is cash-priority or restrictive. Do not use as a standalone screener without the regime gate.

**必需技能:** `vcp-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**可选技能:** `stockbee-momentum-burst-screener`, `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**前置工作流（informational）:**

- `market-regime-daily` 所需的 artifact `exposure_decision` — New swing trade risk requires a non-restrictive exposure decision. Skip this workflow on cash-priority or restrictive days.

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `vcp_candidates` | 1 | 是 | — |
| `momentum_burst_candidates` | 2 | 否 | — |
| `canslim_candidates` | 3 | 否 | — |
| `theme_candidates` | 4 | 否 | — |
| `validated_setups` | 5 | 是 | — |
| `position_sizing` | 6 | 是 | — |
| `trade_plans` | 7 | 否 | `trade-memory-loop` |
| `candidate_journal_entry` | 8 | 是 | `trade-memory-loop` |

**步骤:**

**步骤 1: Run VCP screener** → `vcp-screener`

- produces: `vcp_candidates`

**步骤 2: Run Stockbee momentum burst screener** （可选） → `stockbee-momentum-burst-screener`

- produces: `momentum_burst_candidates`

**步骤 3: Run CANSLIM screener** （可选） → `canslim-screener`

- produces: `canslim_candidates`

**步骤 4: Theme detection cross-check** （可选） → `theme-detector`

- produces: `theme_candidates`

**步骤 5: Validate setups on weekly chart** （判断关卡） → `technical-analyst`

- consumes: `vcp_candidates`, `momentum_burst_candidates`, `canslim_candidates`, `theme_candidates`
- produces: `validated_setups`
- **判断:** Which candidates have a clean weekly setup (Stage 2 uptrend, tight base, or Stockbee-style range expansion from a controlled base) and pass the manual chart review? Reject candidates that don't.

**步骤 6: Calculate position size** → `position-sizer`

- consumes: `validated_setups`
- produces: `position_sizing`

**步骤 7: Build entry plan** （可选） → `breakout-trade-planner`

- consumes: `validated_setups`, `position_sizing`
- produces: `trade_plans`

**步骤 8: Register thesis in journal** （判断关卡） → `trader-memory-core`

- consumes: `position_sizing`, `trade_plans`
- produces: `candidate_journal_entry`
- **判断:** For each candidate that survived validation, register the thesis with entry / stop / target. Confirm risk per trade matches position-sizer output and total portfolio heat is within budget.

**人工复核:**

- Confirm market-regime-daily exposure_decision allows new risk before acting.
- Reject any candidate where weekly setup is unclear, even if screener passed.
- Treat Stockbee momentum burst output as candidate generation only; require chart validation and risk-distance review.
- Verify total portfolio heat is within budget before placing any order.
- All orders are placed manually at the broker; no auto-execution.

**Journal 输出位置:** `trader-memory-core`

---

## Trade Memory Loop {#trade-memory-loop}

**`trade-memory-loop`** · ad-hoc · ~30 min · no-api-basic · beginner

**何时运行:** Every time a position is closed (full or partial exit). Records the outcome, generates a postmortem, (optionally) coaches process / risk / execution / behavior patterns, and (optionally) re-validates the original hypothesis via backtest.

**何时不要运行:** Do not run before a position is closed — use trader-memory-core directly to update an open thesis instead. Do not skip this loop after a closed trade, even on winners.

**必需技能:** `trader-memory-core`, `signal-postmortem`

**可选技能:** `trade-performance-coach`, `backtest-expert`

**artifact 一览:**

| Artifact | 生成步骤 | 必需 | 下游提示 |
|---|---|---|---|
| `closed_thesis_record` | 1 | 是 | — |
| `postmortem_findings` | 2 | 是 | `monthly-performance-review` |
| `performance_coach_report` | 3 | 否 | `monthly-performance-review` |
| `next_session_operating_rules` | 3 | 否 | `monthly-performance-review` |
| `backtest_validation` | 4 | 否 | — |
| `lessons_log_entry` | 5 | 是 | `monthly-performance-review` |

**步骤:**

**步骤 1: Record closed trade outcome** → `trader-memory-core`

- produces: `closed_thesis_record`

**步骤 2: Generate postmortem** （判断关卡） → `signal-postmortem`

- consumes: `closed_thesis_record`
- produces: `postmortem_findings`
- **判断:** What was the root cause of the outcome — thesis quality, execution, market environment, or randomness? Classify and document.

**步骤 3: Coach process, risk, and behavior patterns** （可选） （判断关卡） → `trade-performance-coach`

- consumes: `closed_thesis_record`, `postmortem_findings`
- produces: `performance_coach_report`, `next_session_operating_rules`
- **判断:** Which next-session operating rules should the trader accept, modify, defer, or journal only?

**步骤 4: Re-validate hypothesis via backtest** （可选） → `backtest-expert`

- consumes: `postmortem_findings`
- produces: `backtest_validation`

**步骤 5: Append lessons to journal** → `trader-memory-core`

- consumes: `postmortem_findings`, `backtest_validation`
- produces: `lessons_log_entry`

**人工复核:**

- Be honest about whether the win was thesis-driven or lucky.
- Be honest about whether the loss was thesis-flawed or executed poorly.
- Don't rationalize randomness as either skill or failure.

**Journal 输出位置:** `trader-memory-core`

---
