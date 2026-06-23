---
layout: default
title: "Downtrend Duration Analyzer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 15
lang_peer: /en/skills/downtrend-duration-analyzer/
permalink: /zh/skills/downtrend-duration-analyzer/
generated: false
---

# Downtrend Duration Analyzer
{: .no_toc }

分析历史下跌趋势的持续时间,生成交互式 HTML 直方图,展示按板块和市值划分的典型回调时长。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/downtrend-duration-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/downtrend-duration-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

分析历史价格数据以识别下跌趋势区间(从波峰到波谷),并构建回调持续时间的统计分布。生成按板块和市值细分的交互式 HTML 直方图可视化结果,帮助交易者理解典型的恢复周期,从而为均值回归策略设定合理的预期。

---

## 2. 使用时机

- 交易者询问某个板块或市值层级的典型回调时长
- 用户想了解历史回撤的恢复时间
- 构建均值回归或逢低买入策略,需要合理的持仓周期估算
- 比较不同市场细分领域的回调行为差异
- 设定止损时限或持仓周期上限

---

## 3. 前提条件

- Python 3.9+
- FMP API 密钥(设置 `FMP_API_KEY` 环境变量,或使用 `--api-key`)
- 所需软件包:`requests`、`pandas`、`numpy`(标准数据分析工具栈)

---

## 4. 快速开始

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:获取历史价格数据

运行分析脚本,获取一组股票的 OHLC 数据并识别下跌趋势区间。

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

### 步骤 2:分析下跌趋势持续时间

脚本会自动执行以下操作:
1. 使用滚动窗口分析识别局部波峰和波谷
2. 计算每段下跌趋势的持续时间(交易日数)和深度(下跌百分比)
3. 按板块和市值层级(超大盘、大盘、中盘、小盘)对结果进行分组
4. 计算汇总统计量(中位数、均值、百分位数)

### 步骤 3:生成交互式 HTML 可视化

```bash
python3 skills/downtrend-duration-analyzer/scripts/generate_histogram_html.py \
  --input reports/downtrend_analysis_*.json \
  --output-dir reports/
```

这会生成一个交互式 HTML 文件,包含:
- 下跌趋势持续时间的直方图
- 板块和市值筛选器
- 带百分位信息的悬停提示
- 汇总统计表

### 步骤 4:解读分布洞察

加载生成的 Markdown 报告以解读分析结果:
- **短期回调(5-15 天)**:上升趋势中的典型回撤
- **中期回调(15-40 天)**:常见的板块轮动
- **长期回调(40 天以上)**:趋势反转或熊市

---

## 6. 资源

**参考文档(References):**

- `skills/downtrend-duration-analyzer/references/downtrend_methodology.md`

**脚本(Scripts):**

- `skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py`
- `skills/downtrend-duration-analyzer/scripts/generate_histogram_html.py`
