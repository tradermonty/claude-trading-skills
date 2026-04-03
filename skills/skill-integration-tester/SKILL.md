---
name: skill-integration-tester
description: Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. Use when adding new workflows, modifying skill outputs, or verifying pipeline health before release.
requires_api_key: false
---

# Skill Integration Tester

## Overview

Validate multi-skill workflows defined in CLAUDE.md (Daily Market Monitoring,
Weekly Strategy Review, Earnings Momentum Trading, etc.) by executing each step
in sequence. Check inter-skill data contracts for JSON schema compatibility
between output of step N and input of step N+1, verify file naming conventions,
and report broken handoffs. Supports dry-run mode with synthetic fixtures.

## When to Use

- After adding or modifying a multi-skill workflow in CLAUDE.md
- After changing a skill's output format (JSON schema, file naming)
- Before releasing new skills to verify pipeline compatibility
- When debugging broken handoffs between consecutive workflow steps
- As a CI pre-check for pull requests touching skill scripts

## Prerequisites

- Python 3.9+
- No API keys required
- No third-party Python packages required (uses only standard library)

## Workflow

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

## Output Format

### JSON Report

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-03-01T12:00:00+00:00",
  "dry_run": false,
  "summary": {
    "total_workflows": 8,
    "valid": 6,
    "broken": 1,
    "warnings": 1
  },
  "workflows": [
    {
      "workflow": "Daily Market Monitoring",
      "step_count": 4,
      "status": "valid",
      "steps": [...],
      "handoffs": [...],
      "naming_violations": []
    }
  ]
}
```

### Markdown Report

Structured report with per-workflow sections showing step validation,
handoff status, and naming violations.

Reports are saved to `reports/` with filenames
`integration_test_YYYY-MM-DD_HHMMSS.{json,md}`.

## Resources

- `scripts/validate_workflows.py` -- Main validation script
- `references/workflow_contracts.md` -- Contract definitions and handoff patterns

## Key Principles

1. No API keys required -- all validation is local and offline
2. Non-destructive -- reads SKILL.md and CLAUDE.md only, never modifies skills
3. Deterministic -- same inputs always produce same validation results
