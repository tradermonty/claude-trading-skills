---
layout: default
title: "Breakout Trade Planner"
grand_parent: 简体中文
parent: 技能指南
nav_order: 12
lang_peer: /en/skills/breakout-trade-planner/
permalink: /zh/skills/breakout-trade-planner/
generated: false
---

# Breakout Trade Planner
{: .no_toc }

根据 VCP 选股器的输出生成 Minervini 风格的突破交易计划。结合最差情形风险分析计算入场价、止损价与目标价,并提供 Alpaca 兼容的括号订单(bracket order)模板。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/breakout-trade-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/breakout-trade-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Breakout Trade Planner 衔接在 VCP Screener(负责发现候选标的)与实际订单执行(负责下单)之间。它回答的关键问题是:**"我找到了一个 VCP 形态——那么接下来到底该买什么、在什么价位、买多少股、止损设在哪里?"**

**它解决的问题:**
- 把 VCP 选股器的评分转化为具体的交易计划,给出精确的入场/止损/目标价位
- 基于最差情形成交价(而非乐观的信号价)计算仓位规模
- 强制执行组合层面的风险限额(风险敞口上限、板块集中度)
- 为每个候选标的生成两套 Alpaca 括号订单模板:预先下单(自动触发)与确认后下单(5 分钟K线验证)
- 把候选标的分类为可执行、待重新验证、观察名单、已拒绝、延后、受限——每一类都附带明确的理由

**设计理念(与 Minervini 方法一致):**
- 绝不追高:最多不超过枢轴点(pivot)上方 2%
- 严控风险:任何最差情形风险超过 8% 的交易都会被拒绝
- 使用止损限价单(stop-limit):触发价为枢轴点 + 0.1%,限价为枢轴点 + 2%,以防止追逐跳空
- 最差情形定仓位:所有仓位计算都以限价(而非止损触发价)作为入场价

**在流水线中的位置:**
```
VCP Screener --> Breakout Trade Planner --> [breakout-monitor (未来功能)]
  (发现)           (规划)                     (执行)
```

---

## 2. 前提条件

> 无需 API 密钥。本技能完全基于本地的 VCP 选股器 JSON 文件运行。
{: .no_api }

**必需:**
- 带有 `schema_version: "1.0"` 的 VCP 选股器 JSON 输出(由 [VCP Screener](/zh/skills/vcp-screener/) 技能生成)
- Python 3.9+
- 不依赖任何外部技能(仓位计算内置)

**可选:**
- `--current-exposure-json` 文件,用于反映现有组合的约束条件

---

## 3. 快速开始

```bash
# 第 1 步:先运行 VCP 选股器(如尚未运行)
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/

# 第 2 步:根据选股器输出生成交易计划
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_2026-04-12_200418.json \
  --account-size 100000 \
  --risk-pct 0.5 \
  --output-dir reports/

# 或者直接告诉 Claude:
# "根据最新的 VCP 选股器结果生成突破交易计划,
#  账户规模 10 万美元"
```

---

## 4. 工作原理

### 交易价格推导

根据每个 VCP 候选标的的枢轴点价格与最近一次收缩低点:

```
signal_entry = pivot * 1.001     (止损触发买入:枢轴点上方 0.1%)
worst_entry  = pivot * 1.02      (限价买入上限:枢轴点上方 2%)
stop_loss    = last_low * 0.99   (最近收缩低点下方 1%)
```

**为什么需要两个入场价?** 止损限价单的实际成交价会落在 `signal_entry` 与 `worst_entry` 之间的某处。规划器在所有风险与仓位计算中均使用 `worst_entry`,以确保即便在最差成交情形下计划依然有效。

### Minervini 关卡(Gate)

每个候选标的在获得交易计划之前都要经过一道严格的关卡检验:

| 条件 | 突破前(Pre-breakout) | 已突破(Breakout) |
|-----------|:---:|:---:|
| valid_vcp = True | 必须满足 | 必须满足 |
| composite_score >= 70 | 必须满足 | 必须满足 |
| risk_pct_worst <= 8% | 必须满足 | 必须满足 |
| breakout_volume_detected | -- | 必须满足 |
| distance_from_pivot <= 2% | -- | 必须满足 |
| current_price <= worst_entry | -- | 必须满足 |

### 分类

候选标的按综合评分从高到低排序,并分类为:

| 分类 | 判定标准 | 输出内容 |
|---------------|---------|--------|
| **可执行(Actionable)** | 突破前,通过关卡 | 订单模板 + 交易计划 |
| **待重新验证(Revalidation)** | 已突破,通过关卡 | 仅供参考(无订单模板) |
| **观察名单(Watchlist)** | valid_vcp 成立,评分 60-69 | 枢轴点提醒触发器 |
| **延后(Deferred)** | 通过关卡但超出风险敞口上限 | 排入下一交易日队列 |
| **受限(Constrained)** | 因板块/持仓限制而股数为 0 | 记录具体原因 |
| **已拒绝(Rejected)** | 未通过关卡 | 拒绝理由 |

### 仓位规模计算

内部调用 [Position Sizer](/zh/skills/position-sizer/) 技能:

1. 根据评级对基础风险百分比应用乘数:
   - 教科书级(90 分以上):1.75 倍
   - 强势(80-89 分):1.0 倍
   - 良好(70-79 分):0.75 倍
2. 根据 `worst_entry` 与 `stop_loss` 计算股数
3. 应用组合约束(最大单一持仓占比、最大板块占比、风险敞口上限)
4. 跟踪所有已生成订单的累积风险

---

## 5. 使用示例

### 示例 1:基础交易计划生成

**提示词:**
```
根据最新的 VCP 选股器结果生成突破交易计划。
账户规模 10 万美元,每笔交易风险 0.5%。
```

**实际执行过程:**
1. 加载最新的 VCP 选股器 JSON
2. 通过 Minervini 关卡过滤
3. 使用最差情形入场价计算仓位规模
4. 输出 JSON(用于自动化)和 Markdown(用于人工审阅)

---

### 示例 2:结合现有组合敞口

创建一个敞口文件:
```json
{
  "sector_exposure": {"Technology": 22.0, "Industrials": 8.5},
  "open_risk_pct": 3.2
}
```

```bash
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_2026-04-12.json \
  --account-size 100000 --risk-pct 0.5 \
  --current-exposure-json exposure.json \
  --output-dir reports/
```

**为什么有用:** 可以防止过度集中持仓。如果科技板块已经占到 22%,再加一只科技股就会受到 30% 板块上限的约束。

---

### 示例 3:保守参数设置

```bash
python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py \
  --input reports/vcp_screener_2026-04-12.json \
  --account-size 50000 \
  --risk-pct 0.25 \
  --max-portfolio-heat-pct 3.0 \
  --max-chase-pct 1.0 \
  --output-dir reports/
```

**效果:** 更小的仓位(0.25% 风险)、更紧的风险敞口上限(3%),以及枢轴点上方仅 1% 的追价容忍度。适合波动较大的市场或较小的账户。

---

### 示例 4:解读一笔可执行订单

JSON 输出中典型的可执行订单(枢轴点 = $100,最近低点 = $95):

```json
{
  "symbol": "EXAMPLE",
  "rating_band": "strong",
  "plan_type": "pending_breakout",
  "decision_code": "ACTIONABLE_PREBREAKOUT",
  "trade_plan": {
    "signal_entry": 100.10,
    "worst_entry": 102.00,
    "stop_loss_price": 94.05,
    "risk_pct_worst": 7.79,
    "target_price": 117.90,
    "shares": 62,
    "risk_dollars": 492.90
  },
  "order_templates": {
    "pre_place": {
      "type": "stop_limit",
      "stop_price": 100.10,
      "limit_price": 102.00,
      "order_class": "bracket"
    },
    "post_confirm": {
      "type": "limit",
      "limit_price": 102.00,
      "order_class": "bracket",
      "entry_condition": { "bar_interval": "5min", "..." : "..." }
    }
  }
}
```

**如何解读**(枢轴点 = $100,最近低点 = $95):
- **signal_entry**($100.10):止损买单在枢轴点 + 0.1% 处触发
- **worst_entry**($102.00):在枢轴点 + 2% 处的最高成交价。所有仓位计算均以此为基础
- **stop_loss_price**($94.05):最近收缩低点 $95 减去 1% 缓冲
- **risk_pct_worst**(7.79%):(102.00 - 94.05) / 102.00——通过 8% 关卡
- **target_price**($117.90):worst_entry + 2R = 102.00 + 2 * (102.00 - 94.05)
- **两套订单模板**:可选择 pre_place(设置后无需干预)或 post_confirm(等待 5 分钟K线确认)

---

## 6. 解读输出

### JSON 报告结构

```
breakout_trade_plan_YYYY-MM-DD_HHMMSS.json
├── schema_version: "1.0"
├── parameters           -- 使用的全部 CLI 参数
├── input_metadata       -- 来源文件、候选标的数量
├── summary              -- 数量统计与汇总
├── actionable_orders[]  -- 带订单模板的交易计划
├── revalidation[]       -- 突破状态下的参考建议
├── watchlist[]          -- 正在形成中的 VCP 提醒
├── rejected[]           -- 未通过关卡(附理由)
├── deferred[]           -- 触及组合风险敞口上限
├── constrained[]        -- 因约束条件股数为零
└── warnings[]           -- 校验问题
```

### 交易计划中的关键字段

| 字段 | 说明 |
|-------|-------------|
| `risk_pct_signal` | 基于信号入场价的风险(乐观值) |
| `risk_pct_worst` | 基于最差入场价的风险(**用于关卡判定**) |
| `r_multiples_signal` | 基于信号入场价的 R 目标(参考用) |
| `r_multiples_worst` | 基于最差入场价的 R 目标(**用于下单**) |
| `cumulative_risk_pct` | 加入此订单后的组合滚动风险敞口 |
| `binding_constraint` | 限制该仓位规模的具体约束条件 |

### Markdown 报告

人类可读的摘要,包含可执行订单、待重新验证候选标的与观察名单条目的表格。

---

## 7. 技巧与最佳实践

**风险管理:**
- 账户规模低于 10 万美元时,建议每笔交易风险从 0.5% 起步
- 将组合风险敞口控制在 6%(默认值)以下——这限制了同时承担的总风险
- 默认的 `--max-chase-pct 2.0` 可防止买入过度延伸的突破。在波动剧烈的市场中可收紧至 1.0%

**订单模板选择:**
- **pre_place**(止损限价单):最适合忙碌的交易者。在开盘前下单,价格触及枢轴点时自动触发。风险:可能在低成交量的假突破上被触发
- **post_confirm**(5 分钟确认后限价单):最适合配合即将推出的 breakout-monitor 进行主动交易的人。会等待收盘价突破枢轴点并在 5 分钟K线上得到成交量确认。误报率更低

**当没有候选标的可执行时:**
- 这是正常且预期的情况。关卡设计本就十分严格
- 查看 `rejected` 列表以了解候选标的失败的原因
- 常见原因:风险过高(止损过宽)、评分低于 70、VCP 形态无效、执行状态不符

**与其他技能结合使用:**
- 使用 `--strict` 运行 VCP Screener,预先过滤出仅有效的 VCP 形态
- 直接使用 Position Sizer 进行手动仓位调整
- 把可执行的标的提供给 Technical Analyst 进行图表确认

---

## 8. 与其他技能组合

### 完整突破交易工作流

```
1. VCP Screener          --> 发现具有 VCP 形态的候选标的
2. Breakout Trade Planner --> 生成带仓位规模的交易计划
3. Technical Analyst      --> 图表视觉确认
4. [breakout-monitor]     --> 5 分钟K线执行(未来功能)
5. Trader Memory Core     --> 登记交易论点,跟踪生命周期
6. Portfolio Manager      --> 通过 Alpaca 监控持仓
```

### 财报动量变体

```
1. Earnings Trade Analyzer --> 为财报后反应打分
2. PEAD Screener           --> 寻找回调形态
3. VCP Screener(自定义范围) --> 在 PEAD 候选标的上检测 VCP
4. Breakout Trade Planner  --> 生成入场计划
```

---

## 9. 故障排查

### "Input JSON missing schema_version"

你的 VCP 选股器 JSON 是在添加 `schema_version` 字段之前生成的。重新运行 VCP 选股器以生成新的报告:

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/
```

### 所有候选标的都被拒绝

检查 JSON 输出中的 `rejected` 数组。常见原因包括:
- **"risk_pct_worst > 8%"**:止损距离入场价过远。该股票最近一次收缩幅度过宽
- **"rating_band=developing"**:评分为 60-69(下单要求的最低评分为 70,即 Good VCP)
- **"valid_vcp=False"**:VCP 形态校验失败(收缩幅度递增、T1 过浅等)
- **"state=Overextended"**:股价距离 SMA200 或枢轴点过远

### 当前市场中没有可执行标的

Minervini 关卡的设计本就十分严格。在市场调整期或延伸过久的上涨行情中,能形成紧凑、可买入的 VCP 形态的股票可能很少。这是设计上的特性,不是缺陷——它能让你避开低概率的形态。

---

## 10. 参考资料

### CLI 参数

| 参数 | 默认值 | 说明 |
|-----------|---------|-------------|
| `--input` | (必填) | VCP 选股器 JSON 路径 |
| `--account-size` | (必填) | 账户净值($) |
| `--risk-pct` | 0.5 | 每笔交易的基础风险百分比 |
| `--max-position-pct` | 10.0 | 单一持仓占账户的最大比例 |
| `--max-sector-pct` | 30.0 | 单一板块占账户的最大敞口比例 |
| `--max-portfolio-heat-pct` | 6.0 | 总持仓风险敞口上限 |
| `--target-r-multiple` | 2.0 | 止盈的 R 倍数 |
| `--stop-buffer-pct` | 1.0 | 最近收缩低点下方的缓冲百分比 |
| `--max-chase-pct` | 2.0 | 入场价相对枢轴点的最大追价百分比 |
| `--pivot-buffer-pct` | 0.1 | 止损买入触发价相对枢轴点的百分比 |
| `--current-exposure-json` | None | 现有组合敞口文件 |
| `--output-dir` | reports/ | 输出目录 |

### 评级分档与仓位规模

| 分档 | 评分区间 | 仓位乘数 | 操作 |
|------|-----------|-------------------|--------|
| 教科书级(Textbook) | 90-100 | 1.75 倍基础风险 | 生成订单模板 |
| 强势(Strong) | 80-89 | 1.0 倍基础风险 | 生成订单模板 |
| 良好(Good) | 70-79 | 0.75 倍基础风险 | 生成订单模板 |
| 发展中(Developing) | 60-69 | 0.0 倍(不下单) | 仅加入观察名单 |
| 弱势(Weak) | <60 | 0.0 倍 | 拒绝 |

### 判定代码

| 代码 | 含义 |
|------|------|
| `ACTIONABLE_PREBREAKOUT` | 突破前状态,通过全部关卡条件 |
| `REVALIDATION_BREAKOUT` | 已突破状态,需要用实时价格重新验证 |

### 输出文件

| 文件 | 格式 | 用途 |
|------|--------|------|
| `breakout_trade_plan_*.json` | JSON | 带订单模板的机器可读计划 |
| `breakout_trade_plan_*.md` | Markdown | 供人工审阅的可读报告 |

### 架构

```
plan_breakout_trades.py   主流水线:加载、过滤、定仓位、输出
  ├── risk_calculator.py  交易价格、风险百分比、R 倍数、仓位计算(自成一体)
  └── order_builder.py    Alpaca 括号订单模板
```
