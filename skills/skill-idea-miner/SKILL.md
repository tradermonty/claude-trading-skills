---
name: skill-idea-miner
description: "Mine Claude Code session logs for skill idea candidates. Use when running the weekly skill generation pipeline, analyzing coding sessions for patterns, reviewing session history, or discovering new skill opportunities to extract, score, and backlog ideas from recent sessions."
---

# Skill Idea Miner

Extract skill idea candidates from Claude Code session logs,
score them for novelty, feasibility, and trading value, and maintain a
prioritized backlog for downstream skill generation.

## When to Use

- Weekly automated pipeline run (Saturday 06:00 via launchd)
- Manual backlog refresh
- Dry-run to preview candidates without LLM scoring

## Workflow

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
6. Invoke Claude CLI headless for idea abstraction:
   ```bash
   claude -p "Extract skill ideas from these session signals..." \
     --output-format json --max-turns 1 --budget $1.00
   ```
7. Output `raw_candidates.yaml`

**Run Stage 1:**

```bash
# Full mining run (past 7 days, all allowlist projects)
python3 scripts/mine_session_logs.py --output-dir reports

# Single project, custom lookback
python3 scripts/mine_session_logs.py --project claude-trading-skills --lookback-days 14

# Preview candidates without LLM abstraction
python3 scripts/mine_session_logs.py --dry-run
```

**Validate:** Confirm `raw_candidates.yaml` exists and contains at least one candidate before proceeding to Stage 2.

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
4. Merge scored candidates into backlog

**Run Stage 2:**

```bash
# Score candidates against existing skills
python3 scripts/score_ideas.py --candidates reports/skill-idea-miner/raw_candidates.yaml \
  --project-root . --backlog reports/skill-idea-miner/idea_backlog.yaml

# Preview scoring without LLM (zero scores)
python3 scripts/score_ideas.py --dry-run
```

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

## Resources

- `references/idea_extraction_rubric.md` — Signal detection criteria and scoring rubric
- `scripts/mine_session_logs.py` — Session log parser
- `scripts/score_ideas.py` — Scorer and deduplicator
