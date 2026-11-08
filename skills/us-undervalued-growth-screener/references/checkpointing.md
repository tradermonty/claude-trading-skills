# Checkpoint and Completion Guide — Contract v3.5

## Purpose

Preserve every stage of a long screen, make resumption deterministic, and prevent selected candidates or unresolved pool rows from disappearing.

## Layout

```text
run/
├── run_state.json
├── screening_audit.json
├── screening_funnel.json
├── market_context.json
├── global_sources.json
├── universe_artifact.jsonl
├── candidate_pool_artifact.jsonl
├── candidates/
│   ├── SYMBOL.draft.json
│   └── SYMBOL.verified.json
└── final-snapshot.json
```

Write state atomically. Every state and audit carries v3.5 runtime metadata.

## Initialize

Use `manage_run_state.py init` with live market context, source ledger, price basis, and optional base repository commit.

## Attach the Audit

Use `set-screening-audit` only with a contract-3.5 audit whose runtime fingerprint matches the installed skill. The manager independently hashes the listing and candidate artifacts and checks their row counts and decisions.

Once a run contains any candidate at stage `verified`, `set-screening-audit` rejects every attachment, including the identical audit, with exit 1 before changing any files. Verification belongs to the existing audit and must not silently carry over to new evidence. To rescreen, initialize a new run directory, attach its audit, and verify its candidates again. Re-saving a verified candidate as `draft` is refused, so the guard cannot be bypassed by downgrading. While `candidate_pool_status` is `sufficient_pending_enrichment`, `save-candidate --stage verified` is refused and deep dives are saved as `draft`; resolve the pool, reattach the resolved audit, then save as `verified`. A run containing only draft candidates can still replace its audit; drafts remain unfinished and selected symbols must still be verified.

A run saved by an earlier version can hold verified candidates that this version can no longer complete: for example, candidates verified under a `sufficient_pending_enrichment` audit, or verified with `--allow-unselected` before any audit was attached. Reattaching, re-verifying and downgrading are all refused for such a run. Start over in a new run directory and verify the candidates against its audit. Do not use `init --force` on the same directory for this: it resets `run_state.json` but leaves the old `candidates/*.json` and `audit/*` files and appends to the existing `events.ndjson`.

Attaching or replacing an audit is all-or-nothing. The manager validates the metadata and hashes staged copies of every artifact before touching the run, then commits the artifacts, audit, event log, and `run_state.json` together, restoring all of them if any step fails. A rejected command leaves the prior checkpoint byte-identical and exits 1.

Details of the commit:

- Artifact names are compared case-insensitively, so `UNIVERSE-AUDIT-RESULTS.JSONL` collides with `universe-audit-results.jsonl` on every filesystem. An enrichment entry and a generation entry may point at the same file only when the SHA-256 is identical.
- A replaced file keeps its existing permission bits. New files get the default mode.
- Backups are plain copies with the permission bits only, so a macOS immutable flag on a live file is not copied to the backup.
- Backups are deleted only after the commit succeeded or the restore finished with no failures. A restore that fails or is interrupted keeps the `.set-screening-audit-*` directory, and the command continues restoring the remaining files before it reports. If the directory cannot be removed after a clean outcome, the command prints a warning naming it; delete it by hand.
- Non-finite numbers (`Infinity`), deeply nested JSON, and other malformed values are reported as `ERROR:` with exit 1 and no file changes.

If the error says the prior checkpoint could not be fully restored, each failure line names the target and the `backup-N.tmp` file in the kept `.set-screening-audit-*` directory that holds its prior bytes. Copy that backup over the target by hand. Targets with no backup were new files and can be deleted. A process killed during the commit cannot roll back: `prepublish_audit.py` rejects the resulting hash mismatch. Rerunning `set-screening-audit` repairs a run without verified candidates. For a legacy interrupted replacement in a run with verified candidates, restore the prior checkpoint from backups or initialize a new run directory and verify again; reattachment is rejected.

Limits that are documented rather than handled:

- The command assumes one writer. An event appended to `events.ndjson` by another process while the command runs is lost when the staged copy replaces the log.
- A live file that is a symbolic link is replaced by a regular file, and a rollback restores a regular file, not the link.

## Save Every Selected Candidate

For each selected symbol, save a draft early and replace it with a verified record after primary-source review. A selected company that becomes an M&A exclusion still receives a verified `excluded` candidate record.

## Funnel Counts

Maintain:

```text
universe_count
listing_in_scope_count
candidate_pool_count
discovery_evaluable_count
deep_dive_selected_count
preflight_passed_count
deep_dive_completed_count
```

`preflight_passed_count` and `deep_dive_completed_count` refer only to selected symbols. The evaluator independently recomputes both counts.

## Completion Gate

The manager enforces:

```text
unprocessed_candidates = selected_symbols − verified_candidate_symbols
```

It refuses `complete` when:

- the pool is unresolved or not exhausted,
- the queue is nonempty,
- generation audit/runtime evidence is invalid,
- any selected symbol lacks a verified record,
- funnel counts are inconsistent.

## Assemble and Evaluate

Assemble only from the attached audit, live source ledger, current context, and verified candidates. Then run:

```bash
python3 skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py \
  --input <final-snapshot.json> \
  --artifact-root <run-root> \
  --output-dir <final-dir> \
  --strict --require-final --language ja
```

## Resume

On resume:

1. verify installed runtime with `--version`;
2. inspect `run_state.json` runtime metadata;
3. reject stale contract revisions/fingerprints;
4. inspect selected, verified, unprocessed, and enrichment queue states;
5. continue from the earliest incomplete stage.

## v3.5 Publication Checkpoint

After strict evaluation, store the generated report JSON/Markdown under the run directory, run the prepublication audit, then build the complete ZIP. A run is operationally complete only when:

```text
strict evaluator exit = 0
prepublish audit exit = 0
bundle builder exit = 0
bundle manifest contains every referenced artifact
```

Do not delete intermediate audit or candidate files before bundling.
