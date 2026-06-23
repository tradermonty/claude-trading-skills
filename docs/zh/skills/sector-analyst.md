---
layout: default
title: "Sector Analyst"
grand_parent: 简体中文
parent: 技能指南
nav_order: 43
lang_peer: /en/skills/sector-analyst/
permalink: /zh/skills/sector-analyst/
generated: false
---

# Sector Analyst
{: .no_toc }

本技能应用于分析板块轮动模式和市场周期定位。它从 CSV 数据源获取板块上升趋势数据(无需 API 密钥),并可选择性地接受图表图片以补充分析。当用户请求板块轮动分析、周期性与防御性评估、超买/超卖识别,或市场周期阶段估计时使用本技能。所有分析与输出均以英文进行。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/sector-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/sector-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能通过获取 TraderMonty 公开 CSV 数据集中的上升趋势比率数据,实现对板块轮动与市场周期定位的全面分析。它对板块进行排名,计算周期性与防御性的风险状态评分,识别超买/超卖状况,并估计当前所处的市场周期阶段。图表图片可作为可选输入,为这套以数据驱动的分析补充行业层面的细节。

---

## 2. 使用时机

在以下情况下使用本技能:
- 用户请求板块轮动分析(无需提供图表图片)
- 用户询问周期性板块与防御性板块的定位情况
- 用户想了解哪些板块处于超买或超卖状态
- 用户请求估计市场周期阶段
- 用户提供板块表现图表以进行补充分析
- 用户请求基于板块的情景分析或预测

用户请求示例:
- "运行一次板块轮动分析"
- "目前是周期性板块还是防御性板块领涨?"
- "现在有哪些板块处于超买状态?"
- "我们现在处于市场周期的哪个阶段?"
- "分析这些板块表现图表,告诉我我们目前处于市场周期的哪个位置"

---

## 3. 前提条件

- 基于图表图片的分析
- 推荐 Python 3.9+

---

## 4. 快速开始

按照以下结构化工作流执行:

### 第 1 步:CSV 数据采集

---

## 5. 工作流

按照以下结构化工作流执行:

### 第 1 步:CSV 数据采集

1. 运行分析脚本:`python3 skills/sector-analyst/scripts/analyze_sector_rotation.py`
2. 从输出中提取:
   - 按上升趋势比率排名的板块
   - 风险状态(周期性 vs. 防御性)及其评分
   - 超买/超卖板块
   - 周期阶段估计及置信度水平
3. 如果出现数据新鲜度警告,需在分析中注明

### 第 2 步:市场周期评估

以脚本给出的周期阶段估计为起点:
- 阅读 `references/sector_rotation.md` 以获取市场周期与板块轮动框架
- 将脚本的量化结果与各周期阶段的预期模式进行对比:
  - 早期复苏周期(Early Cycle Recovery)
  - 中期扩张周期(Mid Cycle Expansion)
  - 后期周期(Late Cycle)
  - 衰退(Recession)
- 结合知识库进行定性解读补充

如果提供了图表图片,可用它们补充行业层面的细节:
- 从图表图片中提取行业层面的表现数据
- 对比 1 周与 1 月的表现以判断趋势的一致性
- 注明板块内部表现出强势或弱势的具体行业

### 第 3 步:当前形势分析

将各项观察综合为一份客观评估:
- 说明当前表现最接近哪个市场周期阶段
- 突出支持性证据(哪些板块/行业证实了这一判断)
- 注明任何矛盾信号或异常模式
- 根据信号的一致性评估置信度水平

使用数据驱动的表述方式,并具体引用表现数据。

### 第 4 步:情景构建

基于板块轮动原理与当前定位,为下一阶段构建 2-4 个潜在情景:

对于每个情景:
- 描述市场周期的转换过程
- 识别哪些板块可能表现优于大盘
- 识别哪些板块可能表现逊于大盘
- 明确能够确认该情景的催化因素或条件
- 分配概率(参见 sector_rotation.md 中的概率评估框架)

情景应从最可能(概率最高)到备选/逆向情景依次排列。

### 第 5 步:输出生成

创建一份包含以下各部分的结构化 Markdown 文档:

**必需部分:**
1. **执行摘要**:2-3 句话概述关键发现
2. **当前形势**:对当前表现模式与市场周期定位的详细分析
3. **支持性证据**:支持周期判断的具体板块与行业表现数据
4. **情景分析**:2-4 个情景及其描述与概率分配
5. **建议定位**:基于情景概率的战略与战术定位建议
6. **关键风险**:需要关注的显著风险或矛盾信号

---

## 6. 资源

**参考文档(References):**

- `skills/sector-analyst/references/sector_rotation.md`

**脚本(Scripts):**

- `skills/sector-analyst/scripts/analyze_sector_rotation.py`
