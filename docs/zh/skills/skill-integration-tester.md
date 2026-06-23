---
layout: default
title: "Skill Integration Tester"
grand_parent: 简体中文
parent: 技能指南
nav_order: 47
lang_peer: /en/skills/skill-integration-tester/
permalink: /zh/skills/skill-integration-tester/
generated: false
---

# Skill Integration Tester
{: .no_toc }

通过检查技能是否存在、技能间数据契约(JSON schema 兼容性)、文件命名规范以及交接完整性,验证 CLAUDE.md 中定义的多技能工作流。当新增工作流、修改技能输出,或在发布前验证流水线健康度时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/skill-integration-tester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/skill-integration-tester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

按顺序逐步执行,验证 CLAUDE.md 中定义的多技能工作流(每日市场监控、每周策略复盘、盈余动量交易等)。
检查上一步输出与下一步输入之间的技能间数据契约是否满足 JSON schema 兼容性,核实文件命名规范,并报告出现问题的交接环节。支持使用合成测试夹具的 dry-run(空跑)模式。

---

## 2. 使用时机

- 在 CLAUDE.md 中新增或修改多技能工作流之后
- 在更改某个技能的输出格式(JSON schema、文件命名)之后
- 在发布新技能之前验证流水线兼容性
- 在调试相邻工作流步骤之间出现交接问题时
- 作为涉及技能脚本改动的 Pull Request 的 CI 前置检查

---

## 3. 前提条件

- Python 3.9+
- 无需 API 密钥
- 无需第三方 Python 包(仅使用标准库)

---

## 4. 快速开始

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:运行集成验证

针对项目的 CLAUDE.md 执行验证脚本:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --output-dir reports/
```

该脚本会解析“多技能工作流”章节中所有 `**Workflow Name:**` 区块,将每一步的显示名称解析映射到对应的技能目录,并验证其存在性、契约与命名规范。

### 步骤 2:验证指定工作流

通过名称子串定位单个工作流:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --workflow "Earnings Momentum" \
  --output-dir reports/
```

### 步骤 3:使用合成测试夹具进行 Dry-Run

为每个技能预期输出创建合成的 JSON 测试夹具文件,并在没有真实数据的情况下验证契约兼容性:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --dry-run \
  --output-dir reports/
```

测试夹具文件会写入 `reports/fixtures/`,并带有 `_fixture` 标记。

### 步骤 4:查看结果

打开生成的 Markdown 报告获取人类可读的摘要,或解析 JSON 报告供程序化使用。每个工作流会显示:
- 逐步骤的技能存在性检查
- 交接契约验证结果(PASS / FAIL / N/A)
- 文件命名规范违规情况
- 整体工作流状态(valid / broken / warning)

### 步骤 5:修复有问题的交接

对每个 `FAIL` 的交接环节,核实以下内容:
1. 上游技能的输出是否包含所有必需字段
2. 下游技能的输入参数是否接受上游技能的输出格式
3. 上游输出与下游输入之间的文件命名模式是否一致

---

## 6. 资源

**参考文档(References):**

- `skills/skill-integration-tester/references/workflow_contracts.md`

**脚本(Scripts):**

- `skills/skill-integration-tester/scripts/validate_workflows.py`
