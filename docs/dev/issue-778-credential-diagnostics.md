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
