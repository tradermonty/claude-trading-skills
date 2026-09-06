# Provider response contracts (FMP, slice 1)

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
    profile.v1.json
    quote.v1.json
    historical-price-eod-full.v1.json
    earnings-calendar.v1.json
```

Location follows `config/ci-test-policy.yaml`'s convention: data lives under
`config/`, the code that reads it lives under `scripts/` — see
`scripts/provider_contracts.py` (loader/validator, stdlib-only at import time) and
`scripts/check_provider_contracts.py` (the `check` / `canary` CLI).

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
    "marketCap": {"types": ["int", "float"], "nullable": true},
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
| `wrong_type:<f>:<got>` | fatal | required key's value type is outside its declared `types` |
| `canonical_absent_legacy_present:<legacy>-><canonical>` | fatal | **the #328 signature** — the legacy field name showed up instead of the canonical one |
| `legacy_alias_present:<legacy>` | deprecation (non-fatal) | both the legacy and canonical keys are present; informational only |

A contract result is `ok = True` when it has zero fatal anomalies (a
deprecation-only result is still `ok`).

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
falsy/non-list calendar bodies evaluated first in `classify_empty_calendar`,
the rest in `explain_empty_selection` in fixed order, first match wins):

| Code | Condition | Exit |
|---|---|---|
| `no_earnings_rows` | the calendar returned `[]`, or rows none of which carried a `symbol` — a genuine empty window | 0 |
| `calendar_fetch_failed` | the calendar fetch returned no usable body (`None` on transport/HTTP/rate-limit failure, or a non-list body) | 1 |
| `profiles_budget_exhausted` | budget exhausted (`api_stats["budget_remaining"] == 0` or `rate_limit_reached`) and no profiles were returned at all | 0 |
| `no_profiles_returned` | ≥1 earnings symbol, but `get_company_profiles` returned nothing | 1 |
| `profiles_missing_required_field:marketCap` | ≥1 profile came back, but none has a usable numeric `marketCap` (non-bool `int`/`float`, finite) | 1 |
| `profiles_missing_required_field:exchange` | ≥1 usable market cap exists, but none of those profiles has a string `exchange` | 1 |
| `all_below_market_cap_floor` | every usable profile's market cap is below `--min-market-cap` | 0 |
| `all_non_us_exchange` | every usable profile's exchange is a non-US exchange (not in `FMPClient.US_EXCHANGES`) | 0 |
| `mixed_filters_rejected_all` | usable profiles exist and were all rejected, but by a *mix* of the cap-floor and exchange filters rather than one uniform cause — treated as an ordinary empty day, not schema drift | 0 |
| *(fallback)* `unknown` / any other reason not in the table | none of the above matched | 1 |

**pead-screener** (`screen_pead.py`, `_ZERO_RESULT_REASONS` / `_get_candidates_mode_a`
+ `_get_candidates_mode_b`, both return `(candidates, reason)` with `reason is None`
when `candidates` is non-empty):

| Code | Condition | Exit | Level |
|---|---|---|---|
| `no_earnings_rows` | Mode A: the FMP earnings calendar returned no rows (or no rows carried a `symbol`) for the lookback window | 0 | WARNING |
| `calendar_fetch_failed` | Mode A: the calendar fetch returned no usable body (`None` on transport/HTTP/rate-limit failure, or a non-list body); non-dict rows are ignored, never dereferenced | 1 | ERROR |
| `profiles_budget_exhausted` | Mode A: profiles came back empty and the budget is exhausted (`budget_remaining == 0` or `rate_limit_reached`) | 0 | WARNING |
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

| Endpoint | Owners (skills whose generated `fmp_client.py` calls it) |
|---|---|
| `profile` | earnings-trade-analyzer, pead-screener, ibd-distribution-day-monitor, parabolic-short-trade-planner, canslim-screener, us-undervalued-growth-screener |
| `quote` | vcp-screener, parabolic-short-trade-planner, ftd-detector, canslim-screener, market-top-detector, us-undervalued-growth-screener |
| `historical-price-eod-full` | all 10 generated clients: pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor, vcp-screener, parabolic-short-trade-planner, ftd-detector, canslim-screener, macro-regime-detector, market-top-detector, us-undervalued-growth-screener |
| `earnings-calendar` | pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor |

Owners are validated against `skills-index.yaml` by `check` — an owner naming a
skill directory that does not exist there is a validation error.

## Deliberately out of scope: session-aware empty suspicion

A clean HTTP 200 `[]` on a busy earnings weekday (silent drop) still exits 0
with `no_earnings_rows`: the exit code distinguishes transport/shape failure
(`None`/non-list) from an empty body, not a quiet window from a dropped one.
Session-awareness was rejected for the CLI because a stdlib weekday heuristic
false-positives on exchange holidays, and importing the shared XNYS calendar
(`scripts/market_calendar/`) from a skill script would break clean-room
installs (`package_skills.py` ships only the skill directory; vendoring would
expand the #340 generator's consumer set). Async coverage stays with the
weekly canary via the `earnings-calendar` `non_empty` contract. Session-aware
suspicion is tracked as follow-up work in
[Issue #356](https://github.com/tradermonty/claude-trading-skills/issues/356).

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

`.github/workflows/fmp-contract-canary.yml` runs
`python3 scripts/check_provider_contracts.py canary` weekly (Monday 12:00 UTC) plus
on `workflow_dispatch`. It is **report-only** (`continue-on-error: true`,
mirroring the `packaged-deps-nightly` / #349 pattern): a live anomaly does not fail
CI on its own today. If `secrets.FMP_API_KEY` is unset, the job prints
`SKIPPED: FMP_API_KEY secret not set` and exits 0 without probing anything.

Report (`reports/fmp-canary-report.json` in CI, uploaded as an artifact for 30
days; default local path `reports/fmp_canary_<YYYY-MM-DD>.json`, override with
`--report`):

```json
{
  "generated_at": "2026-09-05T12:00:00+00:00",
  "budget": {"max": 4, "used": 4},
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

| `/stable/...` path | Covered in slice 1 | Owners (grep-discovered) | Deferred to |
|---|---|---|---|
| `profile` | ✅ `profile.v1.json` | see ownership table above | — |
| `quote` | ✅ `quote.v1.json` | see ownership table above | — |
| `historical-price-eod/full` | ✅ `historical-price-eod-full.v1.json` | see ownership table above | — |
| `earnings-calendar` (v3 alias: `earning_calendar`) | ✅ `earnings-calendar.v1.json` | pead-screener, earnings-trade-analyzer, ibd-distribution-day-monitor call `get_earnings_calendar`; vcp-screener/parabolic-short-trade-planner vendor the same v3→stable compat rename but do not call it | — |
| `company-screener` | ❌ | dividend-growth-pullback-screener, downtrend-duration-analyzer, pair-trade-screener, stockbee-20pct-study, stockbee-exhaustion-hammer-screener, stockbee-momentum-burst-screener, value-dividend-screener | slice 2 (needs a field-usage inventory across its 9 ad-hoc consumers first — see plan §I) |
| `sp500-constituent` (v3 alias: `sp500_constituent`) | ❌ | vcp-screener, parabolic-short-trade-planner call `get_sp500_constituents`; pead-screener/earnings-trade-analyzer/ibd-distribution-day-monitor vendor the compat rename but do not call it | slice 2 |
| `income-statement` | ❌ | canslim-screener, dividend-growth-pullback-screener, value-dividend-screener | slice 2 |
| `ratios` | ❌ | value-dividend-screener | slice 2 |
| `profile-bulk` | ❌ | parabolic-short-trade-planner | slice 2 |
| `aftermarket-quote` | ❌ | parabolic-short-trade-planner | slice 2 |
| `institutional-ownership/symbol-positions-summary` | ❌ | canslim-screener | slice 2 |
| `etf/holdings` | ❌ | theme-detector | slice 2 |
| `economic-calendar` | ❌ | economic-calendar-fetcher | slice 2 |
| `historical-price-eod/light` | ❌ | news-reaction-failure-analyzer | slice 2 |
| `commitment-of-traders-report` | ❌ | cot-contrarian-detector | slice 2 |

This table defines slice 2's completion criteria: every row marked ❌ needs its own
contract file (and, for `company-screener`, the field-usage inventory across its
nine ad-hoc consumers) before slice 2 can close.

## Out of scope (this slice)

- Non-FMP providers.
- Every `/stable` endpoint above marked ❌ in the "Covered in slice 1" column.
- `company-screener` and its nine ad-hoc consumers specifically (needs its own
  field-usage inventory — different consumers read different subsets of a wide,
  inconsistent response shape).
- Zero-result reason codes for consumers other than earnings-trade-analyzer and
  pead-screener.
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

# Live probe — needs FMP_API_KEY. Makes one GET per contract (query-param
# auth), scores the response, writes a JSON report, exits 1 if any contract
# is not ok.
python3 scripts/check_provider_contracts.py canary [--max-calls N] [--report PATH]
```
