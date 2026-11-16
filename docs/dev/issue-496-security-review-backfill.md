# Issue #496 step 2 — `security_review` verification backfill (assessed 2026-11-15)

Assessed commit: `7b236db9fb3eceaa8a24ec1d419724c9c8a2eeb4` (origin/main after the
review-driven rebase; the first pass was run at `13079ab4`). The evidence is pinned per skill in
the verification baseline overrides in
`docs/dev/production-verification-baseline.yaml`: the mechanical scan and
reconciliation are reproduced by `scripts/backfill_security_review.py`, and each
skill-override `evidence` carries the assessment date, the process used, and the
assessed commit. The evidence is an automated heuristic scan; no named human
reviewer is recorded, and a reviewer should be added only after that person has
reviewed the skill.

## Scope

This is the second slice of issue #496. Step 1 (#588) backfilled the
`unit_tests` axis. This step covers the `security_review` axis for production
skills that read an API key, following the lightweight checklist in
[`docs/dev/security-review-checklist.md`](security-review-checklist.md).

The issue acceptance criterion for this axis reads "`security_review` is `passed`
for at least all production skills that read API keys". This PR records the
first pass against that criterion. Acceptance criteria not covered here —
`instruction_contract` for every canonical-workflow skill, and the
"stale-evidence reset rule enforced by `validate_skills_index.py`" — remain open
for follow-ups and are called out below.

## Method

- Enumeration: `scripts/backfill_security_review.py` scans
  `skills/<id>/scripts/**/*.py` (excluding `tests`, the same rule as #588) for
  `FMP_API_KEY|FINVIZ_API_KEY|ALPACA_API_KEY|ALPACA_SECRET_KEY|--api-key|X-API-Key`
  and reconciles that set against the SSoT `integrations[]` declarations
  (`id` in `fmp` / `finviz` / `alpaca`). Integration `note` text (for example
  "Alpaca order templates" on `breakout-trade-planner`) is deliberately **not**
  treated as a key declaration.
- Check: per-skill mechanical checks — hard-coded credential literal, shell
  invocation, a key-bearing request combined with an unredacted exception
  print/log (`requests` exception text embeds the full URL including the
  query string), explicit network timeout, dependency manifest — plus the
  repo-wide `scripts/check_skill_deps.py check` (exit 0).
- Fail-closed gate: `--reviewer-confirmed <id>` starts empty; a skill is only
  proposed `passed` when it is mechanically clean **and** explicitly
  reviewer-confirmed. The raw report (`reports/security_review_evidence.json`)
  records every per-skill finding so the pass can be independently re-checked.
  `reports/` is gitignored, so the report is not a committed artifact — the
  recorded evidence pins the reviewed source directories, the reviewer/date/
  commit, and the regenerable command
  `python3 scripts/backfill_security_review.py --reviewer-confirmed <ids> ... --output-dir reports/`,
  mirroring the #588 precedent of citing reproducible evidence rather than
  committing report files.

## Enumeration result (28 target skills)

| Group | Count | Skills |
|---|---|---|
| Key readers via the generated FMP client | 17 | canslim-screener, cot-contrarian-detector, dividend-growth-pullback-screener, earnings-calendar, earnings-trade-analyzer, economic-calendar-fetcher, ftd-detector, ibd-distribution-day-monitor, institutional-flow-tracker, kanchi-dividend-sop, macro-regime-detector, market-top-detector, pair-trade-screener, parabolic-short-trade-planner, pead-screener, value-dividend-screener, vcp-screener |
| Direct HTTP with explicit timeout | 8 | downtrend-duration-analyzer, news-reaction-failure-analyzer, options-strategy-advisor, portfolio-manager, signal-postmortem, technical-analyst, theme-detector, trader-memory-core |
| No HTTP data fetch in scripts | 3 | edge-candidate-agent, finviz-screener, kanchi-dividend-review-monitor |

Reconciliation against `integrations[]`:

- `declared_but_no_script_ref` (integration declares a key source but scripts do
  not reference the credential): `edge-candidate-agent`,
  `kanchi-dividend-review-monitor`, `options-strategy-advisor`. These are all
  `optional`/`recommended` enrichments where the credential is consumed through a
  caller path rather than a literal in the skill's scripts; each is still
  reviewed.
- `script_ref_but_not_declared` (scripts reference a credential the
  `integrations[]` do not declare): only the two scanner-only meta skills,
  `dual-axis-skill-reviewer` and `skill-integration-tester`, which contain the
  credential pattern because they audit other skills. They are excluded from the
  reviewed set by an explicit allowlist and are **not** key readers.

### Excluded from the reviewed set (with reason)

- `dual-axis-skill-reviewer`, `skill-integration-tester` — meta skills that scan
  other skills for credential patterns; their own scripts do not read a key.
- `breakout-trade-planner` — `integrations[]` is `local_calculation` ("Alpaca
  order templates"); its scripts contain no key reference, so it does not read an
  API key.

## Outcome

22 of the 28 target skills are recorded `security_review: passed` (index value +
baseline override with per-skill rationale and evidence). Six skills are recorded
`not_verified` because they send a key in the request and print or log the
`requests` exception, whose text contains the request URL with the key:

| Skill | Leak path |
|---|---|
| downtrend-duration-analyzer | `analyze_downtrends.py`: `apikey` in params, `{e}` to stderr |
| value-dividend-screener | `screen_dividend_stocks.py`: FINVIZ `auth` in params, `{e}` to stderr |
| dividend-growth-pullback-screener | `screen_dividend_growth_rsi.py`: FINVIZ `auth` in params, `{e}` to stderr |
| parabolic-short-trade-planner | `check_live_apis.py`: `apikey` in params, `{e}` to stdout |
| canslim-screener | `check_institutional_endpoint.py`: `apikey` in params, `{e}` to stderr |
| theme-detector | `representative_stock_selector.py` (`auth=` in URL, `logger.exception`) and `finviz_performance_client.py` |

These skills need redaction (the `_redact` pattern in technical-analyst) in a
follow-up before the axis can pass; their code is unchanged here. The collector
now flags this pattern (`exception_key_leak_findings`) and counts it against
`clean`. The scan is a file-level heuristic, not a data-flow proof, and it does
not check logging of the key value in general.

Policy for the three skills with no key read in their scripts
(`edge-candidate-agent`, `kanchi-dividend-review-monitor`) or a caller-provided
key only (`options-strategy-advisor`): they are recorded `passed` because their
`integrations[]` declare a key source and the scripts make no key-bearing
requests; the rationale says so explicitly. The global `audit.baseline_commit`
is intentionally left untouched (the #588 precedent pins per-axis evidence at
per-override `assessed_commit` values instead).

## Not covered by this PR (tracked under #496)

1. `instruction_contract` for every canonical-workflow skill — follow-up.
2. The "stale-evidence reset rule enforced by `validate_skills_index.py`" — this
   rule currently exists only as prose in
   [`docs/dev/production-verification.md`](production-verification.md)
   ("Keeping evidence current"); no mechanical staleness reset exists in the
   validator. This PR does **not** claim to satisfy that criterion and leaves it
   open.
3. `unit_tests` re-backfill of the skills left `not_verified` in step 1 (#588,
   47 skills) — follow-up.

## Collector prerequisite follow-up (#783)

The collector is advisory. A mechanically clean result plus explicit confirmation
only proposes `passed`; it does not perform the five-dimension human security
review, certify historical verification metadata, or modify the index/baseline.

Executable Python skills must have `requirements.txt`. Prompt-only skills need
no manifest. The timeout prerequisite is evaluated per recognized network call,
not by the presence of a `timeout=` string anywhere in the skill. The report
includes `network_applicability`, `network_calls` (path, line, call and bounded
argument evidence), and `network_timeout_findings`. Missing, None, boolean,
nonpositive, infinite and dynamic/unproven timeout arguments prevent a clean
proposal even with `--reviewer-confirmed`. Each connect/read tuple component must
be a finite positive literal. `timeout_present` remains a legacy diagnostic,
not evidence that every request is bounded.

Direct requests/httpx/aiohttp/urllib calls, imported aliases, and constructor-bound
sessions (including `self.session = requests.Session()`) are inspected. Dynamic
dispatch, escaped clients/callables (including return values and collections),
ambiguous imports, rebinding, delegated SDK operations, parse/read errors and otherwise
unresolved network imports produce explicit gaps for human review. `urllib.parse`
URL manipulation alone is local and needs no timeout. This deliberately limited
static analysis may request review of valid wrapper/default timeout paths; it
is not whole-program data-flow analysis or proof of an overall wall-clock bound.
It does not validate the contents of dependency manifests; use the dependency
checker separately. Existing verification metadata is not rewritten by this scan.

Both `--skill` and `--reviewer-confirmed` must name eligible reconciled production
API consumers. Unknown/ineligible IDs (including mixed valid/invalid selections)
return exit 2 with eligible IDs on stderr before any output directory/report is
created or overwritten. An eligible confirmation outside the selected subset
has no effect on unselected skills.
