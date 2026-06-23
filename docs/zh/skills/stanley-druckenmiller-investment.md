---
layout: default
title: "Stanley Druckenmiller Investment"
grand_parent: 简体中文
parent: 技能指南
nav_order: 48
lang_peer: /en/skills/stanley-druckenmiller-investment/
permalink: /zh/skills/stanley-druckenmiller-investment/
generated: false
---

# Stanley Druckenmiller Investment
{: .no_toc }

Druckenmiller 策略综合器 —— 整合 8 个上游技能的输出(市场宽度、上升趋势分析、市场顶部、宏观体制、FTD Detector、VCP Screener、Theme Detector、CANSLIM Screener),生成统一的确信度评分(0-100)、模式分类与配置建议。当用户询问整体市场确信度、组合定位、资产配置、策略综合,或 Druckenmiller 风格分析时使用。常见触发问句包括:“我的确信度水平是多少?”“我该如何定位?”“运行策略综合器”“Druckenmiller 分析”“总合的な市场判断”“确信度スコア”“ポートフォリオ配分”“ドラッケンミラー分析”。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stanley-druckenmiller-investment.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stanley-druckenmiller-investment){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Stanley Druckenmiller Investment 技能是一个策略综合器:它把多个上游技能各自独立的分析结果整合为一个统一的市场确信度判断,并据此给出配置建议。

---

## 2. 使用时机

- 用户问“我整体的确信度如何?”或“我该如何定位仓位?”
- 用户希望获得一个综合宽度、上升趋势、顶部风险、宏观与 FTD 信号的统一视角
- 用户询问 Druckenmiller 风格的组合定位方法
- 用户在运行完各个独立分析技能后,要求进行策略综合
- 用户问“我应该增加还是减少敞口?”
- 用户想要模式分类(政策转向、扭曲、逆向投资、观望等待)

---

## 3. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 4. 快速开始

```bash
python3 skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py \
  --reports-dir reports/ \
  --output-dir reports/ \
  --max-age 72
```

---

## 5. 工作流

### 阶段 1:验证前提条件

检查 `reports/` 目录中是否存在 5 个必需的上游技能 JSON 报告,且这些报告是否足够新(小于 72 小时)。如果缺失任何一个,先运行对应的技能。

### 阶段 2:执行策略综合器

```bash
python3 skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py \
  --reports-dir reports/ \
  --output-dir reports/ \
  --max-age 72
```

脚本会:
1. 加载并校验所有上游技能的 JSON 报告
2. 从每个技能中提取归一化信号
3. 计算 7 个分量评分(各自加权,范围 0-100)
4. 计算综合确信度评分
5. 归类为 4 种 Druckenmiller 模式之一
6. 生成目标配置与仓位规模建议
7. 输出 JSON 与 Markdown 报告

### 阶段 3:呈现结果

呈现生成的 Markdown 报告,重点突出:
- 确信度评分与所处区间
- 检测到的模式及匹配强度
- 最强与最弱的分量
- 目标配置(股票/债券/另类资产/现金)
- 仓位规模参数
- 相关的 Druckenmiller 投资原则

### 阶段 4:提供 Druckenmiller 背景知识

加载合适的参考文档以提供哲学层面的背景:
- **高确信度:** 强调集中持仓与“肥球”(fat pitch)原则
- **低确信度:** 强调资本保全与耐心等待
- **特定模式:** 从 `references/case-studies.md` 中应用相关案例研究

---

## 6. 资源

**参考文档(References):**

- `skills/stanley-druckenmiller-investment/references/case-studies.md`
- `skills/stanley-druckenmiller-investment/references/conviction_matrix.md`
- `skills/stanley-druckenmiller-investment/references/investment-philosophy.md`
- `skills/stanley-druckenmiller-investment/references/market-analysis-guide.md`

**脚本(Scripts):**

- `skills/stanley-druckenmiller-investment/scripts/allocation_engine.py`
- `skills/stanley-druckenmiller-investment/scripts/report_generator.py`
- `skills/stanley-druckenmiller-investment/scripts/report_loader.py`
- `skills/stanley-druckenmiller-investment/scripts/scorer.py`
- `skills/stanley-druckenmiller-investment/scripts/strategy_synthesizer.py`
