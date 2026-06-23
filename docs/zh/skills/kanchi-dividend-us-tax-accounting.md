---
layout: default
title: "Kanchi Dividend US Tax Accounting"
grand_parent: 简体中文
parent: 技能指南
nav_order: 33
lang_peer: /en/skills/kanchi-dividend-us-tax-accounting/
permalink: /zh/skills/kanchi-dividend-us-tax-accounting/
generated: false
---

# Kanchi Dividend US Tax Accounting
{: .no_toc }

为 Kanchi 风格的收益型投资组合提供美国股息税务及账户配置工作流。当用户询问合格股息与普通股息的区分、1099-DIV 解读、REIT/BDC 分配的税务处理、持有期检验,或股息类资产在应税账户与 IRA 账户之间的配置决策时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-us-tax-accounting.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-us-tax-accounting){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

为股息投资者应用一套实用的美国税务工作流,同时确保决策过程可审计。
重点在于账户配置与分类判断,而非替代专业的法律/税务建议。

---

## 2. 使用时机

当用户需要以下内容时使用本技能:
- 美国股息税务分类规划(合格股息与普通股息的假设判断)。
- 年终税务规划前的持有期检验。
- 股票/REIT/BDC/MLP 类收益型持仓的账户配置决策。
- 标准化的年度股息税务备忘录格式。

---

## 3. 前提条件

准备以下持仓层级的输入数据:
- `ticker`(股票代码)
- `instrument_type`(工具类型)
- `account_type`(账户类型)
- `hold_days_in_window`(窗口期内持有天数,如有)

若需要确定性的输出产物,提供 JSON 输入并运行:

```bash
python3 skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py \
  --input /path/to/tax_input.json \
  --output-dir reports/
```

---

## 4. 快速开始

### 1)对每笔分配现金流进行分类

针对每个持仓,将预期现金流分类为:
- 潜在合格股息。
- 普通股息/非合格分配。
- 适用情况下的 REIT/BDC 特定分配组成部分。

---

## 5. 工作流

### 1)对每笔分配现金流进行分类

针对每个持仓,将预期现金流分类为:
- 潜在合格股息。
- 普通股息/非合格分配。
- 适用情况下的 REIT/BDC 特定分配组成部分。

使用 `references/qualified-dividend-checklist.md`
进行持有期和分类检验。

### 2)验证持有期资格假设

对于可能享受合格股息待遇的持仓:
- 检查除息日窗口。
- 检查计量窗口内所需的最低持有天数。
- 标记有可能未满足持有期要求的持仓。

如果数据不完整,将状态标记为 `ASSUMPTION-REQUIRED`(需假设)。

### 3)映射到报税字段

将规划假设映射到预期的税表分类项:
- 普通股息总额。
- 合格股息子项。
- 单独报告时的 REIT 相关组成部分。

统一使用税表术语,便于年终对账核实。

### 4)构建账户配置建议

使用 `references/account-location-matrix.md`,按税务特征将资产配置到合适账户:
- 应税账户用于预期将持续保持合格股息特征的持仓。
- 税收优惠账户用于偏普通收入性质的分配类持仓。

当约束条件相互冲突(流动性、策略、集中度)时,明确说明其中的权衡取舍。

### 5)生成年度规划备忘录

使用 `references/annual-tax-memo-template.md`,并包含以下内容:
- 所采用的假设。
- 分配分类汇总。
- 已采取的配置操作。
- 留待会计师/税务顾问复核的未决事项。

---

## 6. 资源

**参考文档(References):**

- `skills/kanchi-dividend-us-tax-accounting/references/account-location-matrix.md`
- `skills/kanchi-dividend-us-tax-accounting/references/annual-tax-memo-template.md`
- `skills/kanchi-dividend-us-tax-accounting/references/qualified-dividend-checklist.md`

**脚本(Scripts):**

- `skills/kanchi-dividend-us-tax-accounting/scripts/build_tax_planning_sheet.py`
