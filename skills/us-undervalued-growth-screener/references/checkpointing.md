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

Attaching or replacing an audit is all-or-nothing. The manager validates the metadata and hashes staged copies of every artifact before touching the run, then commits the artifacts, audit, event log, and `run_state.json` together, restoring all of them if any step fails. A rejected command leaves the prior checkpoint byte-identical and exits 1.

If the error says the prior checkpoint could not be fully restored, the prior files remain in the `.set-screening-audit-*` directory it names. A process killed during the commit cannot roll back: `prepublish_audit.py` rejects the resulting hash mismatch, and rerunning `set-screening-audit` repairs the run.

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
