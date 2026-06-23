---
layout: default
title: "Parabolic Short Trade Planner"
grand_parent: 简体中文
parent: 技能指南
nav_order: 39
lang_peer: /en/skills/parabolic-short-trade-planner/
permalink: /zh/skills/parabolic-short-trade-planner/
generated: false
---

# Parabolic Short Trade Planner
{: .no_toc }

筛选美股中的抛物线式衰竭形态,生成条件性的盘前做空计划,再根据实时 5 分钟K线评估盘中触发是否成立。第一阶段是每日 5 因子打分器(MA 偏离度 / 加速度 / 成交量高潮 / 波动区间扩张 / 流动性),第二阶段为每个候选股生成 ORL 跌破 / 首根 5 分钟阴线 / VWAP 失守三套计划,并附带明确的可借股 / SSR / 人工确认门槛,第三阶段是单次运行的盘中有限状态机,用于检测触发是否成立并解析出具体股数。覆盖第一、第二、第三阶段。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/parabolic-short-trade-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/parabolic-short-trade-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

为美股生成 Qullamaggie 风格的抛物线做空(Parabolic Short)观察名单,以及条件性的盘前交易计划。本技能从不发送订单,只输出 JSON + Markdown,供交易者在入场前与券商核对。

分为三个阶段:

- **第一阶段(`screen_parabolic.py`)**:从 FMP 拉取日线 K 线和公司概况数据,应用(区分模式的)硬性失效规则,对幸存标的按 5 个因子(权重 30/25/20/15/10)打分,并给出 A/B/C/D 等级。
- **第二阶段(`generate_pre_market_plan.py`)**:读取第一阶段的 JSON,按 `--tradable-min-grade`(默认 `B`)筛选,检查 Alpaca 的可借股库存(或 `ManualBrokerAdapter`),依据继承的前一交易日收盘价评估 SEC Rule 201(SSR)状态,并为每个候选股生成三套触发计划。
- **第三阶段(`monitor_intraday_trigger.py`)**:读取第二阶段的计划,获取 5 分钟K线(Alpaca 实时数据或测试夹具),将每个计划的有限状态机向前推进一步,持久化每个计划的状态,并写出包含 `state`、`entry_actual`、`stop_actual`、以及(触发时的)`shares_actual` 的 `intraday_monitor` JSON。这是单次运行——交易者通过 `watch` 或定时任务每 1-5 分钟运行一次;由于具备重放确定性,重复运行会得到逐字节一致的结果。

---

## 2. 使用时机

在用户想要以下操作时调用本技能:

- 基于标普 500(或自定义 CSV)构建每日抛物线做空观察名单。
- 把观察名单转化为带有明确可借股 / SSR / 状态上限门槛的盘前交易计划。
- 在 Alpaca 下单前,审核某候选股的人工确认理由中哪些属于阻断性、哪些只是参考性。

**不要**在以下场景调用本技能:

- 多头动量筛选——请使用 vcp-screener 或 canslim-screener。
- 1 分钟以下的超短线盘中信号——第三阶段只评估 5 分钟K线。
- 实盘订单路由——本技能在设计上只做检测;第三阶段会给出 `triggered` 状态以及具体的入场价/止损价/股数,但下单动作必须由交易者手动完成。

---

## 3. 前提条件

- 需要 **FMP API 密钥**(环境变量 `FMP_API_KEY`)
- 筛选环节使用 FMP;Alpaca 为可选项(直接用 `requests`,无需 SDK)。若没有配置 Alpaca,每个候选股都会被标记为 `plan_status: watch_only`
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
```

---

## 5. 工作流

### 第一阶段——每日筛选器

1. 确认已设置 `FMP_API_KEY`(环境变量或 `--api-key`)。
2. 以更安全的默认模式运行:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
   ```
3. 查看 `reports/parabolic_short_<date>.md`——观察名单按等级(A→D)分组呈现。
4. 把感兴趣的标的提升至第二阶段。

对于小盘股的爆发式行情,切换到 `--mode classic_qm`(市值与日均成交量下限更宽松,5 日涨幅阈值更高)。

如果想在不调用 API 的情况下测试,可对 JSON 测试夹具运行 `--dry-run --fixture <path>`(仓库已内置一份位于 `scripts/tests/fixtures/dry_run_minimal.json`)。

### 第二阶段——盘前计划生成器

1. 可选:设置 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` 以进行实时可借股检查。若未设置,计划生成器会回退到 `ManualBrokerAdapter`,把每个候选股标记为 `borrow_inventory_unavailable` / `plan_status: watch_only`。
2. 运行:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
     --candidates-json reports/parabolic_short_2026-04-30.json \
     --account-size 100000 --risk-bps 50 --output-dir reports/
   ```
3. 输出:`reports/parabolic_short_plan_<date>.json`。每份计划包含三套入场方案(5 分钟 ORL 跌破、首根 5 分钟阴线、VWAP 失守),并附带 `entry_hint` / `stop_hint` 公式字符串(不预先写入股数——交易者在触发时刻根据 `shares_formula` 自行计算股数)。

### 第三阶段——盘中触发监控

1. 确认已设置 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`(第三阶段使用 Alpaca 行情数据;`data.alpaca.markets` 同时适用于模拟和实盘账户)。
2. 在美股正常交易时段内,按固定节奏单次运行——典型做法是开盘后前 30 分钟每 60 秒运行一次,之后每 5 分钟运行一次:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/monitor_intraday_trigger.py \
     --plans-json reports/parabolic_short_plan_2026-05-05.json \
     --bars-source alpaca \
     --state-dir state/parabolic_short/ \
     --output-dir reports/
   ```
   或者用 `watch -n 60 'python3 ...'` 或定时任务包裹运行。
3. 输出:`reports/parabolic_short_intraday_<date>.json` 列出每个被监控的计划,包含 `state`(`armed` / `triggered` / `invalidated` / 或其他有限状态机特有状态)、由K线推导出的状态转换时间戳,以及触发时的 `size_recipe_resolved`(具体的 `shares_actual`)。
4. 如果想在不调用 API 的情况下测试,可对 JSON 测试夹具(`scripts/tests/fixtures/intraday_bars/`)使用 `--bars-source fixture --bars-fixture <path>`。

第三阶段是**幂等的**:每次运行都会从开盘起完整重放当日K线直到 `now_et`(或 `--now-et` 覆盖值),因此在同一分钟内重复运行会得到相同的状态。`prior_state` 仅用于差异对比/通知展示,绝不会推动状态机前进。

### 入场前如何审核一份计划

每个标的需要查看三个顶层字段:

- `plan_status`:`actionable`(人工门槛可以被清除)或 `watch_only`(存在硬性阻断——可借股不可用或 SSR 生效中)。
- `blocking_manual_reasons`:必须在扣动扳机前全部解决。
- `advisory_manual_reasons`:仅作提醒,例如 `manual_locate_required`(始终存在)、`warning:too_early_to_short`。

---

## 6. 资源

**参考文档(References):**

- `skills/parabolic-short-trade-planner/references/broker_capability_matrix.md`
- `skills/parabolic-short-trade-planner/references/intraday_trigger_playbook.md`
- `skills/parabolic-short-trade-planner/references/parabolic_short_methodology.md`
- `skills/parabolic-short-trade-planner/references/short_invalidation_rules.md`
- `skills/parabolic-short-trade-planner/references/short_risk_management.md`
- `skills/parabolic-short-trade-planner/references/smoke_test_runbook.md`
- `skills/parabolic-short-trade-planner/references/smoke_universe_diverse.csv`
- `skills/parabolic-short-trade-planner/references/smoke_universe_relaxed.csv`

**脚本(Scripts):**

- `skills/parabolic-short-trade-planner/scripts/bar_normalizer.py`
- `skills/parabolic-short-trade-planner/scripts/broker_short_inventory_adapter.py`
- `skills/parabolic-short-trade-planner/scripts/check_live_apis.py`
- `skills/parabolic-short-trade-planner/scripts/fmp_client.py`
- `skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_size_resolver.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_state_machine.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_state_store.py`
- `skills/parabolic-short-trade-planner/scripts/invalidation_rules.py`
- `skills/parabolic-short-trade-planner/scripts/manual_reasons.py`
- `skills/parabolic-short-trade-planner/scripts/market_clock.py`
- `skills/parabolic-short-trade-planner/scripts/math_helpers.py`
- `skills/parabolic-short-trade-planner/scripts/monitor_intraday_trigger.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_report_generator.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_scorer.py`
- `skills/parabolic-short-trade-planner/scripts/screen_parabolic.py`
- `skills/parabolic-short-trade-planner/scripts/size_recipe_builder.py`
- `skills/parabolic-short-trade-planner/scripts/ssr_state_tracker.py`
- `skills/parabolic-short-trade-planner/scripts/state_caps.py`
- `skills/parabolic-short-trade-planner/scripts/vwap.py`
