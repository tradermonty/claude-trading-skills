---
layout: default
title: "Earnings Calendar"
grand_parent: 简体中文
parent: 技能指南
nav_order: 17
lang_peer: /en/skills/earnings-calendar/
permalink: /zh/skills/earnings-calendar/
generated: false
---

# Earnings Calendar
{: .no_toc }

本技能使用 Financial Modeling Prep(FMP)API 获取美股即将公布的财报信息。当用户请求财报日历数据、想知道未来一周哪些公司将公布财报,或需要做每周财报回顾时使用。该技能聚焦于对市场有显著影响的中大盘以上公司(市值超过 20 亿美元),将数据按日期和时段整理成清晰的 Markdown 表格。支持多种环境(CLI、Desktop、Web),并提供灵活的 API 密钥管理方式。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/earnings-calendar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/earnings-calendar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能使用 Financial Modeling Prep(FMP)API 获取美股即将公布的财报信息。它聚焦于市值较大(中大盘以上,超过 20 亿美元)、对市场走势可能产生显著影响的公司。该技能会生成结构化的 Markdown 报告,展示未来一周内哪些公司将公布财报,并按日期和时段(开盘前、收盘后,或未公布时间)分组。

**核心特性**:
- 使用 FMP API 获取可靠、结构化的财报数据
- 按市值(>20 亿美元)过滤,聚焦于能影响市场的公司
- 包含每股收益(EPS)和营收预估
- 支持多环境(CLI、Desktop、Web)
- 灵活的 API 密钥管理
- 按日期、时段和市值分组整理

---

## 2. 前提条件

### FMP API 密钥

本技能需要 Financial Modeling Prep API 密钥。

**获取免费 API 密钥**:
1. 访问:https://site.financialmodelingprep.com/developer/docs
2. 注册免费账户
3. 立即获得 API 密钥
4. 免费额度:每天 250 次 API 调用(足够用于每周财报日历)

**各环境下的 API 密钥设置**:

**Claude Code(CLI)**:
```bash
export FMP_API_KEY="your-api-key-here"
```

**Claude Desktop**:
在系统中设置环境变量,或配置 MCP 服务器。

**Claude Web**:
执行技能时会提示输入 API 密钥(仅在当前会话中保存)。

---

## 3. 快速开始

```bash
# 默认:未来 7 天,市值 > 20 亿美元
python3 earnings-calendar/scripts/fetch_earnings_fmp.py --api-key YOUR_KEY

# 自定义日期范围
python3 earnings-calendar/scripts/fetch_earnings_fmp.py \
  --from 2025-11-01 --to 2025-11-07 \
  --api-key YOUR_KEY
```

---

## 4. 工作流

### 步骤 1:获取当前日期并计算目标周

**关键**:务必先获取准确的当前日期。

获取当前日期和时间:
- 使用系统日期/时间获得今天的日期
- 注意:“当前日期”由环境(<env> 标签)提供
- 计算目标周:从当前日期起的未来 7 天

**日期范围计算**:
```
当前日期:[例如 2025 年 11 月 2 日]
目标周开始:[当前日期 + 1 天,例如 2025 年 11 月 3 日]
目标周结束:[当前日期 + 7 天,例如 2025 年 11 月 9 日]
```

**为何重要**:
- 财报日历对时间高度敏感
- “下周”必须基于实际当前日期计算
- 为 API 请求提供准确的日期范围

**日期格式统一为 YYYY-MM-DD** 以兼容 API。

### 步骤 2:加载 FMP API 指南

在获取数据之前,先加载完整的 FMP API 指南:

```
Read: references/fmp_api_guide.md
```

该指南包含:
- FMP API 端点结构与参数
- 身份验证要求
- 市值过滤策略(通过 Company Profile API)
- 财报时段惯例(BMO、AMC、TAS)
- 响应格式与字段说明
- 错误处理策略
- 最佳实践与优化建议

### 步骤 3:检测并配置 API 密钥

根据环境检测 API 密钥的可用性。

**多环境 API 密钥检测**:

#### 3.1 检查环境变量(CLI/Desktop)

```bash
if [ ! -z "$FMP_API_KEY" ]; then
  echo "✓ API key found in environment"
  API_KEY=$FMP_API_KEY
fi
```

如果环境变量已设置,直接进入步骤 4。

#### 3.2 提示用户提供 API 密钥(Desktop/Web)

如果未找到环境变量,使用 AskUserQuestion 工具:

**问题配置**:
```
问题:“本技能需要 FMP API 密钥才能获取财报数据。你是否已有 FMP API 密钥?”
标题:“API 密钥”
选项:
  1. “有,我现在提供” → 进入 3.3
  2. “没有,获取免费密钥” → 显示说明(3.2.1)
  3. “跳过 API,使用手动输入” → 跳转到步骤 8(回退模式)
```

**3.2.1 如果用户选择“没有,获取免费密钥”**:

提供以下说明:
```
获取免费 FMP API 密钥的方法:

1. 访问:https://site.financialmodelingprep.com/developer/docs
2. 点击“Get Free API Key”或“Sign Up”
3. 创建账户(邮箱 + 密码)
4. 立即获得 API 密钥
5. 免费额度包含每天 250 次 API 调用(足够日常使用)

获得 API 密钥后,请选择“有,我现在提供”以继续。
```

#### 3.3 请求输入 API 密钥

如果用户已有 API 密钥,请求其输入:

**提示语**:
```
请在下方粘贴你的 FMP API 密钥:

(你的 API 密钥仅会保存在本次对话会话中,会话结束后将被遗忘。如需常规使用,建议设置 FMP_API_KEY 环境变量。)
```

**将 API 密钥存入会话变量**:
```
API_KEY = [用户输入]
```

**向用户确认**:
```
✓ 已收到 API 密钥,并已为本次会话保存。

安全提示:
- API 密钥仅保存在当前对话上下文中
- 不会保存到磁盘或持久化存储
- 会话结束后将被遗忘
- 如果对话中包含你的 API 密钥,请不要分享该对话

正在继续获取财报数据……
```

### 步骤 4:通过 FMP API 获取财报数据

使用 Python 脚本从 FMP API 获取财报数据。

**脚本位置**:
```
scripts/fetch_earnings_fmp.py
```

**执行方式**:

**方式 A:使用环境变量(CLI)**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09
```

**方式 B:使用会话 API 密钥(Desktop/Web)**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}"
```

**脚本工作流**(自动执行):
1. 验证 API 密钥和日期参数
2. 调用 FMP Earnings Calendar API 获取指定日期范围的数据
3. 获取公司概况(市值、板块、行业)
4. 过滤市值 >20 亿美元的公司
5. 标准化时段(BMO/AMC/TAS)
6. 按日期 → 时段 → 市值(降序)排序
7. 将 JSON 输出到 stdout

**预期输出格式**(JSON):
```json
[
  {
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "date": "2025-11-04",
    "timing": "AMC",
    "marketCap": 3000000000000,
    "marketCapFormatted": "$3.0T",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "epsEstimated": 1.54,
    "revenueEstimated": 123400000000,
    "fiscalDateEnding": "2025-09-30",
    "exchange": "NASDAQ"
  },
  ...
]
```

**保存到文件**(推荐用于配合报告生成器):
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}" > earnings_data.json
```

或捕获到变量:
```bash
earnings_data=$(python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 "${API_KEY}")
```

**错误处理**:

如果脚本返回错误:
- **401 Unauthorized**:API 密钥无效 → 检查密钥或重新输入
- **429 Rate Limit**:超出每天 250 次调用限制 → 等待或升级套餐
- **空结果**:该日期范围内无财报 → 扩大日期范围或在报告中注明
- **连接错误**:网络问题 → 重试,或在有缓存数据时使用缓存

### 步骤 5:处理并整理数据

获取财报数据(JSON 格式)后,进行处理和整理:

#### 5.1 解析 JSON 数据

从脚本输出加载 JSON 数据:
```python
import json
earnings_data = json.loads(earnings_json_string)
```

或者如果已保存到文件:
```python
with open('earnings_data.json', 'r') as f:
    earnings_data = json.load(f)
```

#### 5.2 验证数据结构

确认数据包含必需字段:
- ✓ symbol
- ✓ companyName
- ✓ date
- ✓ timing(BMO/AMC/TAS)
- ✓ marketCap
- ✓ sector

#### 5.3 按日期分组

将所有财报公告按日期分组:
- 周日,[完整日期](如适用)
- 周一,[完整日期]
- 周二,[完整日期]
- 周三,[完整日期]
- 周四,[完整日期]
- 周五,[完整日期]
- 周六,[完整日期](如适用)

#### 5.4 按时段二级分组

在每个日期下,创建三个子分组:
1. **开盘前(Before Market Open, BMO)**
2. **收盘后(After Market Close, AMC)**
3. **未公布时间(Time Not Announced, TAS)**

数据在脚本中已按时段排序,保持该顺序即可。

#### 5.5 各时段分组内部

公司已按市值降序排序(脚本输出):
- 超大盘(>2000 亿美元)排在最前
- 大盘(100 亿-2000 亿美元)排第二
- 中盘(20 亿-100 亿美元)排第三

这种优先级排序确保最具市场影响力的公司排在最前面。

#### 5.6 计算汇总统计

计算以下指标:
- **公司总数**:数据集中所有公司的数量
- **超大盘/大盘数量**:市值 >= 100 亿美元的公司数
- **中盘数量**:市值在 20 亿至 100 亿美元之间的公司数
- **高峰日**:财报公告数量最多的星期几
- **板块分布**:按板块统计数量(科技、医疗保健、金融等)
- **市值最高的公司**:按市值排名的前 5 家公司

### 步骤 6:生成 Markdown 报告

使用报告生成脚本,将 JSON 数据转换为格式化的 Markdown 报告。

**脚本位置**:
```
scripts/generate_report.py
```

**执行方式**:

**方式 A:输出到 stdout**:
```bash
python scripts/generate_report.py earnings_data.json
```

**方式 B:保存到文件**:
```bash
python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
```

**脚本执行内容**:
1. 从 JSON 文件加载财报数据
2. 按日期和时段(BMO/AMC/TAS)分组
3. 在每个分组内按市值排序
4. 计算汇总统计
5. 生成格式化的 Markdown 报告
6. 输出到 stdout 或保存到文件

脚本会自动处理所有格式化细节,包括:
- 正确的 Markdown 表格结构
- 日期分组与星期名称
- 市值排序
- EPS 与营收格式化
- 汇总统计计算

**报告结构**:

```markdown
# Upcoming Earnings Calendar - Week of [START_DATE] to [END_DATE]

**Report Generated**: [Current Date]
**Data Source**: FMP API (Mid-cap and above, >$2B market cap)
**Coverage Period**: Next 7 days
**Total Companies**: [COUNT]

---
```

---

## 5. 资源

**参考文档(References):**

- `skills/earnings-calendar/references/fmp_api_guide.md`

**脚本(Scripts):**

- `skills/earnings-calendar/scripts/fetch_earnings_fmp.py`
- `skills/earnings-calendar/scripts/generate_report.py`
