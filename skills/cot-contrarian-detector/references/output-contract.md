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
date; all original rows remain in `markets`. The vintage of an analyzed market is
the newest analyzed row's `date`, truncated to its first 10 characters. If that
value is missing or is not a canonical `YYYY-MM-DD` date, JSON report generation
stops before writing. A longer string such as `2026-07-07-garbage` is truncated
to `2026-07-07` first and is therefore accepted. Older analyzed rows are not
validated. The CLI exits 1, prints a controlled error to stderr that names the
symbol and the rejected value, and leaves existing JSON/Markdown files unchanged
when using `--format both`. Markdown-only output retains its previous behavior.

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
FMP fetch. The three native consumers (`contrarian-setup-gate`,
`news-reaction-failure-analyzer`, and technical-analyst's weekly confirmation)
validate the consensus `run_context.data_date` and every supplied selected-market
date in `markets[].data_date` and `data_provenance.market_data_dates[symbol]`.
A stale or future selected market is rejected even inside a fresh report; a
fresh selected row cannot bypass an invalid consensus date. The oldest validated
date determines audit age. A fresh ES is not rejected solely because an unrelated
GC row/map date is stale, provided the consensus itself is valid. The map's
oldest duplicate-request date is therefore enforced when supplied.

Legacy reports may omit row/map dates; consumers then use the report date (or
selected map date when available). Explicit null/empty/invalid dates and malformed
provenance/map containers fail closed with existing detector date reason codes.
First matching row/classification behavior and first-10-character date parsing
remain unchanged. A valid in-window row/map divergence may still warn at the gate;
a stale divergence now rejects. Futures Position Sizer consumes the resulting
gate, not raw COT JSON; an unusable crowding input prevents READY_FOR_PLAN and
produces gate_not_ready / NO_TRADE downstream.
The shared validator checks metadata shape; it does not independently establish
the provider's claims, run identity or temporal consistency. Consumers outside replay apply the selected-vintage checks above without
requiring a complete provenance block or adding a strict-provenance mode.
