---
layout: default
title: "Edge Strategy Reviewer"
grand_parent: English
parent: Skill Guides
nav_order: 28
lang_peer: /ja/skills/edge-strategy-reviewer/
permalink: /en/skills/edge-strategy-reviewer/
---

# Edge Strategy Reviewer
{: .no_toc }

Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size adequacy, and execution realism. Use when strategy_drafts/*.yaml exists and needs quality gate before pipeline export. Outputs PASS/REVISE/REJECT verdicts with confidence scores.

{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-strategy-reviewer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-strategy-reviewer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Edge Strategy Reviewer

---

## 2. When to Use

- After `edge-strategy-designer` generates `strategy_drafts/*.yaml`
- Before exporting drafts to `edge-candidate-agent` via the pipeline
- When manually validating a draft strategy for edge plausibility

---

## 3. Prerequisites

- Strategy draft YAML files (output of `edge-strategy-designer`)
- Python 3.10+ with PyYAML

---

## 4. Quick Start

```bash
# Review all drafts in a directory
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/

# Single draft review with JSON output and markdown summary
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --draft reports/edge_strategy_drafts/draft_xxx.yaml \
  --output-dir reports/ --format json --markdown-summary
```

---

## 5. Workflow

1. Load draft YAML files from `--drafts-dir` or a single `--draft` file
2. Evaluate each draft against 8 criteria (C1-C8) with weighted scoring
3. Compute confidence score (weighted average of all criteria)
4. Determine verdict: PASS / REVISE / REJECT
5. Assess export eligibility (PASS + export_ready_v1 + exportable family)
6. Write review output (YAML or JSON) and optional markdown summary

---

## 6. Resources

**References:**

- `skills/edge-strategy-reviewer/references/overfitting_checklist.md`
- `skills/edge-strategy-reviewer/references/review_criteria.md`

**Scripts:**

- `skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py`
