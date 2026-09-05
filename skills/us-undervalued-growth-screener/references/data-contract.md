# Schema-v3 / Screening-Audit-v3.5 Data Contract

## Contract Versions

```text
Top-level snapshot schema_version: 3
Screening audit audit_schema_version: 3
Screening audit contract_revision: 3.5
```

Snapshot schema 3 retains the accounting, source, forecast, and candidate structure introduced in v3.0. Screening contract 3.5 hardens immutable requested scope, average-liquidity evidence, current NTM/FY1 normalization, selected-set commitments, universe enumeration, enrichment resolution, completion, source freshness, and report-disposition rules.


## v3.5 Discovery Evidence Contract

### User-request scope versus executed scope

The default user request remains USD 500 million–20 billion unless the user explicitly changes it. Store both:

```json
{
  "user_requested_scope": {
    "min_market_cap": 500000000,
    "max_market_cap": 20000000000,
    "source": "skill_default | explicit_user_request"
  },
  "executed_scope": {
    "min_market_cap": 500000000,
    "max_market_cap": 20000000000
  },
  "scope_reduced": false,
  "scope_override_authorized": false,
  "user_scope_evidence": null
}
```

Internal context or tool-budget pressure never authorizes a narrower market-cap request. Use a cross-range provider prefilter or stream exhausted bands to disk. A single convenient band is incomplete unless the user explicitly requested that band.

### Average daily dollar volume

A row is valid for discovery only when it provides an allowed averaging method, a window of at least 20 sessions, and resolving source IDs. Raw one-session `volume` is never interpreted as average volume.

```json
{
  "average_daily_dollar_volume": 12000000,
  "average_daily_dollar_volume_method": "provider_average_dollar_volume",
  "average_volume_period_days": 20,
  "liquidity_source_ids": ["quote-source"]
}
```

### Current forward metric

`forward_pe` alone is invalid. Current valuation must identify NTM or FY1 and reconcile to price and a positive current forward EPS:

```json
{
  "forward_pe_period": "FY1",
  "forward_fiscal_year": "FY2027",
  "forward_period_end": "2027-06-30",
  "forward_eps": 3.25,
  "forward_pe": 15.4,
  "forward_estimate_as_of": "2026-08-28T12:00:00Z",
  "forward_estimate_source_ids": ["consensus-source"],
  "forward_metric_origin": "computed_from_price_and_fy1_eps",
  "analyst_count": 6
}
```

Outer-year substitutions, pre-operating companies, a forecast range crossing zero, excessive dispersion, stale estimates, or non-contiguous annual rows cannot become current Forward P/E inputs. Use `normalize_estimates.py` to produce this structure from raw dated annual estimates.

### Committed selected set

The broad-screen audit commits the selected set with a SHA-256 payload. Every selected symbol must receive a verified candidate record. Reducing the deep-dive count requires a fresh deterministic broad-screen run; narrative-stage discretion cannot drop an already selected name.

## Top-Level Snapshot

```json
{
  "schema_version": 3,
  "runtime": {
    "skill_name": "us-undervalued-growth-screener",
    "skill_version": "3.6.1",
    "schema_version": 3,
    "contract_revision": "3.5",
    "runtime_fingerprint": "ug-v3.6.1-claude-code-direct-fmp-20260830"
  },
  "analysis_as_of": "ISO-8601 with timezone",
  "run_metadata": {
    "run_id": "string",
    "status": "partial | complete",
    "base_repository_commit": "optional SHA",
    "selected_symbols": [],
    "unprocessed_candidates": []
  },
  "price_basis": {
    "as_of": "ISO-8601 with timezone",
    "session": "regular_close | pre_market | after_hours | intraday",
    "timezone": "America/New_York",
    "source_id": "source-id"
  },
  "config": {},
  "market_context": {},
  "screening_funnel": {},
  "global_sources": [],
  "screening_audit": {},
  "candidates": []
}
```

All timestamps must be at or before `analysis_as_of` unless a field explicitly represents a future fiscal period.

## Source Ledger

```json
{
  "id": "unique-id",
  "tier": 1,
  "kind": "sec_filing",
  "title": "Form 10-Q",
  "published_at": "2026-08-10T16:05:00-04:00",
  "data_as_of": "2026-06-30T00:00:00-04:00",
  "retrieved_at": "2026-08-22T10:05:00-07:00",
  "url": "https://...",
  "supports": ["latest_earnings.quarter", "financials.cash_flow_ttm"]
}
```

`supports` is always a non-empty string array. `data_as_of` is optional but preferred for dynamic fields whose data date differs from publication time. Retrieval time never makes old data current.

| Kind | Usual tier |
|---|---:|
| `sec_filing` | 1 |
| `official_macro`, `official_statistics` | 1 |
| `company_ir` | 2 |
| `exchange_status` | 2 or 3 |
| `market_data`, `consensus`, `news`, `third_party_transcript` | 3 |
| `analyst_calculation`, `analyst_assumption`, `local_artifact` | 4 |

A third-party transcript is never `company_ir`.

## Market Context

Required fields:

```json
{
  "summary": "non-placeholder narrative",
  "as_of": "ISO-8601",
  "policy_rate_pct": 3.625,
  "treasury_10y_yield_pct": 4.74,
  "real_gdp_growth_pct": 1.5,
  "inflation_yoy_pct": 3.4,
  "market_forward_pe": 21.2,
  "small_mid_cap_valuation_context": "current context",
  "sector_cycle_notes": [],
  "source_ids": [],
  "inferences": []
}
```

Field-level evidence and default maximum ages:

| Field | Default max age | Source rule |
|---|---:|---|
| Policy rate | 60 days | official macro/statistics |
| 10-year Treasury | 7 days | official macro/statistics |
| Inflation | 45 days | official statistics |
| GDP | 120 days | official statistics |
| Market forward P/E | 14 days | current market-data/research source |
| Small/mid-cap context | 14 days | current market-data/research source |

Market-rate expectation language such as “markets price hikes/cuts” requires a source supporting `market_context.market_rate_expectations` or an `analyst_inference` object with resolving source IDs.

## Layered Screening Audit

```json
{
  "audit_schema_version": 3,
  "contract_revision": "3.5",
  "runtime": {
    "skill_name": "us-undervalued-growth-screener",
    "skill_version": "3.6.1",
    "schema_version": 3,
    "contract_revision": "3.5",
    "runtime_fingerprint": "ug-v3.6.1-claude-code-direct-fmp-20260830"
  },
  "conclusion_scope": "full_listing_universe | provider_prefilter | stratified_discovery_pool | bounded_available_fundamentals | user_supplied",
  "generated_at": "ISO-8601",
  "analysis_as_of": "ISO-8601",
  "candidate_generation_mode": "liquidity_stratified_estimates",
  "candidate_pool_status": "sufficient | sufficient_pending_enrichment | no_qualifying_candidates | no_qualifying_candidates_in_bounded_pool | insufficient_data",
  "selection_outcome": "selected | selected_pending_enrichment | no_candidates | no_candidates_in_bounded_pool | insufficient_data",
  "selected_symbols": ["AAA"],
  "filters": {},
  "source_ids": ["listing-source", "estimate-source"],
  "scope": {
    "requested_min_market_cap": 500000000,
    "requested_max_market_cap": 20000000000,
    "retrieval_min_market_cap": 500000000,
    "retrieval_max_market_cap": 20000000000,
    "retrieval_scope_explicit": true,
    "scope_override_authorized": false,
    "scope_complete": true,
    "reasons": [],
    "enumeration": {
      "verified": true,
      "provider_reported_total": 1786,
      "rows_fetched": 1786,
      "pages_fetched": 18,
      "pagination_exhausted": true,
      "band_audit": [],
      "bands_verified": false
    }
  },
  "universe": {
    "row_count": 1786,
    "in_scope_count": 1600,
    "listing_data_complete_count": 1770,
    "listing_data_complete_pct": 99.1,
    "decision_counts": {},
    "artifact_path": "audit/universe-audit-results.jsonl",
    "artifact_sha256": "64-character SHA-256"
  },
  "candidate_pool": {
    "row_count": 120,
    "discovery_evaluable_count": 40,
    "selection_eligible_count": 8,
    "selected_count": 5,
    "in_scope_covered_count": 120,
    "in_scope_missing_count": 1480,
    "in_scope_missing_symbols": ["..."],
    "coverage_complete": true,
    "coverage_scope": "stratified_discovery_pool",
    "listing_coverage_complete": false,
    "generation_audit": {
      "audit_schema_version": 2,
      "runtime": {},
      "selection_method": "sector_market_cap_stratified",
      "input_row_count": 1786,
      "selected_count": 120,
      "selected_symbols": [],
      "source_ids": [],
      "artifact_path": "discovery/discovery-pool.jsonl",
      "artifact_sha256": "64-character SHA-256",
      "valid": true
    },
    "fundamental_complete_count": 12,
    "decision_counts": {},
    "symbols_not_in_universe": [],
    "artifact_path": "audit/broad-screen-results.jsonl",
    "artifact_sha256": "64-character SHA-256"
  },
  "enrichment": {
    "status": "pending | complete",
    "next_action": "build_discovery_pool | enrich_queue | expand_candidate_pool | verify_candidate_pool_exhaustion | proceed_to_deep_dive | publish_no_candidates",
    "discovery_pool_required": false,
    "attempted_count": 120,
    "resolved_count": 118,
    "unresolved_count": 2,
    "resolution_pct": 98.3333,
    "all_rows_resolved": false,
    "maximum_attempts": 120,
    "candidate_pool_exhaustion_declared": false,
    "candidate_pool_exhausted": false,
    "candidate_pool_covers_in_scope": false,
    "queue_count": 2,
    "queue_symbols": ["BBB", "CCC"],
    "artifact_path": "enrichment-queue.json",
    "artifact_sha256": "64-character SHA-256"
  }
}
```

## Scope and Enumeration

`scope_complete=true` requires all of:

```text
retrieval_scope_explicit = true
retrieval bounds cover requested bounds
enumeration.verified = true
```

Enumeration is verified when:

- pagination is exhausted and any provider-reported total is consistent with fetched rows, or
- every row in `band_audit` has valid lower/upper bounds, a nonnegative row count, and `provider_exhausted=true`, and the ordered bands cover the complete requested market-cap range without gaps.

A matching lower/upper market-cap bound alone is insufficient. `bands_verified=true` is derived from the band evidence; it is not accepted as self-attestation.


## Requested Scope, Executed Scope, and Authorization

Keep the user's request separate from the data slice actually executed:

```json
{
  "user_requested_scope": {
    "min_market_cap": 500000000,
    "max_market_cap": 20000000000,
    "source": "default_contract | explicit_user_request"
  },
  "executed_scope": {
    "min_market_cap": 500000000,
    "max_market_cap": 20000000000,
    "reduction_authorized": false,
    "authorization_source": null
  }
}
```

A tool/context budget is not authorization to replace the default USD 500M–20B request with a USD 3B–4B request. Stream pages or market-cap bands to disk. A narrower execution may be published only as an explicitly user-authorized scoped run; otherwise the contract remains partial.

## Listing Liquidity Evidence

A listing or discovery row may satisfy ADDV only with a provider-average dollar-volume value or `price × average_volume`, where the averaging window is at least 20 trading days:

```json
{
  "average_daily_dollar_volume": 12500000,
  "average_daily_dollar_volume_method": "provider_average_dollar_volume | price_times_average_volume",
  "average_volume_period_days": 20,
  "liquidity_source_ids": ["quote-history-source"]
}
```

Single-session volume, an unlabeled `volume` field, or a share-volume floor cannot populate ADDV.

## Current Forward Estimate Normalization

The formal current multiple must use a resolving NTM or FY1 period:

```json
{
  "forward_pe": 14.2,
  "forward_eps": 3.10,
  "forward_pe_period": "NTM | FY1",
  "forward_period_end": "2027-06-30",
  "forward_fiscal_year": "FY2027",
  "forward_estimate_as_of": "2026-08-28T00:00:00-04:00",
  "forward_estimate_source_ids": ["consensus-source"],
  "forward_estimate_analyst_count": 6,
  "estimate_normalization_status": "valid"
}
```

For FY1, the period must be the nearest supported fiscal year after `analysis_as_of` and within the configured horizon. A missing FY1/NTM row, pre-operating status, a forecast range crossing zero, extreme dispersion, or noncontiguous outer-year-only estimates produces `estimate_normalization_status="unavailable"`. Canonical `forward_pe` and `forward_eps` are then null; raw outer-year values may be retained only under `raw_forward_candidate` for diagnostics.

## Selected-Set Commitment

The deterministic Broad Screen commits its selected symbols and budget:

```json
{
  "selected_symbols": ["AAA", "BBB"],
  "selected_set_sha256": "64-character SHA-256",
  "max_deep_dive_candidates": 3
}
```

Every committed selected symbol must reach a verified terminal candidate record. The model cannot later process only a preferred subset. To change the budget or selected set, rerun the deterministic Broad Screen so omitted names become `deferred_by_budget`.

## Universe Artifact

`universe-audit-results.jsonl` has one row per listing-universe symbol. Allowed decisions include:

- `in_scope`
- `liquidity_review`
- `out_of_scope`
- `excluded`

`listing_data_complete` refers only to listing/quote/scope fields, not financial statements.

## Candidate-Pool Artifact

`broad-screen-results.jsonl` has one row per bounded economic candidate.

### Resolution fields

```json
{
  "enrichment_attempted": true,
  "enrichment_resolved": false,
  "selection_eligible": false,
  "decision": {
    "status": "needs_enrichment",
    "resolution": "unresolved",
    "selection_eligible": false
  }
}
```

`enrichment_attempted` means a source was queried or at least one economic value was supplied. It does not imply resolution.

### Allowed final broad statuses

| Status | Resolution | Can be selected? | Score |
|---|---|---:|---:|
| `selected` | resolved | yes | numeric |
| `deferred_by_budget` | resolved | no | numeric |
| `screened_out` | resolved | no | numeric when assessable |
| `excluded` | resolved | no | optional |
| `unavailable_after_enrichment` | resolved | no | null |
| `needs_enrichment` | unresolved | no | null |

Before budget assignment, economically plausible rows may use `passed`, `passed_exception`, `near_miss_review`, or `sector_review_required`. The serialized final artifact converts selected/deferred rows to `selected` or `deferred_by_budget` while preserving `preselection_status` and deep-dive requirements.

### Unavailable after enrichment

A row may be resolved as `unavailable_after_enrichment` only with:

```json
{
  "enrichment_exhausted": true,
  "enrichment_exhaustion_reason": "specific reason",
  "enrichment_source_ids": ["attempt-source"]
}
```

The source IDs must resolve in the ledger.

## Candidate-Pool Outcomes

### `sufficient / selected`

- one or more selected rows;
- candidate pool exhausted;
- all rows resolved;
- queue empty.

### `sufficient_pending_enrichment / selected_pending_enrichment`

- one or more selected rows;
- unresolved rows or unverified exhaustion remain.

Deep dives may start, but formal final output is prohibited.

### `no_qualifying_candidates / no_candidates`

A **market-wide** conclusion is allowed only when:

```text
conclusion_scope = full_listing_universe
selected_symbols = []
candidate_pool.coverage_complete = true
candidate_pool.in_scope_missing_count = 0
candidate_pool_exhaustion_declared = true
candidate_pool_exhausted = true
all_rows_resolved = true
unresolved_count = 0
queue_count = 0
discovery_evaluable_count > 0
```

### `no_qualifying_candidates_in_bounded_pool / no_candidates_in_bounded_pool`

A reproducibly generated bounded pool may reach this status when its generation audit is valid, every pool row is resolved, exhaustion is verified, the queue is empty, and at least one row was economically assessable. The report must name the bounded `conclusion_scope` and must not make a market-wide claim.

### `insufficient_data`

- no selected rows;
- unresolved evidence remains, enumeration is incomplete, or no row was economically assessable.

Do not describe this as “no qualifying candidates.”

## Soft Guidelines and Hard Broad Failures

Growth, preferred valuation, ROIC, and preferred leverage values are guidelines. Store misses in `guideline_misses`; do not automatically reject a row for one miss.

Hard failures belong in `screen_fail_reasons`, for example:

- `non_positive_standard_fcf`
- `negative_roic`
- `excessive_leverage`
- `extreme_forward_valuation`
- `negative_forward_growth`
- `valuation_not_supported_by_growth`
- `growth_and_valuation_combination_below_review_threshold`

Cyclical normalization is normally a `deep_dive_requirement`, not a hard failure.

## Candidate Deep-Dive Record

Each selected candidate retains schema-v3 structures for:

- identity and price basis,
- sources and evidence,
- corporate-action check,
- latest quarter and full year as separate records,
- financials and TTM cash-flow reconstruction,
- forward same-basis valuation periods,
- forecast bridge and GAAP reconciliation,
- peer set,
- sector profile,
- cyclicality normalization,
- thesis, catalysts, risks, and invalidation conditions,
- score components and penalties.


## Runtime Compatibility

Every snapshot, screening audit, discovery audit, and checkpoint must match the installed v3.6 runtime metadata. A mismatch in skill version, schema version, contract revision, or runtime fingerprint is a hard contract error. File names and human-readable version labels are not sufficient proof.

## Driver-Derived Forecast Contract

For each rankable future period, `forecast_bridge` must contain operating drivers sufficient to calculate the metric independently.

### EPS

```json
{
  "revenue": 1000000000,
  "operating_margin_pct": 20.0,
  "net_interest_and_other": -5000000,
  "tax_rate_pct": 22.0,
  "diluted_shares": 100000000,
  "after_tax_adjustments": 10000000,
  "source_ids": ["forecast-source"]
}
```

The evaluator derives GAAP net income from revenue, margin, interest/other, and tax, then adds sourced after-tax adjustments only for an adjusted basis. A supplied `metric_numerator` is only a cross-check. A bridge that merely sets numerator equal to target EPS times shares fails.

For adjusted periods, driver-derived GAAP EPS must tie to the GAAP reconciliation and driver adjustments must tie to the reconciliation adjustment amount.

### FCF per share

Derive standard FCF from OCF minus positive capex cash outflow, or from a sourced revenue/FCF-margin model, then divide by diluted shares.

## TTM Cash-Flow Evidence

A TTM method is valid only when the construction periods have resolving source IDs:

- `reported_ttm`: source IDs for the reported TTM value;
- `sum_4_discrete`: source IDs for all four discrete quarters;
- `fy_plus_current_ytd_minus_prior_ytd`: source IDs for FY, current YTD, and prior-year YTD.

## Cash and Financial-Quality Evidence

Ordinary companies may normalize reported cash/equivalents into `corporate_cash`. Payments and custodial businesses must explicitly separate corporate cash, customer/settlement funds, and restricted cash. ROIC and EBITDA used for scoring or leverage require resolving primary-source or transparent analyst-calculation evidence.

## Sector and Peak-Profit Evidence

Sector aliases `biopharma`, `pharma`, `biotechnology`, `royalty_biopharma`, and `drug_delivery_platform` normalize to `commercial_biopharma`. Material product/royalty concentration, nearest LOE, source IDs, and 6x/8x stress scenarios are required.

`peak_profit_risk=true` requires sourced mid-cycle normalization even when the numeric cyclicality score is 1 or 2.

## Completion and Checkpoint Invariants

```text
unprocessed_candidates = selected_symbols - verified_candidate_symbols
```

A run cannot be complete when:

- screening audit is invalid;
- candidate pool status is `insufficient_data` or `sufficient_pending_enrichment`;
- candidate pool does not cover every in-scope listing symbol;
- pool exhaustion was not explicitly declared and independently verified;
- any broad row is unresolved;
- queue is nonempty;
- a selected symbol is not verified;
- `no_qualifying_candidates` is claimed without an assessable exhausted pool.

## Markdown Output Contract

The Markdown report must separately show:

### Broad-screen stage

- selected,
- deferred by budget,
- unresolved/review rows,
- unavailable after enrichment,
- screened out,
- excluded.

### Deep-dive stage

- ranked,
- review required,
- screened out,
- excluded.

Never display `0 / 0 / 0 / 0 / 0` for deep-dive counts in a way that hides nonzero broad-screen dispositions.

## v3.5 Multi-Lane Selection and Publication Contract

### Selection lanes

Every selected Broad Screen row records one of:

```text
core_garp
high_growth_exception
quality_near_miss
cyclical_normalization
```

The default five-name plan targets 2/1/1/1 names across these lanes and applies a two-name sector cap when alternatives exist. Unused lane capacity is deterministically backfilled. The selected set remains committed and every selected symbol must receive a verified terminal candidate record.

### Independent driver provenance

Each year-2/year-3 forecast bridge uses:

```json
{
  "construction_method": "independent_driver_model",
  "driver_provenance": {
    "revenue": {
      "origin": "market_consensus",
      "source_ids": ["consensus-source"],
      "target_solved": false
    },
    "operating_margin_pct": {
      "origin": "historical_run_rate",
      "source_ids": ["10-k-source", "analyst-model"],
      "target_solved": false
    }
  }
}
```

Allowed origins are `company_guidance`, `market_consensus`, `historical_run_rate`, `company_target`, `analyst_assumption`, and `primary_source_calculation`. Any driver solved backwards from target EPS or FCF fails the bridge.

### Explicit cash-flow period support

A generic `financials.cash_flow_ttm` support label does not validate four discrete periods. Each source must explicitly support its period path, for example:

```text
financials.cash_flow_periods.2026-06-30
financials.ttm_reconstruction.latest_fy
financials.cash_flow_ttm.reported_ttm
```

### Corporate transitions

Recent spin-offs, transformative acquisitions, and large divestitures are corporate-transition evidence, not sector valuation special cases. Store `identity.special_case = none` and a sourced `corporate_transition` object. Missing pro-forma normalization routes the candidate to `review_required`, not hard exclusion.

### Publication bundle

A formal publication contains the complete run directory plus `BUNDLE_MANIFEST.json`. The manifest records runtime identity, file paths, sizes, SHA-256 values, and the passing prepublication audit. Summary-only ZIP files are invalid.

### Multi-lane provider-prefilter generation audit

A provider-prefilter pool records:

```json
{
  "selection_method": "provider_prefilter",
  "lane_input_counts": {
    "core_garp": 30,
    "high_growth_exception": 20,
    "quality_near_miss": 25,
    "cyclical_normalization": 25
  },
  "lane_selected_counts": {
    "core_garp": 15,
    "high_growth_exception": 15,
    "quality_near_miss": 15,
    "cyclical_normalization": 15
  },
  "lane_coverage_count": 4,
  "minimum_pool": 30,
  "pool_adequate": true,
  "provider_exhausted": false
}
```

A valid high-recall bounded pool normally has at least 30 rows and at least three represented lanes. `provider_exhausted=true` may waive the row floor, but not liquidity evidence or lane disclosure.

### v3.6.1 discovery additions

The discovery audit additionally carries:

```json
{
  "provider_exhausted_scope": "estimate_seed",
  "listing_provider_exhausted": true,
  "estimate_seed_exhausted": true,
  "economic_candidate_universe_exhausted": false,
  "seed_audit": {
    "seed_selection_basis": "stratified_liquidity_proxy",
    "economic_metrics_available_for_seed": false,
    "cell_count": 55,
    "quota_method": "sqrt_hamilton",
    "alphabetic_tie_break_used_count": 0,
    "hash_tie_break_used_count": 3,
    "seed_limit_configured": 180,
    "seed_limit_effective": 180,
    "reserved_calls": 130
  },
  "quality_probe": {"attempted": [], "resolved": [], "source_id": "fmp-key-metrics-ttm-<date>", "calls_used": 0},
  "fcf_prefilter_excluded_symbols": [],
  "fcf_prefilter_exclusions": [{"symbol": "AAA", "lane": "core_garp", "reason": "fcf_yield_below_prefilter_floor"}]
}
```

`provider_exhausted` may waive the pool row and lane floors only together with `provider_exhausted_scope` in {`economic_candidate_universe`, `full_input`}; a missing scope fails closed (no waiver), `estimate_seed` exhaustion never waives either floor, and `pool_floor_waived` / `lane_floor_waived` record the outcomes. The `sharded_snapshot` candidate-generation mode is distinct from a bounded `provider_prefilter`: it requires a screen-ready same-read snapshot bundle, a 64-character digest binding the explicit listing-enumeration audit, manifest, universe, and all shard hashes, economic attempts and classification totals exactly equal to the frozen universe, current per-row normalization provenance, and a final pool containing only `evaluable` rows. Enumeration verification recomputes continuous full-range coverage independently for every requested exchange, and the frozen market-cap/price scope must contain the later screen request. Exact-liquidity attempts continue past empty/failed histories until the 30–50 name target is met or every eligible name has an explicit outcome; only the latter can justify a short-pool exhaustion claim. That proof supports `conclusion_scope: full_listing_universe` even though deep-dive work is budgeted to the deterministic top pool. The unit gate fails closed on unknown context: a row is exempt only when PROVEN domestic (country `US`, no non-US ISIN, not an ADR/ADS, currency USD or unstated) — a missing country, non-USD currency, non-US ISIN, or ADR/ADS flag requires `unit_reconciliation_verified: true` (listing/statement currency and ordinary-shares-per-ADS evidence); without it the row carries the blocking `unit_reconciliation_required` review and, on the direct-FMP path, resolves as `unavailable_after_enrichment`. `normalize_listing` preserves `isin` and `is_adr` for this purpose. Implausible ratios (forward P/E below 2, FCF yield above 50%, reported EPS above twice the listing price) fail the broad screen as `unit_mismatch_suspected` — suspected currency/ADS-unit mismatch, never "deep value". `sector_profile_type` is inferred from an explicit FMP-taxonomy map (`INDUSTRY_PROFILE_MAP` + family-prefix rules + BDC name needles + the `sector_profile_overrides` config pin); `capital_markets` (advisory/investment banking) is labelled but deliberately not a blocked profile. The run summary and report JSON carry a tri-state `ranking_scope` (`final_marketwide` / `final_scoped` / `diagnostic`) with per-stage coverage counts and percentages (`economic_attempt_*`, `economically_evaluable_*`, `quality_probe_*`, `deep_dive_*`); `final_marketwide` requires estimate acquisition attempted for every listing-universe symbol (exact counts) — a seed-based run is at most `final_scoped` and its conclusions never generalize to the market. Sector-profile rows (`sector_profile_type` in reit / insurance / bank / asset_manager / bdc / mlp) skip the general `excessive_leverage` hard gate and instead require sector-specific valuation evidence (`sector_specific_valuation_required`). `economic_candidate_universe_exhausted` and `economic_screen_scope_complete` are true only when bulk estimates covered every listing-universe symbol (exact `covered_symbol_count == universe_symbol_count`; not a configurable ratio), or when the same exact invariant is proven by a verified `sharded_snapshot`; merely using the bulk route (from 20% coverage) does not qualify. `latest_actual_eps` must be a verified reported figure (`latest_actual_verified: true`, `latest_actual_basis`, `latest_actual_source_ids` resolving to an annual statement accepted at or before `analysis_as_of`, or a provider row marked actual whose period has ended); otherwise the actual-derived fields are null. `growth_pattern` and `current_year_growth_pct` are derived on the consensus basis from `fy0_consensus_eps` (the provider's prior-year row, never labelled actual; `growth_pattern_basis`), and `estimate_basis_likely_adjusted` flags a >15% gap between that row and the GAAP actual. Pool rows may carry `quality_probe_attempted`, `quality_probe_resolved`, `quality_probe_source_ids`, `sbc_adjusted_fcf_yield_pct`, `provider_prefilter_flags` (`weak_fcf_support`, `earnings_recovery`, `foreign_private_issuer_review`), and the growth-basis fields `latest_actual_eps`, `fy1_eps_below_latest_actual`, `current_year_growth_pct`, `eps_growth_actual_to_fy3_pct`, `growth_pattern`.

`run-summary.json` / `NEXT_ACTION.json` add `listing_enumeration_complete`, `economic_screen_scope_complete`, `listing_universe_count`, `estimate_seed_count`, `estimate_seed_coverage_pct`, `valid_estimate_count`, `valid_estimate_coverage_pct`; `scope_complete` remains as a deprecated alias of listing-enumeration completeness. The contract-validated `screening_audit.scope` block is unchanged.
