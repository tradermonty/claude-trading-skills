# Issue #778: credential-safe provider diagnostics

## Scope and evidence

Reviewed by Codex, with independent subagent plan review and three code-review
rounds, on 2026-11-15. Source assessment:
`e02496fb5e845419eb7e73d18288ab44fd79cc3b`.

| Skill | Reviewed script(s) under `scripts/` | Failure behavior |
|---|---|---|
| downtrend-duration-analyzer | `analyze_downtrends.py` | Exception class only; stable-to-v3 fallback retained |
| value-dividend-screener | `screen_dividend_stocks.py` | FINVIZ exception class only; empty set retained |
| dividend-growth-pullback-screener | `screen_dividend_growth_rsi.py` | FINVIZ exception class only; empty set retained |
| canslim-screener | `check_institutional_endpoint.py` | Exception class only; false return retained |
| parabolic-short-trade-planner | `check_live_apis.py` | Class/status diagnostics for all FMP/Alpaca/adapter failures; raw HTTP error and non-JSON bodies suppressed; malformed payload repr suppressed |
| theme-detector | `representative_stock_selector.py`, `finviz_performance_client.py` | Selector warnings carry no traceback; source failure counters/fallbacks retained; performance client already uses fixed failure reasons |

Each skill has an offline `scripts/tests/test_credential_diagnostics.py` using
synthetic credentials, including reserved URL characters. No real credential or
live account is used. ConnectionError, Timeout and HTTPError messages contain
both raw and URL-encoded markers; stdout/stderr must exclude both. Selector tests
also inspect formatted captured logs and require `exc_info is None`.

The first run against the unmodified source produced 39 failures and three
passes (the already-safe performance client). The corrected source passes all
52 diagnostic regressions, including ten reflected HTTP/non-JSON-body cases.
All six existing skill suites pass: 78 + 217 + 196 + 434 + 327 + 556 = 1,808 tests;
one optional finvizfinance test is skipped because that package is absent from
the shared development environment. This is offline evidence, not live-provider
acceptance or a full dependency audit.

The security collector previously confused local literal-only diagnostic
exceptions with request exceptions. Its exemption now requires a plain local
ValueError/RuntimeError subclass, literal-only constructors, no alias/rebinding
or shadowed base, and only formatting/str/repr reads of the handler variable.
Unknown/dynamic exception classes, request exceptions, logger tracebacks and
mutated variables remain flagged. Fifteen new collector cases cover literal
messages, unsafe subclasses/messages, aliases, rebindings and mutation. All
32 collector tests pass. This remains an advisory static heuristic, not a
whole-program proof.

`python scripts/backfill_security_review.py` now reports no mechanical findings
for any of these six skills. `python scripts/check_skill_deps.py check` passes
for all executable skills (no warning for the six affected skills). All six
`.skill` archives have been rebuilt and checked against their source.

## Remaining acceptance gap

Acceptance criteria 1, 2 and 4 are addressed, and the collector portion of
criterion 3 is addressed. **The `security_review: passed` restoration in
criterion 3 is not complete.** All six entries remain `not_verified`, consistent
with `security-review-checklist.md`: clean mechanical scans and targeted leakage
regressions cannot certify all credential, data-exposure, path, I/O/network and
dependency dimensions for the entire skill.

The targeted review verified the changed diagnostics, their existing bounded
request timeouts and failure/fallback behavior, dependency declarations, and
source/package parity. It did not comprehensively review all other source paths
or audit third-party library behavior. In particular, theme-detector's optional
FINVIZ dependency was absent locally, so its network and logging behavior was
not established by these tests. A complete per-skill checklist review remains
necessary before changing these metadata values. Keep #778 open until that
acceptance is separately recorded; this change must not claim full security
certification or live validation.

## Five-dimension checklist review (2026-11-22)

Reviewed by Claude (Opus 5.5 orchestrating six Sonnet reviewers, one per
skill), against `docs/dev/security-review-checklist.md`, on assessed commit
`bb4a8ff60c2054cc8b41807ae648041ff0922938`. Every non-test file under each
skill's `scripts/` was read. `check_skill_deps.py check`, the collector with
`--reviewer-confirmed` for all six skills, and each skill's test suite were run.
Raw exception output was re-checked by hand across five of the skills.

| Skill | Credential | Data exposure | Path | I/O and network | Dependency |
|---|---|---|---|---|---|
| downtrend-duration-analyzer | pass | pass | pass | pass | pass |
| value-dividend-screener | pass | pass | pass | pass | pass |
| dividend-growth-pullback-screener | pass | pass | pass | pass | pass |
| canslim-screener | pass | pass | pass | pass | pass |
| parabolic-short-trade-planner | pass | pass | pass | fixed in this change | pass |
| theme-detector | pass | pass | pass | gap | pass |

**Fixed in this change.** In parabolic-short-trade-planner, live Phase 1
treated provider failures as valid empty results. Three cases were affected:

- A failed or empty S&P 500 universe.
- A failed earnings calendar, a non-list HTTP-200 body such as an FMP error
  dict, or a list containing a row without a symbol or a parsable date. Each
  of these silently disabled the earnings-blackout exclusion. A dropped row
  left that symbol without a known earnings date.
- Per-symbol price failures, including an empty `historical` list, no usable
  bar on or before the run date, and a `--max-api-calls` budget spent before
  the first price fetch.

Each case wrote a normal exit-0 report. Now each case raises an error and
writes no report. Partial price failures are listed in an additive
`data_quality` block. A symbol with an empty history counts as a failure,
not as evaluated. Regressions are in
`scripts/tests/test_live_fail_closed.py`. The first revision of this change
made seven of its ten original cases pass. A follow-up review found two
further gaps: an empty history and a malformed earnings row. Run against the
first revision, seven of the ten cases added for those gaps fail.

**Why the six values stay `not_verified`.** The checklist requires a passed
candidate to be clean on the mechanical checks as well. The collector
(`scripts/security_network_evidence.py`) proposes `gap` for all six skills,
because it accepts only a finite literal timeout at each call site:

- `timeout=self.timeout` in the generated FMP clients is flagged. These are
  value-dividend, dividend-growth-pullback and theme-detector, where
  `self.timeout = 30` is a constant set in `__init__`.
- Delegation to a vendored client is flagged in canslim, downtrend and
  parabolic, even though that client's own calls are bounded.
- The parabolic Alpaca adapters take a `timeout` constructor parameter, which
  defaults to 15.0 or 10.0. No caller overrides it.

The reviewers judged all of these bounded in practice. Clearing them still
needs either a collector extension (constant-attribute and local-delegation
proofs) or call-site changes in the generated client template, so they are
not certified here.

theme-detector also has a real network gap. Its `yf.download`,
`yf.Ticker().info` and `finvizfinance` calls pass no explicit timeout and rely
on third-party library defaults, which could not be verified because those
optional packages were absent locally. Two minor items were noted in
theme-detector's `representative_stock_selector.py`:

- An HTTP-200 Elite export without a `Ticker` column is recorded as success.
  The run still falls back to the public source.
- The Elite request does not set `allow_redirects=False`.
