---
layout: default
title: "Edge Concept Synthesizer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 21
lang_peer: /en/skills/edge-concept-synthesizer/
permalink: /zh/skills/edge-concept-synthesizer/
generated: false
---

# Edge Concept Synthesizer
{: .no_toc }

在进行策略设计/导出之前,把检测器生成的工单与提示信息抽象为可复用的优势概念,包含论点(thesis)、失效信号与策略打法手册。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-concept-synthesizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-concept-synthesizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

在“检测”与“策略实现”之间创建一层抽象层。
本技能对工单证据进行聚类,总结反复出现的条件,并输出带有明确论点与失效逻辑的 `edge_concepts.yaml`。

---

## 2. 使用时机

- 你手上有大量原始工单,需要将其结构化到机制层面。
- 你想避免直接把工单套用为策略而导致过拟合。
- 你需要在进入策略草拟之前,先在概念层面进行复核。

---

## 3. 前提条件

- Python 3.9+
- `PyYAML`
- 来自检测器输出的工单 YAML 目录(`tickets/exportable`、`tickets/research_only`)
- 可选的 `hints.yaml`

---

## 4. 快速开始

1. 从自动检测的输出中收集工单 YAML 文件。
2. 可选地提供 `hints.yaml` 以进行上下文匹配。
3. 运行 `scripts/synthesize_edge_concepts.py`。
4. 对概念去重:合并假设相同、条件存在重叠(包含度超过阈值)的概念。
5. 复核概念,只把高支持度的概念提升进入策略草拟阶段。

---

## 5. 工作流

1. 从自动检测的输出中收集工单 YAML 文件。
2. 可选地提供 `hints.yaml` 以进行上下文匹配。
3. 运行 `scripts/synthesize_edge_concepts.py`。
4. 对概念去重:合并假设相同、条件存在重叠(包含度超过阈值)的概念。
5. 复核概念,只把高支持度的概念提升进入策略草拟阶段。

---

## 6. 资源

**参考文档(References):**

- `skills/edge-concept-synthesizer/references/concept_schema.md`

**脚本(Scripts):**

- `skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py`
