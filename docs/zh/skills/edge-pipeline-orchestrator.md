---
layout: default
title: "Edge Pipeline Orchestrator"
grand_parent: 简体中文
parent: 技能指南
nav_order: 23
lang_peer: /en/skills/edge-pipeline-orchestrator/
permalink: /zh/skills/edge-pipeline-orchestrator/
generated: false
---

# Edge Pipeline Orchestrator
{: .no_toc }

编排完整的策略优势(edge)研究流水线,从候选标的检测一直到策略设计、审查、修订与导出。当需要端到端协调多阶段的策略优势研究工作流时使用本技能。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-pipeline-orchestrator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-pipeline-orchestrator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Edge Pipeline Orchestrator(策略优势流水线编排器)

本技能负责协调整个策略优势研究流水线的各个阶段——从原始 OHLCV 数据或交易凭据(ticket)的候选标的检测开始,依次经过线索提取、概念综合、策略草案设计、审查与修订反馈循环,最终导出符合条件的策略。它通过子进程方式调度本地的各个 edge 系列技能,使整套多阶段研究流程可以一次性端到端运行,也可以从任意阶段断点续跑。

---

## 2. 使用时机

- 从交易凭据(或 OHLCV 数据)运行完整的策略优势流水线,直至导出策略
- 从草案阶段恢复一个尚未完成的流水线
- 通过反馈循环对已有的策略草案进行审查与修订
- 试运行(dry-run)流水线以预览结果而不实际导出

---

## 3. 前提条件

- 通过子进程编排本地的多个 edge 系列技能
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
# 从交易凭据运行完整流水线
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --market-summary /path/to/market_summary.json \
  --anomalies /path/to/anomalies.json \
  --output-dir reports/edge_pipeline/

# 仅审查模式,使用已有草案
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --review-only \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/edge_pipeline/

# 试运行(不导出)
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --output-dir reports/edge_pipeline/ --dry-run
```

---

## 5. 工作流

1. 从 CLI 参数加载流水线配置
2. 如提供了 --from-ohlcv,则运行 auto_detect 阶段(从原始 OHLCV 数据生成交易凭据)
3. 运行 hints 阶段,从市场摘要与异常数据中提取策略优势线索
4. 运行 concepts 阶段,根据交易凭据与线索综合出抽象的策略优势概念
5. 运行 drafts 阶段,根据概念设计策略草案
6. 运行审查-修订反馈循环:
   - 审查所有草案(最多 2 轮迭代)
   - 累积 PASS(通过)判定;累积 REJECT(拒绝)判定
   - REVISE(待修订)判定会触发 apply_revisions 并重新审查
   - 经过最大迭代次数后仍为 REVISE 的草案降级为 research_probe(研究性探针)
7. 导出符合条件的草案(PASS + export_ready_v1 + 可导出的 entry_family)
8. 写入 pipeline_run_manifest.json,记录完整的执行轨迹

---

## 6. 资源

**参考文档(References):**

- `skills/edge-pipeline-orchestrator/references/pipeline_flow.md`
- `skills/edge-pipeline-orchestrator/references/revision_loop_rules.md`

**脚本(Scripts):**

- `skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py`
