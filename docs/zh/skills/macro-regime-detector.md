---
layout: default
title: "Macro Regime Detector"
grand_parent: 简体中文
parent: 技能指南
nav_order: 34
lang_peer: /en/skills/macro-regime-detector/
permalink: /zh/skills/macro-regime-detector/
generated: false
---

# Macro Regime Detector
{: .no_toc }

使用跨资产比率分析检测结构性宏观体制转换(1-2 年视角)。分析 RSP/SPY 集中度、收益率曲线、信用状况、规模因子、股债关系与板块轮动,识别集中(Concentration)、扩散(Broadening)、收缩(Contraction)、通胀(Inflationary)与过渡(Transitional)五种体制状态之间的切换。当用户询问宏观体制、市场体制变化、结构性轮动或长期市场定位时运行本技能。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/macro-regime-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/macro-regime-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Macro Regime Detector 技能通过跨资产比率分析,识别股票市场所处的结构性宏观体制,并据此给出对应的组合配置思路。

---

## 2. 使用时机

- 用户询问当前宏观体制或体制转换情况
- 用户想理解结构性市场轮动(集中 vs 扩散)
- 用户询问基于收益率曲线、信用状况或跨资产信号的长期定位
- 用户提到 RSP/SPY 比率、IWM/SPY、HYG/LQD 或其他跨资产比率
- 用户想评估体制变化是否正在发生

---

## 3. 前提条件

- **FMP API 密钥**(必需):设置 `FMP_API_KEY` 环境变量或传入 `--api-key`
- 免费套餐(每日 250 次调用)已足够使用(脚本约消耗 10 次调用)

---

## 4. 快速开始

```bash
python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
```

---

## 5. 工作流

1. 加载参考文档以获取方法论背景:
   - `references/regime_detection_methodology.md`
   - `references/indicator_interpretation_guide.md`

2. 执行主分析脚本:
   ```bash
   python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
   ```
   该脚本会获取 9 只 ETF 共 600 天的数据,以及国债利率数据(总计 10 次 API 调用)。

3. 阅读生成的 Markdown 报告,并向用户展示分析结论。

4. 当用户询问历史相似案例时,使用 `references/historical_regimes.md` 提供额外背景信息。

---

## 6. 组成分量

| # | 组成分量 | 比率/数据 | 权重 | 检测目标 |
|---|-----------|------------|--------|-----------------|
| 1 | 市场集中度 | RSP/SPY | 25% | 大盘股集中 vs 市场扩散 |
| 2 | 收益率曲线 | 10Y-2Y 利差 | 20% | 利率周期转换 |
| 3 | 信用状况 | HYG/LQD | 15% | 信用周期风险偏好 |
| 4 | 规模因子 | IWM/SPY | 15% | 小盘股 vs 大盘股轮动 |
| 5 | 股债关系 | SPY/TLT + 相关性 | 15% | 股债关系体制 |
| 6 | 板块轮动 | XLY/XLP | 10% | 周期性 vs 防御性偏好 |

---

## 7. 体制分类

- **集中(Concentration)**:大盘股领涨,市场广度狭窄。重点关注大盘科技/成长龙头。
- **扩散(Broadening)**:参与度扩大,小盘股/价值股轮动。增加等权重与周期性敞口。
- **收缩(Contraction)**:信用收紧,防御性轮动,风险偏好下降。提高现金比例,优先配置必需消费品/医疗保健板块。
- **通胀(Inflationary)**:股债呈正相关,传统对冲手段失效。配置实物资产、TIPS(通胀保值债券)与短久期债券。
- **过渡(Transitional)**:多个信号并存但方向不明确。增加分散化配置,避免集中押注。

---

## 8. 输出

会向 `--output-dir`(默认:当前目录)保存两个文件:

- `macro_regime_YYYY-MM-DD_HHMMSS.json` —— 供程序化使用的结构化数据
- `macro_regime_YYYY-MM-DD_HHMMSS.md` —— 人类可读的报告,内容包括:
  1. 当前体制评估
  2. 转换信号仪表盘
  3. 各分量详情
  4. 体制分类证据
  5. 组合配置建议

---

## 9. 与其他技能的关系

| 维度 | Macro Regime Detector | Market Top Detector | Market Breadth Analyzer |
|--------|----------------------|--------------------|-----------------------|
| 时间维度 | 1-2 年(结构性) | 2-8 周(战术性) | 当前快照 |
| 数据粒度 | 按月(6 个月/12 个月均线) | 按日(25 个交易日) | 每日 CSV |
| 检测目标 | 体制转换 | 10%-20% 的回调 | 市场宽度健康评分 |
| API 调用次数 | 约 10 次 | 约 33 次 | 0 次(免费 CSV) |

---

## 10. 脚本参数

```bash
python3 macro_regime_detector.py [options]

Options:
  --api-key KEY       FMP API 密钥(默认:$FMP_API_KEY)
  --output-dir DIR    输出目录(默认:当前目录)
  --days N            获取历史数据的天数(默认:600)
```

---

## 11. 资源

**参考文档(References):**

- `skills/macro-regime-detector/references/historical_regimes.md`
- `skills/macro-regime-detector/references/indicator_interpretation_guide.md`
- `skills/macro-regime-detector/references/regime_detection_methodology.md`

**脚本(Scripts):**

- `skills/macro-regime-detector/scripts/fmp_client.py`
- `skills/macro-regime-detector/scripts/macro_regime_detector.py`
- `skills/macro-regime-detector/scripts/report_generator.py`
- `skills/macro-regime-detector/scripts/scorer.py`
