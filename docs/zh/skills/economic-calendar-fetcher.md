---
layout: default
title: "Economic Calendar Fetcher"
grand_parent: 简体中文
parent: 技能指南
nav_order: 19
lang_peer: /en/skills/economic-calendar-fetcher/
permalink: /zh/skills/economic-calendar-fetcher/
generated: false
---

# Economic Calendar Fetcher
{: .no_toc }

使用 FMP API 获取即将发生的经济事件与数据公布。脚本检索原始 JSON 或文本数据,再由助手负责筛选、评估影响并生成按时间排序的 Markdown 报告。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/economic-calendar-fetcher.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/economic-calendar-fetcher){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

从 Financial Modeling Prep(FMP)经济日历 API 获取即将发生的经济事件与数据公布。该技能可以拉取已排定的经济指标,包括央行货币政策决议、就业报告、通胀数据(CPI/PPI)、GDP 公布、零售销售、制造业数据,以及其他会影响金融市场的重大事件。

该技能通过 Python 脚本查询 FMP API,返回原始 JSON 或文本输出。随后由助手筛选事件、评估市场影响,并为每个排定事件生成按时间排序的 Markdown 报告。脚本本身不会自动生成任何文件。

**核心能力:**
- 获取指定日期范围内的经济事件(最长 90 天)
- 支持灵活提供 API 密钥(环境变量或命令行参数)
- 按影响级别、国家或事件类型筛选(筛选工作由助手完成)
- 将筛选结果整理为带影响分析的结构化 Markdown 报告(由助手生成,而非脚本)
- 默认获取未来 7 天数据,便于快速了解市场展望

**数据来源:**
- FMP 经济日历 API:`https://financialmodelingprep.com/api/v3/economic_calendar`
- 覆盖主要经济体:美国、欧盟、英国、日本、中国、加拿大、澳大利亚
- 事件类型:央行决议、就业、通胀、GDP、贸易、住房、调查类数据

---

## 2. 使用时机

在用户提出以下请求时使用本技能:

1. **经济日历查询:**
   - “本周有哪些经济事件即将发生?”
   - “给我看看未来两周的经济日历”
   - “下一次 FOMC 会议是什么时候?”
   - “下个月会公布哪些重要经济数据?”

2. **市场事件规划:**
   - “这周市场上我该关注什么?”
   - “有没有即将公布的高影响经济数据?”
   - “下一次非农就业报告 / CPI 公布 / GDP 报告是什么时候?”

3. **特定日期范围请求:**
   - “获取 1 月 1 日到 1 月 31 日的经济事件”
   - “2025 年第一季度的经济日历是什么样的?”

4. **特定国家查询:**
   - “给我看看下周美国的经济数据公布”
   - “有哪些 ECB(欧洲央行)事件已排定?”
   - “日本什么时候公布通胀数据?”

**不要在以下情况使用本技能:**
- 查询过去的经济事件(历史分析请使用 market-news-analyst)
- 公司盈利日历(本技能不包含财报相关内容)
- 实时市场数据或实时报价
- 技术分析或图表解读

---

## 3. 前提条件

- **FMP API 密钥**(必需):在 https://financialmodelingprep.com 注册免费密钥(每日 250 次请求)。通过 `FMP_API_KEY` 环境变量设置,或在运行脚本时传入 `--api-key`。
- **Python 3.10+**:运行 `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py` 所需。
- **无需第三方包**:脚本只使用 Python 标准库。

---

## 4. 快速开始

```bash
# 默认:未来 7 天
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# 指定日期范围(最长 90 天)
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-11-01 --to 2025-11-30 \
  --api-key YOUR_KEY \
  --format json
```

---

## 5. 工作流

按以下步骤获取并分析经济日历:

### 步骤 1:获取 FMP API 密钥

**检查 API 密钥是否可用:**

1. 首先检查 FMP_API_KEY 环境变量是否已设置
2. 如果不可用,请用户在对话中提供 API 密钥
3. 如果用户没有 API 密钥,提供以下说明:
   - 访问 https://financialmodelingprep.com
   - 注册免费账户(每日限 250 次请求)
   - 进入 API 控制台获取密钥

**用户交互示例:**
```
用户:“给我看看下周的经济事件”
助手:“我会去获取经济日历数据。你有 FMP API 密钥吗?我可以使用 FMP_API_KEY 环境变量,你也可以现在直接提供密钥。”
```

### 步骤 2:确定日期范围

**根据用户请求设置合适的日期范围:**

**默认(未指定具体日期):** 今天起 + 7 天
**用户指定时间段:** 使用确切日期(校验格式:YYYY-MM-DD)
**最大范围:** 90 天(FMP API 限制)

**示例:**
- “下周” → 今天到 +7 天
- “未来两周” → 今天到 +14 天
- “2025 年 1 月” → 2025-01-01 到 2025-01-31
- “2025 年第一季度” → 2025-01-01 到 2025-03-31

**校验日期范围:**
- 确保起始日期 ≤ 结束日期
- 确保范围 ≤ 90 天
- 如果查询的是过去的日期,给出提醒

### 步骤 3:执行 API 获取脚本

**使用合适的参数运行 get_economic_calendar.py 脚本:**

**基本用法(默认 7 天):**
```bash
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY
```

**指定日期范围:**
```bash
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-31 \
  --api-key YOUR_KEY \
  --format json
```

**使用环境变量(无需 --api-key):**
```bash
export FMP_API_KEY=your_key_here
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-07
```

**脚本参数:**
- `--from`:起始日期(YYYY-MM-DD)— 默认:今天
- `--to`:结束日期(YYYY-MM-DD)— 默认:今天 + 7 天
- `--api-key`:FMP API 密钥(若已设置 FMP_API_KEY 环境变量则可省略)
- `--format`:输出格式(json 或 text)— 默认:json
- `--output`:输出文件路径(可选,默认输出到标准输出)

**错误处理:**
- API 密钥无效 → 请用户核实密钥
- 超出速率限制(429) → 建议等待或升级 FMP 套餐,等待后重新运行
- 网络错误 → 检查网络连接并重新运行脚本
- 日期格式无效 → 提供正确的格式示例

### 步骤 4:解析与筛选事件

**处理脚本返回的 JSON 响应:**

1. **解析事件数据:** 从 API 响应中提取所有事件
2. **按用户指定条件筛选(如有):**
   - 影响级别:“High”、“Medium”、“Low”
   - 国家:“US”、“EU”、“JP”、“CN” 等
   - 事件类型:FOMC、CPI、Employment、GDP 等
   - 货币:USD、EUR、JPY 等

**筛选示例:**
- “只看高影响事件” → 筛选 impact == "High"
- “只看美国事件” → 筛选 country == "US"
- “央行决议” → 在事件名称中搜索 “Rate”、“Policy”、“FOMC”、“ECB”、“BOJ”

**事件数据结构:**
```json
{
  "date": "2025-01-15 14:30:00",
  "country": "US",
  "event": "Consumer Price Index (CPI) YoY",
  "currency": "USD",
  "previous": 2.6,
  "estimate": 2.7,
  "actual": null,
  "change": null,
  "impact": "High",
  "changePercentage": null
}
```

### 步骤 5:评估市场影响

**评估每个事件的市场重要性:**

**影响级别分类(来自 FMP):**
- **高影响:** 重大的市场推动型事件
  - FOMC 利率决议、ECB/BOJ 政策会议
  - 非农就业报告(NFP)、CPI、GDP
  - 市场通常会出现 0.5%-2% 以上的日内波动

- **中影响:** 重要但波动性较小
  - 零售销售、工业生产
  - PMI 调查、消费者信心指数
  - 住房数据、耐用品订单

- **低影响:** 次要指标
  - 每周初请失业金人数(除非数值极端)
  - 区域制造业调查
  - 较小规模的拍卖结果

**额外的背景因素:**

1. **当前市场敏感度:**
   - 高通胀环境 → CPI/PPI 重要性上升
   - 衰退担忧 → 就业数据更为关键
   - 降息预期升温 → 央行会议至关重要

2. **意外可能性:**
   - 比较预期值与前值
   - 预期变化幅度大 = 关注度更高
   - 市场共识不确定性高 = 影响潜力更大

3. **事件聚集效应:**
   - 同一天有多个相关事件 = 影响被放大
   - 例如:CPI + 零售销售 + 美联储官员讲话 = 当天影响极高

4. **前瞻性意义:**
   - 该事件是否会影响即将到来的央行决议?
   - 这是初值还是终值?
   - 该数据后续是否会被修正?

### 步骤 6:生成输出报告

> **职责划分:** 脚本只输出原始 JSON 或文本。本步骤由助手基于脚本输出完成。系统不会自动生成 Markdown 文件;结果在对话中展示,如有需要可应用户要求保存到 `reports/`。

**创建包含以下部分的结构化 Markdown 报告:**

**报告标题:**
```markdown
# Economic Calendar
**Period:** [起始日期] to [结束日期]
**Report Generated:** [时间戳]
**Total Events:** [事件数量]
**High Impact Events:** [高影响事件数量]
```

**事件列表(按时间顺序):**

每个事件包含以下内容:

```markdown
## [日期] - [星期]

### [事件名称] ([影响级别])
- **Country:** [国家代码] ([货币])
- **Time:** [HH:MM UTC]
- **Previous:** [前值]
- **Estimate:** [市场预期]
- **Impact Assessment:** [你的分析]

**Market Implications:**
[2-3 句话说明该事件为何重要、市场关注什么、典型的反应模式]

---
```

**事件条目示例:**

```markdown
## 2025-01-15 - Wednesday

### Consumer Price Index (CPI) YoY (High Impact)
- **Country:** US (USD)
- **Time:** 14:30 UTC(美东时间 8:30 AM —— 助手根据美国夏令时日历换算)
- **Previous:** 2.6%
- **Estimate:** 2.7%
- **Impact Assessment:** 非常高 —— 美联储政策决策的核心通胀指标

**Market Implications:**
若 CPI 读数高于预期(>2.7%),可能强化鹰派美联储预期,对股市形成压力并支撑美元。若读数等于或低于 2.7%,可能强化通胀降温叙事,利好风险资产。期权市场预计公布当日标普 500 波动幅度约为 1.2%。

---
```

**摘要部分:**

```markdown
## Key Takeaways

**Highest Impact Days:**
- [日期]:[事件] —— [综合影响理由]

**Central Bank Activity:**
- [已排定的美联储/ECB/BOJ 会议或讲话概述]

**Major Data Releases:**
- 就业:[NFP、失业率公布日期]
- 通胀:[CPI、PPI 公布日期]
- 增长:[GDP、零售销售公布日期]

**Market Positioning Considerations:**
[2-3 条关于交易者可能如何围绕这些事件布局的要点]

**Risk Events:**
[突出标注任何特别高不确定性或意外可能性较大的事件]
```

**筛选说明:**

如果用户要求了特定筛选条件,在报告顶部注明:

```markdown
**Filters Applied:**
- Impact Level: High only
- Country: US
- Events shown: [X] of [Y] total events in date range
```

**输出说明:**
- 结果在对话中展示。系统不会自动生成文件。
- 若要保存**原始 JSON/文本数据**:运行脚本时使用 `--output reports/economic_calendar_[START]_to_[END].json`。
- 若要保存**Markdown 报告**:在对话中生成报告后,要求助手将其写入 `reports/`。

---

## 6. 资源

**参考文档(References):**

- `skills/economic-calendar-fetcher/references/fmp_api_documentation.md`

**脚本(Scripts):**

- `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py`
