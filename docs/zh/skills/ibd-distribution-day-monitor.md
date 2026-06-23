---
layout: default
title: "Ibd Distribution Day Monitor"
grand_parent: 简体中文
parent: 技能指南
nav_order: 29
lang_peer: /en/skills/ibd-distribution-day-monitor/
permalink: /zh/skills/ibd-distribution-day-monitor/
generated: false
---

# Ibd Distribution Day Monitor
{: .no_toc }

检测 QQQ/SPY 上 IBD 风格的派发日(收盘下跌至少 0.2% 且成交量放大),追踪 25 个交易日的失效期与 5% 的作废条件,统计 d5/d15/d25 区间内的派发日簇,将市场风险分类为 NORMAL/CAUTION/HIGH/SEVERE,并给出 TQQQ/QQQ 的敞口建议。适用于收盘后的盘后复盘、调整 TQQQ 敞口之前,或作为 FTD/市场状态框架的输入。不执行交易。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ibd-distribution-day-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ibd-distribution-day-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

IBD Distribution Day Monitor 把威廉·欧奈尔(William O'Neil)CAN SLIM 框架中最具可操作性的单一信号自动化:统计机构悄然出货的天数。历史上,派发日(Distribution Day)的密集出现往往领先于大多数重大市场修正,而本技能把这条规则转化为可复现的每日工作流。

**解决的问题:**
- 消除了交易者在实践中对这条规则的不同理解所带来的歧义(例如:"25 个交易日是否包含当天?"、"派发日当天的盘中高点是否计入作废判定?")。
- 一条命令即可生成确定性的风险等级(NORMAL / CAUTION / HIGH / SEVERE)以及考虑 TQQQ 的敞口建议。
- 用可审计的 JSON 输出取代肉眼判断,其中包含构成当前活跃计数的具体日期。
- 同时处理 QQQ 与 SPY,并以 TQQQ 加权的策略把它们合并起来,使大盘恶化的信号能够及时升级。

**核心能力:**
- 派发日检测:收盘下跌至少 0.2% 且成交量放大,在边界值上显式处理浮点误差(epsilon)
- 25 个交易日失效期与 5% 作废条件分别独立追踪,`removal_reason` 字段会记录为 `expired_25_sessions` 或 `invalidated_5pct_gain`
- 展示用与作废判定用的 `high_since` 是分离的:派发日当天的盘中高点会显示出来,但永远不会被用来作废当天的派发日本身
- 可配置的 `invalidation_price_source`:`high`(保守,默认)或 `close`(仅使用收盘价)
- 风险分级支持可配置的 `RiskThresholds`,并叠加 21EMA / 50SMA 过滤器——当指数同时低于这两条均线时会升级为 SEVERE
- TQQQ 加权的多指数合并逻辑:QQQ 单独达到 HIGH,或 (QQQ, SPY) 组合为 NORMAL+HIGH,都会拉高整体风险
- TQQQ 敞口策略(100 / 75 / 50 / 25%),并配合逐步收紧的移动止损;QQQ 使用相对温和的版本
- UTF-8 输出(`ensure_ascii=False`);审计快照中的 API 密钥会自动打码

---

## 2. 前提条件

- **API 密钥:**[Financial Modeling Prep (FMP)](https://site.financialmodelingprep.com/developer/docs)——免费层(每日 250 次调用)足以支撑每日对 QQQ + SPY 的运行。
- **Python 3.9+:** 标准库加上 `requests`(已安装)和 `pyyaml`(已在 `pyproject.toml` 依赖中)。
- **不依赖 pandas:** 所有 OHLCV 数据都以 `list[dict]` 形式处理,兼顾可移植性和速度。

> 通过环境变量一次性设置 API 密钥:`export FMP_API_KEY=your_key_here`。本技能解析密钥的优先级为 `--api-key` 参数 > 配置文件中的 `data.api_key` > `FMP_API_KEY` 环境变量,因此命令行覆盖始终优先。
{: .tip }

> 派发日规则本身不依赖任何特定的市场结构假设,因此本技能适用于任何 FMP 支持的流动性良好的美股 ETF / 指数。默认参数针对 QQQ + SPY 调优。
{: .note }

---

## 3. 快速开始

使用默认设置运行脚本:

```bash
export FMP_API_KEY=your_key_here

python3 skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py \
  --symbols QQQ,SPY \
  --lookback-days 80 \
  --instrument TQQQ \
  --current-exposure 100 \
  --base-trailing-stop 10 \
  --output-dir reports/
```

脚本会为每个代码拉取 80 个交易日的 OHLCV 数据,检测活跃的派发日,完成风险分级,并向 `reports/` 写入一对 JSON + Markdown 报告,文件名为 `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.{json,md}`。

你也可以在 Claude Code 中用对话方式调用它:"运行今天的 IBD 派发日监测,告诉我是否应该维持 100% 的 TQQQ 敞口。"

---

## 4. 工作原理

```
+-----------------+   +-----------------------+   +-----------------------+
| 1. 拉取 OHLCV   |-->| 2. as_of 归一化       |-->| 3. 检测派发日          |
|   (按代码请求    |   |   prepare_effective_  |   |  pct_change <= -0.002 |
|    FMP)         |   |   history             |   |  且成交量放大          |
+-----------------+   +-----------------------+   +-----------+-----------+
                                                              |
+-----------------+   +-----------------------+   +-----------v-----------+
| 7. 合并风险      |<--| 6. 逐指数分级         |<--| 4. 记录数据增强         |
|   QQQ 加权       |   |   d5/d15/d25 + 均线   |   |  high_since(展示用)   |
+--------+--------+   +-----------------------+   |  作废事件               |
         |                                         |  失效期 / 状态          |
         v                                         +-----------+-----------+
+-----------------+   +-----------------------+               |
| 8. 敞口          |-->| 9. 写入 JSON + MD     |<--------------+
|   策略(TQQQ)    |   |  并打码敏感信息        |
+-----------------+   +-----------------------+
```

1. **拉取 OHLCV** —— 每个代码会额外多请求 `lookback_days + 5` 个交易日,以确保 50SMA 过滤器有足够的历史数据。`fmp_client.py` 已按 Issue #64 的修复正确截断数据。
2. **`as_of` 归一化** —— 无论是默认的今天,还是用户通过 `--as-of YYYY-MM-DD` 指定的日期,都会被重新基准化,使 `effective_history[0]` 始终是评估当天。这一过程不会向下游模块传递 `as_of_index`,从而保持追踪器代码的简洁。
3. **派发日检测** —— 对每一对连续的交易日,判断 `pct_change <= -0.002 + EPSILON` 且成交量放大。收盘价或成交量缺失/非正的交易日会被跳过,并记录到审计信息中的 `skipped_sessions`。
4. **数据增强** —— 每条原始派发日记录都会被补全为完整记录:
    - 用于展示的 `high_since` = `max(history[0:k+1] 中的最高价)`(包含派发日当天)
    - 作废扫描范围 = `history[0:k]` 与失效期窗口的交集,使用配置的 `invalidation_price_source`
    - 状态优先级:`invalidated` > `expired` > `active`
    - 若 5% 涨幅出现在 25 个交易日**之后**,则归类为 `expired_25_sessions`,而非作废。
5. **计数** —— `count_active_in_window(records, N)` 返回 `age_sessions <= N` 的 `active` 记录数。因此 `d25_count` 包含 age 0 到 25(共 26 个交易日)。这与 `expiration_sessions = 25` 保持一致:age=25 的派发日仍处于活跃状态并计入统计;age=26 则已失效并被排除。
6. **逐指数分级** —— 阈值(例如 SEVERE 对应 `d25 >= 6` 或 `d15 >= 4` 等)从配置文件(`RiskThresholds`)加载。21EMA / 50SMA 过滤器只有在收盘价**同时**低于这两条均线、且 `d25 >= 5` 时才会升级为 SEVERE。若因数据不足而无法计算均线,该过滤器值为 `None`,跳过 SEVERE 升级判定。
7. **合并** —— 合并后的风险以 QQQ 为加权核心:任一指数出现 SEVERE,或 QQQ 单独达到 HIGH,都会立即触发升级。`QQQ NORMAL + SPY HIGH` 的组合仍会升级为 HIGH,因为历史上大盘的恶化往往会蔓延到 TQQQ。其余情况取两者中的最大风险等级。
8. **敞口策略** —— 随着风险上升,TQQQ 的目标敞口依次降为 {100, 75, 50, 25}%,并相应收紧移动止损。QQQ 使用更温和的版本({100, 100, 75, 50}%)。该建议永远不会**放宽**用户现有的移动止损——只能收紧。
9. **输出** —— JSON 以 `ensure_ascii=False` 写入,确保日文说明文字在往返读写中不被破坏。敏感字段(`api_key`、`fmp_api_key`、`token` 等)会在写入任何文件之前,通过小写比较自动打码。

---

## 5. 使用示例

### 示例 1:每日盘后检查

**提示词:**
```
运行今天的 IBD 派发日监测,告诉我是否应该调整我的 TQQQ 持仓。
```

**会发生什么:** 该技能加载 80 个交易日的 QQQ + SPY 数据,检测活跃的派发日,并输出合并后的风险等级以及针对 TQQQ 的具体建议(目标敞口百分比、移动止损百分比)。

**为什么有用:** 用几秒钟内得到的确定性答案取代了肉眼盯盘指数图表。同样的输入永远产生同样的输出,这正是风险管理规则所需要的。

---

### 示例 2:回测历史顶部

**提示词:**
```
2025-04-04(关税冲击下跌后的第二天)的 IBD 派发日情况是怎样的?
```

**会发生什么:** 使用 `--as-of 2025-04-04 --lookback-days 80`,该技能会重新基准化历史数据,使 2025-04-04 成为评估当天,并按照"今天就是那一天"的方式运行整套流程。均线过滤器与 5% 作废追踪器都会遵循当时的历史情境。

**为什么有用:** 用于验证这条规则是否能在实际下跌发生之前就发出预警。如果审计信息显示 `insufficient_lookback`,只需通过加大 `lookback-days` 来请求更多历史数据即可。

---

### 示例 3:调整风险阈值

**提示词:**
```
我想要更保守的触发条件。把 HIGH 阈值改为 d25 >= 4,然后重新运行今天的分析。
```

**会发生什么:** 编辑 `skills/ibd-distribution-day-monitor/config/default.yaml`(或传入自定义的 `--config` 文件),将 `risk_thresholds.high.d25_count` 设为 `4`,然后重新运行。该技能会加载新阈值并重新分级。建议先用 `--as-of` 在历史日期上测试改动。

**为什么有用:** 不同交易者偏好不同的敏感度。该技能从不硬编码阈值——所有阈值都存放在 YAML 中,可以按投资组合逐一调整。

---

### 示例 4:切换为收盘价作废判定

**提示词:**
```
我希望只有当指数收盘价比派发日收盘价高出 5% 以上时才作废该派发日,而不是依据盘中高点。
```

**会发生什么:** 在配置文件中设置 `distribution_day_rule.invalidation_price_source: close`。此时 `_find_invalidation_event` 扫描器会用 `row["close"]`(而不是 `row["high"]`)与 `dd_close * 1.05` 进行比较。

**为什么有用:** 部分交易者更偏好严格的收盘价口径。该技能在不改代码的情况下同时支持两种口径,具体选择会记录在 `audit.rule_evaluation.distribution_day_rule.invalidation_price_source` 中。

---

### 示例 5:加仓 TQQQ 前的预交易合理性检查

**提示词:**
```
我正考虑给 TQQQ 加仓 25%。当前市场环境是否适合这么做?
```

**会发生什么:** 该技能运行后报告当前的风险等级。若为 NORMAL,建议是 `HOLD_OR_FOLLOW_BASE_STRATEGY`;若为 CAUTION,建议是 `AVOID_NEW_ADDS`;若为 HIGH 或 SEVERE,则会明确提出降低敞口。

**为什么有用:** 在杠杆加仓前花 5 秒做一次合理性检查。在 HIGH 状态的市场中反复加仓,是业余 TQQQ 交易者亏损超过指数本身跌幅的最常见方式之一。

---

### 示例 6:与 Position Sizer 组合使用

**提示词:**
```
风险等级是 HIGH。根据该建议,用更紧的移动止损重新计算我的 TQQQ 持仓规模。
```

**会发生什么:** IBD Monitor 对 HIGH 状态返回 `trailing_stop_pct: 5`;随后把该值传入 Position Sizer 技能(`--atr-multiplier` 或基于止损的定仓方式),计算出更紧止损下的具体持股数量。

**为什么有用:** 风险管理是层层传递的。派发日信号决定移动止损,移动止损决定持仓股数。两者都是确定性的,也都可审计。

---

## 6. 解读输出

该技能会写出两个文件以及一段控制台摘要:

1. **JSON 报告** —— 完整 schema,包含 `market_distribution_state`、`portfolio_action`、`rule_evaluation` 和 `audit` 等部分。UTF-8 编码,`ensure_ascii=False`。
2. **Markdown 报告** —— 人类可读的摘要,包含各指数的活跃派发日表格、建议操作和审计标记。

### 风险等级速查表

| 风险等级 | 触发条件(满足其一) | TQQQ 操作 | TQQQ 目标敞口 | 移动止损上限 |
|------|------------------|-------------|-------------|----------------|
| NORMAL | `d25 <= 2` | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | 基础值 |
| CAUTION | `d25 >= 3` | AVOID_NEW_ADDS | 75% | 7% |
| HIGH | `d25 >= 5` 或 `d15 >= 3` 或 `d5 >= 2` | REDUCE_EXPOSURE | 50% | 5% |
| SEVERE | `d25 >= 6` 或 `d15 >= 4` 或(收盘价低于 21EMA 且低于 50SMA 且 `d25 >= 5`) | CLOSE_TQQQ_OR_HEDGE | 25% | 3% |

### 单条派发日记录字段

| 字段 | 含义 |
|-------|---------|
| `date` | 派发日日期 |
| `age_sessions` | 自派发日起经过的交易日数(0 表示当天) |
| `expires_in_sessions` | `25 - age_sessions`,下限为 0 |
| `pct_change` | 派发日当天的跌幅(负值) |
| `volume_change_pct` | 派发日当天相对前一交易日的成交量变化 |
| `high_since` | 从派发日当天到今天的盘中高点最大值(展示用,**包含**派发日当天) |
| `invalidation_price` | `dd_close * 1.05` |
| `invalidation_date` | 派发日之后首次触发 5%+ 涨幅的日期(未触发则为 null) |
| `invalidation_trigger_price` | 实际触发的价格(取决于配置,可能是最高价或收盘价) |
| `invalidation_trigger_source` | 按配置取值为 `"high"` 或 `"close"` |
| `status` | `active`、`expired` 或 `invalidated` |
| `removal_reason` | `expired_25_sessions` 或 `invalidated_5pct_gain`(活跃状态下为 null) |

### 审计标记

| 标记 | 含义 |
|------|------|
| `insufficient_lookback` | 已加载的历史数据短于所需窗口(50SMA + 1 等) |
| `insufficient_data_for_moving_average` | 无法计算 21EMA 或 50SMA;跳过 SEVERE 升级判定 |
| `data_quality_warnings` | 至少有一个交易日因 OHLCV 缺失或无效而被跳过 |
| `no_data_returned` | FMP 未为一个或多个代码返回任何数据行 |

---

## 7. 技巧与最佳实践

- **收盘后运行,而不是盘中。** 派发日规则是为收盘数据设计的。盘中的成交量估算并不可靠,一个"盘中派发日"可能会随着尾盘价格收复而消失。
- **关注密集出现的形态,而不只是数量本身。** 5 个交易日内出现 2 次派发日(`d5 >= 2`)比 25 个交易日内分散出现 5 次更危险,即便两者都被判定为 HIGH。该技能通过 d5/d15/d25 三个区间同时捕捉这两种情况。
- **用 `--as-of` 在历史数据上验证规则。** 在信任任何阈值调整之前,先用修改后的配置对 2008、2018、2020、2022 以及 2025 年 4 月这几段历史运行一遍,确认规则会在正确的时间点触发。
- **不要放宽你的移动止损。** 该技能的建议永远是 `min(你的基础止损, 策略上限)`。如果你现有的止损本身就更紧,该技能会尊重这一点。自行手动放宽止损会违背这条规则的初衷。
- **`market_below_21ema_or_50ma=None` 的情况是真实存在的。** 在某只新上市股票或交易稀薄的指数刚上市的前 50 个交易日内,50SMA 过滤器是不可用的。该技能会正确返回 `None` 并跳过 SEVERE 升级判定,而不是去猜测。
- **与 FTD Detector 组合使用以获得完整的市场状态。** 派发日提示你防守,跟进日(Follow-Through Day)则给你进攻的信号。同时运行这两个技能,是用于大盘指数择时最简单的"两极"框架。

---

## 8. 与其他技能组合

| 工作流 | 组合方式 |
|----------|---------------|
| **每日敞口复盘** | 先运行 IBD Distribution Day Monitor 获取风险等级,再运行 Market Breadth Analyzer 做确认。如果两者出现分歧(例如派发日信号为 HIGH,但宽度信号显示 Strong),值得进一步调查 |
| **底部确认搭档** | 在 SEVERE → 下跌 → 反弹之后,从最低收盘价开始运行 FTD Detector。跟进日信号与派发日的警示信号相互制衡 |
| **仓位管理** | 把移动止损建议传入 Position Sizer,用于杠杆 ETF 的定仓;更紧的止损会直接转化为更小的持仓股数 |
| **顶部概率综合评估** | 把 `risk_level` 作为多个顶部侧输入之一喂给 Market Top Detector。派发日聚集是欧奈尔六大顶部信号组件之一 |
| **回测验证** | 在多个历史日期上循环使用 `--as-of`,并把 JSON 结果输入 Backtest Expert,评估该阈值 + 敞口策略相对于买入持有是否改善了回撤 |
| **Kanchi 式股息组合** | 把风险等级当作一层叠加判断:在 HIGH/SEVERE 状态下不加仓 TQQQ,但只要个股层面的 T1-T5 触发条件干净,Kanchi 式的股息加仓仍可继续 |

---

## 9. 故障排查

### `FMP API key required` 报错

**原因:** `--api-key`、`config.data.api_key`、`FMP_API_KEY` 环境变量都未设置。

**解决方法:** 在 shell 中设置 `export FMP_API_KEY=your_key_here`,或在命令行中传入 `--api-key your_key_here`。该技能从不通过其他方式从磁盘读取密钥,除非走显式的配置路径。

### `as_of YYYY-MM-DD not found in loaded history`

**原因:** 传入的日期不是 FMP 数据中的交易日,或者超出了 `lookback_days` 允许的范围。

**解决方法:** 确认该日期是美股交易日(不是周末或假日),然后增大 `--lookback-days`,确保该日期落在已加载的窗口内。对于距今超过 80 个交易日的日期,把 `--lookback-days` 设为 200 或更高。

### `insufficient_lookback` 审计标记

**原因:** 经过 `as_of` 切片后,剩余的历史数据行数少于 `required_min_sessions = max(lookback, 50, expiration_sessions + 2)`。

**解决方法:** 增大 `--lookback-days`,使切片后仍有足够的交易日。分析仍会继续运行,但 50SMA 可能为 `None`,SEVERE 升级判定会被跳过。

### `insufficient_data_for_moving_average` 审计标记

**原因:** 已加载的历史数据收盘价少于 21 条(无法计算 21EMA)或少于 50 条(无法计算 50SMA)。

**解决方法:** 把 `--lookback-days` 增大到至少 80。如果你确实想用更短的历史窗口,需要接受 SEVERE 只能通过 `d25 >= 6` 或 `d15 >= 4` 触发,而不会通过均线条件触发。

### 风险等级显示 HIGH,但新闻面看起来没什么问题

**原因:** 派发日簇往往领先于引发头条新闻的抛售数天甚至数周。2007 年年中、2021 年末和 2022 年初,在实际崩盘成为新闻头条之前,派发日计数都已处于 HIGH 状态。

**解决方法:** 这正是预期中的行为——领先指标在看起来"显而易见"之前,总会让人觉得"为时过早"。请信任这条规则,收紧止损,避免新增加仓。如果想了解为什么等级是 HIGH,可查看 Markdown 报告中的活跃派发日表格。

### 建议的移动止损比我实际设置的止损更宽

**原因:** 该技能返回的是 `min(你的基础止损, 策略上限)`。如果你传入 `--base-trailing-stop 4`,而 HIGH 状态的策略上限是 5%,建议值会正确地保持在 4%。

**解决方法:** 无需处理——这是预期中的行为。该技能从不会放宽你现有的更紧止损。

---

## 10. 参考资料

### 命令行参数

| 参数 | 是否必需 | 默认值 | 说明 |
|----------|----------|---------|-------------|
| `--symbols` | 否 | `QQQ,SPY`(来自配置) | 逗号分隔的代码列表 |
| `--lookback-days` | 否 | `80` | 要加载的交易日数 |
| `--instrument` | 否 | `TQQQ`(来自配置) | `TQQQ` 或 `QQQ`(决定敞口策略) |
| `--current-exposure` | 否 | `100`(来自配置) | 当前敞口,整数百分比 |
| `--base-trailing-stop` | 否 | `10`(来自配置) | 基础移动止损百分比(该技能从不放宽它) |
| `--as-of` | 否 | 最近交易日 | `YYYY-MM-DD`,用于回测评估 |
| `--config` | 否 | `config/default.yaml` | 自定义 YAML 覆盖文件路径 |
| `--api-key` | 否 | `FMP_API_KEY` 环境变量 | FMP API 密钥 |
| `--output-dir` | 否 | `reports/` | JSON + MD 报告对的输出目录 |

### 默认配置(`config/default.yaml`)

| 区块 | 键 | 默认值 |
|---------|-----|---------|
| `distribution_day_rule` | `min_decline_pct` | `-0.002` |
| `distribution_day_rule` | `expiration_sessions` | `25` |
| `distribution_day_rule` | `invalidation_gain_pct` | `0.05` |
| `distribution_day_rule` | `invalidation_price_source` | `high` |
| `risk_thresholds.caution` | `d25_count` | `3` |
| `risk_thresholds.high` | `d25_count` / `d15_count` / `d5_count` | `5 / 3 / 2` |
| `risk_thresholds.severe` | `d25_count` / `d15_count` / `severe_ma_d25` | `6 / 4 / 5` |
| `moving_average_filters` | `ema_periods` | `[21]` |
| `moving_average_filters` | `sma_periods` | `[50]` |
| `strategy_context` | `instrument` | `TQQQ` |
| `strategy_context` | `current_exposure_pct` | `100` |
| `strategy_context` | `base_trailing_stop_pct` | `10` |

### TQQQ 与 QQQ 敞口策略对比

| 风险等级 | TQQQ 操作 | TQQQ 目标敞口 | TQQQ 止损上限 | QQQ 操作 | QQQ 目标敞口 | QQQ 止损上限 |
|------|-------------|-------------|----------------|-----------|------------|---------------|
| NORMAL | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | 基础值 | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | 基础值 |
| CAUTION | AVOID_NEW_ADDS | 75% | 7% | AVOID_NEW_ADDS | 100% | 8% |
| HIGH | REDUCE_EXPOSURE | 50% | 5% | REDUCE_EXPOSURE | 75% | 6% |
| SEVERE | CLOSE_TQQQ_OR_HEDGE | 25% | 3% | REDUCE_EXPOSURE_OR_HEDGE | 50% | 5% |

### 输出文件

| 文件 | 说明 |
|------|-------------|
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json` | 完整结构化报告(UTF-8、`ensure_ascii=False`、敏感信息已打码) |
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.md` | 人类可读摘要 + 活跃派发日表格 |
