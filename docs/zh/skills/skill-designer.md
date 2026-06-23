---
layout: default
title: "Skill Designer"
grand_parent: 简体中文
parent: 技能指南
nav_order: 45
lang_peer: /en/skills/skill-designer/
permalink: /zh/skills/skill-designer/
generated: false
---

# Skill Designer
{: .no_toc }

根据结构化的创意规格设计新的 Claude 技能。当技能自动生成流水线需要产出一个 Claude CLI 提示词,用以创建遵循本仓库规范的完整技能目录(SKILL.md、references、scripts、tests)时使用本技能。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/skill-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/skill-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

根据结构化的技能创意规格,生成一份完整的 Claude CLI 提示词。该提示词指示 Claude 创建一个遵循仓库规范的完整技能目录:带 YAML frontmatter 的 SKILL.md、参考文档、辅助脚本,以及测试脚手架。

---

## 2. 使用时机

- 技能自动生成流水线从积压清单中选中一个创意,需要为 `claude -p` 生成设计提示词
- 开发者想从一份 JSON 创意规格快速搭建一个新技能
- 对已生成技能进行质量评审时,需要了解评分细则

---

## 3. 前提条件

- Python 3.9+
- 无需外部 API 密钥
- 参考文件必须存在于 `skills/skill-designer/references/` 目录下

---

## 4. 快速开始

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root .
```

---

## 5. 工作流

### 步骤 1:准备创意规格

接受一个 JSON 文件(`--idea-json`),内容包含:
- `title`:创意的可读名称
- `description`:该技能的功能描述
- `category`:技能分类(例如 trading-analysis、developer-tooling)

接受一个规范化的技能名称(`--skill-name`),它将用作目录名以及 YAML frontmatter 中的 `name:` 字段。

### 步骤 2:构建设计提示词

运行提示词构建器:

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root .
```

该脚本会:
1. 加载创意 JSON
2. 读取全部三份参考文件(结构指南、质量检查清单、模板)
3. 列出最多 20 个已有技能,以避免重复
4. 把完整的提示词输出到标准输出

### 步骤 3:把提示词喂给 Claude CLI

调用方流水线把提示词管道传递给 `claude -p`:

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root . \
| claude -p --allowedTools Read,Edit,Write,Glob,Grep
```

### 步骤 4:验证输出

Claude 创建技能之后,验证以下内容:
- `skills/<skill-name>/SKILL.md` 存在且 frontmatter 正确
- 目录结构符合规范
- 使用 dual-axis-skill-reviewer 评分,达到阈值要求

---

## 6. 资源

**参考文档(References):**

- `skills/skill-designer/references/quality-checklist.md`
- `skills/skill-designer/references/skill-structure-guide.md`
- `skills/skill-designer/references/skill-template.md`

**脚本(Scripts):**

- `skills/skill-designer/scripts/build_design_prompt.py`
