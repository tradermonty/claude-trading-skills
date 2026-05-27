---
layout: default
title: "Skill Designer"
grand_parent: English
parent: Skill Guides
nav_order: 51
lang_peer: /ja/skills/skill-designer/
permalink: /en/skills/skill-designer/
---

# Skill Designer
{: .no_toc }

Design new Claude skills from structured idea specifications. Use when the skill auto-generation pipeline needs to produce a Claude CLI prompt that creates a complete skill directory (SKILL.md, references, scripts, tests) following repository conventions.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/skill-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/skill-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Generate a comprehensive Claude CLI prompt from a structured skill idea
specification. The prompt instructs Claude to create a complete skill directory
following repository conventions: SKILL.md with YAML frontmatter, reference
documents, helper scripts, and test scaffolding.

---

## 2. When to Use

- The skill auto-generation pipeline selects an idea from the backlog and needs
  a design prompt for `claude -p`
- A developer wants to bootstrap a new skill from a JSON idea specification
- Quality review of generated skills requires awareness of the scoring rubric

---

## 3. Prerequisites

- Python 3.9+
- No external API keys required
- Reference files must exist under `references/`

---

## 4. Quick Start

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root .
```

---

## 5. Workflow

### Step 1: Prepare Idea Specification

Accept a JSON file (`--idea-json`) containing:
- `title`: Human-readable idea name
- `description`: What the skill does
- `category`: Skill category (e.g., trading-analysis, developer-tooling)

Accept a normalized skill name (`--skill-name`) that will be used as the
directory name and YAML frontmatter `name:` field.

### Step 2: Build Design Prompt

Run the prompt builder:

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root .
```

The script:
1. Loads the idea JSON
2. Reads all three reference files (structure guide, quality checklist, template)
3. Lists existing skills (up to 20) to prevent duplication
4. Outputs a complete prompt to stdout

### Step 3: Feed Prompt to Claude CLI

The calling pipeline pipes the prompt into `claude -p`:

```bash
python3 skills/skill-designer/scripts/build_design_prompt.py \
  --idea-json /tmp/idea.json \
  --skill-name "my-new-skill" \
  --project-root . \
| claude -p --allowedTools Read,Edit,Write,Glob,Grep
```

### Step 4: Validate Output

After Claude creates the skill, verify:
- `skills/<skill-name>/SKILL.md` exists with correct frontmatter
- Directory structure follows conventions
- Score with dual-axis-skill-reviewer meets threshold

---

## 6. Resources

**References:**

- `skills/skill-designer/references/quality-checklist.md`
- `skills/skill-designer/references/skill-structure-guide.md`
- `skills/skill-designer/references/skill-template.md`

**Scripts:**

- `skills/skill-designer/scripts/build_design_prompt.py`
