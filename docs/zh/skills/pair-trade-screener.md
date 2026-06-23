---
layout: default
title: "Pair Trade Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 38
lang_peer: /en/skills/pair-trade-screener/
permalink: /zh/skills/pair-trade-screener/
generated: false
---

# Pair Trade Screener
{: .no_toc }

统计套利工具,用于识别和分析配对交易机会。检测板块内具有协整关系的股票对,分析价差行为,计算 z-score,并为市场中性策略提供入场/出场建议。当用户请求配对交易机会、统计套利筛选、均值回归策略或市场中性投资组合构建时使用。支持相关性分析、协整检验和价差回测。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/pair-trade-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pair-trade-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能通过配对交易识别和分析统计套利机会。配对交易是一种市场中性策略,无论大盘整体方向如何,都能从两个相关证券的相对价格变动中获利。该技能使用严格的统计方法(包括相关性分析和协整检验)来寻找稳健的交易对。

**核心方法论:**
- 识别相关性高、板块/行业敞口相似的股票对
- 检验协整关系(长期统计关系)
- 计算价差 z-score,识别均值回归机会
- 基于统计阈值生成入场/出场信号
- 为市场中性敞口提供头寸规模建议

**核心优势:**
- 市场中性:无论涨市、跌市还是横盘市都能获利
- 风险管理:对大盘整体波动的敞口有限
- 统计基础:数据驱动,而非主观判断
- 分散化:与传统的纯多头策略不相关

---

## 2. 使用时机

在以下情况下使用本技能:
- 用户请求“配对交易机会”
- 用户想要“市场中性策略”
- 用户请求“统计套利筛选”
- 用户问“哪些股票联动性强?”
- 用户想对板块敞口进行对冲
- 用户请求均值回归交易想法
- 用户询问相对价值交易

用户请求示例:
- “在科技板块寻找配对交易机会”
- “哪些股票存在协整关系?”
- “筛选统计套利机会”
- “寻找均值回归配对”
- “现在有哪些好的市场中性交易?”

---

## 3. 前提条件

- 需要 **FMP API 密钥**(环境变量 `FMP_API_KEY`)
- 统计套利分析
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
# 在特定板块中筛选配对
python3 pair-trade-screener/scripts/find_pairs.py --sector Technology

# 分析特定配对
python3 pair-trade-screener/scripts/analyze_spread.py AAPL MSFT

# 自定义协整参数
python3 pair-trade-screener/scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.7 \
  --lookback-days 365
```

---

## 5. 工作流

### 步骤 1:定义配对范围

**目标:** 确定要分析配对关系的股票池。

**方式 A:按板块筛选(推荐)**

选择一个特定板块进行筛选:
- 科技(Technology)
- 金融(Financials)
- 医疗保健(Healthcare)
- 消费者非必需品(Consumer Discretionary)
- 工业(Industrials)
- 能源(Energy)
- 原材料(Materials)
- 消费者必需品(Consumer Staples)
- 公用事业(Utilities)
- 房地产(Real Estate)
- 通信服务(Communication Services)

**方式 B:自定义股票列表**

用户提供具体要分析的代码:
```
示例: ["AAPL", "MSFT", "GOOGL", "META", "NVDA"]
```

**方式 C:特定行业**

把焦点收窄到板块内的特定行业:
- 示例:科技板块中的“软件”行业
- 示例:金融板块中的“区域性银行”行业

**筛选标准:**
- 最低市值:20 亿美元(中盘股及以上)
- 最低平均成交量:每日 100 万股(流动性要求)
- 活跃交易:排除已摘牌或不活跃的股票
- 同交易所优先:避免跨交易所带来的复杂性

### 步骤 2:获取历史价格数据

**目标:** 为相关性和协整分析获取价格历史数据。

**数据要求:**
- 时间跨度:2 年(至少 252 个交易日)
- 频率:每日收盘价
- 调整:经拆股和分红调整
- 干净数据:无缺口或缺失值

**FMP API 端点:**
```
GET /v3/historical-price-full/{symbol}?apikey=YOUR_API_KEY
```

**数据验证:**
- 验证所有股票的日期范围一致
- 剔除缺失数据 >10% 的股票
- 用前向填充法填补小缺口
- 记录数据质量问题

**脚本执行:**
```bash
python scripts/fetch_price_data.py --sector Technology --lookback 730
```

### 步骤 3:计算相关性与 Beta

**目标:** 识别具有强线性关系的候选配对。

**相关性分析:**

对股票池中的每一对股票 (i, j):
1. 计算皮尔逊相关系数(ρ)
2. 计算滚动相关性(90 天窗口)以检验稳定性
3. 筛选 ρ >= 0.70(强正相关)的配对

**相关性解读:**
- ρ >= 0.90:极强相关(最佳候选)
- ρ 0.70-0.90:强相关(良好候选)
- ρ 0.50-0.70:中等相关(边缘情况)
- ρ < 0.50:弱相关(排除)

**Beta 计算:**

对每个候选配对(股票 A、股票 B):
```
Beta = Covariance(A, B) / Variance(B)
```

Beta 表示对冲比率:
- Beta = 1.0:等额美元配置
- Beta = 1.5:每 1.00 美元 A 配 1.50 美元 B
- Beta = 0.8:每 1.00 美元 A 配 0.80 美元 B

**相关性稳定性检验:**
- 计算多个区间(6 个月、1 年、2 年)的相关性
- 要求相关性保持稳定(没有恶化)
- 标记近期相关性比历史相关性低 >0.15 的配对

### 步骤 4:协整检验

**目标:** 用统计方法验证长期均衡关系。

**为何协整很重要:**
- 相关性衡量的是短期联动
- 协整证明的是长期均衡关系
- 协整配对会以可预测的方式发生均值回归
- 非协整配对可能永久性地发散

**增强型迪基-富勒检验(ADF Test):**

对每个相关配对:
1. 计算价差:`Spread = Price_A - (Beta × Price_B)`
2. 在价差序列上运行 ADF 检验
3. 检查 p 值:p < 0.05 表示存在协整(拒绝存在单位根的零假设)
4. 提取 ADF 统计量用于强度排名

**协整解读:**
- p 值 < 0.01:极强协整(★★★)
- p 值 0.01-0.05:中等协整(★★)
- p 值 > 0.05:无协整(排除)

**半衰期计算:**

估计均值回归速度:
```
Half-Life = -log(2) / log(mean_reversion_coefficient)
```

- 半衰期 < 30 天:快速均值回归(适合短线交易)
- 半衰期 30-60 天:中等速度(标准)
- 半衰期 > 60 天:慢速均值回归(长持有周期)

**Python 实现:**
```python
from statsmodels.tsa.stattools import adfuller

# 计算价差
spread = price_a - (beta * price_b)

# ADF 检验
result = adfuller(spread)
adf_stat = result[0]
p_value = result[1]

# 解读
is_cointegrated = p_value < 0.05
```

### 步骤 5:价差分析与 Z-Score 计算

**目标:** 量化当前价差与均衡水平的偏离程度。

**价差计算:**

两种常见方法:

**方法 1:价格差(加法)**
```
Spread = Price_A - (Beta × Price_B)
```
适用于:价格水平相近的股票

**方法 2:价格比(乘法)**
```
Spread = Price_A / Price_B
```
适用于:价格水平不同的股票,解读更直观

**Z-Score 计算:**

衡量价差距其均值有多少个标准差:
```
Z-Score = (Current_Spread - Mean_Spread) / Std_Dev_Spread
```

**Z-Score 解读:**
- Z > +2.0:股票 A 相对 B 偏贵(做空 A,做多 B)
- Z > +1.5:中等偏贵(留意入场)
- Z -1.5 到 +1.5:正常区间(不交易)
- Z < -1.5:中等偏便宜(留意入场)
- Z < -2.0:股票 A 相对 B 偏便宜(做多 A,做空 B)

**历史价差分析:**
- 在 90 天滚动窗口内计算均值与标准差
- 绘制历史 z-score 分布
- 识别历史最大 z-score 偏离
- 检查是否存在结构性断裂(价差机制变化)

### 步骤 6:生成入场/出场建议

**目标:** 提供规则明确、可执行的交易信号。

**入场条件:**

**保守方式(Z ≥ ±2.0):**
```
做多信号:
- Z-score < -2.0(价差低于均值 2 个标准差以上)
- 价差具有均值回归性(协整 p < 0.05)
- 半衰期 < 60 天
→ 操作:买入股票 A,做空股票 B(对冲比率 = beta)

做空信号:
- Z-score > +2.0(价差高于均值 2 个标准差以上)
- 价差具有均值回归性(协整 p < 0.05)
- 半衰期 < 60 天
→ 操作:做空股票 A,买入股票 B(对冲比率 = beta)
```

**激进方式(Z ≥ ±1.5):**
- 阈值更低,交易更频繁
- 胜率更高,但单笔平均利润更小
- 需要更严格的风险管理

**出场条件:**

**主要出场:均值回归(Z = 0)**
```
当价差回归均值时出场(z-score 穿越 0)
→ 同时平掉两条腿
```

**次要出场:部分获利**
```
当 z-score 达到 ±1.0 时平掉 50%
剩余 50% 在 z-score = 0 时平掉
```

**止损:**
```
若 z-score 扩大超过 ±3.0(极端发散)则出场
风险:关系可能出现结构性断裂
```

**基于时间的出场:**
```
若 90 天内未发生均值回归则出场
防止无限期持有已失效的配对
```

### 步骤 7:头寸规模与风险管理

**目标:** 确定市场中性敞口所需的美元金额。

**市场中性头寸规模:**

对于配对(股票 A、股票 B),beta = β:

**等额美元敞口:**
```
若为该配对分配的组合规模 = 10,000 美元:
- 买入 5,000 美元股票 A
- 做空 5,000 × β 美元股票 B

示例(β = 1.2):
- 买入 5,000 美元股票 A
- 做空 6,000 美元股票 B
→ 市场中性,beta = 0
```

**头寸规模考量:**
- 单个配对总配置:占组合的 10-20%
- 最大配对数:5-8 个活跃配对,以实现分散化
- 配对间相关性:避免高度相关的配对

**风险指标:**
- 单个配对最大亏损:占组合总额的 2-3%
- 止损触发:z-score > ±3.0 或价差亏损 -5%
- 组合层面风险:所有配对风险之和 ≤ 10%

### 步骤 8:生成配对分析报告

**目标:** 创建结构化的 Markdown 报告,包含发现与建议。

**报告章节:**

1. **执行摘要**
   - 分析的配对总数
   - 发现的协整配对数量
   - 按统计强度排名的前 5 大机会

2. **协整配对表**
   - 配对名称(股票 A / 股票 B)
   - 相关系数
   - 协整 p 值
   - 当前 z-score
   - 交易信号(做多/做空/无)
   - 半衰期

3. **详细分析(前 10 大配对)**
   - 配对描述
   - 统计指标
   - 当前价差位置
   - 入场/出场建议
   - 头寸规模
   - 风险评估

4. **价差图表(文本形式)**
   - 历史 z-score 走势图(ASCII 图)
   - 标注入场/出场水平
   - 当前位置指示

5. **风险提示**
   - 相关性恶化的配对
   - 检测到的结构性断裂
   - 流动性不足提示

**文件命名规则:**
```
pair_trade_analysis_[SECTOR]_[YYYY-MM-DD].md
```

示例:`pair_trade_analysis_Technology_2025-11-08.md`

---

## 6. 资源

**参考文档(References):**

- `skills/pair-trade-screener/references/cointegration_guide.md`
- `skills/pair-trade-screener/references/methodology.md`

**脚本(Scripts):**

- `skills/pair-trade-screener/scripts/analyze_spread.py`
- `skills/pair-trade-screener/scripts/find_pairs.py`
