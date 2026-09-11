---
name: us-undervalued-growth-screener
description: Autonomously screen NYSE, Nasdaq, and NYSE American operating-company stocks for undervalued-growth/GARP opportunities using forward same-basis valuation, driver-derived EPS/FCF forecasts, primary-source financial verification, SBC and dilution controls, sector and cycle normalization, auditable candidate-pool coverage, and fail-closed final reporting. Use when asked to find, screen, rank, or refresh US undervalued-growth stocks, including minimal requests with no ticker list or parameters.
---

# US Undervalued Growth Screener — v3.6 (Claude Code Direct-FMP)

## Overview

Run an end-to-end US undervalued-growth/GARP screen from a minimal request. Find companies whose EPS or FCF per share can compound enough to support attractive two- to three-year returns **without assuming multiple expansion**, while controlling for accounting basis, forecast construction, SBC, dilution, leverage, cyclicality, corporate actions, peer context, source freshness, and evidence quality.

**Claude Code is the preferred execution environment.** In Claude Code, run the local direct-FMP pipeline once. The Python process performs bulk retrieval, persistent caching, FY1 normalization, liquidity calculation, four-lane discovery, and deterministic broad screening while keeping raw FMP payloads on disk and out of the model context. Claude reads only the compact run summary and selected candidate packets, then completes SEC/IR underwriting and the existing strict evaluation sequence.

Treat a request such as **“use this skill to screen for undervalued-growth stocks” as complete**. Resolve defaults, collect current data, choose a viable acquisition path, checkpoint the work, repair obtainable blockers, and return the finished result in the same task. Never ask the user to supply a ticker list, API-plan details, output path, or a separate “continue” instruction unless the user explicitly narrows the scope.

## Non-Negotiable Runtime Preflight

Before reading or reusing any prior run artifact, verify the installed runtime:

```bash
python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py --version
python3 skills/us-undervalued-growth-screener/scripts/screen_universe.py --version
python3 skills/us-undervalued-growth-screener/scripts/build_discovery_pool.py --version
python3 skills/us-undervalued-growth-screener/scripts/build_provider_prefilter_pool.py --version
python3 skills/us-undervalued-growth-screener/scripts/normalize_estimates.py --version
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py --version
python3 skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py --version
python3 skills/us-undervalued-growth-screener/scripts/prepublish_audit.py --version
python3 skills/us-undervalued-growth-screener/scripts/bundle_run_artifacts.py --version
```

Every command must report the same metadata:

```text
skill_version = 3.6.1
schema_version = 3
contract_revision = 3.5
runtime_fingerprint = ug-v3.6.1-claude-code-direct-fmp-20260830
```

Discard and regenerate any audit, checkpoint, or snapshot whose runtime metadata differs. Do not mix scripts, assets, or run artifacts from v3.1 through v3.5. A stale or cached same-name skill is a hard execution failure, not a warning.

## Autonomous Completion Contract

For a minimal request, perform all of the following without handing control back to the user:

1. Fix `analysis_as_of` and the latest completed US regular-session close.
2. Collect current market context with field-level source support and freshness checks.
3. In Claude Code, invoke `run_pipeline.py` instead of issuing bulk FMP MCP calls. Keep provider payloads on disk and expose only compact summaries to the model.
4. Audit the requested NYSE/Nasdaq/NYSE American listing universe through adaptive, exhausted market-cap bands when provider responses saturate.
5. Build a reproducible economic candidate pool. Do not require complete financial statements across the whole market.
6. Distinguish **enrichment attempted** from **enrichment resolved**.
7. Apply the deterministic broad-screen script. Do not replace its statuses with ad hoc LLM cutoffs.
8. Select up to three economically plausible deep-dive candidates in Claude Code through deterministic multi-lane sampling: core GARP, high-growth exceptions, quality near misses, and cyclicals requiring normalization. Apply a two-name sector cap when alternatives exist. Growth thresholds remain guidelines, not isolated hard gates.
9. Resolve every row in the chosen candidate pool or record sourced exhaustion evidence.
10. Perform corporate-action preflight and primary-source underwriting for every selected symbol.
11. Save every selected symbol as a verified candidate record, including `review_required`, `screened_out`, and `excluded` outcomes.
12. Assemble the schema-v3 / contract-v3.5 snapshot.
13. Run `evaluate_candidates.py --strict --require-final`.
14. Apply the final quality eligibility gate; route weak-cash-flow, low-ROIC, overleveraged, heavily dilutive, fragile-low-case, or severe-LOE names to `conditional` or `review_required`.
15. Run `prepublish_audit.py`; repair every obtainable blocker and rerun.
16. Run `bundle_run_artifacts.py` to produce a self-contained audit ZIP containing every referenced artifact.
17. Present a formal ranking and downloadable bundle only when all gates pass.

An exit code of `2` means **continue the same execution**: enrich the queue, verify the pool-generation audit, complete selected deep dives, or repair contract failures. It never means “ask the user to say continue.” After attaching the audit, run `manage_run_state.py next-action`; execute the returned action and every returned symbol. Never ask whether to process two versus five selected names. To change the budget, rerun the broad screen first so omitted names become `deferred_by_budget`.

## Completion Semantics

### Final ranking from an audited bounded pool

A reproducibly generated bounded pool may support a **scoped final ranking** when:

```text
candidate-pool generation audit is valid
candidate_pool_exhausted = true
all_rows_resolved = true
unresolved_count = 0
queue_count = 0
all selected symbols have verified candidate records
strict final evaluation passes
```

Label the conclusion scope, such as `stratified_discovery_pool` or `provider_prefilter`. Do not imply that unexamined market listings were economically screened.

### Market-wide “no qualifying candidates”

A market-wide no-candidates conclusion requires all of the above plus full in-scope economic coverage:

```text
conclusion_scope = full_listing_universe
candidate_pool covers every in-scope listing
in_scope_missing_count = 0
at least one row was economically assessable
selected_symbols = []
```

### Bounded-pool “no qualifying candidates”

A bounded pool may conclude only:

```text
no qualifying candidates in the audited bounded pool
```

It must not claim that the entire US small/mid-cap market has no qualifying company.

Read `references/autonomous-execution.md` before a live minimal-request run.

## When to Use

Use this skill to:

- Discover and rank US-listed undervalued-growth or GARP stocks.
- Screen operating-company common stocks on NYSE, Nasdaq, and NYSE American.
- Test whether EPS or FCF-per-share growth alone supports roughly 30%–50% upside over two to three years.
- Refresh a prior screen after earnings, guidance, filings, corporate actions, or estimate revisions.
- Compare candidates on forward valuation, growth durability, ROIC, standard FCF, SBC, dilution, peers, cycle risk, and sector-specific KPIs.

Do not use it for:

- A generic single-ticker report after a stock is already selected; use `us-stock-analysis`.
- Pure dividend, momentum, technical-pattern, pre-revenue biotechnology, or merger-arbitrage screening.
- Automatic order placement.

## Prerequisites

- Python 3.9 or later.
- `requests` for the generated direct-FMP client; deterministic evaluation and audit scripts otherwise use the standard library.
- `FMP_API_KEY` in the environment for Claude Code direct mode. Never commit or print the key.
- Current SEC, company-IR, and macro sources accessible for selected-company underwriting.
- Writable `reports/` and `.cache/` directories.
- No specific paid FMP plan is assumed. Bulk endpoint failures fall back to bounded per-symbol enrichment and are disclosed in diagnostics.

## Default Scope

Unless the user specifies otherwise:

- Exchanges: NYSE, Nasdaq, NYSE American.
- Security type: active operating-company common stock.
- Market-cap focus: USD 500 million–20 billion.
- Minimum price: USD 5.
- Preferred average daily dollar volume: USD 5 million; hard floor USD 1 million.
- Claude Code provider-prefilter pool: target 30 symbols after code-side economics and verified liquidity; bounded per-symbol fallback may inspect up to 80 names without loading their provider payloads into model context.
- Deep-dive budget: three symbols by default in Claude Code, allocated across four deterministic research lanes. Once selected, every symbol must be resolved; lower the budget only by rerunning the broad screen so omitted names become `deferred_by_budget`.
- Maximum ranked output: ten, though the verified deep-dive set may be smaller.
- Minimum formal constant-multiple upside: 30% over a supported two- or three-year horizon.
- Multiple-contraction stress: current forward multiple reduced by 20%.
- Minimum analysts for a rankable consensus horizon: three, unless a fully sourced independent forecast is constructed.

### Immutable request scope and bounded execution

For a minimal request, the user-requested market-cap scope is always USD 500M–20B. Never rewrite the run config so a convenient 3–4B band becomes the requested scope. Record `user_requested_scope` and `executed_scope` separately. A narrower executed scope is incomplete unless the user explicitly requested it; context or tool-budget pressure is not authorization. Stream listing pages/bands to JSONL rather than loading every row into the conversation context.

### Liquidity evidence

Never calculate ADDV from one session's volume. Candidate generation requires a provider average-dollar-volume measure or `price × average_volume` with an explicit averaging window of at least 20 trading days and source IDs. Rows lacking valid average-liquidity evidence remain `needs_enrichment` and cannot enter the discovery pool.

### Current forward horizon

A current P/E must be explicitly NTM or FY1 and must reconcile to a positive current forward EPS, price, fiscal-year/period metadata, estimate date, analyst count, and source IDs. Generic outer-year P/E values are invalid. A missing FY1/NTM row, a range crossing zero, or extreme forecast dispersion sends the name to enrichment or `unavailable_after_enrichment`; it must never appear as a low-P/E selection.

## Result-Quality Controls

### Deterministic multi-lane candidate discovery

Do not let one global score fill the research budget with a single style or sector. Allocate the default five deep dives across these lanes when qualifying names exist:

- two core GARP names,
- one high-growth exception with Forward P/E up to 30x,
- one quality near miss whose low valuation may compensate for sub-guideline headline growth,
- one cyclical candidate that requires an explicit mid-cycle model.

Backfill unused slots by deterministic priority and limit selections to two per sector when alternatives exist. Report each selected name's `selection_lane`. The LLM may explain these decisions but may not replace them with ad hoc cutoffs.

### Formal eligibility quality gate

A name that passes the upside test is not automatically `eligible`. Formal ranking also requires:

- final score at least 70,
- SBC-adjusted FCF yield at least 3% **or** EV/FCF at most 30x,
- ROIC at least 8%,
- Net Debt/EBITDA no more than 3.0x when applicable,
- diluted-share CAGR no more than 5%,
- at least 15% upside under a supported low-consensus case,
- no severe LOE tail loss worse than the configured threshold.

One or two ordinary failures may produce `conditional`; severe FCF or LOE failures and broader weakness produce `review_required`. Never label a low-P/E/high-EV-FCF transition story as a formal winner merely because average-consensus EPS implies 30% upside.

### Independent forecast-driver evidence

Every ranked year-2/year-3 bridge must use `construction_method=independent_driver_model`. Each revenue, margin, interest, tax, share-count, FCF, and adjustment driver needs an origin and source IDs. Mark any driver solved backwards from target EPS with `target_solved=true`; this fails the bridge. A residual adjustment that merely forces the model to consensus is not independent validation.

### Publish only self-contained results

The final report is not publishable until `prepublish_audit.py` verifies all referenced audit files, counts, hashes, scenario arithmetic, candidate statuses, final-three labels, and absence of unfinished-run language. Package the entire run directory with `bundle_run_artifacts.py`; a ZIP containing only Markdown/JSON summaries is incomplete.

## Data Acquisition Strategy

### Preferred Claude Code path — direct FMP, compact model context

Run one local command:

```bash
python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py \
  --config skills/us-undervalued-growth-screener/assets/claude-code-config.example.json \
  --output-dir reports/us-undervalued-growth-screener
```

The generated FMP client reuses the repository's central `scripts/fmp_client/` source-of-truth pattern. It writes raw responses and a persistent SQLite cache to disk. Do **not** paste or read the raw provider trees into the language-model context. Read only `run-summary.json`, `NEXT_ACTION.json`, `audit/broad-screen-audit.json`, and the compact packets under `candidate-packets/`.

For a market-wide run on a plan without bulk estimates, collect every frozen
universe shard first, then screen the verified snapshot:

```bash
python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py \
  --stage collect-estimates --shard-index 0 --shard-count 8 \
  --snapshot-dir .cache/us-garp/snapshot-current \
  --config skills/us-undervalued-growth-screener/assets/claude-code-config.example.json \
  --resume

python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py \
  --stage screen-full-snapshot \
  --snapshot-dir .cache/us-garp/snapshot-current \
  --config skills/us-undervalued-growth-screener/assets/claude-code-config.example.json \
  --output-dir reports/us-undervalued-growth-screener
```

Run each shard once without `--resume`; use `--resume` only to continue an
existing partial shard. Both collection and screening are current-only:
collection fixes the estimate-normalization basis, while screening adds exact
liquidity and TTM quality evidence. The first collection binds the exhausted
listing-enumeration audit into the snapshot manifest. Screening performs a
read-only content/freshness preflight before creating provider or run
artifacts, carries a digest binding the enumeration proof and every verified
shard into downstream audits, backfills liquidity failures until 50 valid
names or full eligible exhaustion, and commits five probed deep-dive names. Read
`references/full-universe-snapshot.md` for the full collection and screening
contract.

The direct runner first attempts bulk ratios, key metrics, estimate, and EOD datasets. It falls back to bounded per-symbol enrichment only when bulk access is unavailable; a plan-gated (402/403) bulk endpoint is remembered in the cache for 30 days so later runs do not spend calls re-probing it. On the fallback path the estimate seed is a stratified sector × market-cap sample (√-weighted Hamilton quota, liquidity-ranked within cells, hash tie-break) whose size is derived from the remaining call budget; `audit/seed-audit.json` states the selection basis. Before pool selection, the top lane candidates receive a `key-metrics-ttm` quality probe (ROIC, FCF yield, EV/FCF, leverage, SBC) and a probe-resolved row with SBC-adjusted FCF yield below 1% cannot enter any lane except `high_growth_exception`. Exact 20-day ADDV work is prioritized by the four economic lanes, not by ticker order. Read `references/claude-code-execution.md` and `references/migration-v3.6-to-v3.6.1.md` for the full execution contract.

### Layer 1 — Listing-Universe Audit

Collect only fields suitable for broad coverage:

- symbol and exchange,
- active/common-stock status,
- price and quote timestamp,
- market capitalization,
- average daily dollar volume or enough data to calculate it,
- sector and industry when available.

Do not substitute a share-volume floor for an ADDV threshold. If an API can filter only by share volume, fetch broadly, calculate `price × average volume`, and apply the dollar-liquidity rule locally.

Target at least 95% listing-field completeness. Prove enumeration using provider totals and exhausted pagination or exhausted gap-free market-cap bands. Matching only the requested lower and upper market-cap endpoints is not proof of completeness.

### Layer 2 — Economic Candidate Pool

Choose the best route in this order:

1. Multi-lane provider prefilter built with `build_provider_prefilter_pool.py`. Retrieve broad rows separately for core GARP, P/E 21–30 high growth, low-P/E quality near misses, and cyclicals requiring normalization; union and audit the lanes instead of using one narrow `P/E≤20 + revenue≥8% + low-cycle` query.
2. Available estimates/fundamentals already attached to listing rows, then apply the same four-lane tags.
3. Stratified discovery fallback with `build_discovery_pool.py`, followed by enrichment.
4. User-supplied pool only when explicitly supplied.

For a bounded live run, target at least 30 resolved pool rows and at least three represented lanes unless the provider is demonstrably exhausted. A smaller convenience pool may be diagnostic but should not be described as a high-recall GARP search.

State the economic scope honestly. `run-summary.json` separates `listing_enumeration_complete` from `economic_screen_scope_complete` and reports `estimate_seed_coverage_pct` / `valid_estimate_coverage_pct`; on the bounded per-symbol fallback path the economic scope is never complete and the discovery audit records `provider_exhausted_scope: estimate_seed`. Describe such a result as "N seeded names evaluated with consensus estimates", never as a market-wide conclusion. Only `screen-full-snapshot` with a deeply verified full-universe classification and bound verification digest may emit `final_marketwide` on the per-symbol route.

Do not stop because a TTM or statement endpoint is plan-gated. Switch routes automatically.

#### Deterministic broad-screen rules

- Revenue growth, per-share growth, ROIC, leverage, and preferred valuation levels are guidelines, not isolated hard cutoffs.
- Store soft misses in `guideline_misses`.
- Use `screen_fail_reasons` only for severe disqualifiers such as non-positive standard FCF when required, negative ROIC, excessive leverage, extreme valuation unsupported by growth, or negative forward growth.
- Permit `near_miss_review` when valuation is attractive and per-share growth remains credible despite a soft revenue-growth miss.
- Permit P/E 21–30 high-growth exceptions when growth and evidence justify review.
- For cyclicality score 3–5, add `mid_cycle_normalization_required`; do not automatically reject the row.
- If `peak_profit_risk=true`, require normalization regardless of the numeric cyclicality score.
- Banks, insurers, REITs, BDCs, MLPs, and auto dealers remain blocked until sector-appropriate valuation or leverage evidence is available.
- Use the script-generated shortlist as authoritative. Do not remove GDDY-like near misses or KGS/AMKR-like cyclicals by applying an informal revenue-growth or cycle gate after the script runs.

### Layer 3 — Primary-Source Deep Dive

For selected symbols only, verify material facts with SEC filings and company IR. Vendors may supply discovery and consensus data, but primary sources must support actual revenue, cash flow, debt, shares, SBC, guidance, corporate actions, and accounting adjustments whenever available.

## Source and Evidence Rules

Use this hierarchy:

1. SEC filings.
2. Company IR.
3. Official macro/statistical sources.
4. Market-data and consensus vendors.
5. Reputable news and third-party transcripts as supplementary context only.
6. Analyst calculations and assumptions, explicitly labeled.

Every source requires:

```text
unique source ID
tier and kind
publication timestamp
retrieval timestamp
data_as_of when different
URL
non-empty supports[] array
```

Official-source labels must match official domains. A third-party transcript is never company IR. Dynamic market fields are tested against their underlying data date, not just retrieval time.

## Financial and Forecast Controls

### Standard FCF and TTM evidence

Use:

```text
standard FCF = operating cash flow − capex cash outflow
```

Capex is a positive cash outflow. Build TTM cash flow through one documented method:

- reported TTM,
- four discrete quarters, or
- latest FY + current YTD − prior-year YTD.

Every component period must have resolving source IDs. Do not double-count cumulative 10-Q cash-flow values.

### Cash classification

For ordinary operating companies, normalize reported cash and equivalents to `corporate_cash`; separately identify eligible marketable securities. For payments, custodial, marketplace, broker, or money-movement businesses, explicitly separate corporate cash from settlement/customer funds and restricted cash. Enterprise value and net debt use only shareholder-available cash.

### Driver-derived forecast bridge

Do not validate a forecast by dividing a numerator that was merely set equal to `EPS × shares`.

For EPS, independently reconstruct:

```text
forecast operating income = forecast revenue × forecast operating margin
forecast pretax income = operating income + net interest/other income
forecast GAAP net income = pretax income × (1 − tax rate)
forecast adjusted net income = GAAP net income + sourced after-tax adjustments
forecast EPS = forecast net income ÷ forecast diluted shares
```

For FCF per share, derive standard FCF from OCF and capex or a fully sourced revenue/FCF-margin model, then divide by forecast diluted shares.

The driver result must tie to the claimed metric within tolerance. Supplied numerator/denominator fields are cross-checks only. Adjusted periods must also tie the driver-derived GAAP metric and after-tax adjustments to the GAAP reconciliation.

### GAAP and adjusted metrics

Store the basis separately for current, year 2, and year 3. Mixed bases block the formal scenario. Recurrent “one-time” exclusions, SBC, acquisition costs, and intangible amortization must be described and reflected in quality/risk assessment.

### ROIC, EBITDA, and quality evidence

ROIC and EBITDA used in scoring or leverage calculations require source-linked inputs or a transparent analyst calculation. Missing evidence caps data quality and blocks an unsupported 100 score.

## Sector and Cycle Controls

### Commercial biopharma and royalty/drug-delivery platforms

Normalize aliases such as `biopharma`, `pharma`, `biotechnology`, `royalty_biopharma`, and `drug_delivery_platform` to `commercial_biopharma` when the company has commercial product/royalty exposure.

Require:

- product or royalty concentration,
- nearest material LOE/patent event,
- years to LOE,
- resolving source IDs,
- configured 6x and 8x LOE stress scenarios when material.

Missing structural-risk evidence produces `review_required` and a quality cap.

### Cyclicals and peak-profit risk

If cyclicality is 3–5 **or** `peak_profit_risk=true`, require a sourced normalization object with mid-cycle revenue/margin/EPS/FCF or a documented reason the current economics are sustainable. A risk flag without normalization is not enough for `eligible`.

## Workflow

### Step 1 — Run direct discovery in Claude Code

For Claude Code, start with the direct runner above. It creates the run directory, listing and candidate-pool audits, compact candidate packets, `run-summary.json`, and `NEXT_ACTION.json`. Follow `NEXT_ACTION.json` without asking the user for confirmation. The manual commands below remain the fallback for hosts that cannot execute direct HTTP code.

### Step 1B — Manual host fallback: create the run directory and live context

```text
reports/us-undervalued-growth-screener/<run-id>/
├── market-context.json
├── global-sources.json
├── universe.jsonl
├── discovery/
├── broad-screen/
├── run/
└── final/
```

Never copy values, URLs, dates, source IDs, or tickers from synthetic example assets into a live run.

### Step 2 — Build, normalize, and audit the candidate pool

Keep the original user-requested scope in the run contract. If bulk economics are unavailable, build a bounded discovery pool from the fully audited listing universe without narrowing the requested market-cap range. Every listing row used for pool generation must carry validated provider-average or 20+ trading-day liquidity evidence.

When provider screening is available, save one JSONL per lane and combine them deterministically:

```bash
python3 skills/us-undervalued-growth-screener/scripts/build_provider_prefilter_pool.py \
  --universe reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --lane core_garp=reports/us-undervalued-growth-screener/<run-id>/provider/core.jsonl \
  --lane high_growth_exception=reports/us-undervalued-growth-screener/<run-id>/provider/high-growth.jsonl \
  --lane quality_near_miss=reports/us-undervalued-growth-screener/<run-id>/provider/near-miss.jsonl \
  --lane cyclical_normalization=reports/us-undervalued-growth-screener/<run-id>/provider/cyclical.jsonl \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/provider \
  --analysis-as-of <ISO-8601> \
  --source-id <provider-source-id> \
  --per-lane 15 --max-pool 60 --minimum-pool 30
```

Use the emitted `provider-prefilter-audit.json` as `--discovery-audit` and `provider-prefilter-pool.jsonl` as the candidate pool.

```bash
python3 skills/us-undervalued-growth-screener/scripts/build_discovery_pool.py \
  --input reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/discovery \
  --source-id <listing-source-id> \
  --min-market-cap 500000000 \
  --max-market-cap 20000000000 \
  --user-requested-min-market-cap 500000000 \
  --user-requested-max-market-cap 20000000000 \
  --max-pool 120 \
  --per-cell 3
```

Normalize dated annual consensus rows before Broad Screen. `--estimate-as-of` is mandatory. A company without a resolving NTM/FY1 row keeps its raw outer-year data only for diagnostics and becomes `unavailable` or remains in enrichment; it cannot receive a current Forward P/E.

```bash
python3 skills/us-undervalued-growth-screener/scripts/normalize_estimates.py \
  --estimates reports/us-undervalued-growth-screener/<run-id>/discovery/raw-annual-estimates.jsonl \
  --listing-input reports/us-undervalued-growth-screener/<run-id>/discovery/discovery-pool.jsonl \
  --analysis-as-of <ISO-8601> \
  --estimate-as-of <ISO-8601> \
  --source-id <estimate-source-id> \
  --output reports/us-undervalued-growth-screener/<run-id>/discovery/enriched-candidate-pool.jsonl
```

Merge the normalized estimate rows into the bounded pool, then run `screen_universe.py`. Supply explicit retrieval bounds and listing enumeration proof. Pass the generation audit with `--discovery-audit`.

```bash
python3 skills/us-undervalued-growth-screener/scripts/screen_universe.py \
  --input reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --candidate-pool reports/us-undervalued-growth-screener/<run-id>/discovery/enriched-candidate-pool.jsonl \
  --discovery-audit reports/us-undervalued-growth-screener/<run-id>/discovery/discovery-audit.json \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/broad-screen \
  --analysis-as-of <ISO-8601> \
  --source-id <listing-source-id> \
  --candidate-source-id <estimate-source-id> \
  --candidate-generation-mode liquidity_stratified_estimates \
  --retrieval-min-market-cap 500000000 \
  --retrieval-max-market-cap 20000000000 \
  --user-requested-min-market-cap 500000000 \
  --user-requested-max-market-cap 20000000000 \
  --provider-reported-total <count> \
  --pages-fetched <count> \
  --pagination-exhausted \
  --config skills/us-undervalued-growth-screener/assets/screening-config.example.json \
  --max-deep-dives 5
```

If the command exits `2`, inspect `enrichment-queue.json` and `broad-screen-audit.json`, continue enrichment in the same task, and rerun. Pass `--candidate-pool-exhausted` only after every row is resolved and the generation audit proves the bounded scope.

### Step 3 — Checkpoint the run

Initialize and attach the screening audit:

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py init \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --analysis-as-of <ISO-8601> \
  --price-as-of <ISO-8601> \
  --session regular_close \
  --price-source-id <source-id> \
  --market-context reports/us-undervalued-growth-screener/<run-id>/market-context.json \
  --global-sources reports/us-undervalued-growth-screener/<run-id>/global-sources.json \
  --base-commit <git-sha>

python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py set-screening-audit \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --audit reports/us-undervalued-growth-screener/<run-id>/broad-screen/broad-screen-audit.json \
  --universe-artifact reports/us-undervalued-growth-screener/<run-id>/broad-screen/universe-audit-results.jsonl \
  --candidate-artifact reports/us-undervalued-growth-screener/<run-id>/broad-screen/broad-screen-results.jsonl
```

### Step 4 — Complete selected deep dives

For every selected symbol:

1. Perform corporate-action preflight first.
2. Verify the latest quarter and full year separately.
3. Build standard FCF and TTM evidence.
4. Normalize cash classification.
5. Build same-basis current/year-2/year-3 valuation periods.
6. Construct the independent forecast bridge.
7. Reconcile adjusted metrics to GAAP.
8. Source ROIC, EBITDA, SBC, dilution, peers, and sector/cycle evidence.
9. Save the candidate as `verified`, even when the final candidate status will be `review_required`, `screened_out`, or `excluded`.

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py save-candidate \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --candidate reports/us-undervalued-growth-screener/<run-id>/candidates/<SYMBOL>.json \
  --stage verified
```

### Step 5 — Complete and assemble

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py set-status \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  complete

python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py assemble \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --output reports/us-undervalued-growth-screener/<run-id>/final/final-snapshot.json
```

### Step 6 — Strict evaluation and repair loop

```bash
python3 skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py \
  --input reports/us-undervalued-growth-screener/<run-id>/final/final-snapshot.json \
  --artifact-root reports/us-undervalued-growth-screener/<run-id> \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/final \
  --language ja \
  --strict \
  --require-final
```

Do not present a formal result unless the exit code is `0` and the output contains:

```text
contract.valid = true
ranking_status = final
unprocessed_candidates = []
runtime.contract_revision = 3.5
```

### Step 7 — Prepublication audit and self-contained bundle

Locate the generated final JSON and Markdown, then run:

```bash
python3 skills/us-undervalued-growth-screener/scripts/prepublish_audit.py \
  --report-json reports/us-undervalued-growth-screener/<run-id>/final/<report>.json \
  --report-md reports/us-undervalued-growth-screener/<run-id>/final/<report>.md \
  --artifact-root reports/us-undervalued-growth-screener/<run-id> \
  --output reports/us-undervalued-growth-screener/<run-id>/final/prepublish-audit.json

python3 skills/us-undervalued-growth-screener/scripts/bundle_run_artifacts.py \
  --run-dir reports/us-undervalued-growth-screener/<run-id> \
  --report-json reports/us-undervalued-growth-screener/<run-id>/final/<report>.json \
  --report-md reports/us-undervalued-growth-screener/<run-id>/final/<report>.md \
  --output reports/us-undervalued-growth-screener/<run-id>/final/us-undervalued-growth-screen-<date>.zip
```

Both commands must exit `0`. Present the self-contained ZIP together with the report.

## Output Format

Generate both JSON and Markdown. The Markdown must include:

- runtime/version and conclusion scope,
- analysis and price timestamps,
- market context and source ledger,
- listing and candidate-pool audit/funnel,
- broad-screen selected, deferred, review, unavailable, screened-out, and excluded rows,
- formal ranking and score breakdown,
- explicit 2Y/3Y constant-multiple and 2Y/3Y 20%-contraction scenarios,
- candidate details, latest earnings, forecast bridge, GAAP reconciliation, peers, cycle/sector risks, catalysts, and invalidation conditions,
- final three only when ranking is final,
- unresolved data and global warnings.

Never combine a 2Y base case with a 3Y stress case in one unlabeled column.

## Resources

- `references/claude-code-execution.md` — direct-FMP execution, cache, compact-context, and handoff contract.
- `references/autonomous-execution.md` — same-turn execution, fallback, runtime, and completion contract.
- `references/data-contract.md` — schema-v3 / contract-v3.5 source, audit, candidate, and output contract.
- `references/methodology.md` and `methodology-ja.md` — financial and investment methodology.
- `references/research-checklist.md` — primary-source underwriting checklist.
- `references/scoring-rubric.md` — score, penalties, quality caps, and status gates.
- `references/sector-kpis.md` — sector valuation/KPI requirements.
- `references/output-template.md` — required JSON/Markdown presentation.
- `references/checkpointing.md` — atomic save/resume procedure.
- `references/review-regression-matrix.md` — observed failures and preventing tests.
- `references/migration-v3.5-to-v3.6.md` — Claude Code direct-FMP migration and operating changes.
- `references/migration-v3.4-to-v3.5.md` — prior breaking changes and upgrade steps.
- `scripts/skill_version.py` — canonical runtime/version constants.
- `scripts/fmp_client.py` — generated stable-first FMP client with SQLite cache and raw-artifact storage.
- `scripts/run_pipeline.py` — Claude Code-native direct-FMP discovery runner with compact stdout.
- `scripts/build_provider_prefilter_pool.py` — audited four-lane provider pool builder.
- `scripts/build_discovery_pool.py` — deterministic fallback pool generation with average-liquidity validation.
- `scripts/normalize_estimates.py` — identify and validate current NTM/FY1 consensus horizons.
- `scripts/screening_semantics.py` — shared fail-closed liquidity and forward-horizon semantics.
- `scripts/screen_universe.py` — listing audit and broad-screen engine.
- `scripts/manage_run_state.py` — checkpoint and final snapshot manager.
- `scripts/evaluate_candidates.py` — deterministic strict evaluator, quality eligibility gate, and report renderer.
- `scripts/prepublish_audit.py` — final artifact/count/scenario/prose audit.
- `scripts/bundle_run_artifacts.py` — deterministic self-contained audit bundle builder.
