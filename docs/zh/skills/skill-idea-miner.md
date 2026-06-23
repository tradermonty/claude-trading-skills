---
layout: default
title: "Skill Idea Miner"
grand_parent: 简体中文
parent: 技能指南
nav_order: 46
lang_peer: /en/skills/skill-idea-miner/
permalink: /zh/skills/skill-idea-miner/
generated: false
---

# Skill Idea Miner
{: .no_toc }

挖掘 Claude Code 会话日志,提取技能创意候选项。当运行每周技能生成流水线、需要从近期编码会话中提取、评分并将新技能创意加入待办列表(backlog)时使用。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/skill-idea-miner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/skill-idea-miner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

Skill Idea Miner

---

## 2. 使用时机

- 每周自动化流水线运行(周六 06:00,通过 launchd 触发)
- 手动刷新待办列表:`python3 scripts/run_skill_generation_pipeline.py --mode weekly`
- 试运行(dry-run),在不进行 LLM 评分的情况下预览候选项

---

## 3. 前提条件

- **API 密钥:** 无需
- 推荐 **Python 3.9+**

---

## 4. 快速开始

### 阶段 1:会话日志挖掘

1. 枚举 `~/.claude/projects/` 中白名单项目的会话日志
2. 按文件修改时间(mtime)筛选最近 7 天的记录,并通过 `timestamp` 字段进行确认
3. 提取用户消息(`type: "user"`、`userType: "external"`)
4. 从助手消息中提取工具使用模式
5. 运行确定性信号检测:
   - 技能使用频率(`skills/*/` 路径引用)
   - 错误模式(非零退出码、`is_error` 标记、异常关键词)
   - 重复的工具调用序列(3 个以上工具重复出现 3 次以上)

---

## 5. 工作流

### 阶段 1:会话日志挖掘

1. 枚举 `~/.claude/projects/` 中白名单项目的会话日志
2. 按文件修改时间(mtime)筛选最近 7 天的记录,并通过 `timestamp` 字段进行确认
3. 提取用户消息(`type: "user"`、`userType: "external"`)
4. 从助手消息中提取工具使用模式
5. 运行确定性信号检测:
   - 技能使用频率(`skills/*/` 路径引用)
   - 错误模式(非零退出码、`is_error` 标记、异常关键词)
   - 重复的工具调用序列(3 个以上工具重复出现 3 次以上)
   - 自动化请求关键词(英文和日文)
   - 未解决的请求(用户消息后出现 5 分钟以上的空白间隔)
6. 调用 Claude CLI(无头模式)进行创意抽象提炼
7. 输出 `raw_candidates.yaml`

### 阶段 2:评分与去重

1. 从 `skills/*/SKILL.md` 的 frontmatter 加载现有技能列表
2. 通过 Jaccard 相似度(阈值 > 0.5)进行去重,对比对象包括:
   - 现有技能的名称和描述
   - 现有待办列表中的创意
3. 使用 Claude CLI 对非重复候选项进行评分:
   - 新颖性(Novelty,0-100):与现有技能的差异化程度
   - 可行性(Feasibility,0-100):技术上的可实现程度
   - 交易价值(Trading Value,0-100):对投资者/交易者的实际价值
   - 综合得分 = 0.3 × 新颖性 + 0.3 × 可行性 + 0.4 × 交易价值
4. 将评分后的候选项合并写入 `logs/.skill_generation_backlog.yaml`

---

## 6. 资源

**参考文档(References):**

- `skills/skill-idea-miner/references/idea_extraction_rubric.md`

**脚本(Scripts):**

- `skills/skill-idea-miner/scripts/__init__.py`
- `skills/skill-idea-miner/scripts/mine_session_logs.py`
- `skills/skill-idea-miner/scripts/score_ideas.py`
