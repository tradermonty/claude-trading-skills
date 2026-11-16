# Signal postmortem FMP migration (#495)

This is the signal-postmortem slice of Batch D. Batches A/B/C and pair-trade
are already migrated; #495 stays open for the other skills. The plan was
independently reviewed twice. The final plan includes lazy dependency loading
and batch-scoped rate-limit state with cleanup.

## Final implementation plan

1. Register a target-only generated client extension for the caller's exact
   historical date range. Delegate HTTP, retry, timeout and secret redaction
   to the shared transport. Remove local HTTP and the legacy v3 fallback.
2. Load the sibling client lazily and isolate its module name from other skills.
   Preserve manual/help operation without requests, and standalone use outside
   this repository.
3. Keep one lazy client per batch so timing and exhausted-limit state survive
   between signals. Close its session and restore the prior scope on every exit.
4. Preserve raw price evidence until validation, including malformed/duplicate
   dates and non-finite values. Keep the supported historical envelopes and
   exact requested-range filtering. Never turn unavailable evidence into a
   flat outcome.
5. Exercise real CLI paths and fake transport: query parameters, retry/exhaustion,
   invalid data, redaction, cleanup, import isolation and absent dependencies.
   Run generator drift, skill/provider/CLI checks and standalone package smoke.
6. Independently review the complete patch before commit and PR; retain #495
   as an open umbrella and do not merge or call live providers.

## Contract and limits

The recorder retains `fetch_price_data(ticker, start_date, end_date, api_key)`.
The target extension returns raw JSON from `/stable/historical-price-eod/full`;
`observed_prices` validates it before any return or outcome is calculated.
List responses and legacy-shaped `historical` / matching `historicalStockList`
envelopes remain supported, without requesting legacy endpoints. Missing or
ambiguous data returns an empty price map. Only one matching symbol envelope is
accepted. A partial batch keeps only supported outcomes; an entirely skipped
batch exits 1 and may retain its diagnostic summary.

The shared core can emit redacted transport exception details; the adapter's
own failure summary contains no credential, response body or URL. Transport
rate-limit state is reused within a batch. Direct wrapper calls own a temporary
session. No normalizer silently drops rows, deduplicates or truncates history
before validation. Other generated clients must remain byte-identical.

All tests use fictional data and fake transport. Local and hosted CI results
are separate evidence and do not establish live provider availability, trading
correctness, or investment performance. No brokerage access is involved.
