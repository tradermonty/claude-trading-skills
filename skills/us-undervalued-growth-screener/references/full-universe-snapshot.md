# Full-universe estimate snapshot (v3.7 — sharded collection)

The v3.6.1 pilot economically evaluates ~4% of the listed universe and is
therefore permanently `ranking_scope: final_scoped`. The v3.7 path earns
`final_marketwide` the only honest way: by attempting estimate acquisition for
EVERY listed symbol at least once. On plans where bulk endpoints are 402, that
means collecting per-symbol across deterministic shards within each run's API
budget, persisted into a frozen snapshot.

## Stage: `collect-estimates`

```bash
python3 scripts/run_pipeline.py \
  --stage collect-estimates \
  --shard-index 0 --shard-count 8 \
  --snapshot-dir .cache/us-garp/snapshot-2026-08 \
  --config assets/claude-code-config.example.json \
  [--resume]
```

- The FIRST invocation enumerates listings and **freezes the universe** into
  the snapshot directory (`snapshot-manifest.json` + `universe.jsonl` +
  `listing-enumeration-audit.json`,
  identified by `snapshot_id` = timestamp + universe SHA-256). Every later
  shard run writes into that frozen snapshot; new listings and delistings go
  to the NEXT snapshot, never mixed in.
- Collection is current-only: a historical or future `--analysis-as-of` is
  rejected before client/cache/raw/snapshot creation. Each row records
  `snapshot_normalization_as_of`; shard manifests aggregate its bounds so a
  later screen cannot treat an old FY-period normalization as current.
- Shard membership is `sha256(symbol) % shard_count` — the same symbol always
  lands in the same shard, so multi-day collection is deterministic.
- Each attempted symbol is normalized (FY1-FY3 EPS/revenue, analyst counts)
  and classified into exactly one bucket:
  `evaluable / no_estimates / negative_eps / unit_mismatch / excluded`
  (precedence: excluded > unit_mismatch > no_estimates > negative_eps >
  evaluable; the unit gate is the round-8 fail-closed
  `requires_unit_reconciliation`).
- **Provider failures are never classified.** The client returns an empty
  list for HTTP failures, offline cache misses and invalid JSON as well as
  for genuinely empty consensus; the stage distinguishes them via the
  client's per-call diagnostics (calls / cache hits / failure count) and
  records failures as `fetch_failed` — the symbol stays uncollected, the
  shard stays `partial` (`shard_partial_fetch_failures`, exit 3), and the
  marketwide invariant cannot be satisfied by outages. HTTP-200 error
  bodies (`{"Error Message": ...}` plan-limit style) are validated in the
  client itself: recorded as `provider_error_payload`, never cached; a
  malformed object that predates validation in an existing cache is
  flagged `unexpected_payload_shape` on read and likewise becomes a fetch
  failure.
- Budget exhaustion mid-shard exits with code **3**, records the shard as
  `partial` in the manifest, and is resumable with `--resume`. A shard file
  that already exists without `--resume` is refused.
- **The frozen universe is re-verified on every load** (manifest schema,
  row count, symbol uniqueness, canonical SHA-256) before any API access or
  shard append; a swapped `universe.jsonl` is refused.
- Every collected row carries `snapshot_retrieved_at` — the ACTUAL fetch
  time. Cache-served rows (any cache hit, including a failed stable HTTP
  attempt falling back to the v3 cache) are stamped from the cache entry's
  creation time; when that provenance cannot be resolved the stamp stays
  **null** (counted as `retrieval_time_unknown`, never back-filled with
  "now"). Shards aggregate `oldest_retrieved_at` / `newest_retrieved_at`,
  and a run that collects nothing does NOT refresh the shard's `as_of`
  freshness stamp.
- Shard summaries (`shard-<i>-summary.json`) and the manifest carry attempted
  / expected / fetch-failed counts, per-bucket classification, `as_of`,
  retrieval and normalization bounds, and calls used.

## Stage: `screen-full-snapshot`

After every shard is complete, run the current-only market-wide screen:

```bash
python3 scripts/run_pipeline.py \
  --stage screen-full-snapshot \
  --snapshot-dir .cache/us-garp/snapshot-2026-08 \
  --config assets/claude-code-config.example.json \
  --output-dir reports/us-undervalued-growth-screener
```

This stage performs its read-only snapshot preflight before constructing the
FMP client or creating cache, provider-raw, or run directories. It refuses an
incomplete, stale, future-dated, tampered, or semantically misclassified
snapshot with exit code 1 and creates no run artifact tree.

The screen is deliberately current-only. Exact-liquidity and TTM quality
probes use current provider evidence, so an operator-supplied historical
`--analysis-as-of` is rejected before those calls rather than mixing current
fundamentals into a historical ranking. The allowed wall-clock skew defaults
to five minutes.

For a ready snapshot, the stage:

1. uses the verified in-memory shard rows from the same reads that produced
   the readiness verdict;
2. rechecks gap-free exhausted bands for every requested exchange, requires
   the frozen market-cap/price scope to contain the screen request, then binds
   that audit, the manifest, frozen-universe SHA-256, and every shard SHA-256
   into a `snapshot_verification_digest` carried by all downstream audits;
3. records the estimate-attempt classification and retrieval provenance for
   every frozen symbol in `universe-audit-results.jsonl`;
4. builds a deterministic 30–50 name multi-lane pool (default 50), backfills
   failed/empty exact-liquidity calls until the target succeeds or every
   eligible symbol has an explicit outcome, probes every preliminary-pool
   name for current quality evidence, and never selects an unprobed deep-dive
   name; and
5. commits five deep-dive slots for the market-wide path.

A verified snapshot with no economically evaluable names can produce a formal
market-wide no-candidate result. Missing coverage, an unresolved enrichment
queue, or a short pool that cannot prove exhaustion remains diagnostic and
exits 2. A successful underwriting handoff or verified no-candidate result
exits 0.

## Readiness and content binding

Two layers, deliberately separate:

- **`snapshot_status(manifest)` → `collection_ready`** — manifest-level
  aggregation only (all shards complete with zero `fetch_failed`,
  classification counts summing exactly to the frozen universe,
  `retrieval_time_unknown == 0`, `normalization_time_unknown == 0`). It trusts
  the manifest's own counters and
  therefore proves nothing about the shard files.
- **`load_verified_snapshot(snapshot_dir, screening_as_of=..., max_staleness_days=...)`
  → `verdict + verified rows`** — the ONLY source of the screening verdict and
  consumable rows. It
  reads the hash-bound listing-enumeration audit and every `shard-*.jsonl`
  exactly once and verifies against the frozen universe:
  file presence and SHA-256 vs the manifest, no duplicate symbols, every
  symbol in the frozen universe and in its `stable_shard` shard, the union
  covering the universe EXACTLY, classifications limited to allowed values,
  per-shard counts matching the manifest — plus staleness measured from the
  ACTUAL aggregated `oldest_retrieved_at` and
  `oldest_normalization_as_of` against
  `screening_as_of - max_staleness_days` (never the operator-supplied
  collection `as_of`).

Only a run screened from this same-read bundle with
`ready_for_screening: true`, an exact classification total, and a bound
`snapshot_verification_digest` may emit `ranking_scope: final_marketwide`.

## Operating on the FMP Starter plan

~2,371 symbols ≈ 1 estimate call each. With a 350-call per-run budget and the
750-call daily plan limit, 8 shards (~300 symbols each) collect in 2 shards/day
over 4 days. After the initial build, only incremental refresh is needed
(new snapshot per refresh cycle; post-earnings and revised names first).

## Shared coverage semantics

`scripts/coverage_semantics.py` is the single source of truth for
`classify_ranking_scope` / `build_coverage_block` /
`derive_ranking_scope_from_audit` / `validate_coverage_block`; both
`run_pipeline` (discovery) and `evaluate_candidates` (final evaluation) import
it, so the tri-state semantics cannot drift between the two sides.
