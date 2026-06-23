---
layout: default
title: "Dividend Growth Pullback Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 14
lang_peer: /en/skills/dividend-growth-pullback-screener/
permalink: /zh/skills/dividend-growth-pullback-screener/
generated: false
---

# Dividend Growth Pullback Screener
{: .no_toc }

使用本技能寻找正经历短期回调的高质量股息成长股(年化股息增长率 12% 以上、股息率 1.5% 以上),回调标准为 RSI 超卖状态(RSI ≤40)。本技能将基本面股息分析与技术性择时指标相结合,在短期走弱期间识别优质股息成长股的买入机会。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/dividend-growth-pullback-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/dividend-growth-pullback-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能筛选出基本面强劲但正经历短期技术性走弱的股息成长股。它聚焦于股息增长率优异(复合年增长率 12% 以上)且已回调至 RSI 超卖水平(≤40)的股票,为长期股息成长型投资者创造潜在的入场机会。

**投资逻辑:** 高质量股息成长股(当前股息率通常为 1-2.5%)主要通过股息增长(而非高当前收益率)来实现财富复利增长。在这些股票出现短期回调(RSI ≤40)时买入,可以把强劲的基本面增长与有利的技术性入场时机结合起来,从而提升总回报。

---

## 2. 使用时机

在以下情况下使用本技能:
- 寻找具有出色复利潜力的股息成长股(股息复合年增长率 12% 以上)
- 在市场短期走弱期间寻找优质股票的入场机会
- 愿意接受较低的当前股息率(1.5-3%)以换取更高的股息增长率
- 关注 5-10 年的总回报,而非当前收益
- 市场出现板块轮动或波及优质股票的普遍性回调

**不应使用的情况:**
- 寻求高当前收益(应改用 value-dividend-screener)
- 要求即时股息率 >3%
- 寻找有严格 P/E 或 P/B 要求的深度价值型标的
- 关注短线交易(持有期 <6 个月)

---

## 3. 前提条件

- 需要 **FMP API 密钥**(`FMP_API_KEY` 环境变量)
- **FINVIZ Elite** 为可选项(可提升性能)
- FMP 用于深入分析;FINVIZ 用于 RSI 预筛选
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
# 带 RSI 过滤的两阶段筛选(推荐)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --use-finviz

# 仅使用 FMP 的筛选(受 API 限制,约限于 40 只股票)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --max-candidates 40

# 自定义 RSI 阈值和股息增长要求
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py \
  --use-finviz \
  --rsi-threshold 35 \
  --min-div-growth 15
```

---

## 5. 工作流

### 第 1 步:设置 API 密钥

#### 两阶段方法(推荐)

为获得最佳性能,使用 FINVIZ Elite API 进行预筛选,再结合 FMP API 进行详细分析:

```bash
# 将两个 API 密钥都设置为环境变量
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**为什么采用两阶段方法?**
- **FINVIZ**:基于 RSI 过滤的快速预筛选(1 次 API 调用 → 约 10-50 个候选标的)
- **FMP**:仅对经过预筛选的候选标的进行详细基本面分析
- **效果**:用更少的 FMP API 调用次数分析更多股票(保持在免费层级的限额内)

#### 仅使用 FMP 的方法(原始方法)

如果你没有 FINVIZ Elite 访问权限:

```bash
export FMP_API_KEY=your_key_here
```

**限制:** FMP 免费层(每天 250 次请求)将分析数量限制在约 40 只股票。使用 `--max-candidates 40` 以保持在限额内。

### 第 2 步:执行筛选

**两阶段筛选(推荐):**

```bash
cd dividend-growth-pullback-screener/scripts
python3 screen_dividend_growth_rsi.py --use-finviz
```

该步骤执行:
1. FINVIZ 预筛选:股息率 0.5-3%、股息增长率 10% 以上、EPS 增长率 5% 以上、营收增长率 5% 以上、RSI <40
2. FMP 详细分析:验证 12% 以上的股息复合年增长率,精确计算 RSI,分析基本面

**仅使用 FMP 的筛选:**

```bash
python3 screen_dividend_growth_rsi.py --max-candidates 40
```

**自定义选项:**

```bash
# 带自定义参数的两阶段筛选
python3 screen_dividend_growth_rsi.py --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35

# 带自定义参数的仅 FMP 筛选
python3 screen_dividend_growth_rsi.py --min-yield 2.0 --min-div-growth 10.0 --max-candidates 30

# 以参数形式提供 API 密钥(而非环境变量)
python3 screen_dividend_growth_rsi.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY
```

### 第 3 步:查看结果

该脚本会生成两份输出:

1. **JSON 文件:** `dividend_growth_pullback_results_YYYY-MM-DD.json`
   - 包含全部指标的结构化数据,便于进一步分析
   - 包含股息增长率、RSI 数值、财务健康指标

2. **Markdown 报告:** `dividend_growth_pullback_screening_YYYY-MM-DD.md`
   - 包含个股概况的可读性分析
   - 基于情景的概率评估
   - 入场时机建议

### 第 4 步:分析符合条件的股票

对于每只符合条件的股票,报告包含以下内容:

**股息成长概况:**
- 当前股息率与年化股息
- 3 年股息复合年增长率及其稳定性
- 派息率及可持续性评估

**技术性择时:**
- 当前 RSI 数值(≤40 = 超卖)
- RSI 所处区间(极度超卖 <30 vs. 早期回调 30-40)
- 相对于近期趋势的价格走势

**质量指标:**
- 营收与 EPS 增长(确认业务势头)
- 财务健康状况(负债水平、流动性比率)
- 盈利能力(ROE、利润率)

**投资建议:**
- 入场时机评估(立即入场 vs. 等待确认)
- 该股票特有的风险因素
- 基于股息增长复利效应的上涨情景

---

## 6. 资源

**参考文档(References):**

- `skills/dividend-growth-pullback-screener/references/dividend_growth_compounding.md`
- `skills/dividend-growth-pullback-screener/references/fmp_api_guide.md`
- `skills/dividend-growth-pullback-screener/references/rsi_oversold_strategy.md`

**脚本(Scripts):**

- `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py`
