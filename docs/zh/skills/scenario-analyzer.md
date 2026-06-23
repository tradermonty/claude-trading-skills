---
layout: default
title: "Scenario Analyzer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 42
lang_peer: /en/skills/scenario-analyzer/
permalink: /zh/skills/scenario-analyzer/
generated: false
---

# Scenario Analyzer
{: .no_toc }

根据一条新闻标题分析未来 18 个月情景的技能。
先用 scenario-analyst 代理执行主分析,再用 strategy-reviewer 代理获取第二意见。
生成一份完整的英文报告,涵盖一阶/二阶/三阶影响、推荐股票以及批判性复核。
示例:/scenario-analyzer "美联储加息 50 个基点"
触发场景:新闻分析、情景分析、18 个月展望、中长期投资策略

{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/scenario-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/scenario-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能从一条新闻标题出发,分析中长期(18 个月)的投资情景。它依次调用两个专门的代理(`scenario-analyst` 与 `strategy-reviewer`),把多角度分析与批判性复核整合成一份完整报告。

---

## 2. 使用时机

在以下情况使用本技能:

- 你想分析某条新闻标题对中长期投资的影响
- 你想构建多个 18 个月的情景
- 你想把板块/个股影响按一阶/二阶/三阶效应组织起来
- 你需要一份包含第二意见的综合分析

**示例:**
```
/scenario-analyzer "美联储加息 50 个基点,暗示后续还会继续加息"
/scenario-analyzer "中国宣布对美国半导体征收新关税"
/scenario-analyzer "OPEC+ 同意每日减产 200 万桶原油"
```

---

## 3. 前提条件

- **API 密钥**:无(仅使用 WebSearch/WebFetch)
- **MCP 服务器**:无
- **依赖项**:必须能够通过 Task 工具调用 scenario-analyst 和 strategy-reviewer 代理

---

## 4. 快速开始

```bash
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

---

## 5. 工作流

### 阶段 1:准备工作

#### 步骤 1.1:标题解析

解析用户提供的新闻标题。

1. **标题检查**
   - 确认已作为参数传入标题
   - 若未提供,向用户询问输入内容

2. **关键词提取**
   - 关键实体(公司名称、国家名称、机构名称)
   - 数值数据(利率、价格、数量)
   - 动作(加息、降息、宣布、同意等)

#### 步骤 1.2:事件类型分类

把标题归类到以下分类之一:

| 分类 | 示例 |
|----------|----------|
| 货币政策 | FOMC、欧洲央行(ECB)、日本央行(BOJ)、加息、降息、QE/QT |
| 地缘政治 | 战争、制裁、关税、贸易摩擦 |
| 监管与政策 | 环保法规、金融监管、反垄断 |
| 科技 | AI、电动车、可再生能源、半导体 |
| 大宗商品 | 原油、黄金、铜、农产品 |
| 企业与并购 | 收购、破产、财报、行业重组 |

#### 步骤 1.3:加载参考文档

根据事件类型,加载相关参考文档:

```
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

**参考文档内容:**
- `headline_event_patterns.md`:历史事件模式与市场反应
- `sector_sensitivity_matrix.md`:事件 × 板块的影响幅度矩阵
- `scenario_playbooks.md`:情景构建模板与最佳实践

---

### 阶段 2:调用代理

#### 步骤 2.1:调用 scenario-analyst

使用 Agent 工具调用主分析代理。

```
Agent 工具:
- subagent_type: "scenario-analyst"
- prompt: |
    针对以下标题执行 18 个月情景分析。

    ## 目标标题
    [输入的标题]

    ## 事件类型
    [分类结果]

    ## 参考信息
    [已加载参考文档的摘要]

    ## 分析要求
    1. 使用 WebSearch 收集过去 2 周的相关新闻
    2. 构建 3 个情景——基准/乐观/悲观(概率合计为 100%)
    3. 按板块分析一阶/二阶/三阶影响
    4. 挑选 3-5 只受益股和 3-5 只受损股(仅限美股市场)
    5. 全部以英文输出
```

**预期输出:**
- 相关新闻文章列表
- 3 个情景的详情(基准/乐观/悲观)
- 板块影响分析(一阶/二阶/三阶)
- 推荐股票清单

#### 步骤 2.2:调用 strategy-reviewer

使用 scenario-analyst 的结果,调用复核代理。

```
Agent 工具:
- subagent_type: "strategy-reviewer"
- prompt: |
    复核以下情景分析。

    ## 目标标题
    [输入的标题]

    ## 分析结果
    [scenario-analyst 的完整输出]

    ## 复核要求
    从以下角度进行复核:
    1. 被忽略的板块/个股
    2. 情景概率分配的合理性
    3. 影响分析的逻辑一致性
    4. 检测乐观/悲观偏向
    5. 提出替代情景
    6. 时间线的现实性

    用英文输出具有建设性且具体的反馈意见。
```

**预期输出:**
- 指出盲点
- 对情景概率的意见
- 指出偏向
- 提出替代情景
- 最终建议

---

### 阶段 3:整合与生成报告

#### 步骤 3.1:整合结果

整合两个代理的输出,形成最终的投资判断。

**整合要点:**
1. 补全复核中指出的盲点
2. 调整概率分配(如有需要)
3. 在考虑偏向的基础上做出最终判断
4. 制定具体的行动计划

#### 步骤 3.2:生成报告

按以下格式生成最终报告并保存为文件。

**保存位置:** `reports/scenario_analysis_<topic>_YYYYMMDD.md`

```markdown
# 标题情景分析报告

**分析时间**:YYYY-MM-DD HH:MM
**目标标题**:[输入的标题]
**事件类型**:[分类类别]

---
```

---

## 6. 资源

**参考文档(References):**

- `skills/scenario-analyzer/references/headline_event_patterns.md`
- `skills/scenario-analyzer/references/scenario_playbooks.md`
- `skills/scenario-analyzer/references/sector_sensitivity_matrix.md`
