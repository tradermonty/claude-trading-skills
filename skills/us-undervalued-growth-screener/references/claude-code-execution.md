# Claude Code Direct-FMP Execution — v3.6

## Purpose

The v3.6 path prevents bulk FMP responses from consuming the language-model context. Claude Code launches one local Python process. Python performs provider retrieval, persistent caching, listing enumeration, FY1 normalization, liquidity calculation, four-lane discovery, and deterministic broad screening. Claude reads only the compact summary and selected-company evidence packets.

The underwriting and final-ranking contract remains schema 3 / contract 3.5.

## Required environment

```bash
export FMP_API_KEY="..."
```

Never commit or print the key. Cache identities and raw-artifact metadata remove `apikey` and `api_key` fields.

The direct client requires `requests`; SQLite is provided by Python's standard library.

## Standard command

```bash
python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py \
  --config skills/us-undervalued-growth-screener/assets/claude-code-config.example.json \
  --output-dir reports/us-undervalued-growth-screener
```

The program prints one compact JSON object, normally below 20 KB. It does not print provider payloads.

## Reused repository components

- Repository-level generated FMP-client registry and vendoring pattern.
- Stable-first / legacy-v3 fallback, request pacing, retry, circuit breaking, and call-budget conventions.
- `normalize_estimates.py` for dated FY1/FY2/FY3 normalization.
- `build_provider_prefilter_pool.py` for four-lane candidate-pool construction.
- `screen_universe.py` for deterministic broad-screen decisions and deep-dive commitment.
- Existing checkpoint, evaluation, prepublication-audit, and bundle scripts.

## Retrieval strategy

1. Enumerate NASDAQ, NYSE, and AMEX with the company screener.
2. If a response reaches the configured limit, recursively split the market-cap band. A listing enumeration is complete only when all leaf bands are unsaturated.
3. Attempt bulk ratios, key metrics, income-statement growth, annual analyst estimates, and daily EOD datasets.
4. If bulk annual estimates cover enough symbols, normalize all covered listings. Otherwise choose a deterministic sector × market-cap seed and use per-symbol estimate calls.
5. Prefer bulk 20-day EOD volume. If unavailable, rank exact-liquidity work by the four economic lanes and fetch per-symbol history only for the bounded target set.
6. Build core GARP, high-growth exception, quality near-miss, and cyclical-normalization lanes.
7. Produce a 12–30 name audited provider-prefilter pool and select up to three deep-dive names.
8. Fetch candidate-level FMP data once. Store full payloads under `provider/candidate-data/`; write compact projected packets under `candidate-packets/`.

Bulk endpoint names remain configuration-driven because availability varies by FMP plan. A missing bulk endpoint is a fallback condition, not permission to invent data.

## Context discipline

Claude may read:

```text
run-summary.json
NEXT_ACTION.json
audit/listing-enumeration-audit.json
audit/provider-prefilter-audit.json
audit/broad-screen-audit.json
audit/partial-run-diagnostic.json
audit/enriched-estimates.partial.jsonl
candidate-packets/*.fmp-packet.json
```

The CLI stores provider raw responses in a sibling, attempt-specific
`.provider-raw/<run-id>/` directory so creating the FMP client cannot make a
new run directory look stale. An explicitly supplied raw-store path must also
remain outside the screen run directory.

`audit/partial-run-diagnostic.json` is a commit marker for a budget-exhausted
`screen-full-snapshot` attempt. Read the partial JSONL, summary, or preserved
artifacts only after verifying the marker's recorded SHA-256 values and row
counts. A missing or mismatched marker means the preceding files are not
authoritative. Screening has no `--resume`; rerun the same verified snapshot
into a new empty run directory after the provider budget is restored. The
snapshot is read-only. Existing
cache/raw records are not deleted or rewritten, while successful calls may add
new records and a later rerun may reuse them.

Claude must not load the raw provider-response tree into context. Open a raw file only to resolve a specific named mismatch. Provider packets remain secondary evidence; SEC/IR verification is mandatory for formal underwriting.

## Persistent cache

The generated client uses SQLite. Default TTLs are:

| Dataset | TTL |
|---|---:|
| Quotes | 1 hour |
| Listing universe | 7 days |
| Analyst estimates | 3 days |
| Statements / ratios / metrics | 7 days |
| Historical prices | 1 day |

The first run may issue many HTTP requests inside one Python invocation. Later runs reuse the cache and primarily refresh prices, estimates, and selected-company data.

## Key artifacts

```text
<run>/run-summary.json
<run>/NEXT_ACTION.json
<run>/audit/listing-enumeration-audit.json
<run>/audit/universe.jsonl
<run>/audit/enriched-estimates.jsonl
<run>/audit/provider-prefilter-pool.jsonl
<run>/audit/provider-prefilter-audit.json
<run>/audit/broad-screen-results.jsonl
<run>/audit/broad-screen-audit.json
<run>/audit/partial-run-diagnostic.json   # only for budget-exhausted screen attempts
<run>/audit/enriched-estimates.partial.jsonl
<run>/candidate-packets/<SYMBOL>.fmp-packet.json
<run>/provider/candidate-data/<SYMBOL>/*.json
```

## Handoff to underwriting

`run_pipeline.py` stops at `ready_for_underwriting` when selected symbols exist. Claude must then:

1. perform corporate-action preflight;
2. verify current quarter and full year separately using SEC/IR;
3. reconstruct standard FCF with primary-source period evidence;
4. build same-basis valuation periods and an independent forecast bridge;
5. verify SBC, dilution, ROIC, leverage, peers, and cycle/sector evidence;
6. save all selected symbols, regardless of final status;
7. run strict evaluation, prepublication audit, and bundling.

A helper exit code 2 is an internal continuation signal. It is not a reason to ask the user for another turn.

## Deep-dive budget versus lane coverage

The bounded direct-FMP example config keeps `max_deep_dive_candidates: 3` to limit downstream underwriting work. This is a total candidate limit, not a promise of coverage across all four research lanes. The default lane targets are core GARP 2, high-growth exception 1, quality near miss 1, and cyclical normalization 1: five slots in total.

When the limit is below that total, the first selection pass walks candidates in priority order and applies each lane target as a cap. With a limit of three, at least one lane must be absent. At a limit of five or more, the first pass fills lane targets in lane order. In either case, later passes fill unused slots by priority without lane caps; the final pass can relax the sector preference if it would otherwise leave slots unused. Targets and the two-name sector preference therefore do not guarantee the final lane counts or sector counts. Only eligible candidates can be selected.

To allow the five-slot plan on the bounded path, copy `assets/claude-code-config.example.json` to your run configuration, set `max_deep_dive_candidates` to `5`, and pass that copy to `run_pipeline.py --config`. This allows more underwriting work but does not guarantee that every lane has an eligible selected name. Rerun the broad screen through the pipeline to establish the new selected set; when reducing the limit, omitted eligible names must become `deferred_by_budget`. Do not simply stop underwriting part of an already committed set: every selected symbol must be resolved.

The full-snapshot path uses the separate `full_snapshot_deep_dive_candidates` setting and requires it to equal `5`. Changing the bounded-path limit does not change that requirement. Neither a three-name nor a five-name deep-dive set alone establishes market-wide economic coverage; that depends on the full-snapshot verification contract.
