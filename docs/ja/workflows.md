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
| [`kanchi-dividend-weekly`](#kanchi-dividend-weekly) — Kanchi Dividend Weekly | weekly | 60 | mixed | intermediate |
| [`market-regime-daily`](#market-regime-daily) — Market Regime Daily | daily | 15 | no-api-basic | beginner |
| [`monthly-performance-review`](#monthly-performance-review) — Monthly Performance Review | monthly | 90 | no-api-basic | intermediate |
| [`multi-asset-opportunity-daily`](#multi-asset-opportunity-daily) — Multi-Asset Opportunity Daily | daily | 45 | mixed | intermediate |
| [`shapiro-contrarian`](#shapiro-contrarian) — Shapiro COT Contrarian | weekly | 60 | fmp-required | advanced |
| [`stockbee-20pct-study-daily`](#stockbee-20pct-study-daily) — Stockbee 20% Study Daily | daily | 30 | mixed | advanced |
| [`stockbee-ep-daily`](#stockbee-ep-daily) — Stockbee EP Daily | daily | 40 | mixed | advanced |
| [`stockbee-fluency-loop`](#stockbee-fluency-loop) — Stockbee Setup Fluency Loop | daily | 20 | no-api-basic | intermediate |
| [`swing-opportunity-daily`](#swing-opportunity-daily) — Swing Opportunity Daily | daily | 40 | fmp-required | intermediate |
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

## Kanchi Dividend Weekly {#kanchi-dividend-weekly}

**`kanchi-dividend-weekly`** · weekly · ~60 min · mixed · intermediate

**実行タイミング:** Weekly, to source and underwrite new US-listed dividend candidates using Kanchi's 5-step method: screen for yield/quality, deep-dive the strongest names, and register a fully-documented candidate thesis before any entry. v1 covers US-listed dividend stocks only.

**実行してはいけないとき:** Not for Japanese or other non-US-listed dividend stocks -- this workflow neither covers nor implies support for them in v1. Not a claim that Kanchi-style screening is a profitable strategy; it is a disciplined candidate-sourcing routine, not a signal to buy. Not for maintaining an existing holding -- that is core-portfolio-weekly's job (this workflow is for finding and underwriting NEW candidates). No order is ever placed automatically; every buy is entered manually at the broker.

**必須スキル:** `kanchi-dividend-sop`, `trader-memory-core`

**任意スキル:** `value-dividend-screener`, `dividend-growth-pullback-screener`, `kanchi-dividend-us-tax-accounting`, `kanchi-dividend-review-monitor`

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `high_yield_candidates` | 1 | なし | — |
| `pullback_candidates` | 2 | なし | — |
| `kanchi_candidates` | 3 | あり | — |
| `stock_memo` | 3 | あり | — |
| `account_location_advice` | 4 | なし | — |
| `review_queue` | 5 | なし | — |
| `kanchi_thesis_entry` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: Screen for high-yield candidates** （任意） → `value-dividend-screener`

- produces: `high_yield_candidates`

**ステップ 2: Screen for dividend-growth pullbacks** （任意） → `dividend-growth-pullback-screener`

- produces: `pullback_candidates`

**ステップ 3: Run the Kanchi 5-step underwriting** （判断ゲート） → `kanchi-dividend-sop`

- consumes: `high_yield_candidates`, `pullback_candidates`
- produces: `kanchi_candidates`, `stock_memo`
- **判断:** For each candidate, does the Kanchi verdict reach an actionable tier (CLEAN-PASS / PASS-CAUTION / CONDITIONAL-PASS)? A HOLD-REVIEW, STEP1-RECHECK, or FAIL verdict is fail-closed -- it stops here, not forward to sizing or registration. Candidates may come from step 1/2 screeners (use if available) or a manually supplied ticker list -- neither screener is required to run this step.

**ステップ 4: Check US tax and account-location treatment** （任意） → `kanchi-dividend-us-tax-accounting`

- produces: `account_location_advice`

**ステップ 5: Check existing-holding review triggers** （任意） → `kanchi-dividend-review-monitor`

- produces: `review_queue`

**ステップ 6: Register the candidate thesis** （判断ゲート） → `trader-memory-core`

- consumes: `kanchi_candidates`, `stock_memo`, `account_location_advice`, `review_queue`
- produces: `kanchi_thesis_entry`
- **判断:** For each actionable candidate, ingest the kanchi_candidates verdict as an IDEA thesis, then link the saved stock_memo file (and, if available, tax/account-location advice and any review-monitor flags) to it with thesis_store.link_report() so the fully-documented Kanchi memo is part of the auditable record, not just referenced in prose. Confirm no unresolved blockers, sizing, sector concentration, and tranche plan before entering an order. Never transition the thesis to ACTIVE until a real broker fill happens -- this step only reaches IDEA / ENTRY_READY.

**手動レビュー:**

- A HOLD-REVIEW, STEP1-RECHECK, or FAIL Kanchi verdict is fail-closed -- it never advances to sizing or thesis registration.
- The step-3 stock memo (`references/stock-note-template.md` in kanchi-dividend-sop, a hand-written one-pager) is not embedded in the kanchi_candidates JSON -- save it to a file, then after the IDEA thesis is registered, call `thesis_store.link_report(state_dir, thesis_id, "kanchi-dividend-sop", <memo_path>, date)` to attach it. Without this call the thesis has no documented memo in its `linked_reports`, even though one was written.
- No order is ever placed automatically, and the thesis never auto-transitions to ACTIVE; every fill is entered manually at the broker, then recorded with open-position.
- Screeners (steps 1-2) are optional -- a manually supplied ticker list is an equally valid path into step 3.
- Tax and account-location advice (step 4) is advisory, not authoritative -- verify with a tax professional or the actual broker/custodian statements before acting on it.
- If review-monitor (step 5) flags an existing holding WARN or REVIEW, that only pauses additional buys in that name -- it never triggers an automatic sell.
- Screener outputs land under each skill's own `logs/` directory, not a shared `reports/` path; treat artifact ids as logical references, not literal filenames, when wiring steps together.
- Command examples for dividend-growth-pullback-screener must use `screen_dividend_growth_rsi.py` -- `screen_dividend_growth.py` does not exist in this repository.

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

## Shapiro COT Contrarian {#shapiro-contrarian}

**`shapiro-contrarian`** · weekly · ~60 min · fmp-required · advanced

**実行タイミング:** Weekly, after the CFTC Commitment of Traders report publishes (Friday ~3:30pm ET, carrying Tuesday's positioning). Screens roughly 65 futures markets for crowded speculative extremes and, only where a news-failure and a weekly price-action reversal both confirm, produces a contract-sized contrarian fade plan.

**実行してはいけないとき:** Do not run intraday or more than weekly — COT data updates once a week and the edge is positioning-driven, not intraday. Do not act on a crowding extreme alone; the gate must reach READY_FOR_PLAN (crowding, news failure, and price action all CONFIRMED) before any sizing. Not for equities — COT covers CFTC futures markets only.

**必須スキル:** `cot-contrarian-detector`, `news-reaction-failure-analyzer`, `technical-analyst`, `contrarian-setup-gate`, `futures-position-sizer`, `trader-memory-core`

**任意スキル:** （なし）

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `cot_crowding_report` | 1 | あり | — |
| `news_failure_verdict` | 2 | あり | — |
| `price_action_confirmation_report` | 3 | あり | — |
| `contrarian_setup_gate_report` | 4 | あり | — |
| `futures_position_size` | 5 | あり | — |
| `contrarian_thesis_entry` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: Screen COT crowding** （判断ゲート） → `cot-contrarian-detector`

- produces: `cot_crowding_report`
- **判断:** Which futures markets are at a 3-year COT-index crowding extreme (CROWDED_LONG / CROWDED_SHORT) this week? Crowding alone is not a signal — carry only the extremes forward.

**ステップ 2: Check for news-reaction failure** （判断ゲート） → `news-reaction-failure-analyzer`

- consumes: `cot_crowding_report`
- produces: `news_failure_verdict`
- **判断:** For each crowded market, did price fail to react to news favorable to the crowd's direction (CONFIRMED, against a curated primary/wire-source events file built via WebSearch)? Drop NOT_CONFIRMED / INSUFFICIENT_EVIDENCE markets.

**ステップ 3: Confirm weekly price-action reversal** （判断ゲート） → `technical-analyst`

- consumes: `cot_crowding_report`
- produces: `price_action_confirmation_report`
- **判断:** On the weekly chart, is there a reversal against the crowd (key reversal, failed breakout, or failed extreme) — CONFIRMED — with a defined swing stop? Reject NOT_CONFIRMED / INSUFFICIENT_DATA.

**ステップ 4: Synthesize the contrarian setup gate** （判断ゲート） → `contrarian-setup-gate`

- consumes: `cot_crowding_report`, `news_failure_verdict`, `price_action_confirmation_report`
- produces: `contrarian_setup_gate_report`
- **判断:** Does the gate reach READY_FOR_PLAN (crowding, news failure, and price action all CONFIRMED, fail-closed)? Only READY_FOR_PLAN markets proceed to sizing; CROWDED / WATCHING_PRICE / REJECTED / INSUFFICIENT_EVIDENCE stop here.

**ステップ 5: Size the futures position** → `futures-position-sizer`

- consumes: `contrarian_setup_gate_report`
- produces: `futures_position_size`

**ステップ 6: Register the contrarian thesis** （判断ゲート） → `trader-memory-core`

- consumes: `futures_position_size`, `contrarian_setup_gate_report`
- produces: `contrarian_thesis_entry`
- **判断:** Register each fade whose sizer output is sizing_status SIZED — never a NO_TRADE result — in this order: (1) create the IDEA thesis first (manual ingest or register() — attach-futures-position only attaches to an EXISTING thesis, it never creates one); (2) attach the SIZED report with attach-futures-position, which persists contracts / direction / multiplier / USD currency / risk onto the thesis position; (3) link the upstream cot_crowding_report, news_failure_verdict, price_action_confirmation_report, and contrarian_setup_gate_report to the thesis with thesis_store.link_report() so the fade's full evidence chain is auditable; (4) only transition to ACTIVE with open-position once the order actually fills at the broker. Confirm per-trade risk matches the sizer output and total portfolio heat is within budget.

**手動レビュー:**

- COT data is 3 days lagged (Tuesday snapshot, Friday release) — treat the crowding read as end-of-Tuesday, not live.
- Crowding is a precondition, never a trade signal — require the news-failure AND price-action confirmations before sizing.
- News-failure events must be curated from primary/wire sources with real URLs; do not fabricate. INSUFFICIENT_EVIDENCE never advances.
- Confirm the gate setup_status is READY_FOR_PLAN before sizing; the sizer will refuse a non-READY gate, but verify the reason if it does.
- Step 5 needs more than contrarian_setup_gate_report — the sizer's --entry, --account-size, and --risk-pct are always operator-supplied, even in gate-handoff mode; neither the gate nor the sizer derives them, so gather these before invoking futures-position-sizer.
- Verify the sizer's contract count and per-contract risk before any order; confirm total portfolio heat is within budget.
- Futures margin is broker/time-dependent and NOT computed — verify initial and maintenance margin with the broker before trading.
- All orders are placed manually at the broker; no auto-execution. Monitoring (COT normalization, stop, thesis invalidation) is manual until contrarian-position-monitor ships.
- The gate's entry_trigger / sizer's planned entry is not an actual fill. Keep the SIZED report itself (it carries the planned entry); a manual-ingest source also keeps entry_price in origin.raw_provenance.entry_price. Either way, never write it to entry.actual_price before a real fill happens.
- Do not transition the thesis to ACTIVE (open-position) until the order actually fills at the broker. Step 6 only reaches IDEA/ENTRY_READY with the futures position attached — no order is ever placed automatically.

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

**`stockbee-ep-daily`** · daily · ~40 min · mixed · advanced

**実行タイミング:** Run on earnings/news-heavy days after the market-regime workflow allows new risk, or ad hoc when a game-changing catalyst appears. Use this workflow to classify Day 1 Episodic Pivot candidates and decide whether they are actionable today, delayed-EP watchlist names, or PEAD handoff candidates.

**実行してはいけないとき:** Do not run as a blind stock screener without catalyst inputs. Do not use it to bypass market-regime gates, chart validation, position sizing, or manual catalyst review.

**必須スキル:** `drawdown-circuit-breaker`, `stockbee-episodic-pivot-analyzer`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`

**任意スキル:** `earnings-trade-analyzer`, `stockbee-momentum-burst-screener`, `pead-screener`, `theme-detector`, `breakout-trade-planner`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — New EP trades should still respect the market-regime exposure gate.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `circuit_breaker_decision` | 1 | あり | — |
| `earnings_candidates` | 2 | なし | — |
| `momentum_burst_candidates` | 3 | なし | — |
| `episodic_pivot_candidates` | 4 | あり | — |
| `pead_handoff_candidates` | 4 | なし | `swing-opportunity-daily` |
| `delayed_ep_watchlist` | 4 | なし | — |
| `validated_ep_setups` | 5 | あり | — |
| `ep_position_sizing` | 6 | あり | — |
| `ep_trade_plan` | 7 | なし | — |
| `ep_journal_entry` | 8 | あり | `trade-memory-loop` |
| `pre_trade_discipline_decision` | 9 | あり | — |

**ステップ:**

**ステップ 1: Check account circuit breaker** （判断ゲート） → `drawdown-circuit-breaker`

- produces: `circuit_breaker_decision`
- **判断:** Is the account circuit breaker clear (TRADING_ALLOWED) for new EP trade risk today?

**ステップ 2: Optional earnings candidate scan** （任意） → `earnings-trade-analyzer`

- produces: `earnings_candidates`

**ステップ 3: Optional momentum confirmation scan** （任意） → `stockbee-momentum-burst-screener`

- produces: `momentum_burst_candidates`

**ステップ 4: Analyze Day 1 Episodic Pivot candidates** （判断ゲート） → `stockbee-episodic-pivot-analyzer`

- consumes: `earnings_candidates`, `momentum_burst_candidates`
- produces: `episodic_pivot_candidates`, `pead_handoff_candidates`, `delayed_ep_watchlist`
- **判断:** Which candidates have a true game-changing catalyst plus price/volume confirmation? Separate ACTIONABLE_DAY1 from DELAYED_EP_WATCH and reject low-quality headline-only moves.

**ステップ 5: Validate EP chart quality** （判断ゲート） → `technical-analyst`

- consumes: `episodic_pivot_candidates`
- produces: `validated_ep_setups`
- **判断:** Does the chart confirm a clean EP reaction with acceptable close quality, liquidity, and risk to the EP-day low?

**ステップ 6: Calculate EP position size** → `position-sizer`

- consumes: `validated_ep_setups`
- produces: `ep_position_sizing`

**ステップ 7: Build optional EP trade plan** （任意） → `breakout-trade-planner`

- consumes: `validated_ep_setups`, `ep_position_sizing`
- produces: `ep_trade_plan`

**ステップ 8: Register EP thesis or watchlist entry** （判断ゲート） → `trader-memory-core`

- consumes: `validated_ep_setups`, `ep_position_sizing`, `ep_trade_plan`
- produces: `ep_journal_entry`
- **判断:** Which candidates deserve an active thesis, which belong on delayed EP / PEAD watch, and which should be ignored despite a high initial score?

**ステップ 9: Run EP manual execution discipline gate** （判断ゲート） → `pre-trade-discipline-gate`

- consumes: `circuit_breaker_decision`, `ep_journal_entry`, `ep_position_sizing`, `ep_trade_plan`
- produces: `pre_trade_discipline_decision`
- **判断:** Before placing any manual broker order, do ACTIONABLE_DAY1 or ENTRY_READY EP candidates pass the written-plan, predefined-stop, position-size, recent-loss, market-regime, and circuit-breaker discipline checks? Treat delayed EP, PEAD handoff, ignored, or rejected candidates as no-action journal entries, not order approvals.

**手動レビュー:**

- Confirm market-regime-daily allows new risk before acting.
- Confirm circuit_breaker_decision is TRADING_ALLOWED before analyzing new EP trade risk.
- Verify the catalyst manually; this workflow does not discover or validate news truth by itself.
- Treat analyst-only and story-only EPs as lower quality unless price/volume confirmation is exceptional.
- Use EP-day low as the default stop reference only if the distance is realistically sizeable.
- Send overextended earnings/guidance EPs to PEAD monitoring instead of chasing Day 1.
- Confirm pre_trade_discipline_decision is GO before placing any manual broker order; watchlist and PEAD handoff candidates should not be treated as order approvals.
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

**`swing-opportunity-daily`** · daily · ~40 min · fmp-required · intermediate

**実行タイミング:** Only after market-regime-daily has produced a non-restrictive exposure decision. Identifies swing trade candidates and builds entry plans.

**実行してはいけないとき:** Do not run when the latest market-regime-daily exposure_decision is cash-priority or restrictive. Do not use as a standalone screener without the regime gate.

**必須スキル:** `vcp-screener`, `drawdown-circuit-breaker`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`

**任意スキル:** `stockbee-momentum-burst-screener`, `stockbee-exhaustion-hammer-screener`, `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**前提ワークフロー（informational）:**

- `market-regime-daily` が期待する artifact `exposure_decision` — New swing trade risk requires a non-restrictive exposure decision. Skip this workflow on cash-priority or restrictive days.

**artifact 一覧:**

| Artifact | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `circuit_breaker_decision` | 1 | あり | — |
| `vcp_candidates` | 2 | あり | — |
| `momentum_burst_candidates` | 3 | なし | — |
| `exhaustion_hammer_candidates` | 4 | なし | — |
| `canslim_candidates` | 5 | なし | — |
| `theme_candidates` | 6 | なし | — |
| `validated_setups` | 7 | あり | — |
| `position_sizing` | 8 | あり | — |
| `trade_plans` | 9 | なし | `trade-memory-loop` |
| `candidate_journal_entry` | 10 | あり | `trade-memory-loop` |
| `pre_trade_discipline_decision` | 11 | あり | — |

**ステップ:**

**ステップ 1: Check account circuit breaker** （判断ゲート） → `drawdown-circuit-breaker`

- produces: `circuit_breaker_decision`
- **判断:** Is the account circuit breaker clear (TRADING_ALLOWED) for new trade risk today?

**ステップ 2: Run VCP screener** → `vcp-screener`

- produces: `vcp_candidates`

**ステップ 3: Run Stockbee momentum burst screener** （任意） → `stockbee-momentum-burst-screener`

- produces: `momentum_burst_candidates`

**ステップ 4: Run Stockbee exhaustion hammer screener** （任意） → `stockbee-exhaustion-hammer-screener`

- produces: `exhaustion_hammer_candidates`

**ステップ 5: Run CANSLIM screener** （任意） → `canslim-screener`

- produces: `canslim_candidates`

**ステップ 6: Theme detection cross-check** （任意） → `theme-detector`

- produces: `theme_candidates`

**ステップ 7: Validate setups on weekly chart** （判断ゲート） → `technical-analyst`

- consumes: `vcp_candidates`, `momentum_burst_candidates`, `exhaustion_hammer_candidates`, `canslim_candidates`, `theme_candidates`
- produces: `validated_setups`
- **判断:** Which candidates have a clean weekly setup (Stage 2 uptrend, tight base, or Stockbee-style range expansion from a controlled base) and pass the manual chart review? For exhaustion hammers, confirm the pullback is not thesis-breaking and risk to the day low is acceptable. Reject candidates that don't pass.

**ステップ 8: Calculate position size** → `position-sizer`

- consumes: `validated_setups`
- produces: `position_sizing`

**ステップ 9: Build entry plan** （任意） → `breakout-trade-planner`

- consumes: `validated_setups`, `position_sizing`
- produces: `trade_plans`

**ステップ 10: Register thesis in journal** （判断ゲート） → `trader-memory-core`

- consumes: `position_sizing`, `trade_plans`
- produces: `candidate_journal_entry`
- **判断:** For each candidate that survived validation, register the thesis with entry / stop / target. Confirm risk per trade matches position-sizer output and total portfolio heat is within budget.

**ステップ 11: Run manual execution discipline gate** （判断ゲート） → `pre-trade-discipline-gate`

- consumes: `candidate_journal_entry`, `position_sizing`, `trade_plans`, `circuit_breaker_decision`
- produces: `pre_trade_discipline_decision`
- **判断:** Before placing any manual broker order, does each actionable candidate pass the written-plan, predefined-stop, position-size, recent-loss, market-regime, and circuit-breaker discipline checks?

**手動レビュー:**

- Confirm market-regime-daily exposure_decision allows new risk before acting.
- Confirm circuit_breaker_decision is TRADING_ALLOWED before screening or sizing new candidates.
- Reject any candidate where weekly setup is unclear, even if screener passed.
- Treat Stockbee momentum burst output as candidate generation only; require chart validation and risk-distance review.
- Treat Stockbee exhaustion hammer output as candidate generation only; confirm the pullback is not caused by a thesis-breaking news event and verify risk to the day low.
- Verify total portfolio heat is within budget before placing any order.
- Confirm pre_trade_discipline_decision is GO before placing any manual broker order.
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
