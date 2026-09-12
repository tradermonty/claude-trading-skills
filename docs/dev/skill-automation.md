# Skill Automation Quickstart

This GitHub-facing maintainer guide describes the two repository automation
pipelines that were previously documented in the main README. It is not part
of the beginner trading workflow or the documentation-site navigation.

- [Back to README](../../README.md)
- [日本語版](skill-automation.ja.md)
- [Maintenance runbook](maintenance-runbook.md)
- [Self-improvement implementation details](../../CLAUDE.md#skill-self-improvement-loop)
- [Generation implementation details](../../CLAUDE.md#skill-auto-generation-pipeline)

Run every command below from the repository root. For environment setup,
drift gates, recovery procedures, and scheduled-job troubleshooting, use the
[maintenance runbook](maintenance-runbook.md).

The `run_skill_improvement.sh` and `run_skill_generation.sh` entry points are
guarded macOS `launchd` wrappers. On Linux or Windows, invoke the Python
orchestrators shown under **Manual Execution**. Run the improvement orchestrator
only in an already-isolated, clean checkout; the direct Python command does not
create or reset the dedicated checkout managed by the macOS wrapper. See the
[platform support matrix](platform-support.md).

## Safety and side effects

`--dry-run` suppresses branch and PR creation, but it is **not** a read-only
filesystem mode. The current implementations have these boundaries:

| Mode | Reads | Local writes | Claude CLI | Git / GitHub writes |
| --- | --- | --- | --- | --- |
| Self-improvement dry-run | Skills, repository metadata, existing state | Lock and log files, auto-review artifacts, daily summary, `.skill_improvement_state.json` | None | None |
| Self-improvement normal | Skills, repository metadata, existing state | Review artifacts, logs, summaries, state, and possibly the selected skill | Reviews the selected skill on every normal run when Claude CLI is available; edits it only when the auto score is below threshold | Runs `git pull --ff-only`; may create a branch, commit, push, and PR; deletes local automation branches whose PR is merged or closed |
| Generation daily dry-run | Existing idea backlog | Lock and log files, daily summary, `.skill_generation_state.json` | None | None; backlog status is not changed |
| Generation weekly dry-run | Allowlisted session logs under `~/.claude/projects/` | `raw_candidates.yaml`, lock and log files, weekly summary, `.skill_generation_state.json` | None | None; backlog is not updated |
| Generation weekly normal | Allowlisted session logs and existing backlog | Raw candidates, backlog, logs, summary, and state | Session-derived signals and length-limited user-message samples may be sent to the abstraction prompt. The resulting candidate descriptions are then sent to the scoring prompt; raw session-log files are not sent directly. | None |
| Generation daily normal | Existing idea backlog and repository files | `skills/<name>/`, generated EN/JA skill docs and indexes/catalogs, `pyproject.toml` when needed, reports, backlog, logs, summary, and state | Designs and reviews a selected skill | Runs `git pull --ff-only`; may delete a same-name stale local branch, then create a branch, commit, push, and PR; deletes local automation branches whose PR is merged or closed |

This table describes the Python orchestrators when invoked directly. The
self-improvement `launchd` wrapper manages a dedicated checkout and runs
`fetch`, `checkout -B main origin/main`, `reset --hard origin/main`, and
`clean -fd`; see [The improvement loop runs in its own checkout](maintenance-runbook.md#the-improvement-loop-runs-in-its-own-checkout)
before enabling it.

Generation daily normal does not create or update
`skill-packages/<name>.skill`. Package the skill separately after review:

```bash
python3 scripts/package_skills.py --skill <name>
```

Review the inputs before a normal weekly mining run. Although its source files
are local, its abstraction and scoring stages are not local-only when they
invoke `claude -p`.

## Skill Self-Improvement Loop

This section is contributor-oriented. New users can skip it and start with the
Core + Satellite path in the README.

An automated pipeline continuously reviews and improves skill quality. A daily
`launchd` job picks one skill, scores it with the dual-axis reviewer, and, if
the score is below 90/100, invokes `claude -p` to apply improvements and open a
PR.

### How It Works

1. **Round-robin selection** — cycles through all skills (excluding the reviewer itself), persisted in `logs/.skill_improvement_state.json`.
2. **Auto scoring** — runs `run_dual_axis_review.py` to get a deterministic score (0-100).
3. **Improvement gate** — if `auto_review.score < 90`, Claude CLI applies fixes to SKILL.md and references.
4. **Quality gate** — re-scores after improvement (with tests enabled); rolls back if the score did not improve.
5. **PR creation** — commits changes to a feature branch and opens a GitHub PR for human review.
6. **Daily summary** — writes results to `reports/skill-improvement-log/YYYY-MM-DD_summary.md`.

### Manual Execution

```bash
# Dry-run: score one skill without applying improvements or creating PRs
python3 scripts/run_skill_improvement_loop.py --dry-run

# Full run: score, improve if needed, and open PR
python3 scripts/run_skill_improvement_loop.py
```

The previous README also showed the following command:

```bash
python3 scripts/run_skill_improvement_loop.py --dry-run --all
```

The current orchestration CLI does not accept `--all`. To review all skills
without applying improvements, run the reviewer directly:

```bash
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --all --output-dir reports/
```

### launchd Setup (macOS)

The loop runs daily at 05:00 local time via macOS `launchd`:

```bash
# Install the agent
cp launchd/com.trade-analysis.skill-improvement.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-improvement.plist

# Verify
launchctl list | grep skill-improvement

# Manual trigger
launchctl start com.trade-analysis.skill-improvement
```

### Key Files

| File | Purpose |
| --- | --- |
| `scripts/run_skill_improvement_loop.py` | Orchestration script (selection, scoring, improvement, PR) |
| `scripts/run_skill_improvement.sh` | macOS-only guarded shell wrapper for launchd |
| `launchd/com.trade-analysis.skill-improvement.plist` | macOS launchd agent configuration |
| `skills/dual-axis-skill-reviewer/` | Reviewer skill (scoring engine) |
| `logs/.skill_improvement_state.json` | Round-robin state and history |
| `reports/skill-improvement-log/` | Daily summary reports |

## Skill Auto-Generation Pipeline

This section is contributor-oriented. It describes repository maintenance
automation, not a required trading workflow.

An automated pipeline mines session logs for skill ideas (weekly) and designs,
reviews, and creates new skills as PRs (daily). It works alongside the
Self-Improvement Loop to continuously expand the skill catalog.

### How It Works

1. **Weekly mining** — scans Claude Code session logs for recurring patterns that could become skills, then scores each idea for novelty, feasibility, and trading value.
2. **Backlog scoring** — stores ranked ideas in `logs/.skill_generation_backlog.yaml` with status tracking (`pending`, `in_progress`, `completed`, `design_failed`, `review_failed`, `pr_failed`).
3. **Daily selection** — picks the highest-scoring `pending` idea; retries `design_failed` / `pr_failed` once (`review_failed` is terminal).
4. **Design & review** — the Skill Designer builds a complete skill (SKILL.md, references, scripts), then the Dual-Axis Reviewer scores it. If the score is too low, the idea is marked `review_failed`.
5. **PR creation** — commits the new skill to a feature branch and opens a GitHub PR for human review.

### Manual Execution

```bash
# Weekly: mine ideas from session logs and score them
python3 scripts/run_skill_generation_pipeline.py --mode weekly --dry-run

# Daily: design a skill from the highest-scoring backlog idea
python3 scripts/run_skill_generation_pipeline.py --mode daily --dry-run

# Full daily run (creates branch, designs skill, opens PR)
python3 scripts/run_skill_generation_pipeline.py --mode daily
```

### launchd Setup (macOS)

Two `launchd` agents handle the weekly and daily schedules:

```bash
# Install both agents
cp launchd/com.trade-analysis.skill-generation-weekly.plist ~/Library/LaunchAgents/
cp launchd/com.trade-analysis.skill-generation-daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-weekly.plist
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-daily.plist

# Verify
launchctl list | grep skill-generation

# Manual trigger
launchctl start com.trade-analysis.skill-generation-weekly
launchctl start com.trade-analysis.skill-generation-daily
```

### Key Files

| File | Purpose |
| --- | --- |
| `scripts/run_skill_generation_pipeline.py` | Orchestration script (mining, selection, design, review, PR) |
| `scripts/run_skill_generation.sh` | macOS-only guarded shell wrapper for launchd |
| `launchd/com.trade-analysis.skill-generation-weekly.plist` | Weekly mining schedule (Saturday 06:00) |
| `launchd/com.trade-analysis.skill-generation-daily.plist` | Daily generation schedule (07:00) |
| `skills/skill-idea-miner/` | Mining and scoring skill |
| `skills/skill-designer/` | Skill design prompt builder |
| `logs/.skill_generation_backlog.yaml` | Scored idea backlog with status tracking |
| `logs/.skill_generation_state.json` | Run history and state |
| `reports/skill-generation-log/` | Daily generation summary reports |
