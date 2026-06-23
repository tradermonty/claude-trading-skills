---
layout: default
title: "Edge Strategy Reviewer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 26
lang_peer: /en/skills/edge-strategy-reviewer/
permalink: /zh/skills/edge-strategy-reviewer/
generated: false
---

# Edge Strategy Reviewer
{: .no_toc }

针对 edge-strategy-designer 产出的策略草案进行批判性评审,评估其边际优势(edge)是否合理、是否存在过拟合风险、样本量是否充足,以及执行可行性。当 strategy_drafts/*.yaml 已存在、需要在流水线导出前完成质量把关时使用本技能。输出 PASS/REVISE/REJECT 判定结果及置信度评分。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-strategy-reviewer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-strategy-reviewer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Edge Strategy Reviewer 是 Edge 研究流水线的质量门槛环节:它对策略草案逐项打分,判断其边际优势的可信度、过拟合风险、样本充足度与执行可行性,并给出可复现的 PASS / REVISE / REJECT 判定,防止不成熟的策略流入下游导出环节。

---

## 2. 使用时机

- 在 `edge-strategy-designer` 生成 `strategy_drafts/*.yaml` 之后
- 在通过流水线将草案导出给 `edge-candidate-agent` 之前
- 需要手动验证某个策略草案的边际优势是否合理时

---

## 3. 前提条件

- 策略草案 YAML 文件(`edge-strategy-designer` 的输出)
- Python 3.10+,并安装 PyYAML

---

## 4. 快速开始

```bash
# 评审目录下的所有草案
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/

# 单个草案评审,输出 JSON 并生成 markdown 摘要
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --draft reports/edge_strategy_drafts/draft_xxx.yaml \
  --output-dir reports/ --format json --markdown-summary
```

---

## 5. 工作流

1. 从 `--drafts-dir` 或单个 `--draft` 文件加载草案 YAML
2. 按 8 项标准(C1-C8)对每份草案进行加权评分
3. 计算置信度评分(所有标准的加权平均)
4. 确定判定结果:PASS / REVISE / REJECT
5. 评估是否具备导出资格(PASS + export_ready_v1 + 可导出族系)
6. 写出评审结果(YAML 或 JSON)及可选的 markdown 摘要

---

## 6. 资源

**参考文档(References):**

- `skills/edge-strategy-reviewer/references/overfitting_checklist.md`
- `skills/edge-strategy-reviewer/references/review_criteria.md`

**脚本(Scripts):**

- `skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py`
