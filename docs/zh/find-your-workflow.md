---
layout: default
title: 选择你的工作流
parent: 简体中文
nav_order: 6
lang_peer: /en/find-your-workflow/
permalink: /zh/find-your-workflow/
---

# 选择你的工作流
{: .no_toc }

这是 Solo Trader OS 的静态“从哪里开始”指南。在翻阅[技能目录](skill-catalog.md)
或[工作流](workflows.md)页面之前，本页可让你一眼找到契合自身处境的入口工作流。

如果下表都不符合你的情况，请用自然语言把目标告诉
[**`trading-skills-navigator`**](skills/trading-skills-navigator.md)，
它会机械地返回同样的推荐结果。

---

## 按每日节奏选择

| 你的处境 | 起步工作流 |
|---|---|
| 想在开盘前 15 分钟确认行情 | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) |
| 只在行情允许时做波段交易 | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) → [`swing-opportunity-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/swing-opportunity-daily.yaml) |
| 想每周复盘长期组合 | [`core-portfolio-weekly`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/core-portfolio-weekly.yaml) |
| 想从已成交的交易中学习 | [`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml) |
| 想每月回顾绩效并修订规则 | [`monthly-performance-review`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/monthly-performance-review.yaml) |

> 拿不准时，用自然语言把日常节奏告诉 [`trading-skills-navigator`](skills/trading-skills-navigator.md)。

---

## 按目标选择

| 你的目标 | 技能集 | 驱动的工作流 |
|---|---|---|
| 先想知道今天是 risk-on 还是 risk-off | [`market-regime`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/market-regime.yaml) | `market-regime-daily` |
| 想运营 Core（股息・ETF・长期持有）的长期组合 | [`core-portfolio`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/core-portfolio.yaml) | `core-portfolio-weekly` |
| 想只在行情允许时寻找有纪律的卫星波段候选 | [`swing-opportunity`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/swing-opportunity.yaml) | `swing-opportunity-daily` |
| 想记录全部交易、生成事后复盘、把心得留在日志里 | [`trade-memory`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/trade-memory.yaml) | `trade-memory-loop`, `monthly-performance-review` |

> 不确定自己的目标对应哪个，把自由描述的目标交给
> [`trading-skills-navigator`](skills/trading-skills-navigator.md)，它会帮你对应到技能集与工作流。

---

## 当现有工作流都不适用时

### 无需 API 密钥的入口

如果你还没有 FMP / FINVIZ / Alpaca 的付费订阅，先手动跑这 5 个技能。
同样的最小循环可在没有付费数据的情况下支撑
[`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml)
与
[`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml)。

1. [`market-breadth-analyzer`](skills/market-breadth-analyzer.md) —— 用公开 CSV 计算宽度评分
2. [`uptrend-analyzer`](skills/uptrend-analyzer.md) —— 公开 CSV 的上升趋势参与比率
3. [`position-sizer`](skills/position-sizer.md) —— 纯计算
4. [`trader-memory-core`](skills/trader-memory-core.md) —— 用本地 YAML 记录交易日志
5. [`signal-postmortem`](skills/signal-postmortem.md) —— 复盘框架

“无需 API”并不等于“无需外部数据”。这些技能需要公开 CSV、图表截图或本地文件。
精确的输入要求请参阅各技能在
[`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
中的 `integrations:` 字段。

### 已知的缺口

部分使用场景尚无打包好的工作流。它们在
[`PROJECT_VISION.md`](https://github.com/tradermonty/claude-trading-skills/blob/main/PROJECT_VISION.md)
中作为后续候选被明确跟踪。

- **纯做空 / risk-off 日内** —— `parabolic-short-trade-planner` 已部分覆盖，
  但尚无端到端的做空工作流
- **财报周日内** —— `earnings-trade-analyzer` 与 `pead-screener` 已部分覆盖，
  但尚无周度编排工作流
- **策略研究流水线** —— 已有 `edge-pipeline-orchestrator`，但尚无
  “发现新 edge”这一正式（canonical）的工作流 manifest

如果你的处境落入这些缺口，请把它们当作探索性场景：从[技能目录](skill-catalog.md)
中挑选所需的单个技能，在专用工作流推出前临时（ad hoc）运行。

### 自由描述的自然语言入口

对于上表未涵盖的处境，请使用
[`trading-skills-navigator`](skills/trading-skills-navigator.md) 技能。
传入自由描述的目标，它会返回最合适的工作流、技能集、API 配置与设置步骤。
其推荐与本页基于同一份
[`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
的单一事实来源（Single Source of Truth）。

---

## 相关页面

- [新手入门](getting-started.md) —— 面向 Claude Code / Claude Web App / CLI 的安装步骤
- [技能目录](skill-catalog.md) —— 全部技能的字母序目录
- [工作流](workflows.md) —— 全部工作流的自动生成 manifest 参考
- [技能集](skillsets.md) —— 按目标划分的安装包
