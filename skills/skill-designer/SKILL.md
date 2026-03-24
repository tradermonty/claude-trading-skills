---
name: skill-designer
description: "Create a new skill, generate a skill, or build skill scaffolding from a structured idea specification. Use when you need to design a skill, bootstrap a skill template, or the skill auto-generation pipeline needs to produce a Claude CLI prompt that creates a complete skill directory (SKILL.md, references, scripts, tests) following repository conventions."
---

# Skill Designer

## Overview

Generate a comprehensive Claude CLI prompt from a structured skill idea
specification. The prompt instructs Claude to create a complete skill directory
following repository conventions: SKILL.md with YAML frontmatter, reference
documents, helper scripts, and test scaffolding.

## When to Use

- The skill auto-generation pipeline selects an idea from the backlog and needs
  a design prompt for `claude -p`
- A developer wants to bootstrap a new skill from a JSON idea specification
- Quality review of generated skills requires awareness of the scoring rubric

## Prerequisites

- Python 3.9+
- No external API keys required
- Reference files must exist under `skills/skill-designer/references/`

## Workflow

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
- Score meets threshold (>= 70/100) via the dual-axis reviewer:

```bash
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --skill <skill-name> --output-dir reports/
```

If the score is below 70, revise the generated SKILL.md and re-run the reviewer.

## Output Format

The script outputs a plain-text prompt to stdout. Exit code 0 on success,
1 if required reference files are missing.

## Resources

- `references/skill-structure-guide.md` -- Directory structure, SKILL.md format, naming conventions
- `references/quality-checklist.md` -- Dual-axis reviewer 5-category checklist (100 points)
- `references/skill-template.md` -- SKILL.md template with YAML frontmatter and standard sections
- `scripts/build_design_prompt.py` -- Prompt builder script (CLI interface)
