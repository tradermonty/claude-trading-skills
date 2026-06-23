---
layout: default
title: "Market Top Detector"
grand_parent: 简体中文
parent: 技能指南
nav_order: 36
lang_peer: /en/skills/market-top-detector/
permalink: /zh/skills/market-top-detector/
generated: false
---

# Market Top Detector
{: .no_toc }

使用 O'Neil 派发日(Distribution Days)、Minervini 领涨股恶化指标,以及 Monty 防御性板块轮动指标来检测市场见顶概率。生成一个 0-100 的综合评分,并给出风险区间分类。当用户询问市场见顶风险、派发日、防御性轮动、领涨股恶化,或是否应该降低股票敞口时使用。聚焦于针对 10-20% 修正行情的 2-8 周战术性择时信号。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-top-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-top-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Market Top Detector 技能整合 O'Neil 派发日体系、Minervini 领涨股恶化信号与 Monty 防御性板块轮动框架,生成一个量化的市场见顶风险评分,辅助判断未来 2-8 周内是否会出现 10-20% 的修正行情。

---

## 2. 使用时机

**适用场景:**
- 用户问“市场正在见顶吗?”或“我们是不是接近顶部了?”
- 用户注意到派发日在累积
- 用户观察到防御性板块跑赢成长股
- 用户看到领涨股在走弱而指数仍然坚挺
- 用户询问降低股票敞口的时机
- 用户想评估未来 2-8 周的修正概率

---

## 3. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 4. 快速开始

```bash
1. 标普 500 宽度(高于 200 日均线的比例)
   从 TraderMonty CSV 自动获取(无需 WebSearch)
   脚本会自动从 GitHub Pages 的 CSV 数据中获取该数值。
   覆盖方式:使用 --breadth-200dma [数值] 手动指定。
   关闭方式:使用 --no-auto-breadth 完全跳过自动获取。

2. [必需] 标普 500 宽度(高于 50 日均线的比例)
   有效范围:20-100
   主要检索词:"S&P 500 percent stocks above 50 day moving average"
   备用检索词:"market breadth 50dma site:barchart.com"
   记录数据日期

3. [必需] CBOE 股票认沽/认购比率
   有效范围:0.30-1.50
   主要检索词:"CBOE equity put call ratio today"
   备用检索词:"CBOE total put call ratio current"
   备用检索词:"put call ratio site:cboe.com"
   记录数据日期

4. [可选] VIX 期限结构
   取值:steep_contango / contango / flat / backwardation
   主要检索词:"VIX VIX3M ratio term structure today"
   备用检索词:"VIX futures term structure contango backwardation"
   说明:若 FMP API 能取得 VIX3M 报价则自动检测。
   命令行参数 --vix-term 可覆盖自动检测结果。

5. [可选] 保证金债务同比变化(%)
   主要检索词:"FINRA margin debt latest year over year percent"
   备用检索词:"NYSE margin debt monthly"
   说明:通常滞后 1-2 个月。请记录报告所属月份。
```

---

## 5. 工作流

### 阶段 1:通过 WebSearch 收集数据

在运行 Python 脚本之前,先用 WebSearch 收集以下数据。
**数据新鲜度要求:** 所有数据都必须来自最近 3 个交易日内。陈旧数据会降低分析质量。

```
1. 标普 500 宽度(高于 200 日均线的比例)
   从 TraderMonty CSV 自动获取(无需 WebSearch)
   脚本会自动从 GitHub Pages 的 CSV 数据中获取该数值。
   覆盖方式:使用 --breadth-200dma [数值] 手动指定。
   关闭方式:使用 --no-auto-breadth 完全跳过自动获取。

2. [必需] 标普 500 宽度(高于 50 日均线的比例)
   有效范围:20-100
   主要检索词:"S&P 500 percent stocks above 50 day moving average"
   备用检索词:"market breadth 50dma site:barchart.com"
   记录数据日期

3. [必需] CBOE 股票认沽/认购比率
   有效范围:0.30-1.50
   主要检索词:"CBOE equity put call ratio today"
   备用检索词:"CBOE total put call ratio current"
   备用检索词:"put call ratio site:cboe.com"
   记录数据日期

4. [可选] VIX 期限结构
   取值:steep_contango / contango / flat / backwardation
   主要检索词:"VIX VIX3M ratio term structure today"
   备用检索词:"VIX futures term structure contango backwardation"
   说明:若 FMP API 能取得 VIX3M 报价则自动检测。
   命令行参数 --vix-term 可覆盖自动检测结果。

5. [可选] 保证金债务同比变化(%)
   主要检索词:"FINRA margin debt latest year over year percent"
   备用检索词:"NYSE margin debt monthly"
   说明:通常滞后 1-2 个月。请记录报告所属月份。
```

### 阶段 2:执行 Python 脚本

将收集到的数据作为命令行参数运行脚本:

```bash
python3 skills/market-top-detector/scripts/market_top_detector.py \
  --api-key $FMP_API_KEY \
  --breadth-50dma [数值] --breadth-50dma-date [YYYY-MM-DD] \
  --put-call [数值] --put-call-date [YYYY-MM-DD] \
  --vix-term [steep_contango|contango|flat|backwardation] \
  --margin-debt-yoy [数值] --margin-debt-date [YYYY-MM-DD] \
  --output-dir reports/ \
  --context "Consumer Confidence=[数值]" "Gold Price=[数值]"
# 200日均线宽度数据会自动从 TraderMonty CSV 获取。
# 如需要,可用 --breadth-200dma [数值] 覆盖。
# 用 --no-auto-breadth 可关闭自动获取。
```

脚本会:
1. 从 FMP API 获取标普 500、QQQ、VIX 的报价与历史数据
2. 获取领涨 ETF(ARKK、WCLD、IGV、XBI、SOXX、SMH、KWEB、TAN)数据
3. 获取板块 ETF(XLU、XLP、XLV、VNQ、XLK、XLC、XLY)数据
4. 计算全部 6 个分量
5. 生成综合评分与报告

### 阶段 3:呈现结果

把生成的 Markdown 报告呈现给用户,重点突出:
- 综合评分与风险区间
- 数据新鲜度警告(如有数据超过 3 天)
- 最强的警示信号(得分最高的分量)
- 历史对比(最接近的历史顶部形态)
- 假设情景分析(对关键变量变化的敏感度)
- 基于风险区间的建议操作
- 跟进日(Follow-Through Day)状态(如适用)
- 与上一次运行结果的差异(如存在历史报告)

---

## 6. 资源

**参考文档(References):**

- `skills/market-top-detector/references/distribution_day_guide.md`
- `skills/market-top-detector/references/historical_tops.md`
- `skills/market-top-detector/references/market_top_methodology.md`

**脚本(Scripts):**

- `skills/market-top-detector/scripts/breadth_csv_client.py`
- `skills/market-top-detector/scripts/fmp_client.py`
- `skills/market-top-detector/scripts/historical_comparator.py`
- `skills/market-top-detector/scripts/market_top_detector.py`
- `skills/market-top-detector/scripts/report_generator.py`
- `skills/market-top-detector/scripts/scenario_engine.py`
- `skills/market-top-detector/scripts/scorer.py`
- `skills/market-top-detector/scripts/utils.py`
