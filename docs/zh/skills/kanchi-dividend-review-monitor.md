---
layout: default
title: "Kanchi Dividend Review Monitor"
grand_parent: 简体中文
parent: 技能指南
nav_order: 31
lang_peer: /en/skills/kanchi-dividend-review-monitor/
permalink: /zh/skills/kanchi-dividend-review-monitor/
generated: false
---

# Kanchi Dividend Review Monitor
{: .no_toc }

使用 Kanchi 式强制复核触发器(T1-T5)监控股息投资组合,把异常情况转化为 OK/WARN/REVIEW 三种状态,而不会自动卖出。当用户要求做减配检测、8-K 治理监控、股息安全性监控、REVIEW 队列自动化,或周期性股息风险检查时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-review-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-review-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

检测异常的股息风险信号,并将其导入人工复核队列。
把自动化定位为异常检测,而不是自动化交易执行。

---

## 2. 使用时机

在用户需要以下功能时使用本技能:
- 对股息持仓进行每日/每周/每季度的异常检测。
- 针对 T1-T5 风险触发条件进行强制复核排队。
- 对持仓股票代码进行 8-K/治理相关关键词扫描。
- 在人工做决策之前,先得到确定性的 `OK/WARN/REVIEW` 输出。

---

## 3. 前提条件

提供符合以下规范的标准化输入 JSON:
- `references/input-schema.md`

如果上游数据不可用,至少需要提供:
- `ticker`(股票代码)
- `instrument_type`(工具类型)
- `dividend.latest_regular`(最新常规股息)
- `dividend.prior_regular`(此前常规股息)

---

## 4. 快速开始

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

---

## 5. 工作流

### 1)标准化输入数据集

在一份 JSON 文档中,按股票代码收集以下字段:
- 股息数据点(最新常规股息、此前常规股息、缺失/零值标记)。
- 覆盖率字段(FCF 或 FFO 或 NII、已支付股息、覆盖率历史)。
- 资产负债表趋势字段(净负债、利息覆盖率、回购/股息对比)。
- 文件文本片段(尤其是近期的 8-K 或同等级别的警示文本)。
- 经营趋势字段(营收复合增长率、利润率趋势、业绩指引趋势)。

字段定义和示例数据请参考 `references/input-schema.md`。

### 2)运行规则引擎

运行:

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

脚本会根据 T1-T5 规则,把每个股票代码映射为 `OK/WARN/REVIEW` 之一。
输出文件会以带日期的文件名(例如 `review_queue_20260227.json` 与 `.md`)保存到指定目录。

### 3)优先级排序与去重

如果多个触发条件同时命中:
- 保留全部发现记录,用于审计追溯。
- 最终状态只升级到最高严重级别。
- 把触发原因以单行文字形式存为证据。

### 4)生成人工复核工单

对每个被标记为 `REVIEW` 的股票代码,需包含:
- 触发器 ID 与证据。
- 疑似的失效模式。
- 做出下一步决策前所需的人工核查项。

输出格式请使用 `references/review-ticket-template.md`。

---

## 6. 资源

**参考文档(References):**

- `skills/kanchi-dividend-review-monitor/references/input-schema.md`
- `skills/kanchi-dividend-review-monitor/references/review-ticket-template.md`
- `skills/kanchi-dividend-review-monitor/references/trigger-matrix.md`

**脚本(Scripts):**

- `skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py`
