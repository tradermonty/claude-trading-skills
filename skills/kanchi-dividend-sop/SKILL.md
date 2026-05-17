---
name: kanchi-dividend-sop
description: Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. Use when users ask for かんち式配当投資, dividend screening, dividend growth quality checks, PERxPBR adaptation for US sectors, pullback limit-order planning, or one-page stock memo creation. Covers screening, deep dive, entry planning, and post-purchase monitoring cadence.
---

# Kanchi Dividend Sop

## Overview

Implement Kanchi's 5-step method as a deterministic workflow for US dividend investing.
Prioritize safety and repeatability over aggressive yield chasing.

## When to Use

Use this skill when the user needs:
- Kanchi-style dividend stock selection adapted for US equities.
- A repeatable screening and pullback-entry process instead of ad-hoc picks.
- One-page underwriting memos with explicit invalidation conditions.
- A handoff package for monitoring and tax/account-location workflows.

## Prerequisites

### API Key Setup

The entry signal script requires FMP API access:

```bash
export FMP_API_KEY=your_api_key_here
```

### Input Sources

Prepare one of the following inputs before running the workflow:
1. Output from `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`.
2. Output from `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth.py`.
3. User-provided ticker list (broker export or manual list).

#### Expected JSON Input Format

When using `--input`, provide JSON in one of these formats:

```json
{
  "profile": "balanced",
  "candidates": [
    {"ticker": "JNJ", "bucket": "core"},
    {"ticker": "O", "bucket": "satellite"}
  ]
}
```

Or simplified:

```json
{
  "tickers": ["JNJ", "PG", "KO"]
}
```

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

## Workflow

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
- Step-1 yield = the **regular forward yield** = `latest_declared_regular
  dividend × cadence-implied frequency / price` (WS-1 `dividend_basis.py`).
  Never use `profile.lastDiv` / TTM — it lags the latest declared raise
  (defect D5) and silently bundles specials (D4).
- Apply the profile floor (income-now 4.0% / balanced 3.0% / growth-first
  1.5%) to the **regular** yield only.

Trap & freshness controls (machine-emitted by `dividend_basis.py`):
- `special_dividend_flag` → exclude specials; report regular vs ttm yield.
- `variable_policy_flag` → `FAIL` (CALM-style; not an income base).
- `cut_flag` → `FAIL`; `suspension_flag` → `FAIL`.
- `freeze_flag` → `HOLD-REVIEW` (income cash-cow exception decided in
  Step 8 synthesis only if safety is clean & unblocked).
- **Data Freshness Gate**: if the regular yield is within ±0.20pp of the
  floor (`floor_borderline`) and the latest declared dividend is not
  confirmed from an authoritative source, emit `STEP1-RECHECK` — **never a
  hard FAIL** (this is the CFR D5 fix).

### 4) Apply Kanchi Step 2 (growth and safety) — sector-dispatched

Safety is **sector-specific** — a uniform GAAP/FCF triad mis-judges banks
(FCF meaningless) and regulated utilities (FCF structurally negative).
Use `references/sector-step2-modules.md`; the deterministic dispatch is
`scripts/payout_safety.py`.

- Always compute the **payout triad**: GAAP-EPS payout, Adjusted-EPS
  payout, FCF payout. The safety verdict uses **Adjusted-EPS + FCF**
  (consumer), or the sector module (bank / utility / insurer).
- `adjusted_eps_source = UNAVAILABLE` ⇒ cap `HOLD-REVIEW` (fail-safe;
  never a silent PASS).
- GAAP↔Adjusted EPS divergence > 25% ⇒ Step-4 one-off flag.
- A merger **completed within 4 quarters** presumes GAAP EPS is distorted
  ⇒ force the adjusted path or `HOLD-REVIEW` (FITB/Comerica golden case).
- Regulated utilities: **negative FCF is not an auto-FAIL** — judge on
  FFO/debt + allowed ROE + rate-case + equity-issuance risk.

When trend is mixed but not broken, classify as `HOLD-REVIEW` instead of
hard reject.

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

### 6b) Apply Kanchi Step 4b (forward structural-event scan)

Step 4 is backward-looking; Step 4b catches *pending/recent* structural
events (the MKC-Unilever miss, D3). For each surviving candidate, run a
WebSearch + issuer-IR/SEC check using the **source hierarchy**: issuer IR
→ SEC filing (8-K/10-Q/10-K/proxy/S-4) → exchange/company deck →
reputable wire → finance portals (secondary only). Record findings into a
curated events JSON and pass it via `build_entry_signals.py --events-json`.

- Only a **major structural event** caps the verdict to `HOLD-REVIEW`
  (tx > 10% mcap, share issuance > 10–20%, leverage +0.5x EBITDA,
  control/listing/HQ change, merger-of-equals / RMT / spin-off / large
  asset sale, dividend/rating/leverage-policy change, sector-specific
  materiality, or rolling-24m cumulative M&A > 15% mcap). Minor bolt-ons
  are a CAUTION note only.
- **Pessimistic cap**: `FAILED-DEGRADED` / `SKIPPED` / `NO_EVENT_FOUND`
  on a Step-5 TRIGGERED name ⇒ `HOLD-REVIEW` + **T1 BLOCKED**. WebSearch
  unavailable (web app / offline) is treated the same — never a silent
  skip. `CLEAN_CONFIRMED` (primary source checked) is stronger than
  `NO_EVENT_FOUND` (search only).

### 7) Apply Kanchi Step 5 (buy on weakness with rules)

Set entry triggers mechanically:
- Yield trigger: current yield above 5y average yield + alpha (default `+0.5pp`).
- Valuation trigger: target multiple reached (`P/E`, `P/FFO`, or `P/FCF`).

Execution pattern:
- Split orders: `40% -> 30% -> 30%`.
- **Pre-order blockers**: if a candidate has any unresolved
  `pre_order_blockers[]` (from WS-1/2/3 — variable/cut/suspension,
  adjusted-EPS-unavailable, GAAP/Adj divergence, bank credit, utility
  FFO/debt, event-scan failed/skipped, stale dividend, …) OR
  `t1_blocked` is true, the first tranche is **blocked or downsized to a
  ≤20% tracking tranche** — not 40%.
- **Sector cluster risk**: when ≥ `SECTOR_CLUSTER_WARN_COUNT` same-sector
  names pass (e.g. many small banks share one macro beta), emit a
  portfolio-level `CLUSTER-RISK` warning.
- Require one-sentence sanity check before each *unblocked* add: "thesis
  intact vs structural break".

### 8) Produce standardized outputs

Always produce:
1. Screening table with the **actionable verdict tier**: `CLEAN-PASS`,
   `PASS-CAUTION`, `CONDITIONAL-PASS`, `HOLD-REVIEW`, `STEP1-RECHECK`,
   `FAIL` (synthesized by `verdict.py` from Step 1 + Step 2 + Step 4b +
   blockers). Include evidence per row.
2. One-page stock memo (use `references/stock-note-template.md`) with the
   per-ticker **provenance block** (price/dividend/payout/event sources,
   `unresolved_blockers`, `evidence_refs[]`).
3. Limit-order plan with split sizing, blocker gate, and invalidation.
4. Top-level **run_context** (profile, yield_floor_pct, safety_bias,
   universe_source, excluded_asset_types) so a 3%-run result is never
   silently reused inside a 4%-run.

## Output

Return and/or generate:
1. SOP screening summary in markdown.
2. Underwriting memo set based on
`references/stock-note-template.md`.
3. Optional plan artifact file generated by
`skills/kanchi-dividend-sop/scripts/build_sop_plan.py` in `reports/`.
4. Optional Step 5 entry-signal artifacts generated by
`skills/kanchi-dividend-sop/scripts/build_entry_signals.py` in `reports/`.

## Cadence

Use this minimum rhythm:
- Weekly (15 min): check dividend and business-news changes only.
- Monthly (30 min): rerun screening and refresh order levels.
- Quarterly (60 min): deep safety review using latest filings/earnings.

## Multi-Skill Handoff

Run this skill first, then hand off outputs:
1. To `kanchi-dividend-review-monitor` for daily/weekly/quarterly anomaly detection.
2. To `kanchi-dividend-us-tax-accounting` for account-location and tax classification planning.

## Guardrails

- Do not issue blind buy calls without Step 4, Step 4b and safety checks.
- Do not treat high yield as value before validating coverage quality.
- Use the **regular** forward yield for Step 1, never a special/TTM-inclusive
  figure; near-floor + unconfirmed ⇒ `STEP1-RECHECK`, not FAIL.
- A failed/skipped event scan on a TRIGGERED name ⇒ `HOLD-REVIEW` + T1
  blocked. Never silently skip Step 4b.
- Keep assumptions explicit; `adjusted_eps`/data missing ⇒ fail-safe
  `HOLD-REVIEW`, never silent PASS.

## Resources

- `scripts/thresholds.py`: **single source of truth** for all SOP
  thresholds + `SCHEMA_VERSION` (downstream schema-evolution guard).
- `scripts/dividend_basis.py`: WS-1 regular/special/variable/freeze/cut +
  Data Freshness Gate engine (pure, offline).
- `scripts/payout_safety.py`: WS-2 sector-aware GAAP/Adjusted/FCF payout
  triad + completed-merger linkage.
- `scripts/event_scanner.py`: WS-3 isolated forward/recent corporate-action
  scanner + materiality gate + pessimistic cap.
- `scripts/verdict.py`: WS-5 actionable-tier synthesis + run_context +
  evidence_ref helpers.
- `scripts/build_entry_signals.py`: orchestrator (Step 5 targets + WS-1/2/3/5
  integration). Flags: `--yield-floor`, `--events-json`, `--profile`,
  `--safety-bias`, `--universe-source`.
- `scripts/build_sop_plan.py`: deterministic SOP plan scaffold generator.
- `scripts/tests/test_golden_p0.py`: **P0 merge gate** — end-to-end frozen
  verdicts for CALM/ORI/CMCSA/MKC/CFR/cut (run via `scripts/run_all_tests.sh`).
- `references/default-thresholds.md`: human-readable threshold mirror.
- `references/sector-step2-modules.md`: Step 2 safety indicators by sector.
- `references/valuation-and-one-off-checks.md`: Step 3 valuation + Step 4 one-off.
- `references/stock-note-template.md`: one-page memo + provenance block.
