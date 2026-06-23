---
layout: default
title: "PEAD Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 40
lang_peer: /en/skills/pead-screener/
permalink: /zh/skills/pead-screener/
generated: false
---

# PEAD Screener
{: .no_toc }

筛选财报后跳空上涨的股票,识别 PEAD(Post-Earnings Announcement Drift,财报后公告漂移)形态。通过分析周线K线形态来检测红色回调K线与突破信号。支持两种输入模式——FMP 财报日历(模式 A)或 earnings-trade-analyzer 的 JSON 输出(模式 B)。当用户询问 PEAD 筛选、财报后漂移、财报跳空后续表现、红色K线突破形态,或周线财报动量形态时使用本技能。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/pead-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pead-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

PEAD Screener —— 财报后公告漂移(Post-Earnings Announcement Drift)

PEAD(财报后公告漂移)是指股票在财报公布后,价格往往会延续与财报反应方向一致的趋势(而非立即逆转)。本技能专注于捕捉财报后跳空上涨、随后出现短暂回调(红色周K线)、再向上突破的形态,以此识别具备后续上涨潜力的交易设置。

---

## 2. 使用时机

- 用户要求进行 PEAD 筛选或财报后漂移分析
- 用户希望寻找具有后续上涨潜力的财报跳空上涨股票
- 用户请求财报后的红色K线突破形态
- 用户要求获取周线财报动量交易设置
- 用户提供 earnings-trade-analyzer 的 JSON 输出以进行进一步筛选

---

## 3. 前提条件

- FMP API 密钥(设置 `FMP_API_KEY` 环境变量,或传入 `--api-key`)
- 免费层级(每天 250 次调用)足以满足默认筛选需求
- 模式 B 需要:schema_version 为 "1.0" 的 earnings-trade-analyzer JSON 输出文件

---

## 4. 快速开始

```bash
# 模式 A:FMP 财报日历(独立运行)
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --min-gap 3.0 --max-api-calls 200 \
  --output-dir reports/

# 模式 B:来自 earnings-trade-analyzer 输出的流水线模式
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_*.json \
  --min-grade B --output-dir reports/
```

---

## 5. 工作流

### 第 1 步:准备并执行筛选

以下面两种模式之一运行 PEAD 筛选脚本:

**模式 A(FMP 财报日历):**
```bash
# 默认:最近 14 天的财报,5 周监控窗口
python3 skills/pead-screener/scripts/screen_pead.py --output-dir reports/

# 自定义参数
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 21 \
  --watch-weeks 6 \
  --min-gap 5.0 \
  --min-market-cap 1000000000 \
  --output-dir reports/
```

**模式 B(以 earnings-trade-analyzer 的 JSON 作为输入):**
```bash
# 来自 earnings-trade-analyzer 的输出
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B \
  --output-dir reports/
```

### 第 2 步:查看结果

1. 阅读生成的 JSON 与 Markdown 报告
2. 加载 `references/pead_strategy.md` 以了解 PEAD 理论与形态背景
3. 加载 `references/entry_exit_rules.md` 以了解交易管理规则

### 第 3 步:呈现分析结果

针对每个候选标的,呈现以下内容:
- 阶段分类(MONITORING 监控中、SIGNAL_READY 信号就绪、BREAKOUT 已突破、EXPIRED 已过期)
- 周K线形态细节(红色K线位置、突破状态)
- 综合评分与评级
- 交易设置:入场价、止损价、目标价、风险回报比
- 流动性指标(ADV20、平均成交量)

### 第 4 步:提供可执行建议

根据阶段与评级:
- **BREAKOUT + 强势设置(85 分以上):** 高确信度的 PEAD 交易,可使用全仓位
- **BREAKOUT + 良好设置(70-84 分):** 稳健的 PEAD 设置,使用标准仓位
- **SIGNAL_READY:** 红色K线已形成,设置突破红色K线高点的提醒
- **MONITORING:** 财报已发布,尚未形成红色K线,加入观察名单
- **EXPIRED:** 超出监控窗口,从观察名单中移除

---

## 6. 资源

**参考文档(References):**

- `skills/pead-screener/references/entry_exit_rules.md`
- `skills/pead-screener/references/pead_strategy.md`

**脚本(Scripts):**

- `skills/pead-screener/scripts/fmp_client.py`
- `skills/pead-screener/scripts/report_generator.py`
- `skills/pead-screener/scripts/scorer.py`
- `skills/pead-screener/scripts/screen_pead.py`
