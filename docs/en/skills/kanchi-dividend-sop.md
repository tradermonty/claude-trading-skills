---
layout: default
title: "Kanchi Dividend SOP"
grand_parent: English
parent: Skill Guides
nav_order: 27
lang_peer: /ja/skills/kanchi-dividend-sop/
permalink: /en/skills/kanchi-dividend-sop/
---

# Kanchi Dividend SOP
{: .no_toc }

Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. Use when users ask for Kanchi-style dividend investing, dividend screening, dividend growth quality checks, PERxPBR adaptation for US sectors, pullback limit-order planning, or one-page stock memo creation. Covers screening, deep dive, entry planning, and post-purchase monitoring cadence.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-sop.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-sop){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Implement Kanchi's 5-step method as a deterministic workflow for US dividend investing.
Prioritize safety and repeatability over aggressive yield chasing.

---

## 2. When to Use

Use this skill when the user needs:
- Kanchi-style dividend stock selection adapted for US equities.
- A repeatable screening and pullback-entry process instead of ad-hoc picks.
- One-page underwriting memos with explicit invalidation conditions.
- A handoff package for monitoring and tax/account-location workflows.

---

## 3. Prerequisites

### API Key Setup

The entry signal script requires FMP API access:

```bash
export FMP_API_KEY=your_api_key_here
```

### Input Sources

Prepare one of the following inputs before running the workflow:
1. Output from `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`.
2. Output from `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py`.
3. User-provided ticker list (broker export or manual list).

For deterministic artifact generation, provide tickers to:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_sop_plan.py \
  --tickers "JNJ,PG,KO" \
  --output-dir reports/
```

For Step 5 entry timing artifacts:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_entry_signals.py \
  --tickers "JNJ,PG,KO" \
  --alpha-pp 0.5 \
  --output-dir reports/
```

---

### Entry CLI options and input boundaries

These options belong to `skills/kanchi-dividend-sop/scripts/build_entry_signals.py`.
The entry CLI fetches current provider data; an evaluation date alone does not
turn those downloads into a complete point-in-time data snapshot.

| Option | Meaning |
| --- | --- |
| `--tickers` | Comma-separated symbols; a nonempty list takes precedence over `--input`. |
| `--input` | JSON containing candidates/stocks/tickers. Only ticker identities are consumed; supplied screening prices or financial values do not replace provider data. |
| `--alpha-pp` | Yield increment in percentage points; default `0.5`. |
| `--yield-floor` | Explicit Step 1 yield floor in percent (for example `3.0`). Default is unset; enables the Step 1/Data Freshness assessment when supplied. |
| `--financials-json` | Per-ticker sourced financial overrides, with units, source, as-of date and document reference; accepted values are recorded as MANUAL. Documents are not fetched or verified. |
| `--events-json` | Curated corporate-event evidence for the event scan. Missing file option yields SKIPPED; an absent ticker yields NO_EVENT_FOUND. These do not establish a completed clean event review. |
| `--as-of` | Evaluation date `YYYY-MM-DD`; defaults to the local current date. |
| `--profile` | Profile label such as income-now/balanced/growth-first, recorded in run context. Does not automatically set `--yield-floor` or other thresholds. |
| `--safety-bias` | tight/medium label recorded in run context; does not itself change payout-safety rules. |
| `--universe-source` | Universe-origin provenance label recorded in run context; does not select or fetch a universe. |
| `--output-dir` | Output directory; default `reports`. |
| `--filename-prefix` | Output filename prefix; default `kanchi_entry_signals`. |
| `--sleep-seconds` | Provider-call pacing; default `0.15` seconds. |

Choose thresholds explicitly and review the recorded evidence. Event evidence is
curated input, not an automatic WebSearch performed by this CLI. The existing
withheld-target restriction still applies: adding flags or labels does not make
an unverifiable buy target actionable. Use the sourced-financial input contract with `--financials-json` for financial
overrides rather than placing them in `--input`.


## 4. Quick Start

### 1) Define mandate before screening

Collect and lock the parameters first:
- Objective: current cash income vs dividend growth.
- Max positions and position-size cap.
- Allowed instruments: stock only, or include REIT/BDC/ETF.
- Preferred account type context: taxable vs IRA-like accounts.

---

## 5. Workflow

### 1) Define mandate before screening

Collect and lock the parameters first:
- Objective: current cash income vs dividend growth.
- Max positions and position-size cap.
- Allowed instruments: stock only, or include REIT/BDC/ETF.
- Preferred account type context: taxable vs IRA-like accounts.

Load `references/default-thresholds.md` and apply baseline
settings unless the user overrides.

### 2) Build the investable universe

Start with a quality-biased universe:
- Core bucket: long dividend growth names (for example, Dividend Aristocrats style quality set).
- Satellite bucket: higher-yield sectors (utilities, telecom, REITs) in a separate risk bucket.

Use explicit source priority for ticker collection:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` output (FMP/FINVIZ).
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` output.
3. User-provided broker export or manual ticker list when APIs are unavailable.

Return a ticker list grouped by bucket before moving forward.

### 3) Apply Kanchi Step 1 (yield filter with trap flag)

Primary rule:
- `forward_dividend_yield >= 3.5%`

Trap controls:
- Flag extreme yield (`>= 8%`) as `deep-dive-required`.
- Flag sudden jump in payout as potential special dividend artifact.

Output:
- `PASS` or `FAIL` per ticker.
- `deep-dive-required` flag for potential yield traps.

### 4) Apply Kanchi Step 2 (growth and safety)

Require:
- Revenue and EPS trend positive on multi-year horizon.
- Dividend trend non-declining over the review period.

Add safety checks:
- Payout ratio and FCF payout ratio in reasonable range.
- Debt burden and interest coverage not deteriorating.

When trend is mixed but not broken, classify as `HOLD-FOR-REVIEW` instead of hard reject.

### 5) Apply Kanchi Step 3 (valuation) with US sector mapping

Use `references/valuation-and-one-off-checks.md` and apply
sector-specific valuation logic:
- Financials: `PER x PBR` can remain primary.
- REITs: use `P/FFO` or `P/AFFO` instead of plain `P/E`.
- Asset-light sectors: combine forward `P/E`, `P/FCF`, and historical range.

Always report which valuation method was used for each ticker.

### 6) Apply Kanchi Step 4 (one-off event filter)

Reject or downgrade names where recent profits rely on one-time effects:
- Asset sale gains, litigation settlement, tax effect spikes.
- Margin spike unsupported by sales trend.
- Repeated "one-time/non-recurring" adjustments.

Record one-line evidence for each `FAIL` to keep auditability.

### 7) Apply Kanchi Step 5 (buy on weakness with rules)

Set entry triggers mechanically:
- Yield trigger: current yield above 5y average yield + alpha (default `+0.5pp`).
- **Current CLI limitation (Issue #769)**: the provider's five-year average
  includes an unverified regular/special mix. The CLI currently emits no buy
  targets, including for issuers with no detected specials, until a matching
  regular-only historical average is available. It emits
  `ASSUMPTION-REQUIRED`, the withholding reason, and a non-actionable
  `HOLD-REVIEW` cap with T1 blocked (stricter FAIL/recheck decisions remain).
  Do not infer a replacement entry price from the provider diagnostic average
  or register these rows as actionable theses.
- Valuation trigger: target multiple reached (`P/E`, `P/FFO`, or `P/FCF`).

Execution pattern:
- Split orders: `40% -> 30% -> 30%`.
- Require one-sentence sanity check before each add: "thesis intact vs structural break".

### 8) Produce standardized outputs

Always produce three artifacts:
1. Screening table (`PASS`, `HOLD-FOR-REVIEW`, `FAIL` with evidence).
2. One-page stock memo (use `references/stock-note-template.md`).
3. Limit-order plan with split sizing and invalidation condition.

---

## 6. Resources

**References:**

- `skills/kanchi-dividend-sop/references/default-thresholds.md`
- `skills/kanchi-dividend-sop/references/stock-note-template.md`
- `skills/kanchi-dividend-sop/references/valuation-and-one-off-checks.md`

**Scripts:**

- `skills/kanchi-dividend-sop/scripts/build_entry_signals.py`
- `skills/kanchi-dividend-sop/scripts/build_sop_plan.py`

## Sourced financial metrics

Pass `--financials-json financials.json` to re-run with per-ticker adjusted EPS,
FFO/debt, bank, insurer or REIT metrics. Each value needs a unit, source,
`as_of` date and document reference. Accepted values are recorded as MANUAL;
source documents are user assertions and are not fetched or verified. Invalid
inputs keep HOLD-REVIEW with explicit reasons; existing FAIL stays FAIL.
See the [complete schema, fictional example and metric table](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/kanchi-dividend-sop/references/sourced-financials.md).

Use `order_ready` in JSON/CSV/Markdown as the aggregate screening readiness flag.
It requires TRIGGERED timing, CLEAN-PASS or CONDITIONAL-PASS, no final T1 block,
and no pre-order blockers. PASS-CAUTION is false. `event_t1_blocked` is event-only;
legacy `t1_blocked` is the final T1 restriction and may be false with open
blockers. Screening readiness does not authorize a trade.
