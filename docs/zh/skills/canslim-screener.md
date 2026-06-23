---
layout: default
title: "CANSLIM Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 2
lang_peer: /en/skills/canslim-screener/
permalink: /zh/skills/canslim-screener/
generated: false
---

# CANSLIM Screener
{: .no_toc }

用 William O'Neil 经过验证的 CANSLIM 成长股方法论筛选美股。第 3 阶段实现全部 7 个分量,方法论覆盖率 100%。
{: .fs-6 .fw-300 }

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/canslim-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/canslim-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

CANSLIM Screener 应用 William O'Neil 的成长股选股系统 —— 该系统源于对 1953 年至今每一只重大牛股的研究。该方法论识别多倍股在其重大上涨前所展现的 7 个共同特征。

**它解决什么:**
- 在 7 个 CANSLIM 维度上系统性地为股票评分,而非依赖主观判断
- 提供带清晰解读区间的综合评级(0-100)
- 防止在熊市买入(M 分量为所有建议设置关卡)
- 自动化分析盈利、成长、动量、机构行为与市场状况这一繁重过程

**第 3 阶段实现全部 7 个分量:**

| 分量 | 权重 | 衡量内容 |
|------|------|----------|
| **C** - 当前盈利(Current Earnings) | 15% | 季度 EPS 与营收增长(同比) |
| **A** - 年度成长(Annual Growth) | 20% | 3 年 EPS 复合增长率与稳定性 |
| **N** - 新高(Newness) | 15% | 距 52 周高点的距离、突破检测 |
| **S** - 供需(Supply/Demand) | 15% | 基于成交量的吸筹/派发 |
| **L** - 领导地位(Leadership) | 20% | 多周期 RS(3 月/6 月/12 月对比可配置基准,默认 ^GSPC) |
| **I** - 机构(Institutional) | 10% | 持有人数 + 持股比例(含 Finviz 回退) |
| **M** - 市场方向(Market Direction) | 5% | S&P 500 趋势 vs 50 日 EMA |

---

## 2. 前提条件

> 需要 FMP API 密钥。免费档(250 次/天)每次运行最多支持 35 只股票。用 `--max-candidates 35` 控制在上限内。
{: .api_required }

**API 需求:**
- **FMP API 密钥** —— 免费档:250 次/天。Starter 档($29.99/月):750 次/天,可做完整 40 股筛选。
- 注册:[https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

**Python 依赖:**
- Python 3.7+
- `requests`(FMP API 调用)
- `beautifulsoup4`(用于 I 分量回退的 Finviz 网页抓取)
- `lxml`(HTML 解析)

```bash
pip install requests beautifulsoup4 lxml
```

**API 预算(第 3 阶段):**
- 40 股 × 每股 7 次 FMP 调用 = 280 次 FMP 调用
- 市场数据(S&P 500 报价、VIX、52 周历史):3 次调用
- 合计:每次运行约 283 次 FMP 调用(超出 250 免费档)
- **建议:** 免费档用 `--max-candidates 35`(248 次调用),或升级到 Starter

---

## 3. 快速开始

```bash
# 设置你的 API 密钥
export FMP_API_KEY=your_key_here

# 用默认 S&P 500 范围运行(按市值前 40)
python3 skills/canslim-screener/scripts/screen_canslim.py --output-dir reports/

# 免费档优化(最多 35 股)
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --output-dir reports/
```

或直接对 Claude 说:

```
对 S&P 500 前 35 只股票运行 CANSLIM 筛选
```

---

## 4. 工作原理

筛选器以两阶段流水线运作:

**阶段 1 —— 数据收集与评分(FMP API + Finviz):**
1. 获取 S&P 500 历史数据,用于 M 分量(市场方向)与 L 分量(相对强度基准)
2. 对每只股票,发起 7 次 FMP API 调用:概况、报价、利润表(2 期)、90 日历史、365 日历史、机构持有人
3. 用专门的计算模块计算全部 7 个分量评分
4. 当 FMP 机构数据不完整时,自动回退到 Finviz 网页抓取获取持股比例

**阶段 2 —— 排名与报告:**
1. 计算加权综合分:C(15%) + A(20%) + N(15%) + S(15%) + L(20%) + I(10%) + M(5%)
2. 按综合分对所有股票排名(从高到低)
3. 生成供程序化使用的 JSON 输出与供人工查阅的 Markdown 报告

**Finviz 回退行为:**
- 当 FMP `sharesOutstanding` 不可用时自动触发
- 从 Finviz.com 抓取机构持股比例(免费,无需 API 密钥)
- 限速为每次请求 2.0 秒
- 把 I 分量准确度从 35/100(部分数据)提升到 60-100/100(完整数据)

---

## 5. 使用示例

### 示例 1:默认 S&P 500 筛选

**提示词:**
```
对 S&P 500 筛选 CANSLIM 股票
```

**发生了什么:** Claude 对默认 40 股范围(按市值的 S&P 500 头部)运行筛选器。约需 2 分钟。生成带综合分与分量拆解的排序报告。

**为何有用:** 用经过验证的方法论,最快识别大盘范围内最强的成长股。

---

### 示例 2:聚焦半导体板块

**命令:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --universe NVDA AMD QCOM AVGO TXN INTC MU MRVL AMAT LRCX \
  --output-dir reports/
```

**为何有用:** 把分析收窄到单一高成长板块。当你已有板块论点、想用 CANSLIM 标准在其中排出最佳候选时很有用。

---

### 示例 3:免费档优化

**命令:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --top 10 --output-dir reports/
```

**为何有用:** 在分析一个有意义范围的同时,保持在 FMP 免费档上限(250 次/天)内。`--top 10` 标志让报告聚焦于最强候选。

---

### 示例 4:分量深剖

运行筛选后,查看高分股票的分量拆解:

```
Score: 92.3 / 100 (Exceptional+)
  C (Current Earnings): 100/100 - EPS +58% QoQ, Revenue +32%
  A (Annual Growth):     95/100 - 3yr EPS CAGR 42%, consistent growth
  N (Newness):           98/100 - Within 2% of 52-week high, volume breakout
  S (Supply/Demand):     85/100 - Up/Down Volume Ratio 1.65 (Accumulation)
  L (Leadership):        92/100 - 52wk: +45% (+22% vs S&P 500), RS 88
  I (Institutional):     90/100 - 6,199 holders, 68.3% ownership
  M (Market Direction): 100/100 - Strong uptrend, S&P above 50-day EMA
```

**为何有用:** 理解哪些分量驱动评分,有助于评估该股的强势是广泛的还是集中在某一方面。各分量都高分的股票最可靠。

---

### 示例 5:熊市情景

当 M 分量检测到熊市(S&P 500 低于 50 日 EMA、VIX 升高):

```
Market Condition: BEAR MARKET DETECTED
M Score: 0/100

WARNING: CANSLIM methodology recommends raising 80-100% cash in bear markets.
3 out of 4 stocks follow the market trend. Do NOT initiate new positions.
```

**为何有用:** M 分量充当断路器。即便个股在其他分量上得 90+,CANSLIM 的历史数据也表明在确认的熊市买入胜率很差。这能保护本金。

---

### 示例 6:解读评分区间

| 评级 | 评分 | 指引 | 仓位规模 |
|------|------|------|----------|
| Exceptional+ | 90-100 | 所有分量近乎完美。激进买入 | 组合的 15-20% |
| Exceptional | 80-89 | 出色的基本面 + 动量。强烈买入 | 组合的 10-15% |
| Strong | 70-79 | 各分量扎实、弱点轻微。标准买入 | 组合的 8-12% |
| Above Average | 60-69 | 达标但有一个弱分量。回调时买入 | 组合的 5-8% |

**为何有用:** 解读区间把抽象评分转化为具体的仓位指引,使风险敞口与确信度对齐。

---

## 6. 解读输出

筛选器生成两个文件:
- `canslim_screener_YYYY-MM-DD_HHMMSS.json` —— 供程序化使用的结构化数据
- `canslim_screener_YYYY-MM-DD_HHMMSS.md` —— 人类可读报告

**报告章节:**
1. **市场状况摘要** —— 当前趋势、M 分、警告
2. **前 N 个 CANSLIM 候选** —— 按综合分排序,含:
   - 综合分与评级区间
   - 各分量评分及解释细节
   - 数据来源说明(例如“机构数据来自 Finviz”)
   - 最弱分量识别
3. **汇总统计** —— 评级分布(多少个 Exceptional+、Exceptional、Strong 等)
4. **方法说明** —— 第 3 阶段:7 个分量,100% 覆盖

**需留意的质量警告:**
- “Revenue declining despite EPS growth” —— 可能的回购扭曲
- “Using Finviz institutional ownership data” —— 数据来源切换(仍准确)
- “Bear market detected” —— M 分量 = 0,不要买入

---

## 7. 技巧与最佳实践

- **始终先看 M 分量。** 若 M = 0,从 CANSLIM 角度看其余分数都无意义。提高现金并等待。
- **寻找广泛的强势。** 各分量都高于 70 的 85 分,比一个分量 100、另一个 40 的 85 分更可靠。
- **免费档用 `--max-candidates 35`。** 这是 250 次/天 FMP 免费档上限的最佳点。
- **每周运行,而非每天。** CANSLIM 是周度筛选方法。盈利数据按季更新,多数分量逐周稳定。
- **与图表交叉引用。** CANSLIM 识别基本面强劲的股票,但入场时机也重要。用 Technical Analyst 技能做基于图表的入场确认。
- **Finviz 回退可靠。** 测试显示 100% 成功率(39/39 股),每次请求约 2.5 秒。数据质量与 FMP 等同。

---

## 8. 与其他技能组合

| 工作流 | 步骤 |
|--------|------|
| **完整成长股流水线** | CANSLIM Screener(排候选)> Technical Analyst(确认图表形态)> Position Sizer(计算股数) |
| **CANSLIM + VCP** | 运行 CANSLIM 识别成长龙头,再用 VCP Screener 检查头部候选是否也呈现 VCP 形态 |
| **用 FinViz 预过滤** | 用 FinViz Screener(`fa_epsqoq_o25,ta_sma200_pa,ta_highlow52w_b0to10h`)构建自定义范围,再用 `--universe` 把这些代码传给 CANSLIM Screener |
| **财报确认** | CANSLIM 排出候选后,查 Earnings Calendar 的即将发布日期,避免在波动事件前入场 |
| **熊市保护** | 当 CANSLIM M = 0 时,切换到 Market Environment Analysis 与 Breadth Chart Analyst 监控复苏信号 |

---

## 9. 故障排查

### FMP API 限流(429 错误)

脚本会在 60 秒后自动重试。若错误持续:
- 缩减范围:`--max-candidates 30`
- 检查每日用量:免费档在 UTC 0 点重置
- 升级到 FMP Starter($29.99/月)以获得 750 次/天

### 缺少 Python 库

```
ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml
```

安装所有依赖:
```bash
pip install requests beautifulsoup4 lxml
```

### Finviz 网页抓取失败(403 错误)

当 Finviz 阻止抓取请求时发生。脚本会优雅降级:
- 仅回退到 FMP 持有人数
- I 分量评分封顶为 70/100 并施加 50% 惩罚
- 等几分钟后重试,或核实你对 finviz.com 的网络访问

### 所有股票评分都低于 60

这可能表明熊市状况或一个缺乏成长股的范围:
- 检查 M 分量 —— 若 M = 0,遵循熊市协议(提高现金)
- 试试不同板块或扩大范围
- 在疲弱市场中,55-65 区间的评分可能仍是相对最佳的选择

---

## 10. 参考资料

### CLI 参数

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| `--api-key` | 否 | `$FMP_API_KEY` | FMP API 密钥 |
| `--max-candidates` | 否 | `40` | 最大分析股票数(免费档用 35) |
| `--top` | 否 | `20` | 报告中的前 N 结果数 |
| `--output-dir` | 否 | `reports/` | JSON 与 Markdown 报告的输出目录 |
| `--universe` | 否 | S&P 500 前 40 | 自定义代码列表 |
| `--rs-benchmark` | 否 | `^GSPC` | L 分量 RS 的基准代码(如 SPY、QQQ、IWM)。M 分量仍用 ^GSPC 以保持 EMA 量纲一致。 |
| `--disable-rs` | 否 | `false` | 跳过 L 分量计算。省去每股 365 日价格获取与自定义基准获取(若适用)。L 固定为中性 50。 |

### 默认范围

默认范围包括按市值的 S&P 500 前 40 只股票:

```
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, BRK.B, UNH, JNJ,
XOM, V, PG, JPM, MA, HD, CVX, MRK, ABBV, PEP, COST, AVGO, KO,
ADBE, LLY, TMO, WMT, MCD, CSCO, ACN, ORCL, ABT, NKE, CRM, DHR,
VZ, TXN, AMD, QCOM, INTC
```

### 评分公式

```
Composite = C x 0.15 + A x 0.20 + N x 0.15 + S x 0.15 + L x 0.20 + I x 0.10 + M x 0.05
```

### 加权 RS 计算(第 3.1 阶段)

L 分量现在对可配置基准(默认 `^GSPC`)使用多周期加权相对强度:

```
Weighted RS = 0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m
```

- 周期:3m = 63 个交易日,6m = 126 个交易日,12m = 252 个交易日。
- 当某些周期缺失(历史不足)时,权重会在可用周期上重新归一化,使其仍合计为 1.0。
- 当完整多周期数据不可用时的**回退层级**:
  1. **无基准** → 用加权绝对股票表现评分,并施加 20% 惩罚(保留旧回退行为)。
  2. **所有多周期窗口缺失但有 ≥50 个交易日价格历史**(例如少于 63 个交易日但长于 50 个交易日的序列)→ 回退到旧的 365 日完整窗口绝对收益作为评分输入。无基准时 20% 惩罚仍适用。
  3. **<50 个交易日价格历史** → score=0 并设 `error`;不执行评分。
- 传入 `--rs-benchmark SPY`(或 QQQ、IWM 等)以更换基准。M 分量始终使用 `^GSPC` 以保持其 EMA 计算量纲。

### 输出 Schema(第 3.1 阶段)

L 分量子对象新增以下字段。为向后兼容,保留既有字段。

| 字段 | 类型 | 说明 |
|------|------|------|
| `rs_3m_return` / `rs_6m_return` / `rs_12m_return` | float \| null | 股票在 63 / 126 / 252 个交易日的绝对收益。 |
| `benchmark_3m_return` / `benchmark_6m_return` / `benchmark_12m_return` | float \| null | 基准在相同窗口的绝对收益。 |
| `rel_3m` / `rel_6m` / `rel_12m` | float \| null | 股票减基准(按周期)。无基准时为 null。 |
| `weighted_stock_performance` | float \| null | 加权绝对收益(无基准时作评分输入)。 |
| `weighted_relative_performance` | float \| null | 加权相对收益(有基准时作评分输入)。 |
| `benchmark_52w_performance` | float \| null | `sp500_52w_performance` 的代码中性后继字段。 |
| `rs_benchmark` | string | 所用基准代码(如 `^GSPC`、`SPY`)。 |
| `rs_benchmark_relative_return` | float \| null | 等于 `rel_12m`(252 日相对)。注意:这与旧的 `relative_performance`(使用完整 365 日窗口)**不同**。 |
| `rs_rating` | string | 由 `rs_rank_percentile` 派生的简短标签:`Market Leader` / `Strong` / `Above Average` / `Average` / `Laggard` / `Weak`。 |
| `rs_component_score` | int | `score` 的别名(0–100)。 |
| `rs_rank_percentile` | int \| null | 由相对表现阈值派生的**估计**分位。**不是**所筛选范围内的横截面分位。 |

弃用说明:

- 为向后兼容保留 `sp500_52w_performance`。当 `--rs-benchmark` 设为非 `^GSPC` 代码时,该字段包含该基准的收益(字段名具有误导性)。优先使用 `benchmark_52w_performance`。
- `relative_performance` 继续表示 365 日完整窗口的 股票 − 基准 收益。它不同于 `rs_benchmark_relative_return`(252 日)与 `weighted_relative_performance`(多周期加权)。

### 评级区间

| 区间 | 评分 | 解读 |
|------|------|------|
| Exceptional+ | 90-100 | 所有分量近乎完美 |
| Exceptional | 80-89 | 出色的基本面 + 动量 |
| Strong | 70-79 | 各分量扎实 |
| Above Average | 60-69 | 达标但弱点轻微 |
| Average | 50-59 | 信号混杂 |
| Below Average | < 50 | 不符合 CANSLIM 标准 |
