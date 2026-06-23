---
layout: default
title: "Signal Postmortem"
grand_parent: 简体中文
parent: 技能指南
nav_order: 44
lang_peer: /en/skills/signal-postmortem/
permalink: /zh/skills/signal-postmortem/
generated: false
---

# Signal Postmortem
{: .no_toc }

记录并分析由 edge 流水线及其他技能生成的信号的交易后结果。跟踪假阳性、错失机会与体制错配,并把结果反馈到 edge-signal-aggregator 的权重与技能改进待办。
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/signal-postmortem.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/signal-postmortem){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Signal Postmortem 记录并分析由 edge 流水线、筛选器及其他技能生成的交易信号的结果。它把预测的 edge 方向与 5 日、20 日的已实现收益对比,对结果进行分类(真阳性、假阳性、错失机会、体制错配),并为 edge-signal-aggregator 的权重调整和技能改进待办生成反馈。

---

## 2. 使用时机

- 一笔交易平仓后,你想记录结果
- 复盘一批已到持有期(5 日或 20 日)的信号
- 识别来自特定技能的系统性假阳性模式
- 为 edge-signal-aggregator 的权重校准生成反馈
- 从决策质量指标构建技能改进待办
- 进行周期性(每周/每月)信号质量审计

---

## 3. 前提条件

- Python 3.9+
- FMP API 密钥(可选,用于在未手动提供时获取已实现收益)
- 标准库 + `requests`(用于 API 调用)
- 输入:JSON 格式的信号记录(来自 edge-signal-aggregator 或筛选器输出)

---

## 4. 快速开始

```bash
# 示例:列出已可做事后复盘的信号(满 5 天)
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --list-ready \
  --signals-dir state/signals/ \
  --min-days 5
```

---

## 5. 工作流

### 步骤 1:准备信号记录

收集已平仓或已到期的信号记录。每条记录应包含:
- `signal_id`:唯一标识符
- `ticker`:股票代码
- `signal_date`:信号生成日期
- `predicted_direction`:LONG 或 SHORT
- `source_skill`:由哪个技能生成该信号
- `entry_price`:信号生成时的价格(可选,用于手动覆盖)

```bash
# 示例:列出已可做事后复盘的信号(满 5 天)
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --list-ready \
  --signals-dir state/signals/ \
  --min-days 5
```

### 步骤 2:记录结果

运行 postmortem recorder 获取已实现收益并对结果分类。

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signals-file state/signals/aggregated_signals_2026-03-10.json \
  --holding-periods 5,20 \
  --output-dir reports/
```

手动记录结果(当价格数据已具备时):

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signal-id sig_aapl_20260310_abc \
  --exit-price 178.50 \
  --exit-date 2026-03-15 \
  --outcome-notes "Closed at target, +3.2% in 5 days" \
  --output-dir reports/
```

### 步骤 3:对结果分类

recorder 会自动把每条信号归入以下四类之一:

| 类别 | 定义 |
|------|------|
| TRUE_POSITIVE(真阳性) | 预测方向与已实现收益符号一致 |
| FALSE_POSITIVE(假阳性) | 预测方向与已实现收益相反 |
| MISSED_OPPORTUNITY(错失机会) | 未采纳的信号但本应盈利 |
| REGIME_MISMATCH(体制错配) | 因市场体制变化导致信号失败 |

分类规则记录在 `references/outcome-classification.md` 中。

### 步骤 4:生成反馈文件

为下游消费者生成反馈:

```bash
# 为 edge-signal-aggregator 生成权重调整建议
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --generate-weight-feedback \
  --output-dir reports/

# 生成技能改进待办条目
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --generate-improvement-backlog \
  --output-dir reports/
```

### 步骤 5:查看汇总统计

按技能、按股票、按时间段生成汇总统计:

```bash
python3 skills/signal-postmortem/scripts/postmortem_analyzer.py \
  --postmortems-dir reports/postmortems/ \
  --summary \
  --group-by skill,month \
  --output-dir reports/
```

---

## 6. 资源

**参考文档(References):**

- `skills/signal-postmortem/references/feedback-integration.md`
- `skills/signal-postmortem/references/outcome-classification.md`

**脚本(Scripts):**

- `skills/signal-postmortem/scripts/postmortem_analyzer.py`
- `skills/signal-postmortem/scripts/postmortem_recorder.py`
