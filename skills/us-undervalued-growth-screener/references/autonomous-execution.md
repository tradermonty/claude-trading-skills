# Autonomous Execution Contract — v3.6 Runtime / Contract 3.5

## Purpose

Make a minimal instruction sufficient for a complete screen. The operator supplies the research request; the skill supplies defaults, current data acquisition, fallback routing, deterministic screening, primary-source underwriting, checkpointing, repair, and final reporting.

Never pause after an intermediate stage to ask for “continue.” Exit code `2` from a helper script is an internal continuation signal, not a user handoff.

In Claude Code, the mandatory default is the local direct-FMP runner. Do not consume the listing universe through repeated MCP calls. Run `run_pipeline.py`, keep raw payloads in its cache/artifact directories, and read only the compact summary, audits, and selected candidate packets.

## Runtime Identity

All run artifacts must contain the installed runtime metadata:

```json
{
  "skill_name": "us-undervalued-growth-screener",
  "skill_version": "3.6.1",
  "schema_version": 3,
  "contract_revision": "3.5",
  "runtime_fingerprint": "ug-v3.6.1-claude-code-direct-fmp-20260830"
}
```

Run every helper with `--version` before a live screen. Reject stale or mixed artifacts. This prevents a cached v3.1-v3.5 package from producing a seemingly valid contract-3.5 result.

## Request-Scope and Evidence Guardrails

- Preserve the default USD 500M–20B user request unless the user explicitly changes it.
- Never turn one convenient market-cap band into the requested scope. Stream exhausted pages/bands to disk or use a reproducible provider-prefilter grid across the entire requested range.
- Use only 20+ session average-dollar-liquidity evidence. Raw single-session volume is not ADDV.
- Run raw annual consensus rows through `normalize_estimates.py`; a current multiple must be NTM/FY1, dated, sourced, positive, and reconciled to price/EPS.
- Run `manage_run_state.py next-action` after each checkpoint and execute every returned symbol. The selected set is committed; changing its size requires rerunning the Broad Screen.

## Staged Coverage Model

### Listing coverage

Audit the complete requested listing universe for identity, active/common-stock status, quote, market cap, liquidity, sector, and exchange. This stage does not require full financial statements.

### Bounded economic pool

Generate a reproducible bounded pool by provider prefilter, available estimates, or stratified discovery. The generation audit must prove exactly how the pool was selected from the listing universe.

### Selected-name underwriting

Use SEC and company IR for the small selected set. Complete corporate-action, financial, forecast, peer, cycle, and sector evidence before ranking.

## Completion Invariants

A final ranking requires:

```text
valid runtime metadata
valid market context
valid listing-universe enumeration
valid candidate-pool generation audit
candidate pool exhausted
all candidate-pool rows resolved
queue empty
all selected symbols saved as verified candidate records
unprocessed_candidates empty
strict evaluator exit 0
```

A bounded pool can support a final **scoped ranking**. It cannot support a market-wide no-candidates claim unless every in-scope listing was economically covered.

## Attempted Is Not Resolved

`enrichment_attempted=true` records a query attempt or partial data receipt. A row becomes resolved only when it receives one of:

- `selected`
- `deferred_by_budget`
- `screened_out`
- `excluded`
- `unavailable_after_enrichment`

`unavailable_after_enrichment` requires a specific exhaustion reason and resolving source IDs.

## Deterministic Broad-Screen Authority

Always execute `screen_universe.py`. Preserve its decisions and requirements. The LLM may explain a decision but must not replace it with an informal gate.

Examples:

- Revenue growth below a guideline does not by itself remove a low-multiple, credible per-share grower.
- A cyclical candidate is routed to mid-cycle normalization, not automatically rejected.
- A high-growth 21–30x candidate may advance under the high-growth exception.
- Sector-specific rows remain review-blocked until the appropriate measure exists.


## Immutable Requested Scope

For a minimal request, retain the default USD 500M–20B request even when execution uses streaming, pagination, or a bounded discovery pool. Never rewrite the requested scope to a convenient band such as USD 3B–4B. A narrower executed scope requires explicit user authorization and must remain visibly separate from the original request.

## Liquidity and Forward-Horizon Gates

- ADDV requires provider-average evidence or price multiplied by an average-volume series covering at least 20 trading days. One-session volume is invalid.
- Current formal P/E requires NTM/FY1 metadata and a positive matching EPS. Distant outer-year estimates, missing intervening years, pre-operating names, zero-crossing ranges, or extreme dispersion cannot become the current multiple.
- Run raw annual estimates through `normalize_estimates.py` with an explicit estimate-as-of timestamp before deterministic screening.

## Selected-Set Commitment

The Broad Screen owns the selected set. Every committed selected symbol must be underwritten to a terminal verified record. The model cannot later ask whether to research two instead of three, or silently drop difficult names. Reduce the budget only by rerunning the deterministic Broad Screen and recording omitted names as `deferred_by_budget`.

A packet-stage provider-budget stop invalidates the entire broad-screen selection,
including rejected rows: every active decision becomes `deferred_by_budget`,
selection eligibility is disabled, and active lane/reason fields are removed.
The first original decision remains in `prior_decision`, with top-level selection
fields in `prior_selection`. These fields preserve the selected/rejected audit
trail only; they never authorize deep dives. Rerun in a new empty output directory
after restoring the budget.

## Provider Fallback Hierarchy

1. Use bulk listing and estimate/fundamental data when available.
2. Use a reproducible provider prefilter.
3. Build a stratified discovery pool and enrich it.
4. Use SEC/IR only for the selected set.

Do not stop because a premium endpoint is unavailable. Do not make an API-plan upgrade or CSV upload the primary user action.

## Candidate-Pool Scope

### Full-universe fundamentals

May support a market-wide final ranking or no-candidates conclusion when the full in-scope universe is economically covered and resolved.

### Provider prefilter or stratified discovery

May support a scoped final ranking after the bounded pool is audited, exhausted, and resolved. The report must state the bounded conclusion scope.

### User-supplied pool

May support only a user-supplied-pool conclusion unless the user explicitly claims broader coverage and supplies evidence.

## Tool-Budget Discipline

- Build a pool that can be completed.
- Limit deep dives to three by default for a minimal one-shot request; an explicit user override may raise the cap to five.
- Checkpoint after every selected candidate.
- Start selected deep dives while lower-priority enrichment continues when useful, but do not publish final until the pool is resolved.
- If tool budget becomes constrained, reduce the pool prospectively or resolve lower-priority rows as `deferred_by_budget`; never silently abandon them.

## Mandatory Repair Loop

After strict evaluation:

1. Read contract review reasons and candidate warnings.
2. Acquire missing obtainable evidence.
3. Correct source types, periods, cash classification, bridges, or funnel counts.
4. Rerun the deterministic evaluator.
5. Repeat until final or until a genuine unavailable condition is fully documented.

A genuine unavailable condition can lead to `review_required` or `unavailable_after_enrichment`; it does not justify invented numbers.

## Failure Behavior

When finality cannot be achieved, return a clearly labeled partial diagnostic, not a formal ranking. State the exact unresolved rows, selected candidate state, next internal action, and preserved artifact path. Do not invite the user to say “continue”; continue automatically when execution capacity remains.

## v3.5 Result-Quality and Publication Loop

1. Select through the deterministic multi-lane plan rather than a single global score.
2. Resolve every selected name and run the formal eligibility quality gate.
3. Permit `conditional` and `review_required`; do not lower quality floors to manufacture a ranked list.
4. Generate JSON and Markdown only after strict evaluation.
5. Run `prepublish_audit.py`. Exit code 2 is an internal repair instruction.
6. Run `bundle_run_artifacts.py` and present the self-contained ZIP.

The narrative layer must never announce completion before these steps finish. It must not contain “continue,” “next turn,” or similar handoff language in a final report.

### Provider-prefilter recall protection

Never use one narrow provider query as the whole economic pool. Retrieve and save four separate lanes—core GARP, high-growth exception, quality near miss, and cyclical normalization—then combine them with `build_provider_prefilter_pool.py`. This avoids systematically dropping GDDY-like low-headline-growth compounders, KGS-like high-growth exceptions, and AMKR-like cyclicals before primary-source review.
