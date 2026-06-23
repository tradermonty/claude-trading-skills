---
layout: default
title: "Kanchi Dividend SOP"
grand_parent: 简体中文
parent: 技能指南
nav_order: 32
lang_peer: /en/skills/kanchi-dividend-sop/
permalink: /zh/skills/kanchi-dividend-sop/
generated: false
---

# Kanchi Dividend SOP
{: .no_toc }

把 Kanchi 式股息投资法转化为可重复执行的美股操作流程。当用户提到かんち式配当投資(Kanchi 式股息投资)、股息筛选、股息增长质量检查、PER×PBR 在美股板块的适配、回调限价单规划,或单页个股备忘录撰写时使用。覆盖筛选、深度研究、入场规划与买入后的监控节奏。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-sop.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-sop){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

将 Kanchi 的五步法实现为一套确定性工作流,用于美股股息投资。
该方法优先考虑安全性与可重复性,而不是激进追逐高股息率。

---

## 2. 使用时机

当用户需要以下内容时使用本技能:
- 把 Kanchi 式选股法适配到美股的股息选股流程。
- 一套可重复的筛选与回调入场流程,而不是临时拍脑袋选股。
- 带有明确失效条件的单页核保备忘录。
- 用于后续监控以及税务/账户归属工作流的交接材料包。

---

## 3. 前提条件

### API 密钥设置

入场信号脚本需要 FMP API 访问权限:

```bash
export FMP_API_KEY=your_api_key_here
```

### 输入数据来源

运行工作流前,准备以下任一输入:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` 的输出。
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` 的输出。
3. 用户提供的股票代码清单(券商导出或手动列表)。

如需生成确定性产出文件,提供股票代码运行:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_sop_plan.py \
  --tickers "JNJ,PG,KO" \
  --output-dir reports/
```

如需第五步入场时机相关产出文件:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_entry_signals.py \
  --tickers "JNJ,PG,KO" \
  --alpha-pp 0.5 \
  --output-dir reports/
```

---

## 4. 快速开始

### 1) 筛选前先确定投资目标

先收集并锁定以下参数:
- 目标:当前现金收益 vs 股息增长。
- 最大持仓数量与单仓位规模上限。
- 允许的投资品种:仅个股,还是包含 REIT/BDC/ETF。
- 偏好的账户类型背景:应税账户 vs 类 IRA 账户。

---

## 5. 工作流

### 1) 筛选前先确定投资目标

先收集并锁定以下参数:
- 目标:当前现金收益 vs 股息增长。
- 最大持仓数量与单仓位规模上限。
- 允许的投资品种:仅个股,还是包含 REIT/BDC/ETF。
- 偏好的账户类型背景:应税账户 vs 类 IRA 账户。

加载 `references/default-thresholds.md` 并应用其中的基线设置,除非用户另有要求。

### 2) 构建可投资股票池

从质量优先的股票池开始构建:
- 核心仓:长期股息增长标的(例如类似股息贵族的优质股票集合)。
- 卫星仓:高股息率板块(公用事业、电信、REIT),单独划入一个风险仓位类别。

按以下明确的优先级顺序收集股票代码:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` 的输出(FMP/FINVIZ)。
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` 的输出。
3. 当 API 不可用时,使用用户提供的券商导出文件或手动股票代码清单。

在进入下一步之前,返回按仓位类别分组的股票代码列表。

### 3) 应用 Kanchi 第一步(带陷阱标记的股息率筛选)

主规则:
- `forward_dividend_yield >= 3.5%`

陷阱控制:
- 将极端高股息率(`>= 8%`)标记为 `deep-dive-required`(需要深入研究)。
- 将派息突增标记为可能的特别股息伪影。

输出:
- 每只股票的 `PASS` 或 `FAIL` 结果。
- 针对潜在股息陷阱的 `deep-dive-required` 标记。

### 4) 应用 Kanchi 第二步(增长与安全性)

要求:
- 营收与 EPS 趋势在多年期视角下为正。
- 在复核期内股息趋势不下降。

增加安全性检查:
- 派息率与自由现金流派息率处于合理区间。
- 债务负担与利息覆盖率没有恶化。

当趋势喜忧参半但尚未破坏时,归类为 `HOLD-FOR-REVIEW`(待复核),而不是直接淘汰。

### 5) 应用 Kanchi 第三步(估值)并适配美股板块

使用 `references/valuation-and-one-off-checks.md`,并应用针对板块的估值逻辑:
- 金融股:`PER × PBR` 仍可作为主要指标。
- REIT:使用 `P/FFO` 或 `P/AFFO`,而非单纯的 `P/E`。
- 轻资产板块:结合远期 `P/E`、`P/FCF` 与历史区间综合判断。

务必为每只股票记录所使用的估值方法。

### 6) 应用 Kanchi 第四步(一次性事件筛查)

剔除或降级那些近期利润依赖一次性因素的标的:
- 资产出售收益、诉讼和解、税务一次性影响。
- 利润率突增但销售趋势未能支撑。
- 反复出现“一次性/非经常性”调整项。

为每个 `FAIL` 记录一句话证据,以保持可审计性。

### 7) 应用 Kanchi 第五步(按规则逢低买入)

以机械化方式设置入场触发条件:
- 股息率触发:当前股息率高于近 5 年平均股息率 + alpha(默认 `+0.5pp`)。
- 估值触发:达到目标倍数(`P/E`、`P/FFO` 或 `P/FCF`)。

执行模式:
- 拆分订单:`40% -> 30% -> 30%`。
- 每次加仓前要求一句话的理性检查:“论点是否仍然成立,还是出现了结构性破坏”。

### 8) 产出标准化结果

始终产出三份成果:
1. 筛选结果表(`PASS`、`HOLD-FOR-REVIEW`、`FAIL`,并附证据)。
2. 单页个股备忘录(使用 `references/stock-note-template.md`)。
3. 限价单计划,包含拆分规模与失效条件。

---

## 6. 资源

**参考文档(References):**

- `skills/kanchi-dividend-sop/references/default-thresholds.md`
- `skills/kanchi-dividend-sop/references/stock-note-template.md`
- `skills/kanchi-dividend-sop/references/valuation-and-one-off-checks.md`

**脚本(Scripts):**

- `skills/kanchi-dividend-sop/scripts/build_entry_signals.py`
- `skills/kanchi-dividend-sop/scripts/build_sop_plan.py`
