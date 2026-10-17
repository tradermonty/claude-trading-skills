# FMP client migration: dividend/value Batch B (#495)

The following standalone skills now vendor generated `scripts/fmp_client.py`
from `scripts/fmp_client/registry.py`, the shared core and `dividend_stable`
extension:

- `value-dividend-screener`
- `dividend-growth-pullback-screener`
- `kanchi-dividend-sop`

Their main scripts keep thin `FMPClient` subclasses for domain methods and
return conventions. FMP HTTP/authentication, error redaction, timeouts, rate
limiting, JSON retry and 429 handling run in the generated client. FINVIZ
transport remains separate. The existing fourteen generated clients retain
byte-identical output in this migration, including the economic-calendar client
used by PR #572.

## Preserved behavior

CLI `--api-key` / `FMP_API_KEY` precedence, successful report formats, financial
calculations, filters, ranking and Kanchi review blockers are unchanged.
Supported statement/profile/quote/ratio/dividend calls target `/stable` through
query parameters. Legacy *internal endpoint names* still work, for example
`income-statement/AAA` maps to `/stable/income-statement?symbol=AAA` without
putting the symbol in the URL path.

The dividend-history wrapper, `returnOnEquity` → `roe`, and
`netDividendsPaid` → `dividendsPaid` aliases preserve the readers' shapes, scale
and signs. Kanchi still restores `lastDividend` → `lastDiv` and requests one
quote/profile per symbol. Historical-price lists stay most-recent-first and
are truncated to the requested count. Value returns `[]` on history failure;
pullback returns `None`. Other statement/dividend None/[]/{} conventions remain
in their domain adapters.

Kanchi retains its `sleep_seconds` and `timeout` constructor arguments and its
`api_calls` view. The delay is now the shared minimum interval between requests,
not a sleep after successful responses. `api_calls` reads the shared counter,
including retried HTTP responses. The configurable timeout branch is enabled
only for these three new generator targets; existing targets still emit their
original fixed-timeout transport.

## Intentional transport changes

- The migrated domain paths use stable endpoints only. A 402/403, empty history,
  or unsupported endpoint does not attempt retired v3 URLs. Unknown internal
  endpoint names fail without HTTP. Historical query windows use the shared
  America/New_York calendar date rather than the machine's local date.
- All three inherit the shared single 429 retry (60-second wait) and fail closed
  after the second 429. Kanchi previously waited two seconds for its retry.
- Malformed HTTP-200 JSON is retried once, then returns the shared failure value.
- Provider/transport errors mask raw and URL-encoded API-key echoes. Shared
  transport exceptions remain visible even when a low-level caller asks for
  quiet HTTP diagnostics. This is not a promise that the separate FINVIZ client
  has the same logging policy.

The generated client drift gate covers seventeen targets. CI and pre-commit
package checks include these three archives. Tests run each skill in isolation
because standalone bundles intentionally share module names such as
`fmp_client`. The new fake-transport integration test also imports each bundle
in its own Python process and does not need a live API key.

This PR completes the proposed Batch B, not the remaining #495 batches.
