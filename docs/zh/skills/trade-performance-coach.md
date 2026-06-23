---
layout: default
title: "Trade Performance Coach"
grand_parent: 简体中文
parent: 技能指南
nav_order: 53
lang_peer: /en/skills/trade-performance-coach/
permalink: /zh/skills/trade-performance-coach/
generated: false
---

# Trade Performance Coach
{: .no_toc }

针对已平仓交易、部分止盈/止损以及月度交易汇总,审查流程遵循度、风险纪律、执行质量,并基于证据识别交易行为模式。在 trader-memory-core 与 signal-postmortem 已经产出记录之后使用,或当用户需要交易后教练式复盘、风险经理视角的审查、规则遵循度审查、下一交易日的操作规则,或具有心理学视角的交易行为反馈时使用。本技能不提供买卖建议、心理治疗,也不执行券商下单。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trade-performance-coach.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-performance-coach){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Trade Performance Coach 审查已记录的交易结果与交易日志证据,帮助交易者改进自己的决策流程。它把已平仓交易记录、复盘(postmortem)发现、风险规则,以及可选的市场环境(regime)背景信息,转化为一份基于证据的教练式报告,内容涵盖:

- 流程遵循度
- 风险纪律
- 执行质量
- 可能存在的交易行为模式
- 下一交易日的操作规则
- 用于反思的教练式提问

本技能旨在填补专业交易环境中风险经理、交易台主管或交易教练所承担的支持性角色。它严格定位为流程审查类技能:从不就具体证券的买入、卖出、做空、持有或仓位规模给出建议。

---

## 2. 使用时机

在以下任一情况下使用本技能:

- 某笔交易已平仓,用户想要一份交易后的教练式复盘。
- 发生了部分平仓,用户想检查仓位规模、止损或离场行为是否合理。
- 用户已有 `trader-memory-core` 的论点(thesis)记录和 `signal-postmortem` 的复盘发现,想要得到下一交易日的操作规则。
- 用户想对反复出现的流程、风险、执行或行为模式做月度复盘。
- 用户希望以风险经理的视角审查自己记录下的交易。
- 用户想知道某笔亏损属于流程错误、执行错误、市场环境问题,还是可接受的正常波动。
- 用户想根据证据,标记出可能存在的 FOMO(追涨杀跌焦虑)、报复性交易、过度自信、犹豫不决、随意移动止损,或仓位规模逐渐膨胀(size creep)等行为模式。

---

## 3. 前提条件

推荐的上游记录:

- `trader-memory-core` 的已平仓论点记录或交易日志条目
- `signal-postmortem` 的复盘发现
- 原始交易计划或交易票据(trade ticket)
- 实际的入场 / 离场 / 部分平仓操作记录
- 用户自定义的风险计划(如有)
- 可选的 `market-regime-daily` / `exposure-coach` 背景信息

无需付费 API 密钥。该确定性脚本基于本地 JSON / 类 YAML 记录运行。

---

## 4. 快速开始

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input reports/trade_memory/closed_thesis_EXMPL.json \
  --output-dir reports/trade-performance-coach
```

---

## 5. 工作流

### 步骤 1 — 收集源记录

收集最近的已平仓交易记录、复盘报告、风险计划和交易日志笔记。

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input reports/trade_memory/closed_thesis_EXMPL.json \
  --output-dir reports/trade-performance-coach
```

### 步骤 2 — 评估流程遵循度

将实际操作与用户记录的计划和规则进行对比。检查以下问题:

- 入场前缺少论点记录
- 跳过了设置确认环节
- 在市场环境(market-regime)闸门不通过的情况下仍进行了交易
- 在没有预设规则的情况下移动了止损
- 离场 / 部分平仓与计划不一致
- 记录质量不完整

### 步骤 3 — 评估风险纪律

将实际风险敞口和持仓热度与风险计划进行对比。检查以下问题:

- 单笔交易风险超过上限
- 组合整体持仓热度超过上限
- 单周亏损或连续亏损后风险持续升级
- 在盈利或亏损之后下了超大仓位
- 如有提供数据,检查相关性敞口

### 步骤 4 — 评估执行质量

对入场、止损、离场、加仓、减仓和复盘行为进行分类,把"流程正确但仍亏损"与"执行失误"区分开来。

### 步骤 5 — 识别可能的行为模式

利用交易日志笔记和操作标记中的证据,标注可能存在的交易行为模式。标签必须始终与具体证据相对应,并使用非诊断性的措辞。

支持的 MVP(最小可行产品)标签:

- `fomo_entry`(FOMO 追涨入场)
- `revenge_trade`(报复性交易)
- `premature_exit`(过早离场)
- `overconfidence_after_winner`(盈利后过度自信)
- `stop_moved`(随意移动止损)
- `size_creep`(仓位规模膨胀)
- `hesitation`(犹豫不决)
- `rule_drift`(规则漂移)
- `no_pattern_detected`(未检测到明显模式)

### 步骤 6 — 生成下一交易日操作规则

把发现转化为临时的、具体的护栏规则。例如:

- 要求在下一次入场前补全论点记录和截图
- 在出现规则违反后,将接下来两笔交易的风险上限设为 0.5R
- 在反复出现报复性交易证据后,切换为仅复盘模式
- 不要追涨错过的入场机会;将其加入观察列表,等待下一个有效设置

### 步骤 7 — 人工决策闸门

每份报告结尾都必须设置一个人工决策闸门。默认动作为 `journal_only`(仅记录日志)。

允许的动作:

```text
accept_rules / modify_rules / defer / journal_only
```

---

## 6. 资源

**参考文档(References):**

- `skills/trade-performance-coach/references/behavior-tags.md`
- `skills/trade-performance-coach/references/hermes-integration.md`
- `skills/trade-performance-coach/references/output-contract.md`
- `skills/trade-performance-coach/references/review-framework.md`
- `skills/trade-performance-coach/references/risk-review-checklist.md`

**脚本(Scripts):**

- `skills/trade-performance-coach/scripts/review_trade_performance.py`
