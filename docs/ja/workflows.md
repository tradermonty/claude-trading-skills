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

**翻訳方針:** 本ページは見出しラベルのみ日本語化しています。manifest 本文（`when_to_run` / `decision_question` / `manual_review` 等）は英語正本をそのまま表示します。本文の日本語化は将来の対応予定です（manifest 側に `*_ja` フィールドを追加するか、別のローカライズ層を設ける方向で検討中）。

---

## ワークフロー一覧

| ワークフロー | 頻度 | 目安(分) | API プロファイル | 難易度 |
|---|---|---|---|---|
| [`core-portfolio-weekly`](#core-portfolio-weekly) — Core Portfolio Weekly | weekly | 60 | mixed | beginner |
| [`market-regime-daily`](#market-regime-daily) — Market Regime Daily | daily | 15 | no-api-basic | beginner |
| [`monthly-performance-review`](#monthly-performance-review) — Monthly Performance Review | monthly | 90 | no-api-basic | intermediate |
| [`multi-asset-opportunity-daily`](#multi-asset-opportunity-daily) — Multi-Asset Opportunity Daily | daily | 45 | mixed | intermediate |
| [`stockbee-20pct-study-daily`](#stockbee-20pct-study-daily) — Stockbee 20% Study Daily | daily | 30 | mixed | advanced |
| [`stockbee-ep-daily`](#stockbee-ep-daily) — Stockbee EP Daily | daily | 35 | mixed | advanced |
| [`stockbee-fluency-loop`](#stockbee-fluency-loop) — Stockbee Setup Fluency Loop | daily | 20 | no-api-basic | intermediate |
| [`swing-opportunity-daily`](#swing-opportunity-daily) — Swing Opportunity Daily | daily | 35 | fmp-required | intermediate |
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

**任意スキル:** `trade-performance-coach`, `backtest-expert`, `dual-axis-skill-reviewer`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `monthly_aggregate` | 1 | あり | — |
| `aggregate_postmortem` | 2 | あり | — |
| `monthly_performance_coach_report` | 3 | なし | — |
| `monthly_behavior_patterns` | 3 | なし | — |
| `next_month_operating_rules` | 3 | なし | — |
| `hypothesis_revalidation` | 4 | なし | — |
| `skill_review_findings` | 5 | なし | — |
| `monthly_decision_log` | 6 | あり | — |
| `rule_changes_for_next_month` | 6 | あり | — |
| `skill_improvement_backlog` | 6 | なし | — |

**ステップ:**

**ステップ 1: Aggregate the month's trades and theses** → `trader-memory-core`

- produces: `monthly_aggregate`

**ステップ 2: Pattern-level postmortem across the month** （判断ゲート） → `signal-postmortem`

- consumes: `monthly_aggregate`
- produces: `aggregate_postmortem`
- **判断:** What recurring patterns appear across the month's outcomes? Classify by thesis quality, execution, market environment, and randomness.

**ステップ 3: Coach monthly process, risk, and behavior patterns** （任意） （判断ゲート） → `trade-performance-coach`

- consumes: `monthly_aggregate`, `aggregate_postmortem`
- produces: `monthly_performance_coach_report`, `monthly_behavior_patterns`, `next_month_operating_rules`
- **判断:** Which next-month operating rules should be accepted, modified, deferred, or journaled only?

**ステップ 4: Re-validate hypotheses via backtest** （任意） → `backtest-expert`

- consumes: `aggregate_postmortem`
- produces: `hypothesis_revalidation`

**ステップ 5: Review which skills helped or hurt** （任意） → `dual-axis-skill-reviewer`

- consumes: `aggregate_postmortem`
- produces: `skill_review_findings`

**ステップ 6: Produce decision log and rule changes** （判断ゲート） → `trader-memory-core`

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

## Multi-Asset Opportunity Daily {#multi-asset-opportunity-daily}

**`multi-asset-opportunity-daily`** · daily · ~45 min · mixed · intermediate

**実行タイミング:** Only after market-regime-daily has produced a non-restrictive exposure decision. Sweeps macro + themes + news to surface multi-asset ideas (equities, commodities-via-equity-proxies, options expressions) and synthesizes them into ranked hypothesis cards.

**実行してはいけないとき:** Do not run when the latest market-regime-daily exposure_decision is cash-priority. Do not treat hypothesis cards as buy/sell signals — they carry manual_review_required and must pass human sign-off before any capital moves. Forex output is research-only; never feed it into a broker.

**必須スキル:** `macro-regime-detector`, `theme-detector`, `trade-hypothesis-ideator`, `position-sizer`, `trader-memory-core`

**任意スキル:** `market-news-analyst`, `market-environment-analysis`, `sector-analyst`, `scenario-analyzer`, `stanley-druckenmiller-investment`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — Multi-asset opportunity scanning requires a non-restrictive exposure posture. Skip on cash-priority days; reduce scope on restrict days.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `macro_regime_brief` | 1 | あり | `swing-opportunity-daily`, `monthly-performance-review` |
| `hot_themes` | 2 | あり | `swing-opportunity-daily` |
| `catalyst_news_brief` | 3 | なし | — |
| `hypothesis_cards` | 4 | あり | `swing-opportunity-daily`, `trade-memory-loop` |
| `sized_hypotheses` | 5 | あり | — |
| `opportunity_journal_entries` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: Refresh macro regime context** → `macro-regime-detector`

- produces: `macro_regime_brief`

**ステップ 2: Detect hot themes + sector rotation** → `theme-detector`

- consumes: `macro_regime_brief`
- produces: `hot_themes`

**ステップ 3: Scan news + catalyst landscape** （任意） → `market-news-analyst`

- consumes: `hot_themes`
- produces: `catalyst_news_brief`

**ステップ 4: Synthesize ranked hypothesis cards** （判断ゲート） → `trade-hypothesis-ideator`

- consumes: `macro_regime_brief`, `hot_themes`, `catalyst_news_brief`
- produces: `hypothesis_cards`
- **判断:** For each hypothesis, does layer 1 (macro) align with layer 2 (theme) and is what-is-priced-in still favorable? Reject any card where the gap to consensus is unclear or already closed.

**ステップ 5: Apply risk-based sizing to hypothesis cards** → `position-sizer`

- consumes: `hypothesis_cards`
- produces: `sized_hypotheses`

**ステップ 6: Persist as IDEA / ENTRY_READY entries** （判断ゲート） → `trader-memory-core`

- consumes: `hypothesis_cards`, `sized_hypotheses`
- produces: `opportunity_journal_entries`
- **判断:** Which hypotheses should be promoted from IDEA to ENTRY_READY, which stay as IDEA pending more confirmation, and which are rejected?

**手動レビュー:**

- Confirm the regime brief does not contradict the exposure_decision from market-regime-daily.
- Confirm each hypothesis has a written thesis AND a kill criterion.
- Confirm position sizing respects portfolio risk caps (per-position and per-sector).
- For forex-related output, confirm research_only=true; never wire to a broker.
- Confirm IDEA → ENTRY_READY transitions are explicit and reviewed.

**Journal 出力先:** `trader-memory-core`

---

## Stockbee 20% Study Daily {#stockbee-20pct-study-daily}

**`stockbee-20pct-study-daily`** · daily · ~30 min · mixed · advanced

**実行タイミング:** Run after the US market close, or during historical research backfills, to identify +20%/-20% movers, classify event context, update matured outcomes, and accumulate a model book of explosive market moves.

**実行してはいけないとき:** Do not use as a buy/sell signal workflow or automatic execution system. Do not promote new rules from small samples, current-only universes, or events without survivorship-bias and data-quality notes.

**必須スキル:** `stockbee-20pct-study`

**任意スキル:** `trader-memory-core`, `edge-candidate-agent`, `edge-hint-extractor`, `stockbee-episodic-pivot-analyzer`, `theme-detector`, `backtest-expert`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `twenty_pct_mover_events` | 1 | あり | — |
| `classified_event_study` | 2 | あり | — |
| `matured_event_outcomes` | 3 | あり | — |
| `twenty_pct_cohort_summary` | 4 | あり | `monthly-performance-review` |
| `edge_hints_yaml` | 4 | なし | `monthly-performance-review` |
| `accepted_lessons_log` | 5 | なし | `monthly-performance-review` |

**ステップ:**

**ステップ 1: Scan daily +20% and -20% movers** → `stockbee-20pct-study`

- produces: `twenty_pct_mover_events`

**ステップ 2: Classify catalyst, chart context, theme cluster, and risk flags** → `stockbee-20pct-study`

- consumes: `twenty_pct_mover_events`
- produces: `classified_event_study`

**ステップ 3: Update matured forward outcomes for prior 20% study records** → `stockbee-20pct-study`

- consumes: `classified_event_study`
- produces: `matured_event_outcomes`

**ステップ 4: Summarize cohorts and export edge hints** （判断ゲート） → `stockbee-20pct-study`

- consumes: `matured_event_outcomes`
- produces: `twenty_pct_cohort_summary`, `edge_hints_yaml`
- **判断:** Which 20% mover patterns have enough sample size, stable outcome behavior, and execution realism to promote into edge research rather than journal-only observation?

**ステップ 5: Log accepted lessons** （任意） （判断ゲート） → `trader-memory-core`

- consumes: `twenty_pct_cohort_summary`, `edge_hints_yaml`
- produces: `accepted_lessons_log`
- **判断:** Which findings are accepted as operating-rule candidates, which are rejected, and which remain pending more examples?

**手動レビュー:**

- Inspect representative winner and failure charts before accepting any pattern.
- Separate observation, research hypothesis, and executable trade plan.
- Mark current-universe backfills as survivorship-biased unless delisted symbols are included.
- Require explicit sample-size thresholds before promoting a cohort rule.
- Feed accepted lessons into monthly-performance-review rather than changing rules ad hoc.

**Journal 出力先:** `trader-memory-core`

---

## Stockbee EP Daily {#stockbee-ep-daily}

**`stockbee-ep-daily`** · daily · ~35 min · mixed · advanced

**実行タイミング:** Run on earnings/news-heavy days after the market-regime workflow allows new risk, or ad hoc when a game-changing catalyst appears. Use this workflow to classify Day 1 Episodic Pivot candidates and decide whether they are actionable today, delayed-EP watchlist names, or PEAD handoff candidates.

**実行してはいけないとき:** Do not run as a blind stock screener without catalyst inputs. Do not use it to bypass market-regime gates, chart validation, position sizing, or manual catalyst review.

**必須スキル:** `stockbee-episodic-pivot-analyzer`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**任意スキル:** `earnings-trade-analyzer`, `stockbee-momentum-burst-screener`, `pead-screener`, `theme-detector`, `breakout-trade-planner`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — New EP trades should still respect the market-regime exposure gate.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `earnings_candidates` | 1 | なし | — |
| `momentum_burst_candidates` | 2 | なし | — |
| `episodic_pivot_candidates` | 3 | あり | — |
| `pead_handoff_candidates` | 3 | なし | `swing-opportunity-daily` |
| `delayed_ep_watchlist` | 3 | なし | — |
| `validated_ep_setups` | 4 | あり | — |
| `ep_position_sizing` | 5 | あり | — |
| `ep_trade_plan` | 6 | なし | — |
| `ep_journal_entry` | 7 | あり | `trade-memory-loop` |

**ステップ:**

**ステップ 1: Optional earnings candidate scan** （任意） → `earnings-trade-analyzer`

- produces: `earnings_candidates`

**ステップ 2: Optional momentum confirmation scan** （任意） → `stockbee-momentum-burst-screener`

- produces: `momentum_burst_candidates`

**ステップ 3: Analyze Day 1 Episodic Pivot candidates** （判断ゲート） → `stockbee-episodic-pivot-analyzer`

- consumes: `earnings_candidates`, `momentum_burst_candidates`
- produces: `episodic_pivot_candidates`, `pead_handoff_candidates`, `delayed_ep_watchlist`
- **判断:** Which candidates have a true game-changing catalyst plus price/volume confirmation? Separate ACTIONABLE_DAY1 from DELAYED_EP_WATCH and reject low-quality headline-only moves.

**ステップ 4: Validate EP chart quality** （判断ゲート） → `technical-analyst`

- consumes: `episodic_pivot_candidates`
- produces: `validated_ep_setups`
- **判断:** Does the chart confirm a clean EP reaction with acceptable close quality, liquidity, and risk to the EP-day low?

**ステップ 5: Calculate EP position size** → `position-sizer`

- consumes: `validated_ep_setups`
- produces: `ep_position_sizing`

**ステップ 6: Build optional EP trade plan** （任意） → `breakout-trade-planner`

- consumes: `validated_ep_setups`, `ep_position_sizing`
- produces: `ep_trade_plan`

**ステップ 7: Register EP thesis or watchlist entry** （判断ゲート） → `trader-memory-core`

- consumes: `validated_ep_setups`, `ep_position_sizing`, `ep_trade_plan`
- produces: `ep_journal_entry`
- **判断:** Which candidates deserve an active thesis, which belong on delayed EP / PEAD watch, and which should be ignored despite a high initial score?

**手動レビュー:**

- Confirm market-regime-daily allows new risk before acting.
- Verify the catalyst manually; this workflow does not discover or validate news truth by itself.
- Treat analyst-only and story-only EPs as lower quality unless price/volume confirmation is exceptional.
- Use EP-day low as the default stop reference only if the distance is realistically sizeable.
- Send overextended earnings/guidance EPs to PEAD monitoring instead of chasing Day 1.
- All orders are placed manually at the broker; no auto-execution.

**Journal 出力先:** `trader-memory-core`

---

## Stockbee Setup Fluency Loop {#stockbee-fluency-loop}

**`stockbee-fluency-loop`** · daily · ~20 min · no-api-basic · intermediate

**実行タイミング:** After stockbee-momentum-burst-screener produces candidate reports, and again after 3/5 trading-day windows have matured. Builds a model book of Stockbee Momentum Burst examples so the trader can improve setup recognition.

**実行してはいけないとき:** Do not use as an execution workflow or signal service. Do not change trading rules from tiny samples; require enough matured examples and manual chart review before promoting or filtering a setup tag.

**必須スキル:** `stockbee-setup-fluency-trainer`

**任意スキル:** `trader-memory-core`, `signal-postmortem`, `backtest-expert`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `model_book_ingest` | 1 | あり | — |
| `matured_setup_outcomes` | 2 | あり | — |
| `setup_fluency_summary` | 3 | あり | `monthly-performance-review` |
| `rule_candidates` | 3 | なし | `monthly-performance-review` |
| `accepted_lessons_log` | 4 | なし | `monthly-performance-review` |

**ステップ:**

**ステップ 1: Ingest latest Stockbee momentum burst candidates** → `stockbee-setup-fluency-trainer`

- produces: `model_book_ingest`

**ステップ 2: Update matured 3-day and 5-day outcomes** → `stockbee-setup-fluency-trainer`

- consumes: `model_book_ingest`
- produces: `matured_setup_outcomes`

**ステップ 3: Summarize setup cohorts and rule candidates** （判断ゲート） → `stockbee-setup-fluency-trainer`

- consumes: `matured_setup_outcomes`
- produces: `setup_fluency_summary`, `rule_candidates`
- **判断:** Which setup tags have enough matured examples to promote, downgrade, or continue monitoring? Require representative chart review before changing trade rules.

**ステップ 4: Log accepted lessons** （任意） （判断ゲート） → `trader-memory-core`

- consumes: `setup_fluency_summary`, `rule_candidates`
- produces: `accepted_lessons_log`
- **判断:** Which findings are accepted as operating-rule changes, and which remain journal-only observations pending more examples?

**手動レビュー:**

- Inspect representative winner and failure charts before accepting a rule change.
- Separate evidence from execution decisions; this workflow records setup behavior, not actual P&L.
- Keep sample-size thresholds explicit, especially when market regime changes.
- Feed accepted lessons into monthly-performance-review rather than adding ad-hoc rules daily.

**Journal 出力先:** `trader-memory-core`

---

## Swing Opportunity Daily {#swing-opportunity-daily}

**`swing-opportunity-daily`** · daily · ~35 min · fmp-required · intermediate

**実行タイミング:** Only after market-regime-daily has produced a non-restrictive exposure decision. Identifies swing trade candidates and builds entry plans.

**実行してはいけないとき:** Do not run when the latest market-regime-daily exposure_decision is cash-priority or restrictive. Do not use as a standalone screener without the regime gate.

**必須スキル:** `vcp-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**任意スキル:** `stockbee-momentum-burst-screener`, `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — New swing trade risk requires a non-restrictive exposure decision. Skip this workflow on cash-priority or restrictive days.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `vcp_candidates` | 1 | あり | — |
| `momentum_burst_candidates` | 2 | なし | — |
| `canslim_candidates` | 3 | なし | — |
| `theme_candidates` | 4 | なし | — |
| `validated_setups` | 5 | あり | — |
| `position_sizing` | 6 | あり | — |
| `trade_plans` | 7 | なし | `trade-memory-loop` |
| `candidate_journal_entry` | 8 | あり | `trade-memory-loop` |

**ステップ:**

**ステップ 1: Run VCP screener** → `vcp-screener`

- produces: `vcp_candidates`

**ステップ 2: Run Stockbee momentum burst screener** （任意） → `stockbee-momentum-burst-screener`

- produces: `momentum_burst_candidates`

**ステップ 3: Run CANSLIM screener** （任意） → `canslim-screener`

- produces: `canslim_candidates`

**ステップ 4: Theme detection cross-check** （任意） → `theme-detector`

- produces: `theme_candidates`

**ステップ 5: Validate setups on weekly chart** （判断ゲート） → `technical-analyst`

- consumes: `vcp_candidates`, `momentum_burst_candidates`, `canslim_candidates`, `theme_candidates`
- produces: `validated_setups`
- **判断:** Which candidates have a clean weekly setup (Stage 2 uptrend, tight base, or Stockbee-style range expansion from a controlled base) and pass the manual chart review? Reject candidates that don't.

**ステップ 6: Calculate position size** → `position-sizer`

- consumes: `validated_setups`
- produces: `position_sizing`

**ステップ 7: Build entry plan** （任意） → `breakout-trade-planner`

- consumes: `validated_setups`, `position_sizing`
- produces: `trade_plans`

**ステップ 8: Register thesis in journal** （判断ゲート） → `trader-memory-core`

- consumes: `position_sizing`, `trade_plans`
- produces: `candidate_journal_entry`
- **判断:** For each candidate that survived validation, register the thesis with entry / stop / target. Confirm risk per trade matches position-sizer output and total portfolio heat is within budget.

**手動レビュー:**

- Confirm market-regime-daily exposure_decision allows new risk before acting.
- Reject any candidate where weekly setup is unclear, even if screener passed.
- Treat Stockbee momentum burst output as candidate generation only; require chart validation and risk-distance review.
- Verify total portfolio heat is within budget before placing any order.
- All orders are placed manually at the broker; no auto-execution.

**Journal 出力先:** `trader-memory-core`

---

## Trade Memory Loop {#trade-memory-loop}

**`trade-memory-loop`** · ad-hoc · ~30 min · no-api-basic · beginner

**実行タイミング:** Every time a position is closed (full or partial exit). Records the outcome, generates a postmortem, (optionally) coaches process / risk / execution / behavior patterns, and (optionally) re-validates the original hypothesis via backtest.

**実行してはいけないとき:** Do not run before a position is closed — use trader-memory-core directly to update an open thesis instead. Do not skip this loop after a closed trade, even on winners.

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**任意スキル:** `trade-performance-coach`, `backtest-expert`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `closed_thesis_record` | 1 | あり | — |
| `postmortem_findings` | 2 | あり | `monthly-performance-review` |
| `performance_coach_report` | 3 | なし | `monthly-performance-review` |
| `next_session_operating_rules` | 3 | なし | `monthly-performance-review` |
| `backtest_validation` | 4 | なし | — |
| `lessons_log_entry` | 5 | あり | `monthly-performance-review` |

**ステップ:**

**ステップ 1: Record closed trade outcome** → `trader-memory-core`

- produces: `closed_thesis_record`

**ステップ 2: Generate postmortem** （判断ゲート） → `signal-postmortem`

- consumes: `closed_thesis_record`
- produces: `postmortem_findings`
- **判断:** What was the root cause of the outcome — thesis quality, execution, market environment, or randomness? Classify and document.

**ステップ 3: Coach process, risk, and behavior patterns** （任意） （判断ゲート） → `trade-performance-coach`

- consumes: `closed_thesis_record`, `postmortem_findings`
- produces: `performance_coach_report`, `next_session_operating_rules`
- **判断:** Which next-session operating rules should the trader accept, modify, defer, or journal only?

**ステップ 4: Re-validate hypothesis via backtest** （任意） → `backtest-expert`

- consumes: `postmortem_findings`
- produces: `backtest_validation`

**ステップ 5: Append lessons to journal** → `trader-memory-core`

- consumes: `postmortem_findings`, `backtest_validation`
- produces: `lessons_log_entry`

**手動レビュー:**

- Be honest about whether the win was thesis-driven or lucky.
- Be honest about whether the loss was thesis-flawed or executed poorly.
- Don't rationalize randomness as either skill or failure.

**Journal 出力先:** `trader-memory-core`

---
