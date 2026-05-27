---
name: skill-idea-miner
description: Mine Claude Code session logs for skill idea candidates. Use when running the weekly skill generation pipeline to extract, score, and backlog new skill ideas from recent coding sessions.
---

# Skill Idea Miner

Automatically extract skill idea candidates from Claude Code session logs,
score them for novelty, feasibility, and trading value, and maintain a
prioritized backlog for downstream skill generation.

## When to Use

- Weekly automated pipeline run (Saturday 06:00 via launchd)
- Manual backlog refresh: `python3 scripts/run_skill_generation_pipeline.py --mode weekly`
- Dry-run to preview candidates without LLM scoring

## Prerequisites

- **Python 3.10+** with `pyyaml` package
- **Claude CLI** installed and authenticated (`claude --version` to verify)
- **Session logs** in `~/.claude/projects/<project>/` (created automatically by Claude Code)
- No API keys required (uses Claude CLI for LLM calls)

## Workflow

### Quick Start

```bash
# Dry-run: preview mined candidates without LLM scoring
python3 scripts/mine_session_logs.py --dry-run --output-dir reports/

# Full mining with scoring (requires Claude CLI)
python3 scripts/mine_session_logs.py --output-dir reports/

# Score existing candidates
python3 scripts/score_ideas.py \
  --candidates reports/raw_candidates.yaml \
  --output-dir logs/
```

### Stage 1: Session Log Mining

1. Enumerate session logs from allowlist projects in `~/.claude/projects/`
2. Filter to past 7 days by file mtime, confirm with `timestamp` field
3. Extract user messages (`type: "user"`, `userType: "external"`)
4. Extract tool usage patterns from assistant messages
5. Run deterministic signal detection:
   - Skill usage frequency (`skills/*/` path references)
   - Error patterns (non-zero exit codes, `is_error` flags, exception keywords)
   - Repetitive tool sequences (3+ tools repeated 3+ times)
   - Automation request keywords (English and Japanese)
   - Unresolved requests (5+ minute gap after user message)
6. Invoke Claude CLI headless for idea abstraction
7. Output `raw_candidates.yaml`

### Stage 2: Scoring and Deduplication

1. Load existing skills from `skills/*/SKILL.md` frontmatter
2. Deduplicate via Jaccard similarity (threshold > 0.5) against:
   - Existing skill names and descriptions
   - Existing backlog ideas
3. Score non-duplicate candidates with Claude CLI:
   - Novelty (0-100): differentiation from existing skills
   - Feasibility (0-100): technical implementability
   - Trading Value (0-100): practical value for investors/traders
   - Composite = 0.3 * Novelty + 0.3 * Feasibility + 0.4 * Trading Value
4. Merge scored candidates into `logs/.skill_generation_backlog.yaml`

## Output Format

### raw_candidates.yaml

```yaml
generated_at_utc: "2026-03-08T06:00:00Z"
period: {from: "2026-03-01", to: "2026-03-07"}
projects_scanned: ["claude-trading-skills"]
sessions_scanned: 12
candidates:
  - id: "raw_2026w10_001"
    title: "Earnings Whispers Image Parser"
    source_project: "claude-trading-skills"
    evidence:
      user_requests: ["Extract earnings dates from screenshot"]
      pain_points: ["Manual image reading"]
      frequency: 3
    raw_description: "Parse Earnings Whispers screenshots to extract dates."
    category: "data-extraction"
```

### Backlog (logs/.skill_generation_backlog.yaml)

```yaml
updated_at_utc: "2026-03-08T06:15:00Z"
ideas:
  - id: "idea_2026w10_001"
    title: "Earnings Whispers Image Parser"
    description: "Skill that parses Earnings Whispers screenshots..."
    category: "data-extraction"
    scores: {novelty: 75, feasibility: 60, trading_value: 80, composite: 73}
    status: "pending"
```

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `strategy_review` | `StrategyReview` | Multi-criterion scoring with PASS/REVISE/REJECT verdict |

Schema: `schemas/json/strategy_review.json`

## Resources

- `references/idea_extraction_rubric.md` — Signal detection criteria and scoring rubric
- `scripts/mine_session_logs.py` — Session log parser
- `scripts/score_ideas.py` — Scorer and deduplicator
