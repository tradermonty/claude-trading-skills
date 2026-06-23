---
layout: default
title: "Trading Skills Navigator"
grand_parent: 简体中文
parent: 技能指南
nav_order: 55
lang_peer: /en/skills/trading-skills-navigator/
permalink: /zh/skills/trading-skills-navigator/
generated: false
---

# Trading Skills Navigator
{: .no_toc }

根据自然语言描述的目标,推荐合适的交易工作流、技能组合、API 配置方案和上手路径。当用户表达了交易或投资目标、需要知道该用哪个技能/工作流、从哪里开始,或是否存在无需付费 API 密钥的方案时,把这个技能作为入口使用——例如“我该从哪开始”“该用哪个技能”“我只想在市场环境有利时做波段”“有哪些不需要 API 密钥就能用”“どれを使えばいい”“API キー無しで使えるものは”。本技能只做路由和解释,绝不会执行交易或自动运行其他技能,并且在尚无对应工作流时会如实告知。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trading-skills-navigator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Trading Skills Navigator 读取本仓库的技能索引(skills-index.yaml)与工作流清单(workflows/*.yaml),把用户用自然语言表达的交易/投资目标,转译为具体的工作流推荐、技能组合、API 配置方案以及上手路径。

---

## 2. 使用时机

- 用户表达了交易/投资目标,并询问该从哪里开始,或该用哪个技能/工作流(“どれを使えばいい”“我该从哪开始”)。
- 用户询问哪些功能**不需要付费 API 密钥**就能用。
- 用户想把无 API 路径和需要 API 的路径分开说明,或想要一条新手路径。
- 用户描述了一种画像(“兼职波段交易者”“股息投资者”“我想做空”“我想回测想法”),需要据此进行路由推荐。

**不要**用本技能来执行交易、下单,或自动运行其他技能。它只负责推荐和解释。

---

## 3. 前提条件

- 读取本地的 skills-index.yaml + workflows/*.yaml(或内置快照);无需联网
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<用户目标的原文>" \
  --format json
  # 可选: --no-api  --time-budget 15m|30m|60m|90m|any
  #       --experience beginner|intermediate|advanced
```

---

## 5. 工作流

### 步骤 1 —— 提取目标与约束条件

从用户的消息中提取:

- 自然语言描述的**目标**(保留原文即可)。
- 可选约束条件:是否仅限**无 API**方案?每日**时间预算**(15分钟/30分钟/60分钟/90分钟)?**经验**水平(初级/中级/高级)?

只有当目标为空或完全无法判断意图时,才最多提出一个简短的澄清问题。否则直接继续——推荐器本身具备优雅降级能力。

### 步骤 2 —— 运行推荐器

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<用户目标的原文>" \
  --format json
  # 可选: --no-api  --time-budget 15m|30m|60m|90m|any
  #       --experience beginner|intermediate|advanced
```

- 在 **Claude Code** 中,脚本会自动读取仓库根目录的权威数据源(`skills-index.yaml` + `workflows/*.yaml`)。
- 在 **Claude Web App** 中没有仓库根目录,脚本会无感回退到内置的 `assets/metadata_snapshot.json`。两种环境下的推荐结果逐字节一致——用户感受不到任何行为差异。

### 步骤 3 —— 用对话方式讲解结果

解析 JSON,并用用户使用的语言进行解释:

- **主要工作流** —— `display_name`、`cadence`(执行频率)、`~estimated_minutes`(预计耗时)、`api_profile`。直接说明它是做什么的、什么时候该运行。
- **次要工作流** —— 如果有,说明它们之间的关系(例如“先做市场环境检查,等它放行风险敞口后再做这个”)。
- **技能组合** —— `skillset.id`(对应 skills-index 中的分类)。注意 `manifest_status: deferred` 表示打包好的技能组合清单是后续阶段才会推出的功能;目前的推荐是基于工作流的。
- **无 API vs 需要 API** —— 如果 `no_api` 为 true,说明该方案不需要付费密钥即可使用。如果某个工作流在 `--no-api` 条件下被排除,展示 `rationale` 中说明是哪个付费集成导致的那一条理由(例如“swing-opportunity-daily 需要 FMP”)。
- **如实告知缺口** —— 如果 `honest_gap` 为 true,说明**目前没有针对该意图发布的工作流**。要直接说明这一点,然后从相关分类中展示 `suggested_skills`,并转达其中的 `note`。绝不能凭空编造工作流。
- 始终读取 `rationale` 数组,并解释*为什么*会给出这个推荐。

### 步骤 4 —— 解释上手路径

阅读 `references/setup_paths.md`,并针对**用户推荐工作流中实际涉及的技能**(即 JSON 中真实的 `required_skills` / `optional_skills`),按照用户所在的环境(Claude Web App 的 `.skill` 上传方式,或 Claude Code 的文件夹复制方式)逐步引导用户完成上手流程。要点出这些技能各自需要哪些付费 API 密钥。

### 步骤 5 —— 指向学习闭环

最后,引导用户关注 `trader-memory-core` 以及 `trade-memory-loop` / `monthly-performance-review` 工作流,确保每一条被推荐的路径都能汇入“计划 → 交易 → 记录 → 复盘 → 改进”的闭环。

---

## 6. 资源

**参考文档(References):**

- `skills/trading-skills-navigator/references/intent_routing.md`
- `skills/trading-skills-navigator/references/setup_paths.md`

**脚本(Scripts):**

- `skills/trading-skills-navigator/scripts/build_snapshot.py`
- `skills/trading-skills-navigator/scripts/recommend.py`
