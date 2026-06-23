---
layout: default
title: "Earnings Trade Analyzer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 18
lang_peer: /en/skills/earnings-trade-analyzer/
permalink: /zh/skills/earnings-trade-analyzer/
generated: false
---

# Earnings Trade Analyzer
{: .no_toc }

使用 5 因子评分体系(跳空幅度、财报前趋势、成交量趋势、200 日均线位置、50 日均线位置)分析近期财报后的股票表现。为每只股票打出 0-100 的评分,并赋予 A/B/C/D 等级。当用户询问财报交易分析、财报后动量筛选、财报跳空评分,或想找出近期最佳财报反应股票时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/earnings-trade-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/earnings-trade-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Earnings Trade Analyzer —— 财报后 5 因子评分体系

---

## 2. 使用时机

- 用户请求财报后交易分析或财报跳空筛选
- 用户想找出近期最佳的财报反应股票
- 用户请求财报动量评分或分级
- 用户询问财报后吸筹日(PEAD,Post-Earnings Accumulation Day)候选标的

---

## 3. 前提条件

- FMP API 密钥(设置 `FMP_API_KEY` 环境变量,或传入 `--api-key`)
- 免费档(每天 250 次调用)足以满足默认筛选需求(回溯 2 天,取前 20 名)
- 若需更大的回溯窗口或完整筛选,建议使用付费档

---

## 4. 快速开始

```bash
# 默认:回溯 2 天,取前 20 个结果
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --output-dir reports/

# 自定义参数并应用入场质量过滤
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 3 --top 10 --max-api-calls 200 \
  --apply-entry-filter --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:运行 Earnings Trade Analyzer

执行分析脚本:

```bash
# 默认:回溯最近 2 天的财报,取前 20 个结果
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py --output-dir reports/

# 自定义回溯天数和市值过滤条件
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 5 \
  --min-market-cap 1000000000 \
  --top 30 \
  --output-dir reports/

# 应用入场质量过滤
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --apply-entry-filter \
  --output-dir reports/
```

### 步骤 2:查看结果

1. 阅读生成的 JSON 和 Markdown 报告
2. 加载 `references/scoring_methodology.md` 以获取评分解读的背景知识
3. 重点关注 A 级和 B 级股票,寻找可操作的交易设置

### 步骤 3:呈现分析结果

针对每个排名靠前的候选标的,呈现以下内容:
- 综合评分与字母等级(A/B/C/D)
- 财报跳空幅度与方向
- 财报前 20 日趋势
- 成交量比率(20 日均量 vs 60 日均量)
- 相对于 200 日和 50 日均线的位置
- 评分体系中最弱与最强的分量

### 步骤 4:提供可操作的指导建议

根据等级给出建议:
- **A 级(85 分以上):** 财报反应强劲,伴随机构吸筹 —— 可考虑入场
- **B 级(70-84 分):** 财报反应良好,值得关注 —— 等待回调或确认信号
- **C 级(55-69 分):** 信号混杂 —— 谨慎对待,需进一步分析
- **D 级(低于 55 分):** 设置较弱 —— 回避,或等待更好的条件出现

---

## 6. 资源

**参考文档(References):**

- `skills/earnings-trade-analyzer/references/scoring_methodology.md`

**脚本(Scripts):**

- `skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py`
- `skills/earnings-trade-analyzer/scripts/fmp_client.py`
- `skills/earnings-trade-analyzer/scripts/report_generator.py`
- `skills/earnings-trade-analyzer/scripts/scorer.py`
