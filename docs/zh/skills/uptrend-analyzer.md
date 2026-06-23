---
layout: default
title: "Uptrend Analyzer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 56
lang_peer: /en/skills/uptrend-analyzer/
permalink: /zh/skills/uptrend-analyzer/
generated: false
---

# Uptrend Analyzer
{: .no_toc }

使用 Monty 的 Uptrend Ratio Dashboard 数据分析市场宽度,诊断当前市场环境。由 5 个分量(宽度、板块参与度、轮动、动量、历史背景)生成 0-100 的综合评分。当你想了解市场宽度、上升趋势比率,或当前市场环境是否支持持有股票时使用。无需 API 密钥。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/uptrend-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/uptrend-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Uptrend Analyzer 技能使用 Monty 的上升趋势比率仪表盘(Uptrend Ratio Dashboard)数据量化市场宽度的健康度,并把它浓缩为一个 0-100 的综合评分,用以判断当前市场环境是否适合承担股票敞口。

---

## 2. 使用时机

- 用户问“市场宽度健康吗?”或“这波上涨的广度有多大?”
- 用户想评估各板块的上升趋势比率
- 用户询问市场参与度或宽度状况
- 用户需要基于宽度分析的敞口建议
- 用户提到 Monty 的 Uptrend Dashboard 或上升趋势比率

---

## 3. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 4. 快速开始

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

---

## 5. 工作流

### 阶段 1:执行 Python 脚本

运行分析脚本(无需 API 密钥):

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

脚本会:
1. 从 Monty 的 GitHub 仓库下载 CSV 数据
2. 计算 5 个分量评分
3. 生成综合评分与报告

### 阶段 2:呈现结果

把生成的 Markdown 报告呈现给用户,重点突出:
- 综合评分与区间分类
- 敞口建议(满仓 / 正常 / 减仓 / 防御 / 保本)
- 显示最强与最弱板块的板块热力图
- 关键动量与轮动信号

---

## 6. 资源

**参考文档(References):**

- `skills/uptrend-analyzer/references/uptrend_methodology.md`

**脚本(Scripts):**

- `skills/uptrend-analyzer/scripts/data_fetcher.py`
- `skills/uptrend-analyzer/scripts/report_generator.py`
- `skills/uptrend-analyzer/scripts/scorer.py`
- `skills/uptrend-analyzer/scripts/uptrend_analyzer.py`
