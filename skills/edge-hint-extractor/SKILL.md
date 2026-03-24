---
name: edge-hint-extractor
description: "Extract trading signals and edge hints from daily market observations, anomalies, and news reactions into a canonical hints.yaml file. Use when analyzing market news for investment ideas, generating trading signals from daily observations, or preparing structured hint input for downstream concept synthesis and auto detection. Supports rule-based extraction and optional LLM-augmented ideation."
---

# Edge Hint Extractor

## Overview

Convert raw observation signals (`market_summary`, `anomalies`, `news reactions`) into structured edge hints.
This skill is the first stage in the split workflow: `observe -> abstract -> design -> pipeline`.

## When to Use

- You want to turn daily market observations into reusable hint objects.
- You want LLM-generated ideas constrained by current anomalies/news context.
- You need a clean `hints.yaml` input for concept synthesis or auto detection.

## Prerequisites

- Python 3.9+
- `PyYAML`
- Optional inputs from detector run:
  - `market_summary.json`
  - `anomalies.json`
  - `news_reactions.csv` or `news_reactions.json`

## Output

- `hints.yaml` containing:
  - `hints` list
  - generation metadata
  - rule/LLM hint counts

## Workflow

1. Gather observation files (`market_summary`, `anomalies`, optional news reactions).
2. Run `scripts/build_hints.py` to generate deterministic hints.
3. Optionally augment hints with LLM ideas via one of two methods:
   - a. `--llm-ideas-cmd` — pipe data to an external LLM CLI (subprocess).
   - b. `--llm-ideas-file PATH` — load pre-written hints from a YAML file (for Claude Code workflows where Claude generates hints itself).
4. Validate the output file exists and contains well-formed YAML:
   ```bash
   python3 -c "import yaml; d=yaml.safe_load(open('reports/edge_hint_extractor/hints.yaml')); assert 'hints' in d, 'missing hints key'"
   ```
5. Pass `hints.yaml` into concept synthesis or auto detection.

Note: `--llm-ideas-cmd` and `--llm-ideas-file` are mutually exclusive.

## Error Handling

- **Missing input files**: The script exits with an error if `--market-summary` or `--anomalies` files are not found. Run the upstream detector first to generate them.
- **Malformed input**: If JSON/CSV inputs are corrupted, the script raises a parse error. Verify input files with `python3 -m json.tool <file>` before running.
- **LLM command failures**: If `--llm-ideas-cmd` fails, the script falls back to rule-based hints only and logs a warning. Check the external CLI path and permissions.

## Quick Commands

Rule-based only (default output to `reports/edge_hint_extractor/hints.yaml`):

```bash
python3 skills/edge-hint-extractor/scripts/build_hints.py \
  --market-summary /tmp/edge-auto/market_summary.json \
  --anomalies /tmp/edge-auto/anomalies.json \
  --news-reactions /tmp/news_reactions.csv \
  --as-of 2026-02-20 \
  --output-dir reports/
```

Rule + LLM augmentation (external CLI):

```bash
python3 skills/edge-hint-extractor/scripts/build_hints.py \
  --market-summary /tmp/edge-auto/market_summary.json \
  --anomalies /tmp/edge-auto/anomalies.json \
  --llm-ideas-cmd "python3 /path/to/llm_ideas_cli.py" \
  --output-dir reports/
```

Rule + LLM augmentation (pre-written file, for Claude Code):

```bash
python3 skills/edge-hint-extractor/scripts/build_hints.py \
  --market-summary /tmp/edge-auto/market_summary.json \
  --anomalies /tmp/edge-auto/anomalies.json \
  --llm-ideas-file /tmp/llm_hints.yaml \
  --output-dir reports/
```

## Resources

- `skills/edge-hint-extractor/scripts/build_hints.py`
- `references/hints_schema.md`
