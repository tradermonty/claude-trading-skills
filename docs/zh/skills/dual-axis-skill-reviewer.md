---
layout: default
title: "Dual Axis Skill Reviewer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 16
lang_peer: /en/skills/dual-axis-skill-reviewer/
permalink: /zh/skills/dual-axis-skill-reviewer/
generated: false
---

# Dual Axis Skill Reviewer
{: .no_toc }

使用双轴方法对任意项目中的技能进行评审:(1) 基于代码的确定性检查(结构、脚本、测试、执行安全性)以及 (2) LLM 深度评审发现。当你需要为 `skills/*/SKILL.md` 提供可复现的质量评分、希望用分数阈值(例如 90 分以上)来把关合并请求,或需要为低分技能列出具体的改进项时使用本技能。通过 --project-root 可跨项目使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/dual-axis-skill-reviewer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/dual-axis-skill-reviewer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Dual Axis Skill Reviewer 把"确定性自动检查"与"LLM 深度评审"两个维度结合起来,为技能仓库中的每一个技能生成可复现、可解释的质量评分,并在评分不达标时给出具体可执行的改进项。

---

## 2. 使用时机

- 需要为 `skills/*/SKILL.md` 中的某个技能提供可复现的评分。
- 当最终评分低于 90 分时,需要列出改进项。
- 需要同时获得确定性检查与定性的 LLM 代码/内容评审。
- 需要从命令行对**另一个项目**中的技能进行评审。

---

## 3. 前提条件

- Python 3.9+
- `uv`(推荐——通过内联元数据自动解析 `pyyaml` 依赖)
- 测试运行需要:在目标项目中执行 `uv sync --extra dev` 或等效命令
- 若要合并 LLM 维度评分,需要一个符合 LLM 评审 schema 的 JSON 文件(见"资源"部分)

---

## 4. 快速开始

```bash
# 如果是在同一个项目中评审:
REVIEWER=skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py

# 如果是评审另一个项目(全局安装):
REVIEWER=~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py
```

---

## 5. 工作流

根据你的使用场景确定正确的脚本路径:

- **同一项目内**:`skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`
- **全局安装**:`~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`

以下示例使用 `REVIEWER` 作为占位符。设置一次即可:

```bash
# 如果是在同一个项目中评审:
REVIEWER=skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py

# 如果是评审另一个项目(全局安装):
REVIEWER=~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py
```

### 步骤 1:运行自动评分轴 + 生成 LLM 提示词

```bash
uv run "$REVIEWER" \
  --project-root . \
  --emit-llm-prompt \
  --output-dir reports/
```

如果要评审另一个项目,把 `--project-root` 指向该项目:

```bash
uv run "$REVIEWER" \
  --project-root /path/to/other/project \
  --emit-llm-prompt \
  --output-dir reports/
```

### 步骤 2:运行 LLM 评审
- 使用生成在 `reports/skill_review_prompt_<skill>_<timestamp>.md` 中的提示词文件。
- 要求 LLM 返回严格的 JSON 输出。
- 在 Claude Code 中运行时,让 Claude 充当编排者:读取生成的提示词,产出 LLM 评审 JSON,并保存以供合并步骤使用。

### 步骤 3:合并自动轴与 LLM 轴

```bash
uv run "$REVIEWER" \
  --project-root . \
  --skill <skill-name> \
  --llm-review-json <path-to-llm-review.json> \
  --auto-weight 0.5 \
  --llm-weight 0.5 \
  --output-dir reports/
```

### 步骤 4:可选控制项

- 固定选择以保证可复现性:`--skill <name>` 或 `--seed <int>`
- 一次性评审所有技能:`--all`
- 跳过测试以快速分流:`--skip-tests`
- 修改报告输出位置:`--output-dir <dir>`
- 提高 `--auto-weight` 以加强确定性把关。
- 当更看重定性/代码评审深度时,提高 `--llm-weight`。

---

## 6. 资源

**参考文档(References):**

- `skills/dual-axis-skill-reviewer/references/llm_review_schema.md`
- `skills/dual-axis-skill-reviewer/references/scoring_rubric.md`

**脚本(Scripts):**

- `skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`
