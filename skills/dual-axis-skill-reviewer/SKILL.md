---
name: dual-axis-skill-reviewer
description: "Review skills in this repository using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. Use when you need reproducible quality scoring for `skills/*/SKILL.md`, want to gate merges with a score threshold (for example 90+), or need concrete improvement items for low-scoring skills."
---

# Dual Axis Skill Reviewer

Run the dual-axis reviewer script in `scripts/run_dual_axis_review.py` and save reports to `reports/`.

The script supports:
- Random or fixed skill selection
- Auto-axis scoring with optional test execution
- LLM prompt generation
- LLM JSON review merge with weighted final score

## Run Auto Axis + Generate LLM Prompt

```bash
python3 skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . \
  --emit-llm-prompt
```

This command:
1. Picks one skill from `skills/*/SKILL.md`
2. Runs rule-based scoring and test verification
3. Writes:
- `reports/skill_review_<skill>_<timestamp>.json`
- `reports/skill_review_<skill>_<timestamp>.md`
- `reports/skill_review_prompt_<skill>_<timestamp>.md` (LLM request prompt)

## Submit LLM Review

Use the generated prompt and request strict JSON output from the LLM.

JSON schema is documented in `references/llm_review_schema.md`.

## Merge Auto + LLM Axes

After saving the LLM JSON file:

```bash
python3 skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . \
  --skill <skill-name> \
  --llm-review-json <path-to-llm-review.json> \
  --auto-weight 0.5 \
  --llm-weight 0.5
```

Adjust weights when needed:
- Increase `--auto-weight` for stricter deterministic gating
- Increase `--llm-weight` when qualitative/code-review depth is prioritized

## Optional Controls

- Fix selection for reproducibility: `--skill <name>` or `--seed <int>`
- Skip tests for quick triage: `--skip-tests`
- Change report location: `--output-dir <dir>`

## Scoring Policy

- Auto axis scores metadata, workflow coverage, execution safety, artifact presence, and test health.
- LLM axis scores deep content quality (correctness, risk, missing logic, maintainability).
- Final score is weighted average.
- If final score is below 90, improvement items are required and listed in the markdown report.

## Reference Usage

- Read `references/llm_review_schema.md` before requesting LLM review.
- Keep LLM output strict JSON to allow deterministic merge.
