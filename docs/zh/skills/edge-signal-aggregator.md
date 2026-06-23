---
layout: default
title: "Edge Signal Aggregator"
grand_parent: 简体中文
parent: 技能指南
nav_order: 24
lang_peer: /en/skills/edge-signal-aggregator/
permalink: /zh/skills/edge-signal-aggregator/
generated: false
---

# Edge Signal Aggregator
{: .no_toc }

把来自多个寻找“优势”(edge)的技能(edge-candidate-agent、theme-detector、sector-analyst、institutional-flow-tracker)的信号进行聚合与排名,生成一个带加权评分、去重和矛盾检测功能的优先级置信度仪表盘。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-signal-aggregator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-signal-aggregator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

把多个上游“寻找优势”技能的输出合并为单一的加权置信度仪表盘。本技能应用可配置的信号权重,对重叠的主题去重,标记不同技能之间的矛盾信号,并按综合置信度评分对复合型优势点子进行排名。最终结果是一份带优先级的优势点子精选清单,并附带指向每个贡献技能的来源链接。

---

## 2. 使用时机

- 运行了多个“寻找优势”的技能之后,希望得到一个统一的视图
- 需要整合来自 edge-candidate-agent、theme-detector、sector-analyst 和 institutional-flow-tracker 的信号
- 在基于多个信号来源做出投资组合配置决策之前
- 需要识别不同分析方法之间的矛盾之处
- 需要确定哪些优势点子值得进一步深入研究时

---

## 3. 前提条件

- Python 3.9+
- 无需 API 密钥(处理来自其他技能的本地 JSON/YAML 文件)
- 依赖项:`pyyaml`(大多数环境中已标配)

---

## 4. 快速开始

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --edge-concepts reports/edge_concepts_*.yaml \
  --themes reports/theme_detector_*.json \
  --sectors reports/sector_analyst_*.json \
  --institutional reports/institutional_flow_*.json \
  --hints reports/edge_hints_*.yaml \
  --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:收集上游技能的输出

收集你想要聚合的上游技能的输出文件:
- 来自 edge-candidate-agent 的 `reports/edge_candidate_*.json`
- 来自 edge-concept-synthesizer 的 `reports/edge_concepts_*.yaml`
- 来自 theme-detector 的 `reports/theme_detector_*.json`
- 来自 sector-analyst 的 `reports/sector_analyst_*.json`
- 来自 institutional-flow-tracker 的 `reports/institutional_flow_*.json`
- 来自 edge-hint-extractor 的 `reports/edge_hints_*.yaml`

### 步骤 2:运行信号聚合

用上游输出文件的路径执行聚合脚本:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --edge-concepts reports/edge_concepts_*.yaml \
  --themes reports/theme_detector_*.json \
  --sectors reports/sector_analyst_*.json \
  --institutional reports/institutional_flow_*.json \
  --hints reports/edge_hints_*.yaml \
  --output-dir reports/
```

可选:使用自定义权重配置:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --weights-config skills/edge-signal-aggregator/assets/custom_weights.yaml \
  --output-dir reports/
```

### 步骤 3:审阅聚合仪表盘

打开生成的报告,审阅以下内容:
1. **排名后的优势点子** —— 按综合置信度评分排序
2. **信号来源追溯** —— 每个点子由哪些技能贡献而来
3. **矛盾信号** —— 标记出需要人工复核的冲突信号
4. **去重日志** —— 已合并的重叠主题

### 步骤 4:对高置信度信号采取行动

按最低置信度阈值过滤精选清单:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --min-conviction 0.7 \
  --output-dir reports/
```

---

## 6. 资源

**参考文档(References):**

- `skills/edge-signal-aggregator/references/signal-weighting-framework.md`

**脚本(Scripts):**

- `skills/edge-signal-aggregator/scripts/aggregate_signals.py`
