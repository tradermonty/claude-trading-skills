---
layout: default
title: "US Undervalued Growth Screener"
grand_parent: English
parent: Skill Guides
nav_order: 72
lang_peer: /ja/skills/us-undervalued-growth-screener/
permalink: /en/skills/us-undervalued-growth-screener/
generated: true
---

# US Undervalued Growth Screener
{: .no_toc }

Autonomously screen NYSE, Nasdaq, and NYSE American operating-company stocks for undervalued-growth/GARP opportunities using forward same-basis valuation, driver-derived EPS/FCF forecasts, primary-source financial verification, SBC and dilution controls, sector and cycle normalization, auditable candidate-pool coverage, and fail-closed final reporting. Use when asked to find, screen, rank, or refresh US undervalued-growth stocks, including minimal requests with no ticker list or parameters.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/us-undervalued-growth-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/us-undervalued-growth-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Run an end-to-end US undervalued-growth/GARP screen from a minimal request. Find companies whose EPS or FCF per share can compound enough to support attractive two- to three-year returns **without assuming multiple expansion**, while controlling for accounting basis, forecast construction, SBC, dilution, leverage, cyclicality, corporate actions, peer context, source freshness, and evidence quality.

**Claude Code is the preferred execution environment.** In Claude Code, run the local direct-FMP pipeline once. The Python process performs bulk retrieval, persistent caching, FY1 normalization, liquidity calculation, four-lane discovery, and deterministic broad screening while keeping raw FMP payloads on disk and out of the model context. Claude reads only the compact run summary and selected candidate packets, then completes SEC/IR underwriting and the existing strict evaluation sequence.

Treat a request such as **“use this skill to screen for undervalued-growth stocks” as complete**. Resolve defaults, collect current data, choose a viable acquisition path, checkpoint the work, repair obtainable blockers, and return the finished result in the same task. Never ask the user to supply a ticker list, API-plan details, output path, or a separate “continue” instruction unless the user explicitly narrows the scope.

**Deep-dive budget and lane coverage:** The bounded direct-FMP path defaults to `max_deep_dive_candidates: 3`. Three selected names cannot represent all four research lanes. The default lane targets are core GARP 2, high-growth exception 1, quality near miss 1, and cyclical normalization 1 (five slots total). A three-name run prioritizes candidates across lanes; it does not promise one name per lane. For a five-slot lane-first selection, set `max_deep_dive_candidates: 5` in a local copy of `assets/claude-code-config.example.json` and rerun the bounded pipeline with that config. Eligible candidates and diversification preferences still determine actual lane representation. The separate full-snapshot path requires `full_snapshot_deep_dive_candidates: 5`. See `references/claude-code-execution.md` for selection and budget-change details.

---

## 2. When to Use

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

---

## 3. Prerequisites

- Python 3.9 or later.
- `requests` for the generated direct-FMP client; deterministic evaluation and audit scripts otherwise use the standard library.
- `FMP_API_KEY` in the environment for Claude Code direct mode. Never commit or print the key.
- Current SEC, company-IR, and macro sources accessible for selected-company underwriting.
- Writable `reports/` and `.cache/` directories.
- No specific paid FMP plan is assumed. Bulk endpoint failures fall back to bounded per-symbol enrichment and are disclosed in diagnostics.

---

## 4. Quick Start

```bash
Never copy values, URLs, dates, source IDs, or tickers from synthetic example assets into a live run.

### Step 2 — Build, normalize, and audit the candidate pool

Keep the original user-requested scope in the run contract. If bulk economics are unavailable, build a bounded discovery pool from the fully audited listing universe without narrowing the requested market-cap range. Every listing row used for pool generation must carry validated provider-average or 20+ trading-day liquidity evidence.

When provider screening is available, save one JSONL per lane and combine them deterministically:
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/us-undervalued-growth-screener/references/autonomous-execution.md`
- `skills/us-undervalued-growth-screener/references/checkpointing.md`
- `skills/us-undervalued-growth-screener/references/claude-code-execution.md`
- `skills/us-undervalued-growth-screener/references/data-contract.md`
- `skills/us-undervalued-growth-screener/references/full-universe-snapshot.md`
- `skills/us-undervalued-growth-screener/references/methodology-ja.md`
- `skills/us-undervalued-growth-screener/references/methodology.md`
- `skills/us-undervalued-growth-screener/references/migration-v1-to-v2.md`
- `skills/us-undervalued-growth-screener/references/migration-v2-to-v3.md`
- `skills/us-undervalued-growth-screener/references/migration-v3-to-v3.1.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.1-to-v3.2.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.2-to-v3.3.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.3-to-v3.4.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.4-to-v3.5.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.5-to-v3.6.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.6-to-v3.6.1.md`
- `skills/us-undervalued-growth-screener/references/original-prompt-mapping.md`
- `skills/us-undervalued-growth-screener/references/output-template.md`
- `skills/us-undervalued-growth-screener/references/research-checklist.md`
- `skills/us-undervalued-growth-screener/references/review-regression-matrix.md`
- `skills/us-undervalued-growth-screener/references/scoring-rubric.md`
- `skills/us-undervalued-growth-screener/references/sector-kpis.md`

**Scripts:**

- `skills/us-undervalued-growth-screener/scripts/build_discovery_pool.py`
- `skills/us-undervalued-growth-screener/scripts/build_provider_prefilter_pool.py`
- `skills/us-undervalued-growth-screener/scripts/bundle_run_artifacts.py`
- `skills/us-undervalued-growth-screener/scripts/coverage_semantics.py`
- `skills/us-undervalued-growth-screener/scripts/estimate_snapshot.py`
- `skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py`
- `skills/us-undervalued-growth-screener/scripts/fmp_client.py`
- `skills/us-undervalued-growth-screener/scripts/manage_run_state.py`
- `skills/us-undervalued-growth-screener/scripts/normalize_estimates.py`
- `skills/us-undervalued-growth-screener/scripts/prepublish_audit.py`
- `skills/us-undervalued-growth-screener/scripts/research_contract.py`
- `skills/us-undervalued-growth-screener/scripts/run_pipeline.py`
- `skills/us-undervalued-growth-screener/scripts/screen_universe.py`
- `skills/us-undervalued-growth-screener/scripts/screening_semantics.py`
- `skills/us-undervalued-growth-screener/scripts/skill_version.py`
