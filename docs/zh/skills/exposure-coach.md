---
layout: default
title: "Exposure Coach"
grand_parent: 简体中文
parent: 技能指南
nav_order: 27
lang_peer: /en/skills/exposure-coach/
permalink: /zh/skills/exposure-coach/
generated: false
---

# Exposure Coach
{: .no_toc }

整合宽度(breadth)、市场环境(regime)和资金流向分析类技能的信号,生成一页式的"市场姿态"(Market Posture)摘要,涵盖净敞口上限、成长股与价值股偏向、市场参与广度,以及"允许新建仓位"与"优先持有现金"之间的建议。
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/exposure-coach.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/exposure-coach){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Exposure Coach 将 market-breadth-analyzer、uptrend-analyzer、macro-regime-detector、market-top-detector、ftd-detector、theme-detector、sector-analyst 以及 institutional-flow-tracker 等技能的输出整合为统一的"控制层"决策。本技能回答的是个人交易者在进行任何具体选股分析之前最核心的问题:"现在我应该把多少资金投入股票市场?"

---

## 2. 使用时机

- 在建立任何新股票仓位之前,用于确定合适的资金投入比例
- 在每个交易周开始时,用于校准组合敞口
- 当多个市场信号相互矛盾,需要一个统一的姿态判断时
- 在重大宏观事件或市场事件之后,重新评估敞口上限
- 在市场环境(扩散、集中、收缩)切换之际

---

## 3. 前提条件

- Python 3.9+
- FMP API 密钥(设置 `FMP_API_KEY` 环境变量),用于获取 institutional-flow-tracker 的数据
- 来自上游技能的输入 JSON 文件(见"工作流"第 1 步)
- 标准库 + `argparse`、`json`、`datetime`

---

## 4. 快速开始

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth reports/breadth_latest.json \
  --uptrend reports/uptrend_latest.json \
  --regime reports/regime_latest.json \
  --top-risk reports/top_risk_latest.json \
  --ftd reports/ftd_latest.json \
  --theme reports/theme_latest.json \
  --sector reports/sector_latest.json \
  --institutional reports/institutional_latest.json \
  --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:收集上游技能的输出

收集来自各集成技能的最新 JSON 输出。每个文件提供一个特定的信号维度:

| 技能 | 输出文件模式 | 提供的信号 |
|-------|---------------------|-----------------|
| market-breadth-analyzer | `breadth_*.json` | 涨跌比率、新高/新低数量 |
| uptrend-analyzer | `uptrend_*.json` | 上升趋势参与度百分比 |
| macro-regime-detector | `regime_*.json` | 当前市场环境(集中、扩散等) |
| market-top-detector | `top_risk_*.json` | 派发日(distribution day)数量、顶部概率评分 |
| ftd-detector | `ftd_*.json` | 未结清交割(Failure-to-Deliver)异常 |
| theme-detector | `theme_*.json` | 活跃投资主题及轮动情况 |
| sector-analyst | `sector_*.json` | 板块表现排名 |
| institutional-flow-tracker | `institutional_*.json` | 机构净买入/净卖出情况 |

### 步骤 2:运行敞口评分引擎

执行敞口评分脚本,并传入上游输出文件的路径:

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth reports/breadth_latest.json \
  --uptrend reports/uptrend_latest.json \
  --regime reports/regime_latest.json \
  --top-risk reports/top_risk_latest.json \
  --ftd reports/ftd_latest.json \
  --theme reports/theme_latest.json \
  --sector reports/sector_latest.json \
  --institutional reports/institutional_latest.json \
  --output-dir reports/
```

该脚本支持部分输入;缺失文件会降低置信度,但不会阻断执行。

### 步骤 3:解读市场姿态摘要

查看生成的姿态报告,其中包含:

1. **敞口上限(Exposure Ceiling)** —— 建议的最高股票配置比例(0-100%)
2. **偏向方向(Bias Direction)** —— 基于市场环境和资金流向判断的成长股/价值股倾向
3. **参与度评估(Participation Assessment)** —— 市场是广泛参与(健康)还是狭窄参与(脆弱)
4. **行动建议(Action Recommendation)** —— NEW_ENTRY_ALLOWED(允许新建仓位)、REDUCE_ONLY(仅减仓)或 CASH_PRIORITY(现金优先)
5. **置信度等级(Confidence Level)** —— 基于输入数据完整度划分的 HIGH(高)、MEDIUM(中)或 LOW(低)

### 步骤 4:应用敞口指导建议

将姿态建议映射为组合层面的具体操作:

| 建议 | 操作 |
|----------------|--------|
| NEW_ENTRY_ALLOWED | 可继续进行个股分析并建立新仓位 |
| REDUCE_ONLY | 不建立新仓位;在反弹时减持现有仓位 |
| CASH_PRIORITY | 积极提高现金比例;避免任何新的资金投入 |

---

## 6. 资源

**参考文档(References):**

- `skills/exposure-coach/references/exposure_framework.md`
- `skills/exposure-coach/references/regime_exposure_map.md`

**脚本(Scripts):**

- `skills/exposure-coach/scripts/calculate_exposure.py`
