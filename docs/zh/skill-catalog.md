---
layout: default
title: 技能目录
parent: 简体中文
nav_order: 2
lang_peer: /en/skill-catalog/
permalink: /zh/skill-catalog/
---

# 技能目录
{: .no_toc }

按类别介绍 Claude Trading Skills 的全部技能。每个技能的 API 需求徽章可让你立即看清使用时需要哪些外部服务。
{: .fs-6 .fw-300 }

> 建议用英文技能名（如 "CANSLIM"、"VCP"、"FinViz"）搜索。中文部分匹配搜索存在一定限制。
{: .note }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 徽章图例

| 徽章 | 含义 |
|------|------|
| <span class="badge badge-free">无需 API</span> | 无需外部 API 密钥即可运行 |
| <span class="badge badge-api">FMP 必需</span> | 需要 FMP API 密钥 |
| <span class="badge badge-optional">FMP 可选</span> | 配置 FMP API 密钥可增强功能 |
| <span class="badge badge-optional">FINVIZ 可选</span> | 配置 FINVIZ Elite 可加速并提升精度 |
| <span class="badge badge-api">Alpaca 必需</span> | 需要 Alpaca 券商账户 |
| <span class="badge badge-workflow">工作流</span> | 与其他技能协作的工作流技能 |

---

## 1. 个股筛选

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **CANSLIM Screener** | 以 William O'Neil 的 CANSLIM 方法对成长股做 7 项评分。分析季度盈利、年度成长、新高、供需、领导地位、机构持股与市场方向 | <span class="badge badge-api">FMP 必需</span> |
| **VCP Screener** | 检测 Mark Minervini 的波动率收缩形态（VCP）。识别 Stage 2 上升趋势个股的波动率收缩与突破枢轴点 | <span class="badge badge-api">FMP 必需</span> |
| **Stockbee Momentum Burst Screener** | 筛选 Stockbee 式短线动量爆发候选。对 4% 突破、美元突破、区间扩张触发按形态质量与风险幅度做 0-100 分（A/B/Watch）评级。专用于生成候选，可接入 technical-analyst / position-sizer | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">本地 JSON 可选</span> |
| **FinViz Screener** | 用自然语言（中文/英文）构建 FinViz 筛选条件。支持 500+ 过滤代码，并在 Chrome 中打开结果。**主题交叉检索**（30+ 主题 × 268 子主题）可做“AI × 物流”“数据中心 × 电力”等叙事式检索 | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| **Value Dividend Screener** | 筛选高股息价值股。以 P/E、P/B、股息率、3 年成长趋势做多级过滤 | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| **Dividend Growth Pullback Screener** | 检测年度股息增长 12%+ 的高质量股息成长股中、RSI ≤40 处于回调的个股 | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| **Earnings Trade Analyzer** | 对近期财报个股做 5 因子加权评分（跳空、趋势、成交量、MA200、MA50），评 A-D 级 | <span class="badge badge-api">FMP 必需</span> |
| **PEAD Screener** | 对财报跳空高开个股的财报后漂移（PEAD）形态做周线分析。MONITORING→SIGNAL_READY→BREAKOUT 的阶段管理 | <span class="badge badge-api">FMP 必需</span> |
| **FTD Detector** | 以 William O'Neil 的方法检测 Follow-Through Day 信号。用于确认市场底部的双指数跟踪 | <span class="badge badge-api">FMP 必需</span> |
| **Institutional Flow Tracker** | 以 13F SEC 文件跟踪机构投资者的吸筹/派发形态。超级投资者加权的质量框架 | <span class="badge badge-api">FMP 必需</span> |

---

## 2. 市场分析

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Sector Analyst** | 分析板块/行业表现图，基于市场周期理论评估轮动形态 | <span class="badge badge-free">无需 API</span> |
| **Breadth Chart Analyst** | 用 S&P 500 宽度指数与上升趋势比率图诊断市场健康度 | <span class="badge badge-free">无需 API</span> |
| **Technical Analyst** | 周线图的纯技术分析。识别趋势、支撑/阻力、图形形态与动量指标 | <span class="badge badge-free">无需 API</span> |
| **[Market News Analyst]({{ '/zh/skills/market-news-analyst/' | relative_url }})** | 用 WebSearch/WebFetch 收集过去 10 天新闻，以量化影响评分排序 | <span class="badge badge-free">无需 API</span> |
| **Market Environment Analysis** | 全球宏观简报，涵盖股指、外汇、商品、利率与情绪 | <span class="badge badge-free">无需 API</span> |
| **[Market Breadth Analyzer]({{ '/zh/skills/market-breadth-analyzer/' | relative_url }})** | 用 TraderMonty 公开 CSV 数据做 6 项评分（0-100）的市场宽度评估 | <span class="badge badge-free">无需 API</span> |
| **Uptrend Analyzer** | 以约 2,800 只个股、11 个板块的上升趋势比率做 5 项复合评分诊断 | <span class="badge badge-free">无需 API</span> |
| **Macro Regime Detector** | 用跨资产比率分析检测结构性宏观体制转换（1-2 年视野） | <span class="badge badge-api">FMP 必需</span> |
| **[US Market Bubble Detector]({{ '/zh/skills/us-market-bubble-detector/' | relative_url }})** | 基于 Minsky/Kindleberger 框架的 8 指标泡沫表，附分阶段操作手册 | <span class="badge badge-free">无需 API</span> |
| **Market Top Detector** | 以 O'Neil 派发日、Minervini 龙头股恶化、防御性轮动检测顶部概率 | <span class="badge badge-free">无需 API</span> |
| **[IBD Distribution Day Monitor]({{ '/zh/skills/ibd-distribution-day-monitor/' | relative_url }})** | 日度检测 QQQ/SPY 的 IBD 式派发日。跟踪 25 个交易日失效与 5% 上涨失效，并由 d5/d15/d25 聚类判定 NORMAL/CAUTION/HIGH/SEVERE 及 TQQQ/QQQ 敞口建议 | <span class="badge badge-api">FMP 必需</span> |
| **[Downtrend Duration Analyzer]({{ '/zh/skills/downtrend-duration-analyzer/' | relative_url }})** | 分析历史下跌趋势时长（峰→谷），生成按板块/市值划分的交互式直方图 | <span class="badge badge-api">FMP 必需</span> |

---

## 3. 主题与策略

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Theme Detector** | 用 FINVIZ 行业数据以三维评分（Heat、Lifecycle、Confidence）检测多空主题 | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| **[Scenario Analyzer]({{ '/zh/skills/scenario-analyzer/' | relative_url }})** | 从新闻标题做 18 个月情景分析，生成一/二/三级影响与推荐个股 | <span class="badge badge-free">无需 API</span> |
| **[Backtest Expert]({{ '/zh/skills/backtest-expert/' | relative_url }})** | 专业级验证框架，含策略假设的参数稳健性检验与前推验证 | <span class="badge badge-free">无需 API</span> |
| **Options Strategy Advisor** | 用 Black-Scholes 模型计算理论价格与希腊字母，教学式讲解 17+ 期权策略 | <span class="badge badge-optional">FMP 可选</span> |
| **Pair Trade Screener** | 用协整检验发现配对交易机会，计算对冲比率、半衰期与 z-score 信号 | <span class="badge badge-api">FMP 必需</span> |
| **Stanley Druckenmiller Investment** | 编码 Druckenmiller 的投资哲学：宏观定位、非对称风险/回报评估 | <span class="badge badge-free">无需 API</span> |
| **Strategy Pivot Designer** | 当回测陷入停滞时生成结构性不同的策略转向方案，以 4 个确定性触发跳出局部最优 | <span class="badge badge-free">无需 API</span> |

---

## 4. 组合与执行

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Portfolio Manager** | 用 Alpaca MCP Server 获取实时持仓，生成资产配置、风险指标与 HOLD/ADD/TRIM/SELL 建议 | <span class="badge badge-api">Alpaca 必需</span> |
| **[Trader Memory Core]({{ '/zh/skills/trader-memory-core/' | relative_url }})** | 持久跟踪投资论点的全生命周期。将筛选器输出登记为 IDEA，支持 ENTRY_READY→ACTIVE→CLOSED 状态迁移、仓位赋值、复盘排期、含 MAE/MFE 的事后复盘生成 | <span class="badge badge-optional">FMP 可选</span> |
| **[Trade Performance Coach]({{ '/zh/skills/trade-performance-coach/' | relative_url }})** | 对已平仓交易、部分平仓与月度汇总从流程/风险/执行/行为模式/复盘质量 5 个维度评审，生成 OK/WARN/REVIEW_REQUIRED/RULE_VIOLATION/COOL_DOWN 结论与下场运营规则、人工判断关卡的事后教练。Beta。 | <span class="badge badge-free">无需 API</span> |
| **[Weekly Performance Digest]({{ '/zh/skills/weekly-performance-digest/' | relative_url }})** | 从已平仓交易生成周度绩效摘要：胜率、期望值、盈利因子、R 倍数、MAE/MFE，并按来源技能/退出原因/论点类型/板块/机制做胜负模式分析。纯本地计算 | <span class="badge badge-free">无需 API</span> |
| **[Position Sizer]({{ '/zh/skills/position-sizer/' | relative_url }})** | 以 Fixed Fractional、ATR、Kelly 三种方法计算基于风险的仓位规模 | <span class="badge badge-free">无需 API</span> |
| **[Breakout Trade Planner]({{ '/zh/skills/breakout-trade-planner/' | relative_url }})** | 从 VCP 筛选器输出生成 Minervini 式突破交易计划：基于最差入场的关卡、stop-limit bracket 模板（pre_place / post_confirm）、组合热度管理 | <span class="badge badge-free">无需 API</span> |
| **[Parabolic Short Trade Planner]({{ '/zh/skills/parabolic-short-trade-planner/' | relative_url }})** | 抛物线做空候选的日度筛选器（5 因子加权评分）与盘前计划生成器。每个候选输出 3 类触发（5min ORL 突破 / 首根 5 分钟阴线 / VWAP 失败）的条件计划；Alpaca ETB-only 做空确认走 `requests` 直连（不依赖 SDK）、SEC Rule 201 SSR 跟踪、blocking/advisory 分离式人工确认 | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">Alpaca 可选</span> |
| **[Exposure Coach]({{ '/zh/skills/exposure-coach/' | relative_url }})** | 整合宽度、体制、顶部风险、资金流各技能输出，生成含敞口上限（0-100%）、成长/价值倾斜、NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY 建议的市场姿态摘要 | <span class="badge badge-optional">FMP 可选</span> |
| **[US Stock Analysis]({{ '/zh/skills/us-stock-analysis/' | relative_url }})** | 涵盖基本面、技术面、同业对比的综合美股研究助手 | <span class="badge badge-free">无需 API</span> |
| **Earnings Calendar** | 用 FMP API 获取未来财报发布，聚焦市值 $2B 以上的中大型股 | <span class="badge badge-api">FMP 必需</span> |
| **Economic Calendar Fetcher** | 用 FMP API 获取 7-90 天经济事件，生成带影响评级的时间线报告 | <span class="badge badge-api">FMP 必需</span> |

---

## 5. 股息投资

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Kanchi Dividend SOP** | 将 Kanchi 式 5 步法改造为面向美股的可复用工作流，收录阈值表、评估标准与个股备忘模板 | <span class="badge badge-free">无需 API</span> |
| **Kanchi Dividend Review Monitor** | 以 T1-T5 触发器做异常检测，用 OK/WARN/REVIEW 的机械判定生成强制复查队列 | <span class="badge badge-free">无需 API</span> |
| **Kanchi Dividend US Tax Accounting** | 协助梳理 qualified/ordinary 前提、持有期检查与账户配置决策 | <span class="badge badge-free">无需 API</span> |

---

## 6. Edge 研究流水线

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Edge Candidate Agent** | 将日度市场观察转化为研究工单，导出 `strategy.yaml` + `metadata.json` | <span class="badge badge-free">无需 API</span> |
| **Edge Hint Extractor** | 从市场摘要与异常中提取线索，生成 `hints.yaml` | <span class="badge badge-free">无需 API</span> |
| **Edge Concept Synthesizer** | 从研究工单与线索综合 edge 概念，生成 `edge_concepts.yaml` | <span class="badge badge-free">无需 API</span> |
| **Edge Strategy Designer** | 从 edge 概念设计策略草案（`strategy_drafts/*.yaml`） | <span class="badge badge-free">无需 API</span> |
| **Edge Strategy Reviewer** | 以 8 项标准（C1-C8）评审策略草案，判定 PASS/REVISE/REJECT 及导出资格 | <span class="badge badge-free">无需 API</span> |
| **Edge Pipeline Orchestrator** | 端到端编排整条 edge 研究流水线，含评审→修订反馈回路 | <span class="badge badge-free">无需 API</span> |
| **Edge Signal Aggregator** | 对 edge-candidate-agent、theme-detector、sector-analyst、institutional-flow-tracker 的输出做加权、去重、矛盾处理，生成按确信度排序的看板 | <span class="badge badge-free">无需 API</span> |
| **[Signal Postmortem]({{ '/zh/skills/signal-postmortem/' | relative_url }})** | 记录并分析 edge 流水线与筛选器的信号结果。TRUE_POSITIVE/FALSE_POSITIVE/REGIME_MISMATCH 分类、向 edge-signal-aggregator 的权重反馈、技能改进待办生成 | <span class="badge badge-optional">FMP 可选</span> |

---

## 7. 质量与工作流

| 技能 | 说明 | API 需求 |
|------|------|----------|
| **Data Quality Checker** | 校验市场分析文档的价格刻度、日期星期、配置合计与单位是否一致 | <span class="badge badge-free">无需 API</span> |
| **Dual-Axis Skill Reviewer** | 以双轴方式评审技能质量：确定性自动评分 + 可选 LLM 评审 | <span class="badge badge-free">无需 API</span> |
| **Skill Designer** | 从结构化的想法规格设计 Claude 技能，生成含 SKILL.md、references、scripts、tests 的完整技能目录 | <span class="badge badge-free">无需 API</span> |
| **Skill Idea Miner** | 从 Claude Code 会话日志中抽取技能想法候选并评分、入待办 | <span class="badge badge-free">无需 API</span> |
| **Skill Integration Tester** | 从技能存在性、数据契约兼容性、交接完整性角度校验 CLAUDE.md 中定义的多技能工作流 | <span class="badge badge-free">无需 API</span> |
| **Trade Hypothesis Ideator** | 从市场数据、交易日志、日志片段生成可证伪的交易假设并排序，支持 strategy.yaml 导出 | <span class="badge badge-free">无需 API</span> |
| **[Trading Skills Navigator]({{ '/zh/skills/trading-skills-navigator/' | relative_url }})** | 入门导引。从自然语言的交易目标推荐最合适的工作流、技能集、API 需求与配置步骤；确定性推荐，并诚实提示“尚无对应工作流”的缺口。无需 API、面向新手 | <span class="badge badge-free">无需 API</span> |
| **Weekly Trade Strategy** | 周度交易策略的结构化模板与工作流 | <span class="badge badge-workflow">工作流</span> |

---

## 我该用哪个技能？

按目标推荐相应技能。

### 想找成长股

- **CANSLIM Screener** —— 用 O'Neil 的方法对成长股评分
- **VCP Screener** —— 检测 Minervini 的波动率收缩形态
- **FinViz Screener** —— 用自然语言自由指定成长条件

### 想要股息收入

- **Value Dividend Screener** —— 筛选高股息价值股
- **Dividend Growth Pullback Screener** —— 检测增息股的回调买入机会
- **Kanchi Dividend SOP** —— 用 Kanchi 式 5 步法体系化地挑选股息股

### 想把握市场环境

- **Breadth Chart Analyst** —— 诊断市场宽度健康度
- **Sector Analyst** —— 评估板块轮动形态
- **Market Environment Analysis** —— 全球宏观的综合简报
- **Uptrend Analyzer** —— 用上升趋势比率量化市场宽度健康度

### 想做主题投资

- **Theme Detector** —— 以三维评分检测多空主题
- **FinViz Screener** —— 可用 AI 主题、网络安全等主题过滤器

### 想抓财报动量

- **Earnings Trade Analyzer** —— 用 5 因子对财报反应评分
- **PEAD Screener** —— 检测财报后的回调→突破形态
- **Earnings Calendar** —— 按时间线掌握未来财报日

### 想验证策略

- **[Backtest Expert]({{ '/zh/skills/backtest-expert/' | relative_url }})** —— 策略假设的专业级验证
- **Strategy Pivot Designer** —— 从停滞的策略生成新思路

### 想管理组合

- **Portfolio Manager** —— 实时持仓分析与再平衡建议
- **[Position Sizer]({{ '/zh/skills/position-sizer/' | relative_url }})** —— 基于风险的仓位规模计算
- **[Trader Memory Core]({{ '/zh/skills/trader-memory-core/' | relative_url }})** —— 从论点登记到事后复盘的持久跟踪

---

## API 需求矩阵

| 技能 | FMP | FINVIZ Elite | Alpaca |
|------|-----|-------------|--------|
| Backtest Expert | — | — | — |
| Breadth Chart Analyst | — | — | — |
| Breakout Trade Planner | — | — | — |
| CANSLIM Screener | 必需 | — | — |
| Data Quality Checker | — | — | — |
| Dividend Growth Pullback Screener | 必需 | 推荐 | — |
| Downtrend Duration Analyzer | — | — | — |
| Dual Axis Skill Reviewer | — | — | — |
| Earnings Calendar | 必需 | — | — |
| Earnings Trade Analyzer | 必需 | — | — |
| Economic Calendar Fetcher | 必需 | — | — |
| Edge Candidate Agent | 可选 | — | — |
| Edge Concept Synthesizer | — | — | — |
| Edge Hint Extractor | — | — | — |
| Edge Pipeline Orchestrator | — | — | — |
| Edge Signal Aggregator | — | — | — |
| Edge Strategy Designer | — | — | — |
| Edge Strategy Reviewer | — | — | — |
| Exposure Coach | — | — | — |
| Finviz Screener | — | 可选 | — |
| FTD Detector | 必需 | — | — |
| Ibd Distribution Day Monitor | 必需 | — | — |
| Institutional Flow Tracker | 必需 | — | — |
| Kanchi Dividend Review Monitor | 可选 | — | — |
| Kanchi Dividend SOP | 可选 | — | — |
| Kanchi Dividend US Tax Accounting | — | — | — |
| Macro Regime Detector | — | — | — |
| Market Breadth Analyzer | — | — | — |
| Market Environment Analysis | — | — | — |
| Market News Analyst | — | — | — |
| Market Top Detector | — | — | — |
| Options Strategy Advisor | 可选 | — | — |
| Pair Trade Screener | 必需 | — | — |
| Parabolic Short Trade Planner | 必需 | — | — |
| PEAD Screener | 必需 | — | — |
| Portfolio Manager | — | — | 必需 |
| Position Sizer | — | — | — |
| Scenario Analyzer | — | — | — |
| Sector Analyst | — | — | — |
| Signal Postmortem | — | — | — |
| Skill Designer | — | — | — |
| Skill Idea Miner | — | — | — |
| Skill Integration Tester | — | — | — |
| Stanley Druckenmiller Investment | — | — | — |
| Stockbee Momentum Burst Screener | 必需 | — | — |
| Strategy Pivot Designer | — | — | — |
| Technical Analyst | — | — | — |
| Theme Detector | 可选 | 推荐 | — |
| Trade Hypothesis Ideator | — | — | — |
| Trade Performance Coach | — | — | — |
| Trader Memory Core | 可选 | — | — |
| Trading Skills Navigator | — | — | — |
| Uptrend Analyzer | — | — | — |
| US Market Bubble Detector | — | — | — |
| US Stock Analysis | — | — | — |
| Value Dividend Screener | 必需 | 推荐 | — |
| VCP Screener | 必需 | — | — |
| Weekly Performance Digest | — | — | — |
