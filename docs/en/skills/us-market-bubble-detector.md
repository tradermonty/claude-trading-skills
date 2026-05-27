---
layout: default
title: "US Market Bubble Detector"
grand_parent: English
parent: Skill Guides
nav_order: 62
lang_peer: /ja/skills/us-market-bubble-detector/
permalink: /en/skills/us-market-bubble-detector/
---

# US Market Bubble Detector
{: .no_toc }

Evaluates market bubble risk through quantitative data-driven analysis using the revised Minsky/Kindleberger framework v2.1. Prioritizes objective metrics (Put/Call, VIX, margin debt, breadth, IPO data) over subjective impressions. Features strict qualitative adjustment criteria with confirmation bias prevention. Supports practical investment decisions with mandatory data collection and mechanical scoring. Use when user asks about bubble risk, valuation concerns, or profit-taking timing.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/us-market-bubble-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/us-market-bubble-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# US Market Bubble Detection Skill (Revised v2.1)

---

## 2. When to Use

Use this skill when:

**English:**
- User asks "Is the market in a bubble?" or "Are we in a bubble?"
- User seeks advice on profit-taking, new entry timing, or short-selling decisions
- User reports social phenomena (non-investors entering, media frenzy, IPO flood)
- User mentions narratives like "this time is different" or "revolutionary technology" becoming mainstream
- User consults about risk management for existing positions

**Japanese:**
- ユーザーが「今の相場はバブルか?」と尋ねる
- 投資の利確・新規参入・空売りのタイミング判断を求める
- 社会現象(非投資家の参入、メディア過熱、IPO氾濫)を観察し懸念を表明
- 「今回は違う」「革命的技術」などの物語が主流化している状況を報告
- 保有ポジションのリスク管理方法を相談

---

---

## 3. Prerequisites

- User provides indicators
- Python 3.9+ recommended

---

## 4. Quick Start

Invoke this skill by describing your analysis needs to Claude.

---

## 5. Workflow

See the skill's SKILL.md for the complete workflow.

---

## 6. Resources

**References:**

- `skills/us-market-bubble-detector/references/bubble_framework.md`
- `skills/us-market-bubble-detector/references/historical_cases.md`
- `skills/us-market-bubble-detector/references/implementation_guide.md`
- `skills/us-market-bubble-detector/references/quick_reference.md`
- `skills/us-market-bubble-detector/references/quick_reference_en.md`

**Scripts:**

- `skills/us-market-bubble-detector/scripts/bubble_scorer.py`
