---
layout: default
title: "Trade Hypothesis Ideator"
grand_parent: 简体中文
parent: 技能指南
nav_order: 52
lang_peer: /en/skills/trade-hypothesis-ideator/
permalink: /zh/skills/trade-hypothesis-ideator/
generated: false
---

# Trade Hypothesis Ideator
{: .no_toc }

从市场数据、交易记录和交易日志片段中生成可被证伪的交易策略假设。当你拥有一份结构化输入数据包,并希望得到带有实验设计、终止标准(kill criteria),以及可选的、兼容 edge-finder-candidate/v1 格式的 strategy.yaml 导出文件的排序假设卡时使用。

{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trade-hypothesis-ideator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-hypothesis-ideator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Trade Hypothesis Ideator 技能用于从市场数据、交易记录和交易日志片段中生成可被证伪的交易策略假设,并输出带实验设计与终止标准的排序假设卡。

---

## 2. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 3. 快速开始

1. 接收输入 JSON 数据包。
2. 运行第一轮:数据归一化与证据提取。
3. 使用以下提示词生成假设:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md`(注入 `{{evidence_summary}}`)
4. 使用 `prompts/critique_prompt_template.md` 对假设进行批判性审查。
5. 运行第二轮:排序、输出格式化与护栏检查。
6. 可选:通过 Step H 策略导出器导出标记为 `pursue`(值得推进)的假设。

---

## 4. 工作流

1. 接收输入 JSON 数据包。
2. 运行第一轮:数据归一化与证据提取。
3. 使用以下提示词生成假设:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md`(注入 `{{evidence_summary}}`)
4. 使用 `prompts/critique_prompt_template.md` 对假设进行批判性审查。
5. 运行第二轮:排序、输出格式化与护栏检查。
6. 可选:通过 Step H 策略导出器导出标记为 `pursue`(值得推进)的假设。

---

## 5. 资源

**参考文档(References):**

- `skills/trade-hypothesis-ideator/references/evidence_quality_guide.md`
- `skills/trade-hypothesis-ideator/references/hypothesis_types.md`

**脚本(Scripts):**

- `skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py`
