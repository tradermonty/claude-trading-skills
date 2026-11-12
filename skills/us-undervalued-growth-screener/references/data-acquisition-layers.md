# Data Acquisition Layers

Moved verbatim from `SKILL.md`.

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
