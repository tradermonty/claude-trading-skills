---
layout: default
title: "Trade Hypothesis Ideator"
grand_parent: English
parent: Skill Guides
nav_order: 58
lang_peer: /ja/skills/trade-hypothesis-ideator/
permalink: /en/skills/trade-hypothesis-ideator/
---

# Trade Hypothesis Ideator
{: .no_toc }

Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets. Use when you have a structured input bundle and want ranked hypothesis cards with experiment designs, kill criteria, and optional strategy.yaml export compatible with edge-finder-candidate/v1.

{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trade-hypothesis-ideator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-hypothesis-ideator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Trade Hypothesis Ideator

---

## 2. Prerequisites

- Hypothesis generation from journal/data inputs; pure calculation
- Python 3.9+ recommended

---

## 3. Quick Start

1. Receive input JSON bundle.
2. Run pass 1 normalization + evidence extraction.
3. Generate hypotheses with prompts:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md` (inject `{{evidence_summary}}`)
4. Critique hypotheses with `prompts/critique_prompt_template.md`.
5. Run pass 2 ranking + output formatting + guardrails.
6. Optionally export `pursue` hypotheses via Step H strategy exporter.

---

## 4. Workflow

1. Receive input JSON bundle.
2. Run pass 1 normalization + evidence extraction.
3. Generate hypotheses with prompts:
   - `prompts/system_prompt.md`
   - `prompts/developer_prompt_template.md` (inject `{{evidence_summary}}`)
4. Critique hypotheses with `prompts/critique_prompt_template.md`.
5. Run pass 2 ranking + output formatting + guardrails.
6. Optionally export `pursue` hypotheses via Step H strategy exporter.

---

## 5. Resources

**References:**

- `skills/trade-hypothesis-ideator/references/evidence_quality_guide.md`
- `skills/trade-hypothesis-ideator/references/hypothesis_types.md`

**Scripts:**

- `skills/trade-hypothesis-ideator/scripts/run_hypothesis_ideator.py`
