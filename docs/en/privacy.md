---
layout: default
title: Privacy and data handling
parent: English
nav_order: 15
lang_peer: /ja/privacy/
permalink: /en/privacy/
---

# Privacy and data handling

This is the operational policy for repository workflows, not a promise that all
inputs stay on your computer. Review the selected skill, tool permissions and
provider terms before using personal trading data. Keep account identifiers,
holdings, tax records, API keys and unredacted conversations out of public
examples, Issues, PRs and model prompts unless the disclosure is intentional.
Use fictional examples, remove direct identifiers and review derived text too.
Truncation is not anonymization. There is no general automatic PII redactor.
Before sharing reports, logs or postmortems, replace names, account numbers, order
IDs and broker identifiers with fictional labels; remove free-text identifiers
and check filenames and metadata too. Share only the fields needed for review.

## Local storage and Git boundaries

| Location | Likely contents | Handling |
| --- | --- | --- |
| `state/theses`, `state/journal` | Thesis rationale, positions, decisions, trade outcomes | Private; back up before changes |
| `reports/`, `reviews/` | Portfolio analysis, generated reports and review findings | Private by default; inspect before sharing |
| `logs/`, `.cache/`, `.staging/` | Diagnostics, provider responses, automation state and intermediate output | May contain sensitive payloads or error excerpts |
| `.env`, `.env.*`, `.envrc*`, `.mcp.json*`, `.aws/`, `.ssh/` | Credentials and local service configuration | OS access controls; never publish |
| `.claude/`, `~/.claude/projects/` | Local agent configuration and session transcripts | Session transcripts can contain user/tool data; see mining below |
| `private-backups/` | Recovery copies and hash manifests | Restrict OS access; encrypt off-device copies |

The root [`.gitignore`](https://github.com/tradermonty/claude-trading-skills/blob/main/.gitignore)
excludes these repository-local canonical locations. The active-index guard
[`check_private_data_paths.py`](https://github.com/tradermonty/claude-trading-skills/blob/main/scripts/check_private_data_paths.py)
rejects root `state`, `reports`, `logs`, `reviews`, `.cache`, `.claude`, `.staging`,
`private-backups`, `.aws`, `.ssh`, dotenv/`.envrc` variants and `.mcp.json` variants,
including forced adds and case variants. Only exact, regular, empty indexed
`state/journal/.gitkeep` and `state/theses/.gitkeep` placeholders are allowed.
It runs in pre-commit and in the existing root-script CI tests. Install the
repository hooks before contributing; CI checks cannot retract an already pushed
secret.

This guard checks names and Git object metadata, not file contents. Reviewed
fictional fixtures under `examples/`, `docs/` or tests are allowed; real private
data placed there is not detected by this guard. Ignore rules do not encrypt,
delete tracked history, prevent uploads, or protect external absolute paths.
The separate detect-secrets hook excludes several extensions, including Markdown,
JSON and CSV; it is not a complete secret or PII control. If a credential is
exposed, revoke/rotate it with its provider and assess history/artifacts separately.

## External data flow

| Integration | Data sent or exposed | Data returned / boundary |
| --- | --- | --- |
| FMP client | Ticker, dates and filters; API key in header or query depending on endpoint | Market data; cache/output can preserve raw responses |
| FINVIZ | Screening filters and configured authentication key | Screen results |
| Alpaca tools / full portfolio workflow | Broker credentials authorize account/position requests; returned holdings may enter agent context | Broker/account data; local CSV comparison/normalization commands are offline, but connecting other tools changes the boundary |
| WebSearch / browser tools | Search terms, tickers and any user text included in queries | External pages/results; do not include account details in queries |
| Claude / configured model provider | Conversation, pasted files and tool results selected for context; mining/review prompts described below | Model output; use provider retention/access settings appropriate to the data |
| GitHub automation | Selected generated candidates, skill changes, PR text and committed files | May become public; inspect derived output and artifacts before publication |

Transport security depends on the configured endpoint/tool; use HTTPS provider
endpoints and avoid logging keys or pasting them into prompts. This repository
does not enforce redaction across every network path. Skill instructions about
broker usage are not a universal technical order-execution barrier; inspect actual
tool capabilities and permissions. Offline scripts do not authorize network tools.

## Session mining is a separate disclosure decision

[`mine_session_logs.py`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/skill-idea-miner/scripts/mine_session_logs.py)
reads immediate `*.jsonl` files under selected `~/.claude/projects/` project
directories, normally modified within the last seven days. The default allowlist
is `claude-trading-skills`, `claude-market-agents`, `trade-edge-finder`,
`trade-strategy-pipeline` and `weekly-trade-strategy`. A `--project` override can
change/broaden the selected projects. It does not scan all Codex history folders.

Parsing extracts external user messages, assistant tool names/inputs and tool
results/errors to find signals; sidechains and malformed records are skipped.
The model prompt can include project names, patterns, up to five selected user
excerpts (200 characters each), and up to three samples per signal (100 characters
each). It invokes `claude -p` through stdin, with up to three turns, a USD 1 budget
and a 600-second timeout. These limits do not anonymize the text. Review consent
and content before running mining over sessions containing personal information.

`--dry-run` skips model abstraction but still reads/parses local logs and writes
derived candidates. Raw candidates/session details may preserve sensitive text.
The weekly [generation pipeline](https://github.com/tradermonty/claude-trading-skills/blob/main/scripts/run_skill_generation_pipeline.py)
invokes the miner; later generation/backlog/PR steps may publish derived material.
The [improvement loop](https://github.com/tradermonty/claude-trading-skills/blob/main/scripts/run_skill_improvement_loop.py)
also submits skill/review prompts through `claude -p`. Inspect output before sharing;
neither path guarantees PII removal. Disabling a schedule alone does not erase
existing transcripts or generated files.

## Retention policy and current automation

Operational target: retain routine diagnostics for no more than 30 days, minimize
report/session extracts, and retain investigation evidence only until its review
and recovery needs are resolved. The operator must review and remove unnecessary
private files and copies; confirm backup needs before any deletion. Provider-side
retention is separate and governed by the configured provider/account settings.

Current implementation is narrower: generation and improvement scripts rotate
only immediate `logs/*.log` files older than 30 days and cap their own state
histories at 60 entries. Nested logs, JSON state files, reports, provider caches,
Claude transcripts and backup copies have **no uniform automatic purge**. This
policy does not claim that such purging is implemented. Do not use broad cleanup
commands against active or unreviewed evidence.

For a source-preserving recovery drill, follow the
[tested thesis backup/restore procedure](https://github.com/tradermonty/claude-trading-skills/blob/main/docs/dev/thesis-backup-restore.md).
It requires stopped writers, private storage, fresh destinations, a full file-list
and SHA-256 comparison, and the store's read-only `doctor`. Tests use fictional
state and restore after fixture source loss; this is not proof of your own backup.
See [SECURITY.md](https://github.com/tradermonty/claude-trading-skills/blob/main/SECURITY.md)
for reporting limitations and support policy. Capability statements here describe
source reviewed on 2026-11-14; deployed documentation and provider settings may differ.
