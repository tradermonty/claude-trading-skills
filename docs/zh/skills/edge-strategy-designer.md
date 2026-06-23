---
layout: default
title: "Edge Strategy Designer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 25
lang_peer: /en/skills/edge-strategy-designer/
permalink: /zh/skills/edge-strategy-designer/
generated: false
---

# Edge Strategy Designer
{: .no_toc }

把抽象的 Edge 概念转化为策略草案变体,以及可选的、可供 edge-candidate-agent 导出/验证使用的 ticket YAML 文件。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-strategy-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-strategy-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

把概念层面的假设转化为具体的策略草案规格。
本技能位于概念综合之后、流水线导出验证之前。

---

## 2. 使用时机

- 你已有 `edge_concepts.yaml`,需要生成策略候选方案。
- 你希望针对每个概念生成多个变体(核心型/保守型/研究探针型)。
- 你希望为接口 v1 系列生成可选的可导出 ticket 文件。

---

## 3. 前提条件

- Python 3.9+
- `PyYAML`
- 由概念综合阶段生成的 `edge_concepts.yaml`

---

## 4. 快速开始

1. 加载 `edge_concepts.yaml`。
2. 选择风险偏好档位(`conservative`(保守型)、`balanced`(均衡型)、`aggressive`(激进型))。
3. 按假设类型生成出场校准后的各概念变体。
4. 应用 `HYPOTHESIS_EXIT_OVERRIDES`,按假设类型(突破、盈余漂移、恐慌反转等)调整止损、风险回报比、时间止损与移动止损。
5. 将风险回报比下限锁定为 `RR_FLOOR=1.5`,以避免 C5 复核失败。
6. 在适用情况下导出符合 v1 规范的 ticket YAML。
7. 将可导出的 ticket 交接给 `skills/edge-candidate-agent/scripts/export_candidate.py`。

---

## 5. 工作流

1. 加载 `edge_concepts.yaml`。
2. 选择风险偏好档位(`conservative`(保守型)、`balanced`(均衡型)、`aggressive`(激进型))。
3. 按假设类型生成出场校准后的各概念变体。
4. 应用 `HYPOTHESIS_EXIT_OVERRIDES`,按假设类型(突破、盈余漂移、恐慌反转等)调整止损、风险回报比、时间止损与移动止损。
5. 将风险回报比下限锁定为 `RR_FLOOR=1.5`,以避免 C5 复核失败。
6. 在适用情况下导出符合 v1 规范的 ticket YAML。
7. 将可导出的 ticket 交接给 `skills/edge-candidate-agent/scripts/export_candidate.py`。

---

## 6. 资源

**参考文档(References):**

- `skills/edge-strategy-designer/references/strategy_draft_schema.md`

**脚本(Scripts):**

- `skills/edge-strategy-designer/scripts/design_strategy_drafts.py`
