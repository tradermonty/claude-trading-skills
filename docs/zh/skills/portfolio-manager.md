---
layout: default
title: "Portfolio Manager"
grand_parent: 简体中文
parent: 技能指南
nav_order: 41
lang_peer: /en/skills/portfolio-manager/
permalink: /zh/skills/portfolio-manager/
generated: false
---

# Portfolio Manager
{: .no_toc }

通过 Alpaca MCP Server 集成获取持仓与仓位数据,进行全面的投资组合分析,涵盖资产配置、风险指标、个股仓位、分散度评估,并生成再平衡建议。当用户请求组合复盘、仓位分析、风险评估、业绩评价,或针对其证券账户提出再平衡建议时使用本技能。
{: .fs-6 .fw-300 }

<span class="badge badge-api">Alpaca 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/portfolio-manager.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/portfolio-manager){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

通过与 Alpaca MCP Server 集成获取实时持仓数据,对投资组合进行分析与管理,内容涵盖资产配置、分散度、风险指标、个股仓位评估以及再平衡建议。生成包含可执行洞见的详细组合报告。

本技能通过 MCP(Model Context Protocol)调用 Alpaca 的券商 API 来获取实时组合数据,确保分析基于实际当前仓位,而不是手工录入的数据。

---

## 2. 使用时机

当用户提出以下请求时调用本技能:
- "分析我的投资组合"
- "复盘我当前的持仓"
- "我的资产配置是怎样的?"
- "检查我的组合风险"
- "我应该再平衡我的组合吗?"
- "评估我的持仓"
- "组合业绩复盘"
- "我应该买入或卖出哪些股票?"
- 任何涉及组合层面分析或管理的请求

---

## 3. 前提条件

### Alpaca MCP Server 设置

本技能需要配置并连接 Alpaca MCP Server。该 MCP 服务器提供以下数据访问能力:
- 当前组合仓位
- 账户净值与购买力
- 历史仓位与交易记录
- 持仓证券的市场数据

**使用的 MCP 服务器工具:**
- `get_account_info` —— 获取账户净值、购买力、现金余额
- `get_positions` —— 获取所有当前仓位,包括数量、成本基础、市值
- `get_portfolio_history` —— 历史组合业绩数据
- 用于价格报价和基本面数据的市场数据工具

如果 Alpaca MCP Server 未连接,告知用户并提供来自 `references/alpaca_mcp_setup.md` 的设置说明。

---

## 4. 快速开始

```bash
# 测试 Alpaca 连接
python3 skills/portfolio-manager/scripts/check_alpaca_connection.py

# 组合分析通过 Claude 配合 Alpaca MCP 工具完成
# 设置方法见 portfolio-manager/references/alpaca-mcp-setup.md
```

---

## 5. 工作流

### 步骤 1:通过 Alpaca MCP 获取组合数据

使用 Alpaca MCP Server 工具收集当前组合信息:

**1.1 获取账户信息:**
```
使用 mcp__alpaca__get_account_info 获取:
- 账户净值(组合总价值)
- 现金余额
- 购买力
- 账户状态
```

**1.2 获取当前仓位:**
```
使用 mcp__alpaca__get_positions 获取所有持仓:
- 股票代码
- 持有数量
- 平均建仓价格(成本基础)
- 当前市场价格
- 当前市值
- 未实现盈亏($ 和 %)
- 仓位占组合的百分比
```

**1.3 获取组合历史(可选):**
```
使用 mcp__alpaca__get_portfolio_history 进行业绩分析:
- 历史净值数据
- 时间加权收益率计算
- 回撤分析
```

**数据验证:**
- 验证所有仓位都具有有效的股票代码
- 确认各仓位市值之和与账户净值大致相符
- 检查是否存在过期或非活跃仓位
- 处理边界情况(碎股、期权、若支持的加密货币)

### 步骤 2:丰富仓位数据

对组合中的每个仓位,收集额外的市场数据与基本面信息:

**2.1 当前市场数据:**
- 实时或延迟的价格报价
- 日成交量与流动性指标
- 52 周区间
- 市值

**2.2 基本面数据:**
使用 WebSearch 或可用的市场数据 API 获取:
- 板块与行业分类
- 关键估值指标(P/E、P/B、股息率)
- 近期财报与财务健康指标
- 分析师评级与目标价
- 近期新闻与重大事件

**2.3 技术分析:**
- 价格趋势(20 日、50 日、200 日均线)
- 相对强度
- 支撑与阻力位
- 动量指标(若可用则包括 RSI、MACD)

### 步骤 3:组合层面分析

使用参考文件中的框架进行全面的组合分析:

#### 3.1 资产配置分析

**阅读 references/asset-allocation.md** 获取配置框架

从多个维度分析当前配置:

**按资产类别:**
- 股票 vs 固定收益 vs 现金 vs 另类资产
- 与用户风险偏好对应的目标配置进行比较
- 评估配置是否符合投资目标

**按板块:**
- 科技、医疗保健、金融、消费等
- 识别板块集中度风险
- 与基准板块权重(例如标普 500)进行比较

**按市值:**
- 大盘股 vs 中盘股 vs 小盘股的分布
- 超大盘股的集中度
- 市值分散度评分

**按地区:**
- 美国 vs 国际市场 vs 新兴市场
- 国内集中度风险评估

**输出格式:**
```markdown
(资产配置分析的具体结构示例,详见参考文档模板)
```

---

## 6. 资源

**参考文档(References):**

- `skills/portfolio-manager/references/alpaca-mcp-setup.md`
- `skills/portfolio-manager/references/asset-allocation.md`
- `skills/portfolio-manager/references/diversification-principles.md`
- `skills/portfolio-manager/references/portfolio-risk-metrics.md`
- `skills/portfolio-manager/references/position-evaluation.md`
- `skills/portfolio-manager/references/rebalancing-strategies.md`
- `skills/portfolio-manager/references/risk-profile-questionnaire.md`
- `skills/portfolio-manager/references/target-allocations.md`
