---
layout: default
title: "Trader Memory Core"
grand_parent: 简体中文
parent: 技能指南
nav_order: 54
lang_peer: /en/skills/trader-memory-core/
permalink: /zh/skills/trader-memory-core/
generated: false
---

# Trader Memory Core
{: .no_toc }

持久化状态层,跟踪投资论点从筛选想法到平仓并完成事后复盘的全过程。把筛选器、分析、仓位测算与组合管理的输出,按每个交易想法打包进单一论点对象。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trader-memory-core.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trader-memory-core){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Trader Memory Core 回答这样一个问题:“我当时怎么想的、发生了什么、我学到了什么?”它提供一个持久的、基于文件的状态层,跟随每个投资论点走完其完整生命周期:

```
筛选器输出 → IDEA → ENTRY_READY → ACTIVE → CLOSED
                │          │            │
                └──────────┴────────────┴──→ INVALIDATED
```

**它解决什么:**
- 消除筛选与执行跟踪之间的断层
- 为每个交易想法在多次对话间提供单一事实来源
- 强制有纪律的状态迁移(不可跳步)
- 生成含 P&L 与 MAE/MFE 指标的结构化事后复盘报告
- 排定周期性复盘,使任何持仓都不被遗忘

**核心能力:**
- 7 个筛选器适配器:kanchi-dividend-sop、earnings-trade-analyzer、vcp-screener、pead-screener、canslim-screener、edge-candidate-agent、edge-concept-synthesizer
- 仅向前推进、含 5 个状态的状态机
- 基于指纹的去重(同一筛选器输出绝不重复登记)
- 接入 Position Sizer 技能的仓位测算
- 带升级阶梯的复盘排期(OK → WARN → REVIEW)
- 事后复盘生成,MAE/MFE 可选(经 FMP API)

**第 1 阶段范围:** 仅单标的论点。配对交易与期权策略计划在第 2 阶段。

---

## 2. 使用时机

- 筛选器产出候选后,你想**持久跟踪**它们
- 你想把一个论点从想法**迁移**到入场就绪再到活跃持仓
- 需要**附加 position-sizer 输出**来确定交易规模
- 检查**哪些论点到了复盘时间**
- **平仓**并生成含经验教训的事后复盘
- 你想要带结构化 P&L 统计的**交易日志**

**触发短语:** “register thesis”“track this idea”“thesis status”“review due”“close position”“postmortem”“trading journal”

---

## 3. 前提条件

- **Python 3.9+**,含 `pyyaml` 与 `jsonschema`(均在项目依赖中)
- **FMP API 密钥:** 可选 —— 仅在事后复盘报告中计算 MAE/MFE 时需要。核心功能(登记、迁移、平仓、复盘)完全离线可用
- **状态目录:** `state/theses/` 在首次使用时自动创建

> FMP API 仅用于获取每日价格历史,以在事后复盘时计算最大不利偏移(MAE)与最大有利偏移(MFE)。若未设置 API 密钥,事后复盘报告仍会生成,只是不含这两项。
{: .tip }

---

## 4. 快速开始

```bash
# 步骤 1:把筛选器输出登记为论点
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# 步骤 2:查询你的论点
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ list --status IDEA

# 步骤 3:生成汇总统计
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ summary
```

---

## 5. 工作流

### 步骤 1:登记 —— 摄入筛选器输出

用源筛选器名称及其 JSON 输出文件运行 ingest 脚本:

```bash
# 来自 kanchi-dividend-sop
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# 来自 earnings-trade-analyzer
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source earnings-trade-analyzer \
  --input reports/earnings_trade_scored_2026-03-14.json \
  --state-dir state/theses/
```

JSON 中的每个候选都成为一个 `IDEA` 论点。登记是**幂等的** —— 对同一输入运行两次不会产生重复(基于指纹的去重)。

**支持的来源:** `kanchi-dividend-sop`、`earnings-trade-analyzer`、`vcp-screener`、`pead-screener`、`canslim-screener`、`edge-candidate-agent`

### 步骤 2:链接分析报告

在做更深分析(US Stock Analysis、Technical Analyst 等)之后,把报告链接到论点:

```python
from skills.trader_memory_core.scripts.thesis_store import link_report

link_report(state_dir, thesis_id,
            skill="us-stock-analysis",
            file="reports/us_stock_AAPL_2026-03-15.md",
            date="2026-03-15")
```

### 步骤 3:从 IDEA 迁移到 ENTRY_READY

用分析验证论点后,将其提升:

```python
from skills.trader_memory_core.scripts.thesis_store import transition

transition(state_dir, thesis_id, "ENTRY_READY",
           reason="技术确认:站上 200 日均线且伴随放量")
```

> `transition()` 只允许 IDEA → ENTRY_READY。其他所有迁移使用专门函数。
{: .warning }

### 步骤 4:开仓(ENTRY_READY 到 ACTIVE)

执行交易时,记录实际入场:

```python
from skills.trader_memory_core.scripts.thesis_store import open_position

open_position(state_dir, thesis_id,
              actual_price=155.50,
              actual_date="2026-03-16T10:30:00-04:00")
```

这是**通往 ACTIVE 状态的唯一路径**。需要同时提供 `actual_price` 与 `actual_date`(带时区的 RFC 3339 格式)。

### 步骤 5:附加仓位测算

链接 Position Sizer 的输出以记录股数与风险参数:

```python
from skills.trader_memory_core.scripts.thesis_store import attach_position

attach_position(state_dir, thesis_id,
                report_path="reports/position_sizer_AAPL_2026-03-16.json")
```

该报告必须为 `mode: "shares"`(预算模式会被拒绝)。

### 步骤 6:周期性复盘

检查哪些论点需要关注:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ review-due --as-of 2026-04-15
```

记录一次带升级支持的复盘:

```python
from skills.trader_memory_core.scripts.thesis_store import mark_reviewed

mark_reviewed(state_dir, thesis_id,
              review_date="2026-04-15",
              outcome="OK")  # OK、WARN 或 REVIEW
```

`next_review_date` 会根据复盘间隔自动推进。

### 步骤 7:平仓与事后复盘

退出持仓时:

```python
from skills.trader_memory_core.scripts.thesis_store import close

close(state_dir, thesis_id,
      exit_reason="target_reached",
      exit_price=172.00,
      exit_date="2026-05-01T15:45:00-04:00")
```

然后生成事后复盘:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1
```

事后复盘含 P&L、持有天数,以及(在有 FMP API 密钥时)MAE/MFE 指标。输出保存到 `state/journal/pm_{thesis_id}.md`。

---

## 6. 解读输出

### 论点 YAML 文件

每个论点以 YAML 文件存储于 `state/theses/`:

| 区块 | 关键字段 | 说明 |
|------|----------|------|
| 标识 | `thesis_id`、`ticker`、`created_at` | 含代码与哈希的唯一 ID |
| 分类 | `thesis_type`、`setup_type`、`catalyst` | 例如 `dividend_income`、`earnings_drift` |
| 状态 | `status`、`status_history` | 当前状态 + 含时间戳的完整迁移日志 |
| 入场 | `entry.target_price`、`entry.actual_price`、`entry.actual_date` | 计划 vs 实际入场 |
| 出场 | `exit.stop_loss`、`exit.target_price`、`exit.actual_price` | 计划 vs 实际出场 |
| 仓位 | `position.shares`、`position.risk_dollars` | 来自 Position Sizer 附加 |
| 监控 | `next_review_date`、`review_history` | 复盘排期与历次复盘 |
| 来源 | `origin.source_skill`、`origin.screening_grade` | 哪个筛选器、什么评分 |
| 结果 | `outcome.pnl_pct`、`outcome.holding_days` | 平仓时计算 |

### 索引文件

`state/theses/_index.json` 提供轻量查找,无需加载单个 YAML 文件即可快速查询。它会自动重建,也可用 `rebuild_index()` 重新生成。

### 事后复盘日志

`state/journal/pm_{thesis_id}.md` 含结构化 Markdown 报告,包括入场/出场摘要、P&L 分析、MAE/MFE 指标(若可用),以及供填写经验教训的空间。

---

## 7. 技巧与最佳实践

- **早登记,晚决策。** 把所有筛选器输出摄入为 IDEA。不打算跟进的可以作废。
- **幂等是你的朋友。** 运行同一 ingest 命令两次是安全的 —— 指纹防止重复。
- **使用 RFC 3339 日期。** 所有日期时间字段都需要时区(例如 `2026-03-16T10:30:00-04:00`)。无时区的 datetime 与空格分隔会被拒绝。
- **作废而非删除。** 用 `terminate(thesis_id, "INVALIDATED", ...)` 而非手动删除 YAML 文件。这能保留审计轨迹。
- **复盘排期很重要。** 默认复盘间隔为 7 天。逾期论点通过 `review-due` 浮现,防止遗忘持仓。
- **升级阶梯。** 复盘走 OK → WARN → REVIEW。连续 WARN 结果会自动升级。
- **慷慨地链接报告。** 你交叉引用的分析越多,事后复盘越丰富。
- **用 Git 跟踪 state/。** `state/` 目录被设计为可提交,让你通过 `git log` 与 `git blame` 获得完整审计轨迹。
- **无 FMP 也能复盘。** MAE/MFE 是锦上添花。P&L、持有天数与经验教训无需任何 API。

---

## 8. 与其他技能组合

| 技能 | 集成点 | 方式 |
|------|--------|------|
| **kanchi-dividend-sop** | 登记 | `thesis_ingest.py --source kanchi-dividend-sop` |
| **earnings-trade-analyzer** | 登记 | `thesis_ingest.py --source earnings-trade-analyzer` |
| **vcp-screener** | 登记 | `thesis_ingest.py --source vcp-screener` |
| **pead-screener** | 登记 | `thesis_ingest.py --source pead-screener` |
| **canslim-screener** | 登记 | `thesis_ingest.py --source canslim-screener` |
| **edge-candidate-agent** | 登记 | `thesis_ingest.py --source edge-candidate-agent` |
| **US Stock Analysis** | 链接报告 | `link_report(thesis_id, skill="us-stock-analysis", ...)` |
| **Technical Analyst** | 链接报告 | `link_report(thesis_id, skill="technical-analyst", ...)` |
| **Position Sizer** | 附加仓位 | `attach_position(thesis_id, report_path)` |
| **Portfolio Manager** | 执行交易 | 开/平仓,然后更新论点 |
| **kanchi-dividend-review-monitor** | 复盘触发 | T1-T5 异常检测喂给 `mark_reviewed()` |

---

## 9. 故障排查

| 错误 | 原因 | 修复 |
|------|------|------|
| `ValidationError: ... is not a 'date-time'` | 日期字段缺时区或用了空格分隔 | 使用 RFC 3339 格式:`2026-03-16T10:30:00-04:00` |
| `ValueError: Cannot transition from terminal status CLOSED` | 试图修改已平仓/已作废的论点 | 终态是永久的。如需可新建论点。 |
| `ValueError: Use open_position() to transition to ACTIVE` | 用 `transition()` 且目标为 `ACTIVE` | 改用 `open_position(thesis_id, actual_price, actual_date)` |
| `ValueError: Budget mode not supported` | position sizer 报告为 `mode: "budget"` | 用 `--entry` 与 `--stop` 重跑 Position Sizer 以得到 shares 模式 |
| `ValueError: Missing required field: ticker` | 筛选器 JSON 缺少预期字段 | 检查输入是否匹配源适配器的预期格式 |
| 未创建重复论点 | 指纹匹配到已有论点 | 这是有意的(幂等)。返回已有的 thesis_id。 |

---

## 10. 资源

**参考文档(References):**
- `skills/trader-memory-core/references/thesis_lifecycle.md` —— 状态及有效迁移
- `skills/trader-memory-core/references/field_mapping.md` —— 源技能到规范字段的映射

**脚本(Scripts):**
- `skills/trader-memory-core/scripts/thesis_ingest.py` —— 筛选器适配器注册表与 CLI
- `skills/trader-memory-core/scripts/thesis_store.py` —— CRUD、迁移与状态管理
- `skills/trader-memory-core/scripts/thesis_review.py` —— 事后复盘生成与汇总统计
- `skills/trader-memory-core/scripts/fmp_price_adapter.py` —— 用于 MAE/MFE 的 FMP API 集成

**Schema:**
- `skills/trader-memory-core/schemas/thesis.schema.json` —— 用于论点校验的 JSON Schema

**完整示例:**
- `examples/workflows/trade-memory-loop/sample-run-full-path/` —— 端到端的 计划 → 交易 → 记录 → 复盘 → 回测 → 日志 示例运行
