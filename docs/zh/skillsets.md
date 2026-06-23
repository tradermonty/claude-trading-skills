---
layout: default
title: 技能集
parent: 简体中文
nav_order: 5
lang_peer: /en/skillsets/
permalink: /zh/skillsets/
---

# 技能集
{: .no_toc }

> _本页由 `scripts/generate_skillset_docs.py` 自动生成。请勿手动编辑。_

面向个人交易者 OS 的按目标划分的技能集。技能集是按类别划分的一组技能（必需 / 推荐 / 可选），并绑定到将其运营化的工作流（即“为达成此目标该装入哪些技能”一层）。[`skillsets/`](https://github.com/tradermonty/claude-trading-skills/tree/main/skillsets) 下的 manifest 为正本，本页由其自动生成。

**翻译方针：** 本页仅将标题标签中文化。manifest 正文（`when_to_use` / `when_not_to_use` 等）按英文正本原样显示。正文的中文化为后续计划（拟在 manifest 中增加 `*_zh` 字段，或设置单独的本地化层）。

---

## 技能集一览

| 技能集 | 时间框架 | API 配置 | 难度 | 相关工作流 |
|---|---|---|---|---|
| [`core-portfolio`](#core-portfolio) — Core Portfolio | weekly | mixed | beginner | `core-portfolio-weekly` |
| [`market-regime`](#market-regime) — Market Regime | daily | no-api-basic | beginner | `market-regime-daily` |
| [`swing-opportunity`](#swing-opportunity) — Swing Opportunity | daily | fmp-required | intermediate | `swing-opportunity-daily` |
| [`trade-memory`](#trade-memory) — Trade Memory | event-driven | no-api-basic | beginner | `trade-memory-loop`, `monthly-performance-review` |

---

## Core Portfolio {#core-portfolio}

**`core-portfolio`** · weekly · mixed · beginner

**何时使用:** The long-term core sleeve: review holdings, dividend health, and overall allocation once a week. Use to keep the buy-and-hold / dividend book healthy and decide deliberate rebalance actions. Operationalized weekly by the core-portfolio-weekly workflow.

**何时不要使用:** Do not run this as a daily routine — daily portfolio churn defeats the long-term framing. Do not use it to chase short-term swing setups; that is the swing-opportunity sleeve gated by market-regime.

**目标用户:** `long-term-investor`, `dividend-investor`

**必需技能:** `portfolio-manager`, `trader-memory-core`

**推荐技能:** `kanchi-dividend-review-monitor`, `value-dividend-screener`, `kanchi-dividend-us-tax-accounting`

**可选技能:** `dividend-growth-pullback-screener`, `kanchi-dividend-sop`

**相关工作流:** `core-portfolio-weekly`

---

## Market Regime {#market-regime}

**`market-regime`** · daily · no-api-basic · beginner

**何时使用:** The shared risk layer for every trading day. Use before considering new swing-trade risk to decide today's exposure posture (allow / restrict / cash-priority) from breadth, uptrend participation, and top-risk signals. Operationalized daily by the market-regime-daily workflow.

**何时不要使用:** Do not treat this bundle's output as a standalone buy/sell signal — the exposure decision is a posture, not a directive. Do not skip it and run swing-opportunity work directly; the regime gate comes first.

**目标用户:** `part-time-swing-trader`, `growth-investor`

**必需技能:** `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach`

**推荐技能:** `market-top-detector`, `macro-regime-detector`

**可选技能:** `breadth-chart-analyst`, `sector-analyst`, `market-environment-analysis`, `market-news-analyst`, `downtrend-duration-analyzer`, `us-market-bubble-detector`

**相关工作流:** `market-regime-daily`

---

## Swing Opportunity {#swing-opportunity}

**`swing-opportunity`** · daily · fmp-required · intermediate

**何时使用:** The satellite swing sleeve: generate and validate swing-trade candidates and build risk-sized entry plans. Use only on days the market-regime sleeve has allowed new risk. Operationalized by the swing-opportunity-daily workflow (prerequisite: market-regime-daily exposure decision).

**何时不要使用:** Do not run when the latest market-regime exposure decision is cash-priority or restrictive. Do not use the screeners standalone without the regime gate and position sizing.

**目标用户:** `part-time-swing-trader`

**必需技能:** `vcp-screener`, `technical-analyst`, `position-sizer`, `trader-memory-core`

**推荐技能:** `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**可选技能:** `stockbee-momentum-burst-screener`, `finviz-screener`

**相关工作流:** `swing-opportunity-daily`

---

## Trade Memory {#trade-memory}

**`trade-memory`** · event-driven · no-api-basic · beginner

**何时使用:** The shared learning loop: record closed-trade outcomes, run postmortems, and feed lessons back into the process. Use after every closed position and for the monthly performance retrospective. Operationalized by the trade-memory-loop (per closed trade) and monthly-performance-review (monthly) workflows.

**何时不要使用:** Do not run before a position is closed — update an open thesis with trader-memory-core directly instead. Do not skip the loop after a closed trade, even on winners.

**目标用户:** `part-time-swing-trader`, `long-term-investor`, `growth-investor`

**必需技能:** `trader-memory-core`, `signal-postmortem`

**推荐技能:** `backtest-expert`, `trade-performance-coach`

**可选技能:** `trade-hypothesis-ideator`

**相关工作流:** `trade-memory-loop`, `monthly-performance-review`

---
