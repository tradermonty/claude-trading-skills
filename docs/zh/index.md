---
layout: default
title: 简体中文
nav_order: 3
has_children: true
lang_peer: /en/
permalink: /zh/
---

# Claude Trading Skills
{: .no_toc }

<div class="hero">
  <p class="hero-mantra">Empower Solo Traders and Growing Together</p>
  <p class="hero-tagline">由 Claude 驱动、为你定制的市场分析师</p>
</div>

## 什么是 Claude Trading Skills？

Claude Trading Skills 是一套面向股票投资者与交易者的 **Claude 技能集**。每个技能都把领域专属的提示词、知识库和辅助脚本打包在一起，让 Claude 协助你完成市场分析、个股筛选、策略验证、组合管理等工作。

只需用自然语言描述需求，即可获得结构化报告和可执行的洞察。

<div class="category-cards">
  <div class="category-card">
    <h3>个股筛选</h3>
    <p>CANSLIM、VCP、FinViz、股息筛选器等，将多种投资方法转化为系统化的筛选技能。用自然语言说明条件，即可生成排序后的候选清单。</p>
  </div>
  <div class="category-card">
    <h3>市场分析</h3>
    <p>板块轮动、市场宽度（breadth）、技术分析、新闻分析等，用于评估整体市场的健康度与方向。</p>
  </div>
  <div class="category-card">
    <h3>策略与研究</h3>
    <p>回测、期权策略、主题检测、配对交易等，协助你构建并验证投资策略。</p>
  </div>
  <div class="category-card">
    <h3>组合与执行</h3>
    <p>Portfolio Manager、Position Sizer、财报日历等，覆盖从持仓管理、仓位测算到事件监控的全流程。</p>
  </div>
</div>

---

## 三步上手

<div class="steps">
  <div class="step">
    <span class="step-number">1</span>
    <h4>安装</h4>
    <p>将 <code>.skill</code> 文件上传到 Claude Web App，或克隆仓库并放入 Claude Code。</p>
  </div>
  <div class="step">
    <span class="step-number">2</span>
    <h4>用自然语言提问</h4>
    <p>用中文（或英文）告诉 Claude 你想筛选的条件或要研究的内容。</p>
  </div>
  <div class="step">
    <span class="step-number">3</span>
    <h4>获取分析结果</h4>
    <p>以 Markdown + JSON 格式接收结构化报告和可执行的洞察。</p>
  </div>
</div>

---

## 精选技能

| 技能 | 概要 | API |
|------|------|-----|
| [FinViz Screener]({{ '/zh/skills/finviz-screener/' | relative_url }}) | 用自然语言构建 FinViz 筛选条件，并在 Chrome 中打开结果 | 无需 |
| [CANSLIM Screener]({{ '/zh/skills/canslim-screener/' | relative_url }}) | 以 William O'Neil 的 CANSLIM 方法对成长股做 7 项评分 | FMP 必需 |
| [VCP Screener]({{ '/zh/skills/vcp-screener/' | relative_url }}) | 自动检测 Minervini 的波动率收缩形态（VCP） | FMP 必需 |
| [Theme Detector]({{ '/zh/skills/theme-detector/' | relative_url }}) | 以三维评分检测跨板块的多空主题 | 可选 |

完整清单请见[技能目录]({{ '/zh/skill-catalog/' | relative_url }})。

---

## 运营工作流

将多个技能组合起来的 Core + Satellite 运营路径，请参阅[工作流]({{ '/zh/workflows/' | relative_url }})。每条工作流按顺序描述所用技能、判断关卡与产物（artifact），并由 `workflows/*.yaml` 中的正本 manifest 自动生成。

[技能集（Skillsets）]({{ '/zh/skillsets/' | relative_url }})是与之配对的“为达成目标该装入哪些技能”一层，是绑定到各工作流、按类别打包的技能束，由 `skillsets/*.yaml` 自动生成。

---

## 新手入门

第一次使用，请先在[新手入门]({{ '/zh/getting-started/' | relative_url }})页面查看安装步骤与 API 密钥的配置方法。
