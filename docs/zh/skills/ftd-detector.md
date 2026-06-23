---
layout: default
title: "FTD Detector"
grand_parent: 简体中文
parent: 技能指南
nav_order: 28
lang_peer: /en/skills/ftd-detector/
permalink: /zh/skills/ftd-detector/
generated: false
---

# FTD Detector
{: .no_toc }

使用威廉·欧奈尔(William O'Neil)的方法论检测确认市场底部的跟进日(Follow-Through Day, FTD)信号。采用双指数跟踪(标普 500 + 纳斯达克),通过状态机管理反弹尝试、FTD 资格确认与 FTD 后健康度监控。当用户询问市场底部信号、跟进日、反弹尝试、调整后的再入场时机,或是否适合提高股票敞口时使用本技能。本技能与 market-top-detector(防御性)互补——本技能是进攻性的(底部确认)。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP 必需</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ftd-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ftd-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

FTD Detector 使用威廉·欧奈尔的跟进日方法论识别市场底部信号。它同时跟踪标普 500 与纳斯达克/QQQ,通过一个状态机管理从调整、反弹尝试到 FTD 确认的演进过程,并在 FTD 确认后进行健康度监控,包括分布日计数、失效检测与强势趋势(power trend)分析。

---

## 2. 使用时机

- 用户问"市场正在筑底吗?"或"现在适合再次买入吗?"
- 用户观察到市场调整(跌幅 3% 以上)并希望了解再入场时机
- 用户询问跟进日或反弹尝试
- 用户希望评估近期的反弹是否可持续
- 用户询问调整后是否应该提高股票敞口
- Market Top Detector 显示风险升高,用户希望了解底部信号

---

## 3. 前提条件

- **FMP API 密钥:** 必需。设置 `FMP_API_KEY` 环境变量,或通过 `--api-key` 参数传入。
- **Python 3.8+:** 已安装 `requests` 库。
- **API 调用预算:** 每次执行 4 次调用(完全在 FMP 免费层每天 250 次的限额内)。

---

## 4. 快速开始

```bash
python3 skills/ftd-detector/scripts/ftd_detector.py --api-key $FMP_API_KEY
```

---

## 5. 工作流

### 阶段 1:执行 Python 脚本

运行 FTD 检测脚本:

```bash
python3 skills/ftd-detector/scripts/ftd_detector.py --api-key $FMP_API_KEY
```

该脚本会:
1. 从 FMP API 获取标普 500 与 QQQ 的历史数据(60 个以上交易日)
2. 获取两个指数的当前报价
3. 运行双指数状态机(调整 → 反弹 → FTD 检测)
4. 评估 FTD 后的健康度(分布日、失效情况、强势趋势)
5. 计算质量评分(0-100)
6. 生成 JSON 与 Markdown 报告

**API 调用预算:** 4 次调用(完全在每天 250 次的免费层限额内)

### 阶段 2:呈现结果

将生成的 Markdown 报告呈现给用户,重点突出:
- 当前市场状态(调整中、反弹尝试、FTD 已确认等)
- 质量评分与信号强度
- 建议的敞口水平
- 关键关注价位(摆动低点、FTD 当日低点)
- FTD 后健康度(分布日、强势趋势)

### 阶段 3:情境化建议

根据市场状态,提供额外的建议:

**如果 FTD 已确认(评分 60 以上):**
- 建议关注处于合理整理形态中的领涨股
- 引用 CANSLIM 选股器以寻找候选标的
- 提醒注意仓位规模与止损设置

**如果处于反弹尝试阶段(第 1-3 天):**
- 建议保持耐心,不要在 FTD 确认之前抢先买入
- 建议建立观察名单

**如果没有发生调整:**
- FTD 分析在上升趋势中不适用
- 转而参考 Market Top Detector 以获取防御性信号

---

## 6. 资源

**参考文档(References):**

- `skills/ftd-detector/references/ftd_methodology.md`
- `skills/ftd-detector/references/post_ftd_guide.md`

**脚本(Scripts):**

- `skills/ftd-detector/scripts/fmp_client.py`
- `skills/ftd-detector/scripts/ftd_detector.py`
- `skills/ftd-detector/scripts/post_ftd_monitor.py`
- `skills/ftd-detector/scripts/rally_tracker.py`
- `skills/ftd-detector/scripts/report_generator.py`
