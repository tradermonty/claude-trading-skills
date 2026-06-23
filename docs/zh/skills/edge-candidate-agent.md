---
layout: default
title: "Edge Candidate Agent"
grand_parent: 简体中文
parent: 技能指南
nav_order: 20
lang_peer: /en/skills/edge-candidate-agent/
permalink: /zh/skills/edge-candidate-agent/
generated: false
---

# Edge Candidate Agent
{: .no_toc }

从日终观察数据生成并优先排序美股多头优势(edge)研究工单,然后导出供 trade-strategy-pipeline 第一阶段使用的、可直接接入流水线的候选规格。当用户要求把假设/异常现象转化为可复现的研究工单、把已验证的想法转换为 `strategy.yaml` + `metadata.json`,或是在运行流水线回测前先做接口兼容性预检(`edge-finder-candidate/v1`)时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-candidate-agent.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-candidate-agent){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

把每日的市场观察数据转化为可复现的研究工单,以及与第一阶段(Phase I)兼容的候选规格。
优先考虑信号质量与接口兼容性,而不是激进地扩张策略数量。
本技能可以独立完成端到端的全流程,但在拆分式工作流中,它主要承担最终的导出/验证阶段。

---

## 2. 使用时机

- 把市场观察数据、异常现象或假设转化为结构化的研究工单。
- 运行每日自动检测,从日终 OHLCV 数据和可选的提示信息中发现新的优势候选。
- 把已验证的工单导出为 `strategy.yaml` + `metadata.json`,供 `trade-strategy-pipeline` 第一阶段使用。
- 在执行流水线之前,针对 `edge-finder-candidate/v1` 运行兼容性预检。

---

## 3. 前提条件

- 已安装 `PyYAML` 的 Python 3.9+ 环境。
- 能访问目标 `trade-strategy-pipeline` 仓库,用于模式(schema)/阶段验证。
- 通过 `--pipeline-root` 运行由流水线托管的验证时,需要可用的 `uv`。

---

## 4. 快速开始

推荐的拆分式工作流:

1. `skills/edge-hint-extractor`:观察数据/新闻 -> `hints.yaml`
2. `skills/edge-concept-synthesizer`:工单/提示 -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`:概念 -> `strategy_drafts` + 可导出的工单 YAML
4. `skills/edge-candidate-agent`(本技能):导出 + 验证,完成与流水线的交接

---

## 5. 工作流

推荐的拆分式工作流:

1. `skills/edge-hint-extractor`:观察数据/新闻 -> `hints.yaml`
2. `skills/edge-concept-synthesizer`:工单/提示 -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`:概念 -> `strategy_drafts` + 可导出的工单 YAML
4. `skills/edge-candidate-agent`(本技能):导出 + 验证,完成与流水线的交接

---

## 6. 资源

**参考文档(References):**

- `skills/edge-candidate-agent/references/ideation_loop.md`
- `skills/edge-candidate-agent/references/pipeline_if_v1.md`
- `skills/edge-candidate-agent/references/research_ticket_schema.md`
- `skills/edge-candidate-agent/references/signal_mapping.md`

**脚本(Scripts):**

- `skills/edge-candidate-agent/scripts/auto_detect_candidates.py`
- `skills/edge-candidate-agent/scripts/candidate_contract.py`
- `skills/edge-candidate-agent/scripts/export_candidate.py`
- `skills/edge-candidate-agent/scripts/validate_candidate.py`
