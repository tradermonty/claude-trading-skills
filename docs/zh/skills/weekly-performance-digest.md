---
layout: default
title: "Weekly Performance Digest"
grand_parent: 简体中文
parent: 技能指南
nav_order: 58
lang_peer: /en/skills/weekly-performance-digest/
permalink: /zh/skills/weekly-performance-digest/
generated: false
---

# Weekly Performance Digest
{: .no_toc }

根据 trader-memory-core 中已平仓的论点(thesis)记录,生成周度业绩摘要 —— 包括胜率、期望值(expectancy)、盈利因子(profit factor)、R 倍数、最大不利变动/最大有利变动(MAE/MFE),并按来源技能、离场原因、论点类型、板块和交易机制对盈亏模式进行拆解分析。无需 API,纯本地计算。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/weekly-performance-digest.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/weekly-performance-digest){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Weekly Performance Digest 将你在一周内平仓的交易汇总成一份单独的业绩报告。它读取由 `trader-memory-core` 跟踪的已平仓(CLOSED)论点记录(`state/theses/th_*.yaml`),计算核心指标(胜率、期望值、盈利因子、R 倍数、MAE/MFE),并按多个维度(来源技能、离场原因、论点类型、板块、机制标签、筛选等级)对结果进行拆解,同时呈现本周最大的盈利单、亏损单和可吸取的经验教训。输出为一份 JSON 记录,外加一份可读的 Markdown 报告。纯计算逻辑 —— 无需 API 密钥。

---

## 2. 使用时机

- 在交易周结束时,用于回顾累计实现的业绩表现
- 用于衡量所有已平仓仓位的胜率和期望值
- 用于查看哪些来源技能、离场原因、板块或交易机制驱动了盈利或亏损
- 用于支撑月末复盘(汇总四份周度摘要)或一次复盘分析(postmortem)
- 用于基于真实已平仓交易,快速生成"哪些有效 / 哪些无效"的速览

---

## 3. 前提条件

- Python 3.9+,并安装 `PyYAML`(本仓库已自带该依赖)
- `trader-memory-core` 的论点状态目录,包含 YAML 文件(`state/theses/`)
- 无需 API 密钥

---

## 4. 快速开始

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

---

## 5. 工作流

### 步骤 1:为某一周运行摘要生成

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

默认值:`--state-dir state/theses`;`--from-date` 为 `--to-date` 之前的 7 天;`--to-date` 默认为当天;`--output-dir reports/`。若不指定任何日期参数,则默认汇总最近 7 天的数据。

### 步骤 2:阅读报告

运行后会生成 `reports/weekly_digest_<to-date>.json` 和 `reports/weekly_digest_<to-date>.md`。查看 Markdown 报告中的执行摘要、指标表格、模式拆解,以及最大盈利/亏损单;JSON 文件则用于下游消费。

### 步骤 3(可选):接入下游流程

可以将多份周度 JSON 摘要合并用于月度复盘,或将 JSON 传递给复盘(postmortem)/教练类技能步骤。本技能本身只做描述性分析 —— 具体行动应通过你正常的复盘流程来落实。

---

## 6. 资源

**参考文档(References):**

- `skills/weekly-performance-digest/references/weekly-digest-metrics.md`

**脚本(Scripts):**

- `skills/weekly-performance-digest/scripts/generate_weekly_digest.py`
