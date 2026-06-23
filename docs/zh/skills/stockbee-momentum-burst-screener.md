---
layout: default
title: "Stockbee Momentum Burst Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 49
lang_peer: /en/skills/stockbee-momentum-burst-screener/
permalink: /zh/skills/stockbee-momentum-burst-screener/
generated: false
---

# Stockbee Momentum Burst Screener
{: .no_toc }

使用 4% 突破、美元突破、波幅扩张、成交量放大、前期波幅收缩、收盘位置、失败过滤器以及风险距离评分,筛选符合 Stockbee 风格短线动量爆发(Momentum Burst)形态的美股。当用户询问 Stockbee、Pradeep Bonde、动量爆发、4% 突破、波幅扩张、美元突破、短线波段动量候选股,或 3-5 天爆发形态复核时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-momentum-burst-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-momentum-burst-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Stockbee Momentum Burst Screener 技能,用于按 Stockbee(Pradeep Bonde)风格的短线动量爆发方法筛选美股候选标的。

---

## 2. 使用时机

- 用户要求按 Stockbee / Pradeep Bonde 风格筛选动量爆发标的
- 用户想要 4% 突破、美元突破或波幅扩张候选股
- 用户要求短线 3-5 天波段动量形态
- 用户想了解某次日线突破是否具备 A/B/C 级形态质量
- 用户提供股票列表、股票池文件,或用于筛选的历史 OHLCV JSON 数据
- 用户希望将候选股结果输出给 `technical-analyst`、`position-sizer` 或 `trader-memory-core` 做后续处理

---

## 3. 前提条件

- 用于实时股票池及历史 OHLCV 筛选的 FMP API 密钥:
  ```bash
  export FMP_API_KEY=your_api_key_here
  ```
- 可选的无 API 路径:提供包含按代码组织的日线 OHLCV 数据的 `--prices-json`。
- 仅在市场环境(market-regime)工作流允许承担新的波段风险时运行,否则将输出标记为仅供人工复核。

---

## 4. 快速开始

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

---

## 5. 工作流

### 步骤 1:选择输入模式

使用以下三种模式之一:

**模式 A:FMP 股票池扫描**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

**模式 B:指定代码列表**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols NVDA SMCI PLTR TSLA \
  --output-dir reports/
```

**模式 C:离线 OHLCV JSON**
```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --output-dir reports/
```

### 步骤 2:运行筛选

脚本检测以下几类触发条件:

- **4% 突破:** `收盘价 / 前一日收盘价 >= 1.04`,且成交量高于前一日,并高于流动性下限
- **美元突破:** `收盘价 - 开盘价 >= 0.90`,且成交量高于流动性下限
- **波幅扩张:** 当日波幅超过此前三日波幅,且前一日尚未出现扩张

随后使用以下因素对形态质量打分:

- 触发强度
- 成交量放大程度
- 前期整理区间 / 波幅收缩质量
- 收盘价接近当日最高点的程度
- 距触发日最低点的风险距离
- 失败过滤器,例如前期 3 日连涨或近期 4% 破位
- 与市场环境闸门的一致性

### 步骤 3:复核输出

阅读生成的 JSON 和 Markdown 报告。针对每个候选股,呈现以下信息:

- 触发类型及所有匹配的触发标签
- 当日涨幅、美元涨幅、成交量比率、收盘位置百分比
- 前期整理区间长度与区间宽度
- 入场参考价、止损参考价,以及距止损的风险百分比
- 形态评分、评级、状态及拒绝理由
- 建议的下游操作

### 步骤 4:将通过筛选的标的送入交易计划

谨慎使用输出结果:

- **A / A- 级候选股:** 送入 `technical-analyst` 进行人工图表验证,再交给 `position-sizer`
- **B 级候选股:** 仅纳入观察名单或进行较小风险的复核
- **仅观察候选股:** 保留在模型观察池中;除非图表复核将其升级,否则不要规划交易
- **被拒绝的候选股:** 保留用于事后分析,不用于实际执行

---

## 6. 资源

**参考文档(References):**

- `skills/stockbee-momentum-burst-screener/references/entry_exit_rules.md`
- `skills/stockbee-momentum-burst-screener/references/momentum_burst_methodology.md`
- `skills/stockbee-momentum-burst-screener/references/scoring_system.md`

**脚本(Scripts):**

- `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py`
