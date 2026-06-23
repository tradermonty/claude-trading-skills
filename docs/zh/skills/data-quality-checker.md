---
layout: default
title: "Data Quality Checker"
grand_parent: 简体中文
parent: 技能指南
nav_order: 13
lang_peer: /en/skills/data-quality-checker/
permalink: /zh/skills/data-quality-checker/
generated: false
---

# Data Quality Checker
{: .no_toc }

在发布前验证市场分析文档与博客文章中的数据质量。用于检查价格量级不一致(ETF 与期货)、品种代码标注错误、日期与星期不匹配、配置比例总和错误,以及单位不匹配问题。支持英文和日文内容。建议模式——将问题标记为供人工复核的警告,而非阻断发布。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/data-quality-checker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/data-quality-checker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

在发布前检测市场分析文档中常见的数据质量问题。检查器验证五大类别:价格量级一致性、品种代码标注、日期/星期准确性、配置比例总和,以及单位使用。所有发现都是建议性的——它们只是标记潜在问题供人工复核,而不会阻断发布。

---

## 2. 使用时机

- 发布每周策略博客或市场分析报告之前
- 生成自动化市场摘要之后
- 复核翻译文档(英文/日文)的数据准确性时
- 把多个数据源(FRED、FMP、FINVIZ)合并到一份报告中时
- 作为任何包含财务数据文档的发布前检查

---

## 3. 前提条件

- Python 3.9+
- 无需外部 API 密钥
- 无需第三方 Python 包(仅使用标准库)

---

## 4. 快速开始

```bash
# 检查一个 markdown 文件
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file reports/weekly_strategy.md

# 只运行指定的检查项
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --checks price_scale,dates,allocations

# 提供参考日期用于年份推断
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --as-of 2026-02-28 --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:接收输入文档

接受目标 markdown 文件路径以及可选参数:
- `--file`:待验证 markdown 文档的路径(必需)
- `--checks`:要运行的检查项,逗号分隔(可选;默认为全部)
- `--as-of`:用于年份推断的参考日期,格式为 YYYY-MM-DD(可选)
- `--output-dir`:报告输出目录(可选;默认为 `reports/`)

### 步骤 2:执行验证脚本

运行数据质量检查脚本:

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --output-dir reports/
```

仅运行指定的检查项:

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --checks price_scale,dates,allocations
```

提供参考日期用于年份推断(适用于日期中未明确写出年份的文档):

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --as-of 2026-02-28
```

### 步骤 3:加载参考标准

阅读相关参考文档以便对发现的问题进行解读:

- `references/instrument_notation_standard.md` —— 各类品种的标准代码标注、位数提示和命名规范
- `references/common_data_errors.md` —— 常见错误的目录,包括 FRED 数据延迟、ETF/期货量级混淆、节假日疏漏、配置比例总和陷阱,以及单位混淆模式

利用这些参考文档来解释发现的问题并提出修正建议。

### 步骤 4:复核发现的问题

检查输出中的每一条发现:

- **ERROR(错误)**—— 高置信度问题(例如通过日历计算验证出的日期与星期不匹配)。强烈建议修正。
- **WARNING(警告)**—— 需要人工判断的可能问题(例如价格量级异常、代码标注不一致、配置比例总和偏差超过 0.5%)。
- **INFO(提示)**—— 信息性说明(例如可能是有意为之的 bp/% 混用)。

### 步骤 5:生成质量报告

脚本会生成两个输出文件:

1. **JSON 报告**(`data_quality_YYYY-MM-DD_HHMMSS.json`):机器可读的问题清单,包含严重级别、类别、消息、行号和上下文。
2. **Markdown 报告**(`data_quality_YYYY-MM-DD_HHMMSS.md`):按严重级别分组的人类可读报告。

向用户呈现这些发现,并结合知识库给出解释。针对每个问题提出具体的修正建议。

---

## 6. 资源

**参考文档(References):**

- `skills/data-quality-checker/references/common_data_errors.md`
- `skills/data-quality-checker/references/instrument_notation_standard.md`

**脚本(Scripts):**

- `skills/data-quality-checker/scripts/check_data_quality.py`
