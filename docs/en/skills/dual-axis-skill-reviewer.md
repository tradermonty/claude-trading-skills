---
layout: default
title: "Dual Axis Skill Reviewer"
grand_parent: English
parent: Skill Guides
nav_order: 18
lang_peer: /ja/skills/dual-axis-skill-reviewer/
permalink: /en/skills/dual-axis-skill-reviewer/
---

# Dual Axis Skill Reviewer
{: .no_toc }

Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. Use when you need reproducible quality scoring for `skills/*/SKILL.md`, want to gate merges with a score threshold (for example 90+), or need concrete improvement items for low-scoring skills. Works across projects via --project-root.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/dual-axis-skill-reviewer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/dual-axis-skill-reviewer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Dual Axis Skill Reviewer

---

## 2. When to Use

- Need reproducible scoring for one skill in `skills/*/SKILL.md`.
- Need improvement items when final score is below 90.
- Need both deterministic checks and qualitative LLM code/content review.
- Need to review skills in a **different project** from the command line.

---

## 3. Prerequisites

- Python 3.9+
- `uv` (recommended — auto-resolves `pyyaml` dependency via inline metadata)
- For tests: `uv sync --extra dev` or equivalent in the target project
- For LLM-axis merge: JSON file that follows the LLM review schema (see Resources)

---

## 4. Quick Start

```bash
# If reviewing from the same project:
REVIEWER=skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py

# If reviewing another project (global install):
REVIEWER=~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py
```

---

## 5. Workflow

Determine the correct script path based on your context:

- **Same project**: `skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`
- **Global install**: `~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`

The examples below use `REVIEWER` as a placeholder. Set it once:

```bash
# If reviewing from the same project:
REVIEWER=skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py

# If reviewing another project (global install):
REVIEWER=~/.claude/skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py
```

### Step 1: Run Auto Axis + Generate LLM Prompt

```bash
uv run "$REVIEWER" \
  --project-root . \
  --emit-llm-prompt \
  --output-dir reports/
```

When reviewing a different project, point `--project-root` to it:

```bash
uv run "$REVIEWER" \
  --project-root /path/to/other/project \
  --emit-llm-prompt \
  --output-dir reports/
```

### Step 2: Run LLM Review
- Use the generated prompt file in `reports/skill_review_prompt_<skill>_<timestamp>.md`.
- Ask the LLM to return strict JSON output.
- When running inside Claude Code, let Claude act as orchestrator: read the generated prompt, produce the LLM review JSON, and save it for the merge step.

### Step 3: Merge Auto + LLM Axes

```bash
uv run "$REVIEWER" \
  --project-root . \
  --skill <skill-name> \
  --llm-review-json <path-to-llm-review.json> \
  --auto-weight 0.5 \
  --llm-weight 0.5 \
  --output-dir reports/
```

### Step 4: Optional Controls

- Fix selection for reproducibility: `--skill <name>` or `--seed <int>`
- Review all skills at once: `--all`
- Skip tests for quick triage: `--skip-tests`
- Change report location: `--output-dir <dir>`
- Increase `--auto-weight` for stricter deterministic gating.
- Increase `--llm-weight` when qualitative/code-review depth is prioritized.

---

## 6. Resources

**References:**

- `skills/dual-axis-skill-reviewer/references/llm_review_schema.md`
- `skills/dual-axis-skill-reviewer/references/scoring_rubric.md`

**Scripts:**

- `skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py`
