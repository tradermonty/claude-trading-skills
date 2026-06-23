---
layout: default
title: "Market Environment Analysis"
grand_parent: 简体中文
parent: 技能指南
nav_order: 35
lang_peer: /en/skills/market-environment-analysis/
permalink: /zh/skills/market-environment-analysis/
generated: false
---

# Market Environment Analysis
{: .no_toc }

全面的市场环境分析与报告工具。分析全球市场,包括美国、欧洲、亚洲市场、外汇、商品及经济指标。提供风险偏好(risk-on/risk-off)评估、板块分析,以及技术指标解读。可由以下关键词触发:market analysis、market environment、global markets、trading environment、market conditions、investment climate、market sentiment、forex analysis、stock market analysis、相場環境、市場分析、マーケット状況、投資環境。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-environment-analysis.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-environment-analysis){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Market Environment Analysis 技能用于对全球市场环境进行综合分析与报告,涵盖美国、欧洲、亚洲市场、外汇、商品以及经济指标,提供风险偏好评估、板块分析与技术指标解读。

---

## 2. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 3. 快速开始

```bash
1. 执行摘要(3-5 个要点)
2. 全球市场概览
   - 美国市场
   - 亚洲市场
   - 欧洲市场
3. 外汇与商品走势
4. 重要事件与经济指标
5. 风险因素分析
6. 投资策略启示
```

---

## 4. 工作流

### 1. 初始数据收集
使用 web_search 工具收集最新市场数据:
1. 主要股票指数(标普 500、纳斯达克、道琼斯、日经 225、上证综指、恒生指数)
2. 外汇汇率(美元/日元、欧元/美元,主要货币对)
3. 商品价格(WTI 原油、黄金、白银)
4. 美国国债收益率(2 年期、10 年期、30 年期)
5. VIX 指数(恐慌指数)
6. 市场交易状态(开盘/收盘/当前数值)

### 2. 市场环境评估
基于收集到的数据评估以下内容:
- **趋势方向**:上升趋势 / 下降趋势 / 区间震荡
- **风险偏好**:风险偏好(risk-on) / 风险规避(risk-off)
- **波动状态**:由 VIX 反映的市场恐慌程度
- **板块轮动**:资金流向何处

### 3. 报告结构

#### 标准报告格式:
```
1. 执行摘要(3-5 个要点)
2. 全球市场概览
   - 美国市场
   - 亚洲市场
   - 欧洲市场
3. 外汇与商品走势
4. 重要事件与经济指标
5. 风险因素分析
6. 投资策略启示
```

---

## 5. 资源

**参考文档(References):**

- `skills/market-environment-analysis/references/analysis_patterns.md`
- `skills/market-environment-analysis/references/indicators.md`

**脚本(Scripts):**

- `skills/market-environment-analysis/scripts/market_utils.py`
