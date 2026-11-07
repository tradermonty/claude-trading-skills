# Pair Trade FMP Client Migration

Tracking: #495, remaining Batch D. This slice migrates pair-trade-screener;
the tracker remains open for other skills.

Both pair adapters load their sibling generated client under a skill-specific
module name, so another skill's cached `fmp_client` cannot supply the wrong
implementation. The registry selects a budget-free family-B client and a
pair-only response guard. Existing generated clients remain byte-identical.
The full-EOD response contract lists this generated consumer as an owner, and
tests feed its recorded fixtures through both public adapters.

## Endpoints and price basis

The sector screener uses `/stable/company-screener` only. It retains sector,
market-cap and limit parameters, active stock filtering and output mapping. The
obsolete local v3 screener fallback is removed. A failed, empty or non-list
response is a controlled failure. Rows without a usable `symbol` are dropped
with one stderr warning instead of failing the whole sector.

`/stable/historical-price-eod/full` serves dividend-unadjusted `close` and no
`adjClose` (verified live 2026-11-07, KO 2020-01-02 close 54.99 against
adjClose 44.87 on the dividend-adjusted endpoint). Pair statistics need
adjusted prices, so history is fetched in this order:

1. `/stable/historical-price-eod/dividend-adjusted` (recorded contract
   `historical-price-eod-dividend-adjusted.v1.json`). Uses `adjClose`.
   Recorded `price_basis` is `dividend_adjusted`.
2. If that endpoint is unavailable or returns nothing valid, the canonical
   stable `full`, then v3, fallback. `adjClose` is used when supplied
   (`price_basis` `adj_close`), otherwise the raw `close` (`price_basis`
   `close`).

Whether the dividend-adjusted endpoint is available on a given plan tier is
unverified. A symbol that ends on raw `close` produces one stderr warning that
names it. `find_pairs` records `metadata.price_basis` as a symbol-to-basis map
in its JSON output, `analyze_spread` prints the basis of both legs, and a run
that mixes adjusted and raw series prints an extra warning. These fields are
additive; no existing output field is renamed.

## Batch behavior

A batch shares one client, so the daily-limit latch and the per-endpoint
breakers survive between symbols. Once the client reports the daily limit,
remaining symbols are skipped with no HTTP and no sleep, and symbols fetched
earlier are kept. `fetch_historical_prices` still builds its own client when
none is passed. Breaker state is per client, so independent single-symbol calls
cannot disable each other. Three consecutive failures disable an endpoint for
the rest of that client's batch, as in the other generated clients.

## History window and validation

History is requested without a date bound, preserving latest-N-row behavior for
sparse or delisted custom symbols. The two adapters keep their 730/365
defaults, chronological Series and ticker name. The target-only guard checks
flat and wrapped row shapes, symbol types, dates and the selected price, but
only for the rows inside the requested lookback window, so one malformed row
further back no longer drops the symbol. Dates may be `YYYY-MM-DD` or
`YYYY-MM-DD HH:MM:SS`. The guard emits static reasons and advances the existing
historical fallback on bad data. Shared header authentication, redaction,
timeout and bounded retries replace raw requests. No live provider access or
plan-tier verification occurs in tests.

Regenerate with `python3 scripts/generate_fmp_client.py`, then package with
`python3 scripts/package_skills.py --skill pair-trade-screener`. CI and pre-commit
check this client's source and archive. Transport tests use fake Sessions and
fresh interpreters, including a foreign-client cache, sparse history, failures
and redaction.
