---
layout: default
title: "Value Dividend Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 57
lang_peer: /en/skills/value-dividend-screener/
permalink: /zh/skills/value-dividend-screener/
generated: false
---

# Value Dividend Screener
{: .no_toc }

筛选美股中同时具备价值特征(P/E 低于 20、P/B 低于 2)、可观股息率(3% 或以上)与持续增长(股息/营收/EPS 三年趋势向上)的高质量股息机会。支持两阶段筛选:先用 FINVIZ Elite API 高效预筛选,再用 FMP API 做详细分析。当用户需要股息股筛选、收益型组合思路,或寻找基本面扎实的高质量价值股时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/value-dividend-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/value-dividend-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能使用**两阶段筛选方法**,识别同时具备价值特征、可观收益能力与持续增长的高质量股息股:

1. **FINVIZ Elite API(可选但推荐)**:用基础条件对股票进行预筛选(速度快、成本低)
2. **Financial Modeling Prep(FMP)API**:对候选股票进行详细基本面分析

基于估值比率、股息指标、财务健康度与盈利能力等量化标准筛选美股,生成按综合质量评分排名、并附详细基本面分析的完整报告。

**效率优势:** 使用 FINVIZ 预筛选可将 FMP API 调用量减少 90%,非常适合使用免费套餐 API 的用户。

---

## 2. 使用时机

在用户提出以下请求时调用本技能:
- “找一些高质量的股息股”
- “筛选价值型股息机会”
- “给我看看股息增长强劲的股票”
- “找估值合理的收益型股票”
- “筛选可持续的高股息股票”
- 任何结合股息率、估值指标与基本面分析的请求

---

## 3. 前提条件

- 需要 **FMP API 密钥**(`FMP_API_KEY` 环境变量)
- **FINVIZ Elite** 可选(可提升性能)
- FMP 用于分析;FINVIZ 可将执行时间缩短 70-80%
- 推荐使用 Python 3.9+

---

## 4. 快速开始

```bash
# 两阶段筛选(推荐 —— 速度快 70-80%)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py --use-finviz

# 仅使用 FMP 筛选(无需 FINVIZ)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py

# 自定义参数
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --top 50 \
  --output custom_results.json
```

---

## 5. 工作流

### 步骤 1:验证 API 密钥可用性

**两阶段筛选(推荐):**

检查两个 API 密钥是否都可用:

```python
import os
fmp_api_key = os.environ.get('FMP_API_KEY')
finviz_api_key = os.environ.get('FINVIZ_API_KEY')
```

如果不可用,请用户提供 API 密钥或设置环境变量:
```bash
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**仅使用 FMP 筛选:**

检查 FMP API 密钥是否可用:

```python
import os
api_key = os.environ.get('FMP_API_KEY')
```

如果不可用,请用户提供 API 密钥或设置环境变量:
```bash
export FMP_API_KEY=your_key_here
```

**FINVIZ Elite API 密钥:**
- 需要 FINVIZ Elite 订阅(约 40 美元/月,或约 330 美元/年)
- 可获取预筛选结果的 CSV 导出权限
- 强烈建议使用以减少 FMP API 用量

如有需要,可参考 `references/fmp_api_guide.md` 中的说明。

### 步骤 2:执行筛选脚本

使用合适的参数运行筛选脚本:

#### **两阶段筛选(推荐)**

先用 FINVIZ 预筛选,再用 FMP 做详细分析:

**默认执行(前 20 只股票):**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz
```

**显式指定 API 密钥:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz \
  --fmp-api-key $FMP_API_KEY \
  --finviz-api-key $FINVIZ_API_KEY
```

**自定义返回数量 N:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --top 50
```

**自定义输出位置:**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --output /path/to/results.json
```

**脚本行为(两阶段):**
1. FINVIZ Elite 预筛选:
   - 市值:中型股或以上
   - 股息率:3% 以上
   - 股息增长(3 年):5% 以上
   - EPS 增长(3 年):正增长
   - P/B:低于 2
   - P/E:低于 20
   - 销售增长(3 年):正增长
   - 地区:美国
2. 对 FINVIZ 结果(通常 20-50 只股票)进行 FMP 详细分析:
   - 计算股息增长率(3 年 CAGR)
   - 营收与 EPS 趋势分析
   - 股息可持续性评估(派息率、自由现金流覆盖率)
   - 财务健康指标(债务权益比、流动比率)
   - 质量评分(ROE、利润率)
3. 综合评分与排名
4. 将前 N 只股票输出到 JSON 文件

**预计耗时(两阶段):** 对 30-50 只 FINVIZ 候选股票约需 2-3 分钟(远快于纯 FMP 方案)

#### **仅使用 FMP 筛选(原始方法)**

仅使用 FMP 股票筛选器 API(API 用量更高):

**默认执行:**
```bash
python3 scripts/screen_dividend_stocks.py
```

**显式指定 API 密钥:**
```bash
python3 scripts/screen_dividend_stocks.py --fmp-api-key $FMP_API_KEY
```

**脚本行为(仅 FMP):**
1. 使用 FMP 股票筛选器 API 进行初步筛选(股息率 >= 3.0%,P/E <= 20,P/B <= 2)
2. 对候选股票(通常 100-300 只)进行详细分析:
   - 分析内容与两阶段方法相同
3. 综合评分与排名
4. 将前 N 只股票输出到 JSON 文件

**预计耗时(仅 FMP):** 对 100-300 只候选股票约需 5-15 分钟(受限速影响)

**API 用量对比:**
- 两阶段方案:约 50-100 次 FMP API 调用(FINVIZ 预筛选到约 30 只股票)
- 仅 FMP 方案:约 500-1500 次 FMP API 调用(分析全部筛选结果)

### 步骤 3:解析与分析结果

读取生成的 JSON 文件:

```python
import json

with open('dividend_screener_results.json', 'r') as f:
    data = json.load(f)

metadata = data['metadata']
stocks = data['stocks']
```

**每只股票的关键数据点:**
- 基本信息:`symbol`、`company_name`、`sector`、`market_cap`、`price`
- 估值:`dividend_yield`、`pe_ratio`、`pb_ratio`
- 增长指标:`dividend_cagr_3y`、`revenue_cagr_3y`、`eps_cagr_3y`
- 可持续性:`payout_ratio`、`fcf_payout_ratio`、`dividend_sustainable`
- 财务健康:`debt_to_equity`、`current_ratio`、`financially_healthy`
- 质量:`roe`、`profit_margin`、`quality_score`
- 综合排名:`composite_score`

### 步骤 4:生成 Markdown 报告

为用户创建包含以下部分的结构化 Markdown 报告:

#### 报告结构

```markdown
# Value Dividend Stock Screening Report

**Generated:** [时间戳]
**Screening Criteria:**
- Dividend Yield: >= 3.5%
- P/E Ratio: <= 20
- P/B Ratio: <= 2
- Dividend Growth (3Y CAGR): >= 5%
- Revenue Trend: Positive over 3 years
- EPS Trend: Positive over 3 years

**Total Results:** [N] stocks

---

---

## 6. 资源

**参考文档(References):**

- `skills/value-dividend-screener/references/fmp_api_guide.md`
- `skills/value-dividend-screener/references/screening_methodology.md`

**脚本(Scripts):**

- `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`
