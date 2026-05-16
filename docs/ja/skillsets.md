---
layout: default
title: スキルセット
parent: 日本語
nav_order: 5
lang_peer: /en/skillsets/
permalink: /ja/skillsets/
---

# スキルセット
{: .no_toc }

> _このページは `scripts/generate_skillset_docs.py` によって自動生成されます。手動編集しないでください。_

個人トレーダー OS の目的別スキルセット群です。スキルセットはカテゴリ単位のスキル束（必須 / 推奨 / 任意）で、それを運用化するワークフローに紐づきます（「この目的のために何を入れるか」の層）。[`skillsets/`](https://github.com/tradermonty/claude-trading-skills/tree/main/skillsets) 以下の manifest が正本で、本ページはそこから自動生成されます。

**翻訳方針:** 本ページは見出しラベルのみ日本語化しています。manifest 本文（`when_to_use` / `when_not_to_use` 等）は英語正本をそのまま表示します。本文の日本語化は将来の対応予定です（manifest 側に `*_ja` フィールドを追加するか、別のローカライズ層を設ける方向で検討中）。

---

## スキルセット一覧

| スキルセット | タイムフレーム | API プロファイル | 難易度 | 関連ワークフロー |
|---|---|---|---|---|
| [`core-portfolio`](#core-portfolio) — Core Portfolio | weekly | mixed | beginner | `core-portfolio-weekly` |
| [`market-regime`](#market-regime) — Market Regime | daily | no-api-basic | beginner | `market-regime-daily` |
| [`swing-opportunity`](#swing-opportunity) — Swing Opportunity | daily | fmp-required | intermediate | `swing-opportunity-daily` |
| [`trade-memory`](#trade-memory) — Trade Memory | event-driven | no-api-basic | beginner | `trade-memory-loop`, `monthly-performance-review` |

---

## Core Portfolio {#core-portfolio}

**`core-portfolio`** · weekly · mixed · beginner

**使用するとき:** The long-term core sleeve: review holdings, dividend health, and overall allocation once a week. Use to keep the buy-and-hold / dividend book healthy and decide deliberate rebalance actions. Operationalized weekly by the core-portfolio-weekly workflow.

**使用してはいけないとき:** Do not run this as a daily routine — daily portfolio churn defeats the long-term framing. Do not use it to chase short-term swing setups; that is the swing-opportunity sleeve gated by market-regime.

**対象ユーザー:** `long-term-investor`, `dividend-investor`

**必須スキル:** `portfolio-manager`, `trader-memory-core`

**推奨スキル:** `kanchi-dividend-review-monitor`, `value-dividend-screener`, `kanchi-dividend-us-tax-accounting`

**任意スキル:** `dividend-growth-pullback-screener`, `kanchi-dividend-sop`

**関連ワークフロー:** `core-portfolio-weekly`

---

## Market Regime {#market-regime}

**`market-regime`** · daily · no-api-basic · beginner

**使用するとき:** The shared risk layer for every trading day. Use before considering new swing-trade risk to decide today's exposure posture (allow / restrict / cash-priority) from breadth, uptrend participation, and top-risk signals. Operationalized daily by the market-regime-daily workflow.

**使用してはいけないとき:** Do not treat this bundle's output as a standalone buy/sell signal — the exposure decision is a posture, not a directive. Do not skip it and run swing-opportunity work directly; the regime gate comes first.

**対象ユーザー:** `part-time-swing-trader`, `growth-investor`

**必須スキル:** `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach`

**推奨スキル:** `market-top-detector`, `macro-regime-detector`

**任意スキル:** `breadth-chart-analyst`, `sector-analyst`, `market-environment-analysis`, `market-news-analyst`, `downtrend-duration-analyzer`, `us-market-bubble-detector`

**関連ワークフロー:** `market-regime-daily`

---

## Swing Opportunity {#swing-opportunity}

**`swing-opportunity`** · daily · fmp-required · intermediate

**使用するとき:** The satellite swing sleeve: generate and validate swing-trade candidates and build risk-sized entry plans. Use only on days the market-regime sleeve has allowed new risk. Operationalized by the swing-opportunity-daily workflow (prerequisite: market-regime-daily exposure decision).

**使用してはいけないとき:** Do not run when the latest market-regime exposure decision is cash-priority or restrictive. Do not use the screeners standalone without the regime gate and position sizing.

**対象ユーザー:** `part-time-swing-trader`

**必須スキル:** `vcp-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**推奨スキル:** `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**任意スキル:** `finviz-screener`

**関連ワークフロー:** `swing-opportunity-daily`

---

## Trade Memory {#trade-memory}

**`trade-memory`** · event-driven · no-api-basic · beginner

**使用するとき:** The shared learning loop: record closed-trade outcomes, run postmortems, and feed lessons back into the process. Use after every closed position and for the monthly performance retrospective. Operationalized by the trade-memory-loop (per closed trade) and monthly-performance-review (monthly) workflows.

**使用してはいけないとき:** Do not run before a position is closed — update an open thesis with trader-memory-core directly instead. Do not skip the loop after a closed trade, even on winners.

**対象ユーザー:** `part-time-swing-trader`, `long-term-investor`, `growth-investor`

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**推奨スキル:** `backtest-expert`

**任意スキル:** `trade-hypothesis-ideator`

**関連ワークフロー:** `trade-memory-loop`, `monthly-performance-review`

---
