---
layout: default
title: "Strategy Pivot Designer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 50
lang_peer: /en/skills/strategy-pivot-designer/
permalink: /zh/skills/strategy-pivot-designer/
generated: false
---

# Strategy Pivot Designer
{: .no_toc }

检测回测迭代是否陷入停滞,并在参数调优触及局部最优时生成结构性不同的策略转型方案。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/strategy-pivot-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/strategy-pivot-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

检测某个策略的回测迭代循环是否已经停滞,并提出结构性不同的策略架构方案。本技能是 Edge 流水线(hint-extractor -> concept-synthesizer -> strategy-designer -> candidate-agent)中的反馈环节,通过重新设计策略的骨架结构(而不是微调参数)来打破局部最优。

---

## 2. 使用时机

- 尽管经过多轮优化迭代,回测评分仍出现停滞。
- 策略表现出过拟合迹象(样本内表现好,稳健性差)。
- 交易成本侵蚀了策略本就微薄的优势。
- 尾部风险或回撤超出可接受阈值。
- 你想针对同一个市场假设,探索根本不同的策略架构。

---

## 3. 前提条件

- Python 3.9+
- `PyYAML`
- 迭代历史 JSON 文件(累积的 backtest-expert 评估结果)
- 来源策略草案 YAML(来自 edge-strategy-designer)

---

## 4. 快速开始

1. 使用 `--append-eval` 把回测评估结果累积到迭代历史文件中。
2. 对历史记录运行停滞检测,识别触发条件(平台期、过拟合、成本侵蚀、尾部风险)。
3. 如检测到停滞,使用三种技术生成转型方案:假设反转、原型切换、目标重构。
4. 查看按评分排序的方案列表(综合质量潜力与新颖度评分)。
5. 对于可导出的方案,对应的 ticket YAML 已可直接用于 edge-candidate-agent 流水线。
6. 对于仅供研究的方案(research_only),需要先进行人工策略设计,再接入流水线。
7. 将选定的转型草案反馈给 backtest-expert,进入下一轮迭代周期。

---

## 5. 工作流

1. 使用 `--append-eval` 把回测评估结果累积到迭代历史文件中。
2. 对历史记录运行停滞检测,识别触发条件(平台期、过拟合、成本侵蚀、尾部风险)。
3. 如检测到停滞,使用三种技术生成转型方案:假设反转、原型切换、目标重构。
4. 查看按评分排序的方案列表(综合质量潜力与新颖度评分)。
5. 对于可导出的方案,对应的 ticket YAML 已可直接用于 edge-candidate-agent 流水线。
6. 对于仅供研究的方案(research_only),需要先进行人工策略设计,再接入流水线。
7. 将选定的转型草案反馈给 backtest-expert,进入下一轮迭代周期。

---

## 6. 资源

**参考文档(References):**

- `skills/strategy-pivot-designer/references/pivot_proposal_schema.md`
- `skills/strategy-pivot-designer/references/pivot_techniques.md`
- `skills/strategy-pivot-designer/references/stagnation_triggers.md`
- `skills/strategy-pivot-designer/references/strategy_archetypes.md`

**脚本(Scripts):**

- `skills/strategy-pivot-designer/scripts/detect_stagnation.py`
- `skills/strategy-pivot-designer/scripts/generate_pivots.py`
