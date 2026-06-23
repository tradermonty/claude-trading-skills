---
layout: default
title: "Edge Hint Extractor"
grand_parent: 简体中文
parent: 技能指南
nav_order: 22
lang_peer: /en/skills/edge-hint-extractor/
permalink: /zh/skills/edge-hint-extractor/
generated: false
---

# Edge Hint Extractor
{: .no_toc }

从每日市场观察与新闻反应中提取边际优势线索(edge hint),可选叠加 LLM 创意生成,并输出标准化的 hints.yaml,供下游的概念合成与自动检测使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-hint-extractor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-hint-extractor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

把原始观察信号(`market_summary`、`anomalies`、`news reactions`)转化为结构化的边际优势线索。本技能是拆分式工作流中的第一阶段:`观察(observe) -> 抽象(abstract) -> 设计(design) -> 流水线(pipeline)`。

---

## 2. 使用时机

- 你想把每日市场观察转化为可复用的线索对象。
- 你想要受当前异常信号/新闻情境约束的、由 LLM 生成的创意。
- 你需要一份干净的 `hints.yaml` 作为概念合成或自动检测的输入。

---

## 3. 前提条件

- Python 3.9+
- `PyYAML`
- 来自检测器运行的可选输入:
  - `market_summary.json`
  - `anomalies.json`
  - `news_reactions.csv` 或 `news_reactions.json`

---

## 4. 快速开始

1. 收集观察文件(`market_summary`、`anomalies`,以及可选的新闻反应数据)。
2. 运行 `scripts/build_hints.py` 生成确定性线索。
3. 可选地通过以下两种方式之一,用 LLM 创意来增强线索:
   - a. `--llm-ideas-cmd` —— 将数据通过子进程管道传递给外部 LLM CLI。
   - b. `--llm-ideas-file PATH` —— 从一个预先写好的 YAML 文件加载线索(适用于 Claude Code 工作流中由 Claude 自己生成线索的场景)。
4. 将 `hints.yaml` 传入概念合成或自动检测环节。

---

## 5. 工作流

1. 收集观察文件(`market_summary`、`anomalies`,以及可选的新闻反应数据)。
2. 运行 `scripts/build_hints.py` 生成确定性线索。
3. 可选地通过以下两种方式之一,用 LLM 创意来增强线索:
   - a. `--llm-ideas-cmd` —— 将数据通过子进程管道传递给外部 LLM CLI。
   - b. `--llm-ideas-file PATH` —— 从一个预先写好的 YAML 文件加载线索(适用于 Claude Code 工作流中由 Claude 自己生成线索的场景)。
4. 将 `hints.yaml` 传入概念合成或自动检测环节。

注意:`--llm-ideas-cmd` 与 `--llm-ideas-file` 互斥,不能同时使用。

---

## 6. 资源

**参考文档(References):**

- `skills/edge-hint-extractor/references/hints_schema.md`

**脚本(Scripts):**

- `skills/edge-hint-extractor/scripts/build_hints.py`
