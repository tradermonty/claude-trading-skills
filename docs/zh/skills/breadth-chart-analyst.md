---
layout: default
title: "Breadth Chart Analyst"
grand_parent: 简体中文
parent: 技能指南
nav_order: 11
lang_peer: /en/skills/breadth-chart-analyst/
permalink: /zh/skills/breadth-chart-analyst/
generated: false
---

# Breadth Chart Analyst
{: .no_toc }

使用标普 500 宽度指数(基于 200 日均线)和美股上升趋势比率分析市场宽度。支持两种模式:**CSV 数据模式**(无需图表截图,直接从公开来源获取实时数据)和**图表图像模式**(采用两阶段右侧边缘提取的可视化分析)。提供中期战略和短期战术两个层面的市场展望,并附有经过回测验证的持仓信号。所有输出均为英文。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/breadth-chart-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/breadth-chart-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能用于对两个互补的市场宽度指标进行专项分析,分别提供战略层面(中长期)和战术层面(短期)的市场视角。

**两种运行模式:**

| 模式 | 输入 | 数据来源 | 最适合 |
|------|-------|-------------|----------|
| **CSV 数据**(主要) | 无需图像 | GitHub Pages 公开 CSV | 快速数值分析、自动化 |
| **图表图像**(补充) | 用户提供的截图 | 可视化分析 + CSV 交叉验证 | 历史形态背景、可视化确认 |

CSV 数据始终是数值的**主要(PRIMARY)**来源。图表图像提供补充性的可视化背景和历史形态识别。

---

## 2. 使用时机

- 用户请求市场宽度评估或市场健康度评价
- 用户询问基于宽度指标的中期战略定位
- 用户需要用于波段交易的短期战术时点信号
- 用户希望获得战略与战术结合的综合市场展望
- **用户请求宽度分析但未提供图表图像**(CSV 数据模式)
- 用户提供宽度图表图像以进行可视化分析

以下情况**不要**使用本技能:
- 用户询问个股分析(应使用 `us-stock-analysis` 技能)
- 用户需要不依赖宽度图表的板块轮动分析(应使用 `sector-analyst` 技能)
- 用户希望进行基于新闻的市场分析(应使用 `market-news-analyst` 技能)

---

## 3. 前提条件

- **图表图像可选**:公开来源的 CSV 数据是主要数据源;图表图像提供补充性的可视化背景
- **无需 API 密钥**:CSV 数据从公开的 GitHub Pages 获取,无需任何订阅
- **Python 3.9+**:用于运行 CSV 获取脚本(仅使用标准库,无需 pip 安装)
- **语言**:所有分析与输出均使用英文

---

## 4. 快速开始

```bash
# 获取最新宽度数据(无需图表图像)
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py

# 输出 JSON 格式供程序化使用
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py --json
```

**输出示例:**
```
============================================================
Breadth Data (CSV) - 2026-03-13
============================================================
--- Market Breadth (S&P 500) ---
200-Day MA: 62.13% (healthy (>=60%))
8-Day MA:   55.05% (neutral (40-60%))
8MA vs 200MA: -7.08pt (8MA BELOW -- DEAD CROSS)
Trend: -1
--- Uptrend Ratio (All Markets) ---
Current: 12.55% RED (bearish)
10MA: 15.67%, Slope: -0.0157, Trend: DOWN
--- Sector Summary ---
Overbought: Energy (50.3%)
Oversold: Industrials (8.4%), Communication Services (5.8%), ...
============================================================
```

---

## 5. 工作流

### 步骤 0:获取 CSV 数据(主要数据源 —— 必须执行)

CSV 数据是所有宽度数值的主要来源。本步骤**必须**在任何图像分析之前执行。

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py
```

**数据来源:**

| 来源 | URL | 提供内容 |
|--------|-----|----------|
| Market Breadth | `tradermonty.github.io/.../market_breadth_data.csv` | 200 日均线、8 日均线、趋势、死叉 |
| Uptrend Ratio | `github.com/tradermonty/uptrend-dashboard/.../uptrend_ratio_timeseries.csv` | 比率、10 日均线、斜率、趋势、颜色标记 |
| Sector Summary | `github.com/tradermonty/uptrend-dashboard/.../sector_summary.csv` | 各板块比率、趋势、状态 |

**数据来源优先级:**

| 优先级 | 来源 | 可靠性 |
|----------|--------|-------------|
| 1(主要) | **CSV 数据** | 高 |
| 2(补充) | 图表图像 | 中 |
| 3(已弃用) | ~~OpenCV 脚本~~ | 不可靠 |

如果用户没有提供图表图像,跳过步骤 1 和 1.5,直接使用 CSV 数据进行分析。

### 步骤 1:接收图表图像(如有提供)

当用户提供宽度图表图像时:

1. 确认已收到图表图像
2. 识别提供了哪些图表(图表 1:200MA 宽度图,图表 2:上升趋势比率图,或两者皆有)
3. 进入步骤 1.5 进行两阶段图表分析

### 步骤 1.5:两阶段图表分析(提供图表时)

使用**两阶段分析法**,防止把历史数据误读为当前数值:

**阶段 1:完整图表** —— 分析历史背景、过往波峰/波谷、周期规律

**阶段 2:右侧边缘** —— 提取并分析最右侧 25% 区域以获取当前数值:

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

如果阶段 1 和阶段 2 的数值不一致,**以阶段 2 为准**。始终与步骤 0 中的 CSV 数据进行交叉验证。

### 步骤 2:加载方法论

```
Read: references/breadth_chart_methodology.md
```

### 步骤 3:分析图表 1(基于 200MA 的宽度指数)

#### 需提取的关键读数:
- **8MA 水平**(橙色线)和**200MA 水平**(绿色线)
- 斜率、距 73% 和 23% 阈值的距离
- 信号标记:8MA 波谷(紫色 ▼)、200MA 波峰(红色 ▲)

#### 关键:线条颜色核验
- **8MA = 橙色**(变动较快,波动性更高)
- **200MA = 绿色**(变动较慢,更平滑)

#### 买入信号(必须同时满足以下所有条件):
1. 8MA 形成明确波谷(紫色 ▼)
2. 8MA 已开始从波谷向上回升
3. 8MA 已连续上升 2-3 个周期
4. 8MA **当前**正在上升(而非下降)
5. 8MA 维持了上升轨迹

**信号状态**:已确认(CONFIRMED) / 发展中(DEVELOPING) / 失败(FAILED) / 无信号(NO SIGNAL)

#### 卖出信号:
- 200MA 在接近或高于 73% 处形成波峰(红色 ▲)

#### 死叉/金叉判定:
- 8MA 低于 200MA 且持续收敛 = **死叉**(看跌)
- 8MA 低于 200MA 但向上发散 = **金叉**(看涨)

### 步骤 4:分析图表 2(上升趋势股票比率)

#### 关键读数:
- 当前比率、颜色(绿色/红色)、斜率
- 距 10%(超卖)和 40%(超买)阈值的距离
- 近期颜色转换(红转绿 = 买入,绿转红 = 卖出)

### 步骤 5:综合分析

当两套数据都可用时,将市场归入以下四种情形之一:

| 情形 | 战略层面(图表 1) | 战术层面(图表 2) | 含义 |
|----------|-------------------|-------------------|-------------|
| 双多 | 8MA 上升 | 绿色,上升 | 最强烈看涨 |
| 战略多 / 战术空 | 8MA 上升 | 红色,下降 | 持有核心仓位,等待入场时机 |
| 战略空 / 战术多 | 200MA 已见顶 | 绿色,上升 | 仅做战术性交易 |
| 双空 | 两条均线均下行 | 红色,下降 | 转为防御性持仓 |

### 步骤 6:生成报告

保存到 `reports/` 目录:
- `breadth_200ma_analysis_[YYYY-MM-DD].md`
- `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- `breadth_combined_analysis_[YYYY-MM-DD].md`

### 步骤 7:质量保证

关键核验要点:
1. 所有输出均为英文
2. 已核验线条颜色(8MA = 橙色,200MA = 绿色)
3. 趋势方向反映的是**最右侧**数据点,而非历史数据
4. 明确说明死叉/金叉状态
5. 清晰标识信号状态
6. 各情形概率之和为 100%
7. 为每类交易者提供可执行的持仓建议

---

## 6. 资源

**参考文档(References):**

- `skills/breadth-chart-analyst/references/breadth_chart_methodology.md`

**脚本(Scripts):**

- `skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py` —— 主要数据源(仅使用标准库)
- `skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py` —— 图表右侧边缘提取器(PIL)
- `skills/breadth-chart-analyst/scripts/detect_uptrend_ratio.py` —— 基于 OpenCV 的上升趋势检测(已弃用)
- `skills/breadth-chart-analyst/scripts/detect_breadth_values.py` —— 基于 OpenCV 的宽度检测(已弃用)
