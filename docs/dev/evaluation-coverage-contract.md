# Common Trading Data Contract — `evaluation_coverage`

Schema version **1.0**, alongside [data provenance](data-provenance-contract.md).
Source: issue #711. Shared implementation: `scripts/evaluation_coverage.py`;
identical standalone copies ship in VCP Screener, Exposure Coach,
Downtrend Duration Analyzer, Stockbee Momentum Burst Screener and Stockbee
Exhaustion Hammer Screener.

```json
{
  "evaluation_coverage": {
    "schema_version": "1.0",
    "universe_size": 3,
    "evaluated": 1,
    "not_evaluated": 2,
    "not_evaluated_reasons": {"missing_data": 1, "plan_gated": 1},
    "verdict": "partial"
  }
}
```

Counts are nonnegative integers, never booleans. `evaluated + not_evaluated`
must equal `universe_size`. Each unevaluated member has exactly one terminal
reason; positive reason counts sum to `not_evaluated`. Reasons are extensible.

- `complete`: a nonempty universe with every member evaluated.
- `partial`: some members evaluated and some not evaluated.
- `not_evaluable`: no members evaluated, including an empty universe.

An evaluated member reached a supported terminal screening decision. A valid
filter rejection counts as evaluated; missing evidence never counts as a
negative decision. Coverage describes the declared universe and configured
screen, not provider accuracy, freshness, profitability or point-in-time validity.
Keep `data_provenance` separate; this block does not replace it.

## First producer: cross-sectional VCP screening

VCP counts unique requested symbols. A complete quote rejected by the pre-filter
is evaluated without fetching history. A member passing that filter needs 253
usable stock and benchmark closes (252-session return plus initial close), and
finite positive stock highs/lows and nonnegative volume. This also covers the
200-session moving-average comparison with 22 earlier sessions. Missing or
non-finite observations are not replaced by zero. Calculator logic is unchanged.

Reasons in this slice: `missing_data`, `invalid_data`, `provider_error`,
`plan_gated`, `insufficient_history`, `benchmark_unavailable`, `candidate_limit`
and `analysis_failed`. An observed HTTP 402 survives a later failed legacy
fallback as `plan_gated`; a successful fallback is not a coverage failure.
Only reason codes enter the report, never response bodies or credentials.

The default candidate cap can leave coverage partial even when all quotes were
fetched. `--top` and output-mode filters do not change evaluation counts.
Historical single-ticker scanning is outside this cross-sectional contract.

JSON carries the block at the top level. Markdown and stdout display evaluated /
total beside the result; incomplete zero-candidate reports say **undetermined**.
Candidate lists in partial reports describe only evaluated members. Exit zero
means reports were generated, not that evaluation was complete.

## Second producer: downtrend duration analysis

The universe is the screener rows kept after `--max-stocks`. A symbol is
evaluated when its history has at least `2 × peak window + 1` usable bars. An
empty or shorter history is `insufficient_history`: no bars is no evidence, not
a negative result. Failures are `rate_limited` (HTTP 429 after its one retry),
`plan_gated` (HTTP 402), `provider_error` (other HTTP statuses and transport
errors) and `invalid_data` (malformed rows). A 429, 401, 402 or 403 stops the
run at that symbol; the rest are `not_requested`. With nothing evaluated by
then, the run exits 1 and writes no report (#821, #822). Duration statistics
describe only evaluated symbols.

## Third producer: momentum burst screening

The universe is the unique requested symbols: the FMP universe rows, the
explicit symbols, or every symbol the offline JSON names, in each supported
shape. Offline, rows that are absent, null or an empty list are
`missing_data`, rows that are not a list or hold no usable bar are
`invalid_data`, and explicit symbols missing from the file are
`missing_data`. List items that are not an object or carry no `symbol` or
`ticker` name no symbol and are skipped. A symbol is evaluated when its bars reach a
screening decision; a filter rejection counts. `stale_price_data`,
`insufficient_history`, `invalid_price_date` (an unparsable bar date) and
`no_completed_price_data` (no bar on or before the expected session) are not
negative decisions, so they are not evaluated.
An empty fetch is `rate_limited` (HTTP 429 or the client's daily-limit stop),
`plan_gated` (HTTP 402), `provider_error` (other HTTP statuses and transport
errors), `missing_data` (the provider answered without rows) or `invalid_data`
(rows with no usable bar). Symbols after an exhausted `--max-api-calls` budget
are `not_requested`. The fetch policy is unchanged. A run with nothing
evaluated still writes both reports with `not_evaluable` coverage instead of
exiting without one.

## Fourth producer: exhaustion hammer screening

The universe and fetch reasons follow the momentum burst producer, offline
input included, and offline `--max-symbols` caps the file's symbols. `insufficient_history` is the screen's only
hard reject that is not a negative decision. This screen has no session
freshness gate, so there is no stale or no-completed-bar reason. A budget stop
during the optional near-close quote fetch makes that symbol and the rest
`not_requested`. A failed quote alone keeps the history bars, as before.

## Consumers and replay

Exposure Coach excludes declared `partial`, `not_evaluable` or malformed coverage
as missing input. It does not copy the supplied score or regime label, count the
input toward confidence, or use rejected raw sector/flow context for bias.
Warnings go to stderr; normal missing-input diagnostics and haircuts apply.
Legacy reports without this block remain supported, without a coverage guarantee.
VCP is not added as a new Exposure Coach input.

The existing replay artifact gate validates any present top-level block on
canonical JSON/YAML at producer, consumer and publication boundaries. Malformed
accounting fails before replacing published output; valid unavailable coverage
reaches the native consumer and is excluded there. Market-regime replay accepts
the optional field for progressive adoption. Regression fixtures exercise that
handoff; native breadth/uptrend coverage production and the remaining screeners
are follow-up slices of #711, not claimed implemented here.
