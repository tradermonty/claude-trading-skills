# Provider response contracts

Tracking: [Issue #332](https://github.com/tradermonty/claude-trading-skills/issues/332).

## Purpose

The [#328](https://github.com/tradermonty/claude-trading-skills/issues/328) failure
class is: the provider (Financial Modeling Prep, "FMP") returns HTTP 200 with a
response body that silently renamed, dropped, or nulled a field a consumer reads —
`marketCap` → `mktCap`, `exchangeShortName` instead of `exchange` — and nothing in CI
catches it. A downstream screener or analyzer just goes quietly empty. `pytest`
against a hand-written fixture doesn't help, because nobody notices the fixture
itself has drifted from what the provider actually returns.

This slice adds a **recorded, versioned response contract** per FMP endpoint: real
(sanitized) field names, types, and nullability, checked against both a fixture (in
CI, offline) and a live probe (weekly canary). It intentionally does **not** try to
lint arbitrary FMP responses generically — a single endpoint like
`/stable/company-screener` still returns `exchangeShortName` while `/stable/profile`
renamed the same concept to `exchange` (verified live 2026-09-05), so a repo-wide
static rule for legacy field names is not viable. Contracts are per endpoint.

## File layout

```
config/provider-contracts/
  fmp/
    company-screener.v1.json
    sp500-constituent.v1.json
    profile.v1.json
    quote.v1.json
    historical-price-eod-full.v1.json
    historical-price-eod-dividend-adjusted.v1.json
    historical-price-eod-light.v1.json
    earnings-calendar.v1.json
    income-statement.v1.json
    ratios.v1.json
    economic-calendar.v1.json
  trader-monty/
    market-breadth-data.v1.json
    market-breadth-summary.v1.json
    uptrend-ratio-timeseries.v1.json
    uptrend-sector-summary.v1.json
```

Location follows `config/ci-test-policy.yaml`'s convention: data lives under
`config/`, the code that reads it lives under `scripts/` — see
`scripts/provider_contracts.py` (loader/validator, stdlib-only at import time) and
`scripts/check_provider_contracts.py` (the `check` / `canary` CLI).

## Public CSV contracts (trader-monty)

The four `trader-monty` contracts cover keyless public CSVs. They feed
`market-breadth-analyzer` and `uptrend-analyzer`, two of the three required skills of
the `market-regime-daily` workflow. Because no API key is involved, their live canary
actually runs in CI. The schema above is extended additively; FMP contracts are
unchanged and default to `format: "json"`.

| Key | Applies to | Meaning |
|---|---|---|
| `format` | all | `"json"` (default) or `"csv"`. Any other value fails `check`. |
| `url` | csv only | Required for csv, forbidden for json. `https` only, host in `{tradermonty.github.io, raw.githubusercontent.com}`, no port, credentials, query string or fragment. `path` must equal the URL path and `query` must be empty. |
| `max_bytes` | csv only | Positive integer cap on the decompressed body, default 2 MiB. The timeseries sets 16 MiB because the file is 2.81 MB today and grows about 14 KB per trading day. |
| `required_values` | all | `{column: [values]}`. Each value must appear in at least one row, otherwise the fatal `missing_required_value:<column>=<value>`. Used for the `worksheet == "all"` row and the two summary metrics the breadth analyzer reads. |

`parse_csv_rows(text)` returns `(rows, parse_anomalies)` using the stdlib `csv` module:

- A UTF-8 BOM is stripped and the first line is the header.
- An empty cell becomes `None`.
- `true` / `false` in any case becomes `bool`.
- An integer literal becomes `int`; a decimal or exponent literal becomes `float`.
- Everything else stays `str`, including dates, `nan` and `inf`. A numeric column holding
  `nan` therefore reports `wrong_type:<col>:str`. This is intentional, because the breadth
  consumer rejects non-finite numbers, and the live files contain none.
- A short row maps missing cells to `None`. A row with extra cells yields one fatal
  `extra_cells` anomaly and keeps only the header keys.
- A header-only body returns `[]`, which gives `empty_response` when `min_rows >= 1`.

Fixtures are stored as already-coerced JSON rows, so a fixture and a live body go through
the same coercion. Declared types follow what the consumers accept: float-parsed columns
declare `["float", "int"]`, `["int"]` is used only for `Breadth_200MA_Trend`, which the
consumer parses with `int()`, and the timeseries `count` / `total` declare `["int", "float"]`
because the uptrend consumer's `_safe_int` is `int(float(v))` and so tolerates `840.0`. Bool
columns declare `["bool"]` (only `true`/`false` in any case) and are deliberately **stricter**
than any single consumer. The owners disagree on other spellings: market-breadth-analyzer's
`_parse_bool` accepts `1`/`0`/`yes`/`no` and raises on anything else, while
market-top-detector's (`breadth_csv_client.py`) silently reads every value other than
`true`/`1`/`yes` as `False`. A provider switch to `Y`/`N`, `1`/`0` or `yes`/`no` would
therefore produce wrong signals in one owner, so the canary reports it as fatal
`wrong_type:<col>:str` / `:int`. The summary `Value` column declares
`["int", "float", "str"]` because it mixes numbers and dates.

`market-breadth-data` records `SP500_Price`, `Breadth_200MA`, `Breadth_8MA` and `Trend` as
`legacy_aliases`. They are **consumer-tolerated alternates** read by breadth-chart-analyst
(`fetch_breadth_csv.py`), not provider history. A provider rename to one of them is still
fatal (`canonical_absent_legacy_present`) because market-breadth-analyzer and
market-top-detector would break.

### Canary fetch for CSV contracts

One GET per contract with no credentials, `allow_redirects=False`, a 30 s timeout and
`stream=True`. The body is read up to `max_bytes + 1` decompressed bytes and decoded as
`utf-8-sig`. Fetch-level fatal codes:

| Code | When |
|---|---|
| `http_status:<code>` | non-200 response, including a 3xx (redirects are never followed). Validation is skipped, so this is the only code. |
| `transport_error` | the request failed. The redacted message goes to stderr only. It replaces `http_status:-1` for CSV. |
| `body_too_large:<max_bytes>` | the body exceeded the cap. |
| `decode_error` | the body is not valid UTF-8. |
| `parse_error` | the stdlib `csv` parser rejected the body (a NUL byte, or a field over the size limit). Only that contract fails; the other contracts are still reported. |
| `extra_cells` | a row had more cells than the header. |

### Deduplicated anomalies and `count`

`validate_rows` still emits one anomaly per row. The canary and summary use
`RowValidation.summarized()`, which returns the unique `(code, severity)` pairs in
first-seen order with a `count`. A 30k-row timeseries with one renamed column therefore
reports one entry with `count: 30000`. `count` is additive and also appears in FMP reports.
Summary table cells render `code ×count` when the count is above 1.

## Contract schema

```json
{
  "schema_version": 1,
  "provider": "fmp",
  "endpoint": "profile",
  "path": "/stable/profile",
  "query": {"symbol": "AAPL"},
  "contract_version": 1,
  "recorded_on": "2026-09-05",
  "recording": "live /stable response; description/website/image/... removed",
  "owners": ["earnings-trade-analyzer", "pead-screener", "..."],
  "tier_notes": "served on free tier; comma-batched symbol returns []",
  "required_fields": {
    "symbol": {"types": ["str"], "nullable": false},
    "marketCap": {"types": ["int", "float"], "nullable": true, "reject_all_null": true},
    "exchange": {"types": ["str"], "nullable": false}
  },
  "optional_fields": ["beta", "lastDividend", "..."],
  "legacy_aliases": {
    "mktCap": {"canonical": "marketCap"},
    "exchangeShortName": {"canonical": "exchange"}
  },
  "known_gaps": [],
  "non_empty": {"min_rows": 1, "reason": "AAPL profile must never be empty"},
  "fixture": [{"...sanitized real rows...": true}]
}
```

Field semantics:

- **`required_fields`** — fields a consumer skill actually reads. Each entry
  declares `types` (JSON-ish type names: `str`, `int`, `float`, `bool`, `list`,
  `dict`) and `nullable` (whether the provider is known to legitimately return
  `null` for this field, e.g. `epsActual` before an earnings report is filed).
  The optional boolean `reject_all_null` (default `false`) additionally rejects
  a non-empty response when every row explicitly has `null` for that field.
  Individual nulls alongside a non-null value still follow `nullable`; missing
  keys and malformed rows retain their existing fatal anomaly codes. Only
  `profile.marketCap` opts in: the AAPL probe should have a populated market cap.
  Earnings fields such as `epsActual` may legitimately be all-null before
  reporting and do not opt in. Non-boolean policy values fail both the offline
  fixture check and canary validation, including on empty responses.
  Two more opt-in boolean policies exist, both default `false`. `finite: true`
  requires numeric-only `types` (`int`/`float`) and rejects NaN, infinity and
  integers outside finite float range. `iso_date: true` requires `types` to be
  exactly `["str"]` and rejects any value that is not a canonical `YYYY-MM-DD`
  calendar date. Only the light EOD contract opts in. A malformed policy value
  fails the offline fixture check and canary validation, including on empty
  responses.
- **`optional_fields`** — every other field observed live but not read by any
  in-scope consumer. Informational only; not validated.
- **`legacy_aliases`** — a field name the provider used to use (`mktCap`,
  `exchangeShortName`, `lastDiv` on the v3 API) mapped to its current canonical
  name. This is exactly the #328 signature: if a row has the legacy key but not the
  canonical one, the provider silently reverted or the endpoint changed shape.
- **`known_gaps`** — a documented, accepted gap between what the provider *used to*
  return (v3) and what `/stable` returns now, each tied to a follow-up issue number.
  Currently empty across all contracts; only `earnings-calendar` is allowed to
  carry entries here (it previously recorded #352 — the `time` field — until
  `includeReportTimes=true` restored it, see below).
- **`non_empty`** — `min_rows` is the floor below which an empty/`None` response is
  itself an anomaly (`empty_response`), not just a shape mismatch.
- **`fixture`** — real (sanitized) rows recorded live on `recorded_on`. Rules
  enforced by `check`: at least one row; every row satisfies `required_fields`;
  **no row may contain a `legacy_aliases` key** (a fixture records the current
  canonical stable shape, not the legacy one — the rename-regression unit tests
  construct the legacy-shaped row on the fly instead, see
  `scripts/tests/test_provider_contracts.py`).

**Versioning rule:** `contract_version` bumps only on a breaking change (a
required field removed, renamed, or its type narrowed/changed). Adding a new
`optional_fields` entry, widening a type set, or marking a field newly nullable is
non-breaking and does not bump the version. Adding a **new** required field that
consumers start reading (e.g. `time` after #352) is consumer-compatible and does
not bump the version; it tightens the canary only. If the addition needs a new
query parameter, record it in `query` so the canary requests the same shape.

## Anomaly / severity table

Produced by `validate_rows()` in `scripts/provider_contracts.py`:

| Code | Severity | Meaning |
|---|---|---|
| `empty_response` | fatal | `[]` / `None` where `non_empty.min_rows >= 1` |
| `not_a_list` | fatal | the response body itself is not a list |
| `row_not_object` | fatal | a list entry is not a JSON object |
| `missing_required_field:<f>` | fatal | required key absent from a row, and no legacy alias is present either |
| `null_required_field:<f>` | fatal | required key is `null` and `nullable: false` |
| `all_null_required_field:<f>` | fatal | every row explicitly has null for a field with `reject_all_null: true` |
| `invalid_contract_rule:<f>:reject_all_null` | fatal | the opt-in policy value is not a JSON boolean |
| `wrong_type:<f>:<got>` | fatal | required key's value type is outside its declared `types` |
| `non_finite_required_field:<f>` | fatal | a value is NaN, infinity or out of float range for a field with `finite: true` |
| `invalid_contract_rule:<f>:finite` | fatal | the `finite` policy is not a boolean, or its `types` are not numeric-only |
| `invalid_date_format:<f>` | fatal | a value is not a canonical `YYYY-MM-DD` date for a field with `iso_date: true` |
| `invalid_contract_rule:<f>:iso_date` | fatal | the `iso_date` policy is not a boolean, or `types` is not exactly `["str"]` |
| `missing_required_value:<col>=<val>` | fatal | a `required_values` entry (for example `worksheet=all`) appears in no row |
| `canonical_absent_legacy_present:<legacy>-><canonical>` | fatal | **the #328 signature** — the legacy field name showed up instead of the canonical one |
| `legacy_alias_present:<legacy>` | deprecation (non-fatal) | both the legacy and canonical keys are present; informational only |

A contract result is `ok = True` when it has zero fatal anomalies (a
deprecation-only result is still `ok`).

## Economic calendar contract (#332)

`economic-calendar.v1.json` records three unmodified public macro-event rows
from a 2026-10-17 HTTP 200 response (568 rows) for 2026-10-01 through 2026-10-07.
The probe uses the singular `/stable/economic-calendar` endpoint and that known
populated historical window. It joins the existing scheduled canary automatically,
adding one request to its default budget (now nine contracts). Entitlement is not
inferred from a successful recording credential: HTTP 402 remains a failure.

The owning standalone consumer checks every row before reporting or opening an
output file. It requires date/country/event/currency/impact strings and the five
nullable numeric readings (previous/estimate/actual/change/changePercentage).
An absent key is not equivalent to null. All-null readings are allowed; `unit`
and unknown additional fields are preserved. Consumer validation also rejects
blank strings, unparsable `YYYY-MM-DD HH:MM:SS` timestamps, booleans and nonfinite
numeric values. It does not constrain the impact string to High/Medium/Low:
the recording includes the valid string `"None"`.

| CLI reason | Exit | Meaning |
|---|---:|---|
| `economic_calendar_schema_drift` | 1 | Malformed event rows, missing/renamed/retyped fields, invalid dates/numbers, or the generated client's explicit non-array JSON shape error |
| `calendar_fetch_failed` | 1 | HTTP/tier/network failure, or a generic generated-client acquisition failure (including HTTP-200 null and invalid JSON after its existing bounded retry) |
| `empty_calendar_unverified` | 1 | Clean empty array; no trusted completeness classifier proves this is a quiet calendar |

These failures preserve existing output files and do not write a successful
empty report. The low-level Python fetch still returns a validated empty list,
allowing callers with an independent completeness policy to decide what to do.
The canary's `min_rows: 1` applies to its populated historical probe, not to every
arbitrary query window. No global economic-calendar holiday rule is assumed.

This slice does not promote the existing report-only canary, configure secrets,
or complete #332's remaining provider/endpoint inventory.

## Consumer zero-result reason codes

The anomaly table above is what the contract layer itself detects (fixture vs.
live, or live vs. contract in the canary). Two consumer skills go further: when
their own candidate-selection logic empties out, each prints a machine-readable
`ZERO_RESULT_REASON=<code>` line to stderr (one line, exactly that format) before
exiting, so a CI/scheduler consumer can tell "an ordinary quiet day" apart from
"the provider response shape drifted" without parsing prose. Each code maps to a
fixed exit code (and, for pead-screener, a log level); an unrecognized/`unknown`
reason falls back to exit 1 in both scripts.

**earnings-trade-analyzer** (`analyze_earnings_trades.py`, `_ZERO_RESULT_MESSAGES`;
falsy/non-list calendar bodies evaluated first in `classify_empty_calendar`;
`profiles_budget_exhausted` is also emitted directly from the
`except ApiCallBudgetExceeded` around the profile fetch in `main()`;
the rest in `explain_empty_selection` in fixed order, first match wins):

| Code | Condition | Exit |
|---|---|---|
| `no_earnings_rows` | the calendar returned `[]` for an inclusive date window containing zero XNYS sessions, or a non-empty response had no row carrying a `symbol` | 0 |
| `calendar_fetch_failed` | the calendar fetch returned no usable body (`None` on transport/HTTP/rate-limit failure, or a non-list body) | 1 |
| `earnings_calendar_empty_with_market_sessions` | the calendar returned a clean `[]`, but the identical inclusive date window sent to FMP contains at least one XNYS session; possible silent provider drop | 1 |
| `market_calendar_unavailable` | the shared XNYS calendar could not classify a clean `[]`; dependency/query failure is not treated as a quiet window | 1 |
| `profiles_budget_exhausted` | profile fetching raised `ApiCallBudgetExceeded` (including after partial retrieval), or profiles came back empty and the budget is exhausted (`api_stats["budget_remaining"] == 0` or `rate_limit_reached`) | 1 |
| `no_profiles_returned` | ≥1 earnings symbol, but `get_company_profiles` returned nothing | 1 |
| `profiles_missing_required_field:marketCap` | ≥1 profile came back, but none has a usable numeric `marketCap` (non-bool `int`/`float`, finite) | 1 |
| `profiles_missing_required_field:exchange` | ≥1 usable market cap exists, but none of those profiles has a string `exchange` | 1 |
| `all_below_market_cap_floor` | every usable profile's market cap is below `--min-market-cap` | 0 |
| `all_non_us_exchange` | every usable profile's exchange is a non-US exchange (not in `FMPClient.US_EXCHANGES`) | 0 |
| `mixed_filters_rejected_all` | usable profiles exist and were all rejected, but by a *mix* of the cap-floor and exchange filters rather than one uniform cause — treated as an ordinary empty day, not schema drift | 0 |
| *(fallback)* `unknown` / any other reason not in the table | none of the above matched | 1 |

For earnings-trade-analyzer, `profiles_budget_exhausted` exits 1: a daily 429
limit or an aborted profile fetch leaves an incomplete profile set (possibly
none at all), so no scored report can be produced — that is not a benign empty
day.

**pead-screener** (`screen_pead.py`, `_ZERO_RESULT_REASONS` / `_get_candidates_mode_a`
+ `_get_candidates_mode_b`, both return `(candidates, reason)` with `reason is None`
when `candidates` is non-empty):

| Code | Condition | Exit | Level |
|---|---|---|---|
| `no_earnings_rows` | Mode A: the FMP earnings calendar returned no rows (or no rows carried a `symbol`) for the lookback window | 0 | WARNING |
| `calendar_fetch_failed` | Mode A: the calendar fetch returned no usable body (`None` on transport/HTTP/rate-limit failure, or a non-list body); non-dict rows are ignored, never dereferenced | 1 | ERROR |
| `calendar_budget_exhausted` | Mode A: the per-day calendar fetch (`lookback_days + 1` calls) raised `ApiCallBudgetExceeded`; raise `--max-api-calls` or lower `--lookback-days` | 1 | ERROR |
| `profiles_budget_exhausted` | Mode A: profile fetching raised `ApiCallBudgetExceeded` (including after partial retrieval), or profiles came back empty and the budget is exhausted (`budget_remaining == 0` or `rate_limit_reached`) | 1 | ERROR |
| `no_profiles_returned` | Mode A: ≥1 symbol, but `get_company_profiles` returned nothing and the budget is not exhausted | 1 | ERROR |
| `profiles_missing_required_field:marketCap` | Mode A: no candidate passed the cap filter **and** no profile has a coercible `marketCap` *or* `mktCap` — see the value-based nuance below | 1 | ERROR |
| `all_below_market_cap_floor` | Mode A: at least one profile has a usable market cap, but every candidate's cap is below `--min-market-cap` | 0 | INFO |
| `no_input_candidates` | Mode B: no record in the input JSON met the `--min-grade` filter | 0 | INFO |
| *(fallback)* `unknown` / any other reason not in the table | none of the above matched | 1 | ERROR |

**pead-screener's `marketCap` check is value-based, not just key-presence.**
`_coerce_market_cap()` treats a present-but-`null` (or non-numeric, or
non-finite) `marketCap`/`mktCap` as "no usable cap" — the same as the key being
absent entirely. So a lookback window where every returned profile has
`"marketCap": null` (key present, value null) is indistinguishable from one
where the key is missing outright: both set `any_usable_cap = False` for every
symbol and exit 1 with `profiles_missing_required_field:marketCap`, on the
assumption that a batch of all-null market caps is more likely provider drift
than 100% coincidental missing fundamentals data. Contrast this with
`profile_market_cap()` (used only once a profile has already passed that
value-based usability check), which collapses a missing/null/non-numeric cap to
`0.0` so the plain `<` floor comparison never raises — that fallback is for a
*single* bad profile among otherwise-usable ones, not the "everything is null"
signal above.

## Ownership table (this slice)

| Endpoint | Owners (skills that call it) |
|---|---|
| `profile` | earnings-trade-analyzer, pead-screener, ibd-distribution-day-monitor, parabolic-short-trade-planner, canslim-screener, us-undervalued-growth-screener |
| `quote` | vcp-screener, parabolic-short-trade-planner, ftd-detector, canslim-screener, market-top-detector, us-undervalued-growth-screener, stockbee-exhaustion-hammer-screener (generated client `fetch_quote_row`) |
| `historical-price-eod-full` | 15 generated-client owners: pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor, vcp-screener, parabolic-short-trade-planner, ftd-detector, canslim-screener, macro-regime-detector, market-top-detector, us-undervalued-growth-screener, plus the five stockbee clients (#495 Batch C): stockbee-20pct-study, stockbee-episodic-pivot-analyzer, stockbee-exhaustion-hammer-screener, stockbee-momentum-burst-screener, stockbee-setup-fluency-trainer |
| `historical-price-eod-dividend-adjusted` | pair-trade-screener (generated client `fetch_pair_history`, tried before `historical-price-eod/full`; falls back to the unadjusted `close` with a stderr warning and a `price_basis` record) |
| `earnings-calendar` | pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor |
| `sp500-constituent` | vcp-screener, parabolic-short-trade-planner |
| `income-statement` | canslim-screener, dividend-growth-pullback-screener, value-dividend-screener — ad-hoc consumers (their own inline FMP fetch layer) |
| `ratios` | value-dividend-screener — ad-hoc consumer |
| `company-screener` (slice 2a) | dividend-growth-pullback-screener, downtrend-duration-analyzer, institutional-flow-tracker, pair-trade-screener, stockbee-20pct-study, stockbee-exhaustion-hammer-screener, stockbee-momentum-burst-screener, us-undervalued-growth-screener, value-dividend-screener — seven of these are generated-client consumers: dividend-growth-pullback-screener, institutional-flow-tracker, us-undervalued-growth-screener, value-dividend-screener and the three stockbee skills (stockbee-20pct-study, stockbee-exhaustion-hammer-screener, stockbee-momentum-burst-screener, via `fetch_screener_rows` on the stable-only client, #495 Batch C). Only downtrend-duration-analyzer and pair-trade-screener remain **ad-hoc consumers** with their own inline FMP fetch layer |
| `income-statement` (this slice) | canslim-screener, dividend-growth-pullback-screener, value-dividend-screener — ad-hoc consumers (their own inline FMP fetch layer) |
| `ratios` (this slice) | value-dividend-screener — ad-hoc consumer |

| `market-breadth-data` (trader-monty) | market-breadth-analyzer (`csv_client.py`), market-top-detector (`breadth_csv_client.py`), breadth-chart-analyst (`fetch_breadth_csv.py`) |
| `market-breadth-summary` (trader-monty) | market-breadth-analyzer (`csv_client.py`) |
| `uptrend-ratio-timeseries` (trader-monty) | uptrend-analyzer (`data_fetcher.py`), sector-analyst (`analyze_sector_rotation.py`), breadth-chart-analyst (`fetch_breadth_csv.py`), theme-detector (`uptrend_client.py`) |
| `uptrend-sector-summary` (trader-monty) | uptrend-analyzer (`data_fetcher.py`), sector-analyst, theme-detector, breadth-chart-analyst |

Owners are validated against `skills-index.yaml` by `check` — an owner naming a
skill directory that does not exist there is a validation error.

## `company-screener` field-usage inventory (slice 2a prerequisite)

`/stable/company-screener` (legacy alias for callers: v3 `/stock-screener`,
which returns the same fields for legacy keys) is read by 9 call sites — one
per skill, no shared helper — across 9 skills. Recorded below is what each
consumer actually reads from the
response rows, per grep-verified call sites:

| Skill | Fields read from screener rows |
|---|---|
| dividend-growth-pullback-screener | `symbol`, `price`, `companyName`, `marketCap` |
| downtrend-duration-analyzer | `symbol`, `sector`, `marketCap` |
| institutional-flow-tracker | `symbol`, `companyName`, `isEtf`, `isFund`, `isActivelyTrading`, `sector` |
| pair-trade-screener | `symbol`, `companyName`, `marketCap`, `sector`, `exchangeShortName`, `isActivelyTrading` |
| stockbee-20pct-study | `symbol`, `exchangeShortName`, `type` (defaults to `"stock"` — a key `/stable` rows do not carry), `price`, `isEtf`, `isFund` |
| stockbee-exhaustion-hammer-screener | `symbol`, `isEtf`, `isFund`, `marketCap` (defensive fallback `mktCap`) |
| stockbee-momentum-burst-screener | `symbol`, `isEtf`, `isFund`, `isActivelyTrading` (requested as `isActivelyTrading=true` and re-checked client-side), `marketCap` (defensive fallback `mktCap`) |
| us-undervalued-growth-screener | `symbol`, `companyName`, `exchange` OR `exchangeShortName`, `sector`, `industry`, `price`, `marketCap`, `volume`, `isEtf`, `isFund`, `isActivelyTrading` (client pins the three flags server-side; `normalize_listing` re-checks them client-side) |
| value-dividend-screener | `symbol`, `price`, `lastAnnualDividend`, `marketCap`, `isEtf`, `isFund` |

Two semantic notes the contract encodes:

- **`exchange` vs `exchangeShortName`.** On `/stable`, `exchange` carries the
  full venue name (`"NASDAQ Global Select"`) and `exchangeShortName` the
  exchange code (`"NASDAQ"`). They are different concepts, not aliases — the
  contract marks `exchange` optional and `exchangeShortName` required, and
  does NOT map one to the other.
- **`type` is absent on `/stable` rows.** Only stockbee-20pct-study reads it,
  and only with a default, so it is left out of `required_fields` (and the
  fixture records what the provider actually returned).

This inventory is slice 2a's deliverable: it is what makes the `company-screener`
contract's `required_fields` auditable, and it is what slice 2b's consumer
zero-result reason codes must reuse.

## Session-aware empty suspicion

The earnings-trade-analyzer is a generated consumer of the shared XNYS
calendar. For a clean HTTP 200 `[]`, it counts sessions over the exact same
inclusive `from` / `to` dates sent to FMP. Zero sessions remains the benign
`no_earnings_rows` result. One or more sessions is a fail-closed
`earnings_calendar_empty_with_market_sessions` anomaly, while a calendar
dependency or query failure is `market_calendar_unavailable`. This avoids the
exchange-holiday false positives of a weekday approximation and keeps the
standalone `.skill` install complete through the generated runtime and pinned
requirement. Non-empty lists whose rows carry no symbol retain the pre-#356
`no_earnings_rows` behavior; session suspicion applies only to the provider's
literal empty list.

## Follow-up issue: `earnings-calendar` `time` field — resolved (2026-09-06)

Previously (verified live 2026-09-05): `/stable/earnings-calendar` with no query
parameters did not return a `time` field, unlike the legacy v3 `earning_calendar`
endpoint (`bmo` / `amc` — before/after market open/close), which
`earnings-trade-analyzer` and `pead-screener` used for timing logic.

Verified live 2026-09-06: the field is not gone — it is gated behind the
`includeReportTimes=true` query parameter (the value must be the literal string
`"true"` or `"false"`; any other value, including a JSON boolean, is HTTP 400).
With that parameter, `/stable/earnings-calendar` returns `time` as `"bmo"`,
`"amc"`, or `null`, plus `periodEnding`, `fiscalPeriod`, `fiscalYear`, and
`confirmed`. About one third of rows on a typical trading day still carry
`null` (the provider has not confirmed a session for that report), so
`unknown` remains a real, expected outcome downstream — it is now backed by an
explicit `null` from the provider rather than an always-missing key.
[Issue #352](https://github.com/tradermonty/claude-trading-skills/issues/352) is
resolved: the client template requests `includeReportTimes=true`,
`earnings-calendar.v1.json` requires `time` (nullable) with an empty
`known_gaps`, and `earnings-trade-analyzer` / `pead-screener` report a
`timing_unknown_count` alongside their results so the residual `null` rate is
visible rather than silently assumed away.

## Manual fixture refresh procedure

There is no `record` subcommand in slice 1 (kept out for coverage + scope reasons).
To refresh a fixture by hand:

```bash
# Query-param auth (consistent with the canary — the FMP key is a query
# parameter, never a header, on some plans/endpoints).
curl --get "https://financialmodelingprep.com/stable/profile" \
  --data-urlencode "symbol=AAPL" \
  --data-urlencode "apikey=$FMP_API_KEY" \
  | jq 'if type == "array" then map(del(.description, .website, .image, .ceo, .phone, .address, .city, .state, .zip)) else . end'
```

For `earnings-calendar`, the `includeReportTimes=true` query parameter is
required to get the `time` field at all (see above):

```bash
curl --get "https://financialmodelingprep.com/stable/earnings-calendar" \
  --data-urlencode "from=2026-09-04" \
  --data-urlencode "to=2026-09-04" \
  --data-urlencode "includeReportTimes=true" \
  --data-urlencode "apikey=$FMP_API_KEY"
```

For `company-screener`, replay the contract's recorded query verbatim:

```bash
curl --get "https://financialmodelingprep.com/stable/company-screener" \
  --data-urlencode "marketCapMoreThan=200000000000" \
  --data-urlencode "exchange=NASDAQ,NYSE" \
  --data-urlencode "limit=5" \
  --data-urlencode "apikey=$FMP_API_KEY"
```

On refresh, re-judge two required fields before lowering their guard rule:
`sector` (nullable:false rests on the US-listed universe; FMP may legitimately
null it for odd listings) and `lastAnnualDividend` (non-payers are observed to
emit `0`, not `null` — a first-ever `null` should flip it to nullable:true with
a re-recorded fixture). See `company-screener.v1.json`'s `tier_notes` for the
same triggers.

Sanitization checklist before pasting the result into a `fixture` array:

1. Strip free-text / PII-adjacent fields: `description`, `website`, `image`,
   `ceo`, `phone`, `address`, `city`, `state`, `zip`.
2. Never include the `apikey` query value or any header in the recorded `query`.
3. Re-diff the new fixture's keys against `required_fields` +
   `legacy_aliases` + `optional_fields` — a genuinely new field goes to
   `optional_fields` (non-breaking); a removed/renamed/retyped required field is a
   **breaking change** and must bump `contract_version`.
4. Update `recorded_on` to the actual capture date.

## Canary: schedule, report shape, promotion criteria

The public CSV canary is a separate workflow, `.github/workflows/public-csv-contract-canary.yml`
(Mondays 12:30 UTC plus `workflow_dispatch`). It runs `canary --provider trader-monty`,
needs no secret and has no preflight job. It is report-only (`continue-on-error: true`)
under the same promotion policy as the FMP canary, so **the run stays green on drift**.
The `::error` / `::warning` annotations and the step summary are the only drift signal
until a promotion issue makes it fail-closed. The report is uploaded as
`public-csv-canary-report` for 30 days. `fmp-contract-canary.yml` is unchanged.

The remainder of this section describes the FMP canary.

`.github/workflows/fmp-contract-canary.yml` runs
`python3 scripts/check_provider_contracts.py canary` weekly (Monday 12:00 UTC) plus
on `workflow_dispatch`. Drift is **report-only**: only the live probe step has
`continue-on-error: true`; setup failures and the operational health gate fail
the job. A contract anomaly does not fail CI on its own today. It is still visible: a `summarize` step
(`if: always()`) writes a per-contract table to the run summary and emits `::error` /
`::warning` annotations (capped at 10 per severity, overflow aggregated as `+N more`).

The always-running, stdlib-only `health` command requires a complete report for
the current FMP contract set, consistent probe exit/status/budget evidence, and
at least one nonempty HTTP 200 response. Missing, malformed, empty, incomplete or
wrong-provider reports, a skipped/crashed probe, all non-200 responses, and all
empty responses fail the run. The probe removes any old report before execution.
Summary write errors also fail the job; available reports are still uploaded.

A nonempty HTTP 200 response is usable **for diagnosing contract drift**, even
when fields are renamed, null or have the wrong type. It does not certify that
the data is suitable for trading. Partial endpoint availability remains
report-only: if one endpoint supplies that evidence, failures of other endpoints
remain visible in the summary and annotations. This gate does not promote all
contract drift to a blocking failure. The public CSV workflow's policy is unchanged.

To inspect an FMP report offline after a probe (whose exit code is 0 for no fatal
anomalies or 1 for anomalies), run:

```bash
python3 scripts/check_provider_contracts.py health \
  --report reports/fmp-canary-report.json \
  --probe-outcome success --probe-exit-code 0
```

Use `--probe-outcome failure --probe-exit-code 1` when the probe returned 1.
The health command needs only Python's standard library, so it can report missing
evidence even after dependency setup failed. For a failed run, check setup logs,
the probe's recorded exit code, then its retained report; do not treat an empty
summary table or a missing artifact as a successful live check. Local fault tests
simulate these workflow paths without provider requests or real credentials.

The workflow has two jobs and three visible states, so "not configured" can never look
like a pass:

| State | Condition | `preflight` result |
|---|---|---|
| configured | `secrets.FMP_API_KEY` is set | passes; `canary` probes |
| disabled | secret unset and repository variable `FMP_CANARY_ENABLED` is `false` or `0` (any case) | passes with a `::notice`; `canary` is skipped |
| not configured | secret unset, no opt-out | **fails** with `::error` and a step-summary how-to; the run turns red |

A configured `FMP_API_KEY` secret takes precedence over
`FMP_CANARY_ENABLED=false`. The repository variable opts out only when the secret
is absent. Shell steps receive secrets only via `env`; tests reject key-variable
references in `run` bodies except the exact preflight nonempty check, and reject
environment-dump commands.

Setup: add a repository secret `FMP_API_KEY` (a dedicated low-quota key is
recommended), or opt out explicitly with the repository variable
`FMP_CANARY_ENABLED=false`. `preflight` carries a repository guard
(`github.repository == 'tradermonty/claude-trading-skills'`) so forks with schedules
enabled are not red every Monday; update the slug if the repository is renamed or
transferred. If `preflight` is skipped or fails, `canary` does not run.

Report (`reports/fmp-canary-report.json` in CI, uploaded as an artifact for 30
days; default local path `reports/fmp_canary_<YYYY-MM-DD>.json`, override with
`--report`):

```json
{
  "generated_at": "2026-09-05T12:00:00+00:00",
  "budget": {"max": 5, "used": 5},
  "ok": true,
  "contracts": {
    "profile": {
      "status": 200,
      "rows": 1,
      "anomalies": [],
      "deprecations": [],
      "ok": true
    }
  }
}
```

Top-level `budget.max` is the effective `--max-calls` ceiling (default: the number
of loaded contracts), `budget.used` is the number of live fetch calls actually made
(one per contract), and top-level `ok` is true only when every contract's own `ok`
is true.

The key is sent only as a `requests` `params=` value, never string-formatted into a
URL. `scripts.provider_contracts.redact_url()` is applied to the report path printed
to stdout and to transport-level error strings (a
`requests.exceptions.RequestException` message can embed the full request URL,
`apikey` included) before anything is written to the report or printed to
stdout/stderr — so a captured exception never leaks the key either.

**Promotion criteria** (making the canary fail-closed on a schedule, or gating a
PR on it) is explicitly deferred — see "Out of scope" below and the plan's
resolved review notes. Promote only after a period of the canary running green
(or with well-understood/acceptable anomalies) with no false positives.

### Generated client stderr redaction (#357)

The redaction above covers only the canary CLI. All 10 vendored `fmp_client.py`
files (rendered from `scripts/fmp_client/core_template.py.tmpl` and the four
`scripts/fmp_client/specials/*.py.tmpl`) mask `apikey=`/`api_key=` at every site
that can echo provider text. The nine clients rendered from
`core_template.py.tmpl`, `canslim.py.tmpl`, `macro.py.tmpl`, and
`market_top.py.tmpl` mask a non-200 HTTP response body and a
`requests.exceptions.RequestException` message before storing it in
`self._last_error` (the six core-family clients only) and before printing it
to stderr. The GARP client (`us-undervalued-growth-screener`) never reads
`response.text` on a non-200 response — its non-200 `WARN` lines only
interpolate the request `url`, which never carries the key since the client
injects `apikey` into the request `params` dict rather than the `url` string
— so it instead masks its request-exception `{exc}` interpolation and, for
future-proofing, the `url` interpolation in every other `WARN` line, even
though none of them can carry the key today. Because generated clients are
vendored standalone (packaged without `scripts/`), they cannot import
`scripts.provider_contracts.redact_url()`; each template instead carries a
verbatim, module-level mirror (`_APIKEY_RE` + `_redact_key()`) with a comment
naming that function as the source of truth. `scripts/tests/test_generate_fmp_client.py`
asserts the regex literal is identical across all five templates' rendered
output, so the five copies cannot silently drift apart, and
`scripts/tests/test_fmp_client_redaction.py` exercises all 10 vendored clients
at runtime to confirm a fake key never reaches stdout or stderr.

## FMP endpoint inventory (`/stable/...` paths found in `skills/*/scripts`)

Discovered via `grep -rhoE '/stable/[A-Za-z0-9_/-]+' skills/*/scripts`. `/stable/x`
and `/stable/some-bulk-endpoint` are test-fixture placeholder strings, not real
endpoints, and are excluded.

| `/stable/...` path | Recorded contract | Owners (grep-discovered) | Deferred to |
|---|---|---|---|
| `profile` | ✅ `profile.v1.json` | see ownership table above | — |
| `quote` | ✅ `quote.v1.json` | see ownership table above | — |
| `historical-price-eod/full` | ✅ `historical-price-eod-full.v1.json` | see ownership table above | — |
| `historical-price-eod/dividend-adjusted` | ✅ `historical-price-eod-dividend-adjusted.v1.json` | pair-trade-screener (SPY fixture window 2026-10-26..2026-10-30; plan-tier availability unverified) | — |
| `earnings-calendar` (v3 alias: `earning_calendar`) | ✅ `earnings-calendar.v1.json` | pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor call `get_earnings_calendar`; vcp-screener/parabolic-short-trade-planner vendor the same v3→stable compat rename but do not call it | — |
| `company-screener` | ✅ `company-screener.v1.json` | dividend-growth-pullback-screener, downtrend-duration-analyzer, institutional-flow-tracker, pair-trade-screener, stockbee-20pct-study, stockbee-exhaustion-hammer-screener, stockbee-momentum-burst-screener, us-undervalued-growth-screener, value-dividend-screener — the stockbee three are generated-client consumers (`fetch_screener_rows`, stable-only, no v3 fallback) | consumer reason codes → slice 2b |
| `sp500-constituent` (v3 alias: `sp500_constituent`) | ✅ `sp500-constituent.v1.json` | vcp-screener, parabolic-short-trade-planner call `get_sp500_constituents`; pead-screener/earnings-trade-analyzer/ibd-distribution-day-monitor vendor the compat rename but do not call it | covered |
| `income-statement` | ✅ `income-statement.v1.json` | canslim-screener, dividend-growth-pullback-screener, value-dividend-screener — ad-hoc consumers (their own inline FMP fetch layer) | — |
| `ratios` | ✅ `ratios.v1.json` | value-dividend-screener — ad-hoc consumer | — |
| `profile-bulk` | ❌ | parabolic-short-trade-planner | slice 2 |
| `aftermarket-quote` | ❌ | parabolic-short-trade-planner | slice 2 |
| `institutional-ownership/symbol-positions-summary` | ❌ | canslim-screener | slice 2 |
| `etf/holdings` | ❌ | theme-detector | slice 2 |
| `economic-calendar` | ✅ | economic-calendar-fetcher | recorded contract + consumer validation; #332 economic-calendar slice |
| `historical-price-eod/light` | ✅ | news-reaction-failure-analyzer | recorded SPY window; finite price contract |
| `commitment-of-traders-report` | ❌ | cot-contrarian-detector | slice 2 |

This table defines slice 2's completion criteria: every row marked ❌ needs its own
contract file before slice 2 can close. `company-screener` (✅ as of slice 2a)
also carries the field-usage inventory across its nine ad-hoc consumers, and the
headings above now name the two remaining deferred pieces for that endpoint:
consumer zero-result reason codes (slice 2b) and the remaining ❌ rows (each its
own endpoint contract; several need dynamic-date or weekly-report recording
windows for the canary query, e.g. `economic-calendar` / `commitment-of-traders-report`).

## All-null detection follow-up (#332)

The profile contract now detects all-null `marketCap` responses in the offline
fixture gate and the canary report, while preserving per-row nullability. This
adds a probe policy without changing the recorded provider shape, fixture capture
date, or contract version. Tests use synthetic mutations of the recorded fixture;
this follow-up does not claim a new live capture or live canary run.

## `income-statement` + `ratios` contract notes (#332 slice)

Authenticated `/stable/income-statement` (query `symbol=JNJ, limit=5`) and
`/stable/ratios` (query `symbol=JNJ, limit=3`) probes recorded 2026-10-03 and
sanitized to the fields the consumers read. Both endpoints return a flat list of
period records (one dict per reporting period), so the contract fixture is a
flat list of record dicts and `non_empty.min_rows=1` applies.

- `income-statement` `required_fields`: `symbol`/`date` non-nullable (str),
  `revenue` non-nullable (number); `netIncome` and `eps` nullable because a given
  period can legitimately report null for one, and `canslim-screener` falls back
  to `epsdiluted`. `dividendsPaid` is intentionally NOT on this contract — it is a
  cash-flow-statement field (exposed via the `netDividendsPaid` stabilize shim in
  the ad-hoc consumers), and listing it here would FATAL `missing_required_field`.
- `ratios` `required_fields`: `symbol`/`date` non-nullable; `priceToEarningsRatio`
  and `priceToBookRatio` are nullable with `reject_all_null` so a probe losing both
  is flagged while an individual null (negative-EPS / zero-book-value name) is not
  — matching the consumer's own `if pe is None or pb is None: continue` guard.
  `returnOnEquity` etc. are optional (observed null on the recorded fixture).

Issue #332 remains open: the remaining non-FMP providers, the remaining FMP endpoint contracts,
other consumer reason codes, and canary promotion remain outstanding. The
scheduled canary remains report-only. Slice 2a (`company-screener` contract +
its field-usage inventory) has landed; slice 2b is the consumer reason codes for
the nine `company-screener` consumers.

## Out of scope (this slice)

- Providers still without contracts: yfinance, CoinGecko, Binance, Alpaca and FXMacroData.
- Parser hardening for the four trader-monty contract owners that are not hardened yet.
  Their behavior is unchanged and each is a follow-up:
  - market-top-detector: `breadth_csv_client.py`, the read of `market_breadth_data.csv`.
  - breadth-chart-analyst: `fetch_breadth_csv.py`, `fetch_breadth_data` and the uptrend reader.
  - sector-analyst: `analyze_sector_rotation.py`, the uptrend timeseries read.
  - theme-detector: `uptrend_client.py`, the uptrend timeseries read.
- Every `/stable` endpoint above marked ❌ in the "Covered in slice 1" column.
- Zero-result reason codes for the `company-screener` consumers (slice 2b — the
  inventory above is 2b's prerequisite and was delivered in 2a).
- Zero-result reason codes for consumers other than earnings-trade-analyzer and
  pead-screener (outside the slice-1 scope note below).
- Fixing the `earnings-calendar` `time` gap (#352) — only documented here.
- Promoting the canary to fail-closed.
- `skills-index.yaml` schema changes.
- A separate, smaller, pre-existing gap (not touched by this PR):
  `us-undervalued-growth-screener` is missing from the `ci.yml` /
  pre-commit FMP package-drift skill lists.

## CLI reference

```bash
# Offline CI gate — validates every contract file + fixture, checks owners
# against skills-index.yaml. Zero network. Exit 1 on any error.
python3 scripts/check_provider_contracts.py check

# Live probe. --provider fmp (default) needs FMP_API_KEY and makes one GET per
# contract (query-param auth). --provider trader-monty probes the keyless public
# CSVs. --provider all runs both. Scores each response, writes a JSON report
# (default reports/<provider>_canary_<date>.json) with a top-level "provider"
# key, and exits 1 if any contract is not ok.
python3 scripts/check_provider_contracts.py canary [--provider {fmp,trader-monty,all}] [--max-calls N] [--report PATH]

# Render a canary report as markdown (stdout, or appended to --summary-file such as
# $GITHUB_STEP_SUMMARY). --github also prints ::error / ::warning annotations to
# stdout. Stdlib only. Exits 0 for missing/malformed reports (report problems never gate);
# argument or write errors exit non-zero.
python3 scripts/check_provider_contracts.py summarize --report PATH [--provider {fmp,trader-monty,all}] [--summary-file PATH] [--github]
# A report's own "provider" key picks the titles (absent or fmp: FMP titles, otherwise
# "Public CSV ..."). --provider only chooses the title when the report is missing.
```

## S&P 500 constituent recording and consumer boundary

The 2026-10-03 authenticated `/stable/sp500-constituent` probe returned HTTP
200 and 504 rows. The contract retains the first five public company records,
without credentials or request URLs. The key's subscription tier was not
established; this recording does not demonstrate free-tier availability.
Membership count is variable, so the contract requires only one or more rows.

Both owners consume `symbol` for universe membership. VCP also reads `name` and
`sector` for report labels. Although VCP defaults missing labels at runtime,
these three fields are required non-null strings in the raw provider contract
to detect label degradation. `subSector`, `headQuarter`, `dateFirstAdded`,
`cik`, and `founded` are optional; their fixture values are retained for context.

The generated clients retain their public CSV fallback when FMP is unavailable
or empty, including symbol dot-to-hyphen normalization and caching. Offline
tests cover both owners' clients with the recorded response and simulated tier
denials; these denied statuses are test scenarios, not live tier observations.
The raw canary has no CSV fallback: it requires HTTP 200 as well as valid rows.
Other statuses produce a fatal `http_status:<status>` anomaly even if their
payload matches the schema; HTTP 200 with no rows retains `empty_response`.
The existing weekly report-only workflow discovers all loaded contracts and makes
one request per contract with its dynamically computed call budget.

This endpoint completes another part of Issue #332. Other uncovered endpoints
in the inventory, cross-provider contracts, and production consumer reason
codes remain separate work; this change does not close the Issue.


## Light EOD endpoint contract (#332)

`historical-price-eod-light.v1.json` records five SPY rows returned by one
HTTP 200 `/stable/historical-price-eod/light` GET on 2026-11-06 UTC for
2026-10-26 through 2026-10-30. Only public `symbol`, `date`, `price`, and
`volume` values are retained. The subscription tier was not established;
this observation proves neither free-tier availability nor futures coverage.
HTTP denials and malformed response cases in tests are synthetic.

The sole owner is `news-reaction-failure-analyzer`. Its required fields are
non-null `date` (string) and `price` (int/float); `symbol` and `volume` are
informational. The light endpoint uses `price`. A synthetic rename to `close`
is rejected; `close` is not claimed as a historical provider alias. The
existing generic series helper still supports full-endpoint `close` rows.

The additive field rule `finite: true` requires numeric-only declared types
and rejects NaN, infinity, and integers outside finite float range with fatal
`non_finite_required_field:<field>`. Non-boolean policies or use with nonnumeric
types produce `invalid_contract_rule:<field>:finite`, including on empty bodies.
Existing contracts without this opt-in retain their current behavior. Nullable
fields, if any, still follow their separate nullability rule.

The contract's `date` field opts in to `iso_date: true`, so the canary flags a
row dated `10/30/2026` with `invalid_date_format:date`, matching the consumer.
The consumer additionally checks canonical ISO dates before sorting and strips
any extra `close` field so it cannot override the validated light `price`. Malformed
bodies, rows, or required fields return static `schema_drift:<reason>` errors;
values are not echoed. Information cutoff: a row whose `date` parses as canonical
ISO and is strictly after `as_of` is ignored by validation and dropped before
analysis, so a malformed bar the run would discard cannot change which source is
used. A row whose date cannot be parsed still counts as drift, because it cannot
be placed relative to the cutoff. Non-list bodies and non-object rows are always
drift, and any malformed row dated at or before `as_of` rejects the whole source.
The reason is reported in `run_context.price_attempts` (JSON) and a `Price attempts`
line (Markdown) as a static code: `schema_drift:<reason>`, `http_<NNN>`,
`invalid_json`, `request_exception`, `0 rows`, `no_rows_before_as_of` or `ok`.
Response text and the API key are never emitted. A literal empty list retains
attempt status `0 rows`.
A valid series containing only dates after `as_of` reports
`no_rows_before_as_of`. Both cases advance the source chain; exhausting it
retains `no_price_source` and the existing insufficient-evidence verdict.

The scheduled FMP canary discovers the new contract and adds one GET to its
computed budget. It reuses the fixed recorded SPY window to test shape and
nonemptiness, without holiday-dependent empty windows; it does not measure
current-data freshness. Probe errors remain unmasked by consumer fallbacks.
The existing operational-health versus report-only schema-drift policy is
unchanged. No workflow was dispatched or repository secret configured here.

Issue #332 remains open for other uncovered endpoints/providers, broader
consumer reason codes and remaining operational acceptance.
