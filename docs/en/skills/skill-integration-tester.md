---
layout: default
title: "Skill Integration Tester"
grand_parent: English
parent: Skill Guides
nav_order: 53
lang_peer: /ja/skills/skill-integration-tester/
permalink: /en/skills/skill-integration-tester/
---

# Skill Integration Tester
{: .no_toc }

Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. Use when adding new workflows, modifying skill outputs, or verifying pipeline health before release.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/skill-integration-tester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/skill-integration-tester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Validate multi-skill workflows defined in CLAUDE.md (Daily Market Monitoring,
Weekly Strategy Review, Earnings Momentum Trading, etc.) by executing each step
in sequence. Check inter-skill data contracts for JSON schema compatibility
between output of step N and input of step N+1, verify file naming conventions,
and report broken handoffs. Supports dry-run mode with synthetic fixtures.

---

## 2. When to Use

- After adding or modifying a multi-skill workflow in CLAUDE.md
- After changing a skill's output format (JSON schema, file naming)
- Before releasing new skills to verify pipeline compatibility
- When debugging broken handoffs between consecutive workflow steps
- As a CI pre-check for pull requests touching skill scripts

---

## 3. Prerequisites

- Python 3.9+
- No API keys required
- No third-party Python packages required (uses only standard library)

---

## 4. Quick Start

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Run Integration Validation

Execute the validation script against the project's CLAUDE.md:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --output-dir reports/
```

This parses all `**Workflow Name:**` blocks from the Multi-Skill Workflows
section, resolves each step's display name to a skill directory, and validates
existence, contracts, and naming.

### Step 2: Validate a Specific Workflow

Target a single workflow by name substring:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --workflow "Earnings Momentum" \
  --output-dir reports/
```

### Step 3: Dry-Run with Synthetic Fixtures

Create synthetic fixture JSON files for each skill's expected output and
validate contract compatibility without real data:

```bash
python3 skills/skill-integration-tester/scripts/validate_workflows.py \
  --dry-run \
  --output-dir reports/
```

Fixture files are written to `reports/fixtures/` with `_fixture` flag set.

### Step 4: Review Results

Open the generated Markdown report for a human-readable summary, or parse
the JSON report for programmatic consumption. Each workflow shows:
- Step-by-step skill existence checks
- Handoff contract validation (PASS / FAIL / N/A)
- File naming convention violations
- Overall workflow status (valid / broken / warning)

### Step 5: Fix Broken Handoffs

For each `FAIL` handoff, verify that:
1. The producer skill's output contains all required fields
2. The consumer skill's input parameter accepts the producer's output format
3. File naming patterns are consistent between producer output and consumer input

---

## 6. Resources

**References:**

- `skills/skill-integration-tester/references/workflow_contracts.md`

**Scripts:**

- `skills/skill-integration-tester/scripts/validate_workflows.py`
