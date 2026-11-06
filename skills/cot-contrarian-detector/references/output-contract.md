# COT report output contract

The JSON report retains schema version `1.0`, `skill`, `run_context`, ranked
`markets`, and `skipped`. It adds a top-level `data_provenance` object following
Common Trading Data Contract version `1.0` (repository documentation:
`docs/dev/data-provenance-contract.md`). Markdown output is unchanged.

| Field | Meaning |
|---|---|
| `schema_version` | `"1.0"` for the common provenance block |
| `provider` | `fmp` |
| `endpoint` | `commitment-of-traders-report`; no URL or credentials |
| `retrieved_at` | Actual UTC collection-completion instant, also retained in `run_context.retrieved_at` |
| `as_of` | Oldest analyzed market's reported `data_date`; not the request cutoff or publication date |
| `timezone` | `America/New_York` for CFTC business dates |
| `adjusted`, `point_in_time`, `survivorship_free`, `corporate_actions_handled` | All `false`: these properties have not been verified |
| `as_of_basis` | `oldest_analyzed_market_report`, or `request_cutoff_no_analyzed_data` if every market was skipped |
| `market_data_dates` | Map from analyzed symbol to oldest observed report date; empty when no market was analyzed |

`run_context.as_of` remains the requested cutoff and `run_context.data_date`
remains the consensus date for backward compatibility. Consult individual
market dates before assuming all markets have the same vintage. If a symbol
is requested repeatedly and yields different dates, the map retains its oldest
date; all original rows remain in `markets`. An analyzed
market with a missing, malformed or noncanonical `YYYY-MM-DD` date stops JSON
report generation before writing. The CLI exits 1, prints a controlled error to
stderr, and leaves existing JSON/Markdown files unchanged when using `--format
both`. Markdown-only output retains its previous behavior.

An all-skipped report still records the real retrieval instant and skipped
reasons. Its provenance `as_of` is only the query cutoff, explicitly labeled by
`as_of_basis`; it is not evidence of available observations or fresh market
data. An empty `markets` list must not be interpreted as an absence of crowding
in markets whose data could not be analyzed.

A historical `--as-of` request is fetched now: FMP may serve revised history.
Neither this metadata nor the COT index establishes point-in-time availability,
a publication timestamp, adjustment handling or a survivorship-free universe.
The source's lagged COT dates are retained without guessing a release date.

In the bundled Shapiro replay, `cot_crowding_report` requires a schema-valid
provenance block at production, consumer handoff and publication boundaries.
The replay uses an approved **fictional manual-contract fixture**, not a live
FMP fetch. Existing crowding-date checks reject stale/future report dates.
The shared validator checks metadata shape; it does not independently establish
the provider's claims, run identity or temporal consistency. Native consumers
outside replay keep their existing contracts; this slice adds no new strict
provenance mode to those consumers.
