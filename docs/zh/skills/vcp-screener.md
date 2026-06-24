---
layout: default
title: "VCP Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 3
lang_peer: /en/skills/vcp-screener/
permalink: /zh/skills/vcp-screener/
generated: false
---

# VCP Screener
{: .no_toc }

筛选 S&P 500 股票,识别 Mark Minervini 的波动率收缩形态(VCP)。找出处于 Stage 2 上升趋势、在突破枢轴点附近以收缩波动率形成紧致平台的股票。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/vcp-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/vcp-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

VCP Screener 自动检测 Mark Minervini 的波动率收缩形态(VCP)—— 一种先于许多大幅上涨的技术平台形态。当处于 Stage 2 上升趋势的股票多次回调、且每次回调都更浅、交易区间更紧致时,该形态形成,表明供给正被吸收。

**它解决什么:**
- 人工扫描数百张图找 VCP 既耗时又不一致
- 该筛选器用客观、量化的标准在整个 S&P 500 上识别形态
- 提供含枢轴点、止损位与风险百分比的精确交易方案
- 把入场就绪的股票与仍在形成中的(发展中形态)分开

**3 阶段流水线:**
1. **预过滤** —— 基于报价对价格、成交量与 52 周位置筛选(约 101 次 API 调用)
2. **趋势模板** —— 用 260 日价格历史套用 Minervini 的 7 点 Stage 2 过滤(约 100 次 API 调用)
3. **VCP 检测** —— 形态分析、收缩评分、枢轴计算(无额外 API 调用)

---

## 2. 前提条件

> 需要 FMP API 密钥。免费档(250 次/天)足以应对默认的前 100 候选筛选。
{: .api_required }

**API 需求:**
- **FMP API 密钥** —— 免费档:250 次/天(足够默认筛选)。`--full-sp500` 建议用付费档。
- 注册:[https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

**Python 依赖:**
- Python 3.7+
- `requests`(FMP API 调用)

```bash
pip install requests
```

---

## 3. 快速开始

```bash
# 设置你的 API 密钥
export FMP_API_KEY=your_key_here

# 默认:筛选 S&P 500 前 100 候选
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/

# 或者对 Claude 说:
# “筛选 S&P 500 股票的 VCP 形态”
```

---

## 4. 工作原理

**阶段 1 —— 预过滤(基于报价):**
- 获取 S&P 500 股票的当前报价
- 按价格(高于最低)、平均成交量(足够流动性)与 52 周位置过滤
- 把范围从约 500 缩减到约 100 个候选
- 成本:约 101 次 API 调用(1 次批量报价 + 单独报价)

**阶段 2 —— 趋势模板(Minervini 的 7 点检查):**
- 为每个预过滤股票获取 260 日价格历史
- 套用 Minervini 的 Stage 2 趋势模板:
  - 价格高于 50 日与 150 日均线
  - 50 日均线高于 150 日均线
  - 150 日均线高于 200 日均线
  - 200 日均线至少上行 1 个月
  - 价格至少高于 52 周低点 30%
  - 价格在 52 周高点 25% 以内
  - 相对强度排名高于 70
- 按趋势模板标准给每只股票评分(0-100)
- 成本:约 100 次 API 调用(每股 1 次)

**阶段 3 —— VCP 检测(无额外 API 调用):**
- 用基于 ATR 的 ZigZag 摆动检测分析价格数据中的收缩形态
- 识别逐次收紧的回调(T1、T2、T3 等)
- 计算:回调深度、收缩比率、成交量枯竭、枢轴价
- **双轴评分** 把形态质量(综合分)与执行就绪度(执行状态)分开,防止强势但已拉伸的股票收到买入信号
- 综合评分综合趋势模板分、VCP 形态质量、成交量形态、相对强度与枢轴接近度

---

## 5. 使用示例

### 示例 1:默认 S&P 500 VCP 扫描

**提示词:**
```
筛选 S&P 500 的 VCP 形态
```

**发生了什么:** 筛选器对 S&P 500 前 100 候选运行完整 3 阶段流水线。约需 2-3 分钟。结果分为两部分:
- **A 区(入场就绪):** 距枢轴点 3% 以内且风险可接受的股票
- **B 区(已拉伸 / 发展中):** 有 VCP 形态、但要么在枢轴之上(已拉伸)、要么仍在形成的股票

---

### 示例 2:自定义范围

**命令:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --universe AAPL NVDA MSFT AMZN META AVGO CRM ADBE \
  --output-dir reports/
```

**为何有用:** 当你已有来自其他来源的观察清单(例如 CANSLIM Screener 输出),想检查哪些股票正在形成可执行的 VCP 形态时。

---

### 示例 3:严格质量过滤

**命令:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --min-contractions 3 \
  --breakout-volume-ratio 2.0 \
  --trend-min-score 90 \
  --output-dir reports/
```

**为何有用:** 收紧检测标准以获得更高质量的形态。要求 3 次以上收缩与 2 倍突破量,产出更少候选但更具教科书式 VCP 特征。最适合只想要最清晰形态的保守交易者。

---

### 示例 4:解读收缩细节

典型的 VCP 输出展示收缩分析:

```
VCP Pattern: 3 contractions detected
  T1: -18.5% (base correction)
  T2: -11.2% (ratio: 0.61 -- good contraction)
  T3: -5.8%  (ratio: 0.52 -- excellent tightening)
Volume Dry-Up: 0.45 (55% below average -- strong supply exhaustion)
Pivot Price: $185.20
```

**解读:**
- T1 为 -18.5%,确立了平台深度(在 Minervini 典型的 10-35% 范围内)
- T2/T1 比率 0.61 显示有意义的收缩(低于 0.75 阈值)
- T3/T2 比率 0.52 显示收紧在加速 —— 机构吸筹的标志
- 成交量枯竭为 0.45,意味着成交量降至均值的 45%,表明供给已耗尽
- 最后一次收缩越紧、成交量越低,潜在突破越有爆发力

---

### 示例 5:入场就绪 vs 已拉伸股票

报告把股票分为两类:

**A 区 —— 入场就绪:**
- 价格在枢轴的 `--max-above-pivot`(默认 3%)以内
- 到止损的风险在 `--max-risk`(默认 15%)以内
- 已确认有效 VCP 形态(除非设了 `--no-require-valid-vcp`)
- 这些现在就可执行

**B 区 —— 已拉伸 / 发展中:**
- 通过趋势模板但已在枢轴上方拉伸的股票
- 尚未完成足够收缩的发展中形态
- 这些进入观察清单,等待未来入场机会

---

### 示例 6:交易方案

对入场就绪的候选,报告给出完整交易方案:

```
NVDA (Score: 92.1 - Textbook VCP)
  Pivot: $185.20
  Current: $183.50 (0.9% below pivot)
  Stop-Loss: $171.40 (T3 low)
  Risk: 6.6%
  Risk/Reward at 2R: 13.2% upside target = $207.70
```

**如何使用:**
1. 在枢轴价($185.20)处或略上方挂买单
2. 把止损设在 $171.40(最后一次收缩最低点下方)
3. 你的初始风险为持仓价值的 6.6%
4. 用 Position Sizer 根据账户规模与风险承受度计算精确股数

---

## 6. 解读输出

筛选器生成:
- `vcp_screener_YYYY-MM-DD_HHMMSS.json` —— 供程序化使用的结构化结果
- `vcp_screener_YYYY-MM-DD_HHMMSS.md` —— 人类可读报告

**报告章节:**
1. **执行摘要** —— 筛选候选数、发现的 VCP 数、入场就绪数
2. **A 区 —— 入场就绪** —— 带交易方案的近枢轴股票
3. **B 区 —— 已拉伸 / 发展中** —— 观察清单候选
4. **每只股票:**
   - 综合分与评级(教科书 VCP 90+、强 80-89、良好 70-79、发展中 60-69)
   - 趋势模板分(7 点检查)
   - VCP 收缩细节(T1/T2/T3 深度与比率)
   - 成交量形态(枯竭比率)
   - 相对强度排名
   - 枢轴价、止损与风险百分比

**双轴输出:**

每只股票同时获得**质量评级**(形态强度)与**执行状态**(入场时机)。最终评级受执行状态封顶 —— 教科书质量但已过度拉伸的形态不会收到买入信号。

| 执行状态 | 含义 | 最高评级 |
|----------|------|----------|
| 突破前(Pre-breakout) | 枢轴下方(理想入场区) | 无上限 |
| 突破(Breakout) | 枢轴上方 0-3% + 量能确认 | 无上限 |
| 突破后早期(Early-post-breakout) | 枢轴上方 3-5%,或 0-3% 但无量 | 强 VCP |
| 已拉伸(Extended) | 枢轴上方 5-10% | 发展中 VCP |
| 过度拉伸(Overextended) | 枢轴上方 >10% 或高于 SMA200 >50% | 弱 VCP |
| 受损(Damaged) | 低于 SMA50 或止损位 | 无 VCP |
| 无效(Invalid) | 价格 < SMA50 < SMA200 | 无 VCP |

**质量评级区间(状态封顶前):**

| 评级 | 评分 | 行动 |
|------|------|------|
| 教科书 VCP | 90+ | 在枢轴买入,激进仓位 |
| 强 VCP | 80-89 | 在枢轴买入,标准仓位 |
| 良好 VCP | 70-79 | 在枢轴上方量能确认时买入 |
| 发展中 | 60-69 | 观察清单 —— 等更紧的收缩 |
| 弱 / 无 VCP | <60 | 仅监控或跳过 |

---

## 7. 技巧与最佳实践

- **量能确认至关重要。** 在低于均量的成交量上突破枢轴是可疑的。寻找突破量至少为 50 日均量的 1.5 倍(默认阈值)。
- **越紧越好。** 最佳 VCP 的 T3(或最后一次收缩)深度低于 10%。当股票在市场波动中几乎不动时,供给才真正耗尽。
- **检查大盘。** VCP 突破在确认的市场上升趋势中成功率最高。结合 Market Environment Analysis 或 Breadth Chart Analyst 核实条件。
- **不要追已拉伸的股票。** 若股票高于枢轴超过 5%,风险回报比会显著恶化。等回调到枢轴,或等新形态形成。
- **用 prebreakout 模式获得聚焦输出。** `--mode prebreakout` 标志只显示入场就绪候选,过滤掉已拉伸或发展中形态的噪声。
- **为研究调整参数。** 默认参数在多数市况下效果良好。震荡市收紧 `--min-contractions` 与 `--breakout-volume-ratio`;强势上升趋势中放松它们。

---

## 8. 与其他技能组合

| 工作流 | 步骤 |
|--------|------|
| **CANSLIM + VCP** | 用 CANSLIM Screener 找出基本面强劲的成长龙头,再用 VCP Screener 检查 VCP 形态。两者都高分的股票是最强候选 |
| **VCP + Technical Analyst** | VCP Screener 识别入场就绪候选后,用 Technical Analyst 做详细图表确认 —— 支撑/阻力、成交量分布与更大的形态背景 |
| **VCP + Position Sizer** | 把 VCP 输出的枢轴与止损直接喂给 Position Sizer 计算基于风险的股数:`--entry 185.20 --stop 171.40 --account-size 100000 --risk-pct 1.0` |
| **用 FinViz 预过滤** | 用 FinViz Screener 构建自定义范围(例如 `ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to10h,sh_relvol_o1.5`),再用 `--universe` 把这些代码传给 VCP Screener |
| **市场择时** | 仅在 Breadth Chart Analyst 与 Uptrend Analyzer 确认市场宽度健康时交易 VCP 突破。派发信号活跃时避免入场 |

---

## 9. 故障排查

### 找到很少或没有 VCP

**可能原因:**
- 市场处于回调阶段(多数股票处于 Stage 1 或 Stage 4,而非 Stage 2)
- 当前条件下参数过严

**修复:**
- 用 Breadth Chart Analyst 检查市况 —— VCP 主要在 Stage 2 上升趋势中形成
- 试 `--trend-min-score 80`(更松的趋势过滤)
- 试 `--min-contractions 2`(默认)而非 3
- 用 `--full-sp500` 扩大范围(需付费 API 档)

### API 限流(429 错误)

3 阶段流水线对 100 候选约用 201 次 API 调用:
- 阶段 1:约 101 次(报价)
- 阶段 2:约 100 次(历史价格)

免费档(250 次/天)有余量容纳。若因运行多个技能触及上限,等 UTC 0 点重置,或用 `--max-candidates 50` 减少调用。

### ATR 低于阈值的“呆滞”股票

价格波动极小(平均真实波幅 < 价格的 1%)的股票被 `--min-atr-pct` 标志(默认 1.0%)过滤掉。这些可能包括正被收购的股票、仙股或低流动性标的。该过滤防止在实际已“死”的股票上误检 VCP。

---

## 10. 参考资料

### CLI 参数

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| `--api-key` | 否 | `$FMP_API_KEY` | FMP API 密钥 |
| `--max-candidates` | 否 | `100` | 预过滤后做完整 VCP 分析的最大股票数 |
| `--top` | 否 | `20` | 报告中的前 N 结果 |
| `--output-dir` | 否 | `.` | 输出目录 |
| `--universe` | 否 | S&P 500 | 自定义筛选代码 |
| `--full-sp500` | 否 | `false` | 筛选全部 S&P 500(需付费 API) |
| `--mode` | 否 | `all` | 输出模式:`all` 或 `prebreakout`(仅入场就绪) |
| `--max-above-pivot` | 否 | `3.0` | 入场就绪分类的枢轴上方最大 % |
| `--max-risk` | 否 | `15.0` | 入场就绪的最大风险 % |
| `--min-atr-pct` | 否 | `1.0` | 排除呆滞股票的最小日均波幅 % |
| `--min-contractions` | 否 | `2` | 有效 VCP 的最少收缩次数(2-4) |
| `--t1-depth-min` | 否 | `8.0` | T1 回调最小深度 % |
| `--breakout-volume-ratio` | 否 | `1.5` | 突破量对 50 日均量的比率 |
| `--trend-min-score` | 否 | `85.0` | 阶段 2 的最低趋势模板分 |
| `--atr-multiplier` | 否 | `1.5` | ZigZag 摆动检测的 ATR 乘数 |
| `--contraction-ratio` | 否 | `0.75` | 逐次收缩的最大比率 |
| `--min-contraction-days` | 否 | `5` | 每次收缩的最少天数 |
| `--lookback-days` | 否 | `120` | VCP 形态回溯窗口(天) |
| `--ext-threshold` | 否 | `8.0` | 开始计已拉伸惩罚的 SMA50 距离 % |
| `--no-require-valid-vcp` | 否 | `false` | 入场就绪不强制要求 valid_vcp |
| `--max-sma200-extension` | 否 | `50.0` | 进入过度拉伸状态前高于 SMA200 的最大 % |
| `--wide-and-loose-threshold` | 否 | `15.0` | 触发 wide-and-loose 标志的最后收缩深度 % |
| `--strict` | 否 | `false` | 严格模式:要求 3+ 次收缩、每次 7+ 天、比率 0.60 |

### 评分分量

| 分量 | 权重 | 说明 |
|------|------|------|
| 趋势模板 | 25% | Minervini 的 7 点 Stage 2 检查 |
| VCP 形态 | 25% | 收缩质量、深度比率、紧致度 |
| 成交量形态 | 20% | 枯竭比率(越低 = 供给耗尽越好) |
| 枢轴接近度 | 15% | 距计算枢轴点的距离 |
| 相对强度 | 15% | Minervini 加权的相对 S&P 500 表现 |
