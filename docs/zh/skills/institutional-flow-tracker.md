---
layout: default
title: "Institutional Flow Tracker"
grand_parent: 简体中文
parent: 技能指南
nav_order: 30
lang_peer: /en/skills/institutional-flow-tracker/
permalink: /zh/skills/institutional-flow-tracker/
generated: false
---

# Institutional Flow Tracker
{: .no_toc }

使用本技能借助 13F 申报数据跟踪机构投资者的持仓变化与资金流向。分析对冲基金、共同基金等机构持有人,识别出现显著「聪明钱」(smart money)增持或减持的股票。通过追踪专业投资者资金的部署方向,帮助你在大行情启动之前发现机会。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/institutional-flow-tracker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/institutional-flow-tracker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能通过 13F SEC 申报文件跟踪机构投资者的活动,识别流入和流出个股的「聪明钱」。通过分析机构持仓的季度变化,你可以在重大价格波动发生之前,发现专业投资者正在增持的股票,或在机构减持时识别潜在风险。

**核心洞察:** 机构投资者(对冲基金、养老基金、共同基金)管理着数万亿美元的资产并进行深入的研究。它们的集体买卖行为往往会领先于显著的价格波动 1-3 个季度出现。

---

## 2. 使用时机

在以下情况下使用本技能:
- 验证投资想法(检查聪明钱是否认同你的判断)
- 发现新机会(找出机构正在增持的股票)
- 风险评估(识别机构正在退出的股票)
- 持仓监控(跟踪机构对你所持股票的支持度)
- 跟踪特定投资者(跟踪沃伦·巴菲特、凯西·伍德等)
- 板块轮动分析(识别机构资金正在轮动至哪些方向)

**不应使用的情况:**
- 寻求实时日内信号(13F 数据存在 45 天的报告滞后)
- 分析微型股(市值低于 1 亿美元、机构关注度有限)
- 寻找短线交易信号(持有期低于 3 个月)

---

## 3. 前提条件

- **FMP API 密钥:** 设置 `FMP_API_KEY` 环境变量,或在运行脚本时传入 `--api-key`
- **Python 3.8+:** 运行分析脚本所需
- **依赖项:** `pip install requests`(脚本会妥善处理缺失的依赖项)

---

## 4. 快速开始

```bash
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

---

## 5. 工作流

### 第 1 步:识别机构持仓发生显著变化的股票

执行主筛选脚本,找出机构活动显著的股票:

**快速扫描(按机构持仓变化排序的前 50 只股票):**
```bash
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

**聚焦特定板块的扫描:**
```bash
python3 scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

**自定义筛选:**
```bash
python3 scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_flow_results.json
```

**输出包含:**
- 股票代码与公司名称
- 当前机构持股比例(占流通股的百分比)
- 持股数量的环比(季度)变化
- 持有该股票的机构数量
- 机构数量的变化(新进买方与卖方)
- 主要机构持有人

### 第 2 步:对特定股票进行深入分析

要对某只股票的机构持仓进行详细分析:

```bash
python3 scripts/analyze_single_stock.py AAPL
```

**该脚本会生成:**
- 历史机构持仓趋势(8 个季度)
- 所有机构持有人及其仓位变化的列表
- 集中度分析(前 10 大持有人占机构总持仓的百分比)
- 新建仓 vs 加仓 vs 减仓的对比
- 数据质量评估及可靠性评级

**需要评估的关键指标:**
- **持股比例:** 较高的机构持股比例(>70%)意味着更稳定,但上涨空间有限
- **持股趋势:** 持股比例上升 = 看涨,下降 = 看跌
- **集中度:** 高集中度(前 10 大持有人 > 50%)意味着一旦它们卖出会有风险
- **持有人质量:** 是否有优质长期投资者(伯克希尔、富达)而非动量型基金参与

### 第 3 步:跟踪特定机构投资者

> **说明:** `track_institution_portfolio.py` **尚未实现**。FMP API 是按股票(而非按机构)组织机构持有人数据的,这使得仅凭该 API 完整重建机构组合持仓变得不切实际。

**替代方案——使用 `analyze_single_stock.py` 检查某个特定机构是否持有某股票:**
```bash
# 分析一只股票,并在输出中查找特定机构
python3 institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
# 然后在报告的"前 20 大持有人"表格中搜索 "Berkshire" 或 "ARK"
```

**要进行完整的机构层面组合跟踪,可使用以下外部资源:**
1. **WhaleWisdom:** https://whalewisdom.com(提供免费版,13F 组合查看器)
2. **SEC EDGAR:** https://www.sec.gov/cgi-bin/browse-edgar(官方 13F 申报文件)
3. **DataRoma:** https://www.dataroma.com(知名投资人组合跟踪工具)

### 第 4 步:解读与行动

阅读参考文档以获取解读指南:
- `references/13f_filings_guide.md` - 理解 13F 数据及其局限性
- `references/institutional_investor_types.md` - 不同类型的投资者及其策略
- `references/interpretation_framework.md` - 如何解读机构资金流信号

**信号强度框架:**

**强烈看涨(可考虑买入):**
- 机构持股比例环比增长 >15%
- 机构数量增长 >10%
- 优质长期投资者正在加仓
- 当前持股比例较低(<40%)且仍有增长空间
- 多个季度持续出现增持

**温和看涨:**
- 机构持股比例环比增长 5-15%
- 新进买方与卖方混合存在,净值为正
- 当前持股比例 40-70%

**中性:**
- 持股比例变化很小(<5%)
- 买方与卖方数量相近
- 机构持仓基础稳定

**温和看跌:**
- 机构持股比例环比下降 5-15%
- 卖方多于买方
- 持股比例过高(>80%)限制了新增买方

**强烈看跌(可考虑卖出/回避):**
- 机构持股比例环比下降 >15%
- 机构数量下降 >10%
- 优质投资者正在退出仓位
- 多个季度持续出现减持
- 存在集中度风险(最大持有人正在抛售大量仓位)

### 第 5 步:组合应用

**对于新建仓位:**
1. 对你的投资想法运行机构分析
2. 寻找确认信号(机构是否也在增持)
3. 如果出现强烈看跌信号,重新考虑或减小仓位规模
4. 如果出现强烈看涨信号,增强对该投资判断的信心

**对于现有持仓:**
1. 在每个季度 13F 申报截止日期后进行复核
2. 监控是否出现减持(早期预警机制)
3. 如果机构正在退出,重新评估你的投资判断
4. 如果机构普遍卖出,考虑减仓

**纳入筛选工作流:**
1. 使用 Value Dividend Screener 或其他筛选器找出候选标的
2. 对排名靠前的候选标的运行 Institutional Flow Tracker
3. 优先选择机构正在增持的股票
4. 避开机构正在减持的股票

---

## 6. 资源

**参考文档(References):**

- `skills/institutional-flow-tracker/references/13f_filings_guide.md`
- `skills/institutional-flow-tracker/references/institutional_investor_types.md`
- `skills/institutional-flow-tracker/references/interpretation_framework.md`

**脚本(Scripts):**

- `skills/institutional-flow-tracker/scripts/analyze_single_stock.py`
- `skills/institutional-flow-tracker/scripts/data_quality.py`
- `skills/institutional-flow-tracker/scripts/track_institution_portfolio.py`
- `skills/institutional-flow-tracker/scripts/track_institutional_flow.py`
