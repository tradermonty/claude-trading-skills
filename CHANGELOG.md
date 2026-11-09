# Changelog

All notable changes to this repository are recorded here in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Repository releases use stable [Semantic Versioning](https://semver.org/) tags (`vMAJOR.MINOR.PATCH`). A `.skill` package does not have an independent version.

## [Unreleased]

- Generate EN/JA README API guidance linking to the canonical index-derived requirements matrix and detailed mode instructions; reject stale or missing guidance with the catalog drift gate (#654).
- trader-memory-core: generate historical-only postmortems for retired legacy equity shorts without fetching prices or changing state; suppress unsupported accounting values and explain their omission (#682).

- theme-detector: prefer authenticated FINVIZ group export with safe public fallback, require finvizfinance>=1.5.0 for Python3.10+ public scraping, and merge overlapping ETF holdings without a missing-score crash (#671).

Changes merged to `main` since the release process landed in #505 (2026-10-10). No GitHub Release has been published yet.

### Metadata and API contracts

- Correct market-top-detector and downtrend-duration-analyzer to FMP required, signal-postmortem to FMP optional, and market-regime-daily and its skillset to mixed profiles with a key-free base. Add an offline credential-read/no-API-workflow gate and generate EN/JA catalog provider badges/API matrix values from the index (#653).

### Maintenance

- Restore the skill-improvement launcher past its shared logs/reports symlinks, add an independent daily success-heartbeat watchdog with default local macOS alerts and an explicit opt-out, and provide one validated LaunchAgent installer that preserves existing customizations (#652). Live scheduler recovery remains subject to deployment and the next scheduled score.

### Skills

- trader-memory-core keeps equity accounting long-only: reject explicit short-equity intent and incompatible initial stop geometry before wrong P&L can be recorded, while preserving futures LONG/SHORT and active long profit-protecting stops. Remove the unsupported parabolic-short ingest instruction (#662).
- Reject stale, future or invalid selected-market COT dates in the setup gate, news failure analyzer and technical confirmation, in addition to the report date. Validate optional per-market provenance dates, use the oldest validated age, and preserve absent-field legacy compatibility (#649). An unusable crowding input reaches the futures sizer as NO_TRADE.

- stockbee-momentum-burst-screener: reject stale or unplaceable daily bars before scoring; freeze the latest completed NYSE session, add explicit as-of/session-age controls, active-universe filtering and auditable freshness metadata (#670). A tolerated stale bar is capped at `MANUAL_REVIEW`, and an all-stale universe adds a top-level report warning. stockbee-setup-fluency-trainer drops the per-symbol `latest_bar_dates` map when ingesting screener metadata.
- Prepare verified `.skill` assets and SHA-256 checksums from a tagged repository revision.
- Migrate the Batch A FMP callers (earnings-calendar, economic-calendar-fetcher, institutional-flow-tracker, cot-contrarian-detector) from hand-rolled HTTP/retry code to the generated vendored `fmp_client.py` (Issue #495 batch A). Deliberate change: the FMP API key is now sent as an `apikey` header (never in a URL) for these four skills; the economic-calendar 402/404 and COT `(data, error)` redaction contracts are preserved. Note: 5xx no longer gets the COT-specific multi-attempt backoff (single 429 retry from the shared client, which fails closed otherwise), and earnings-calendar's former distinct `Request timeout` / `Connection error` wordings now collapse into the shared client's transport-error wording. Also, a 200 COT payload that parses to a non-list now degrades to `([], error=None)` instead of returning the raw value, and non-429 transport failures do not retry under the shared client.
- Migrate the dividend/value Batch B callers (#573) and the five stockbee skills, Batch C (#587), to the generated FMP clients (#495). The stockbee skills drop their `/stable` to `api/v3` fallbacks. stockbee-setup-fluency-trainer `update` exits 1 without saving the model book when every symbol fails at the transport level.
- FMP clients redact the API key by value, including URL-encoded and padded forms, in every diagnostic, including the special clients (#532, #545, #556). An HTTP 200 with an invalid JSON body is retried once and then reported as an error instead of raising.
- cot-contrarian-detector: the JSON report carries a `data_provenance` block with the oldest analyzed market vintage and per-market dates. An analyzed market with a missing or non-canonical newest report date exits 1 with an error naming the symbol, and an all-skipped report records the request cutoff as a canonical date (#297).
- backtest-expert: deployment decisions fail closed. Break-even or negative expectancy never reaches DEPLOY, expectancy and profit factor are computed exactly in decimal, and too-good results (win rate above 90% with drawdown below 5%) require validation. Invalid input exits 1 (#518).
- canslim-screener: a missing S&P 500 price exits 1 without a report. When the 50-day EMA cannot be computed, the report is marked `DEGRADED` (#564).
- dividend-growth-pullback-screener: a stock is no longer marked sustainable on earnings payout alone when free cash flow is negative, zero or missing (#536).
- value-dividend-screener: REIT assessments without usable FFO are labeled `FFO_UNAVAILABLE`, and overflowed derived FCF is labeled `NON_FINITE` (#570).
- economic-calendar-fetcher: validate every event row against the provider contract. Schema drift, fetch failure and an unverified empty calendar exit 1 instead of publishing a quiet calendar (#572).
- market-breadth-analyzer and uptrend-analyzer: header drift, an unparsable CSV body and all-empty ratios are reported as one explicit error (#589).
- market-breadth-analyzer, uptrend-analyzer and exposure-coach: emit and optionally validate same-run provenance for the `market-regime-daily` handoff (#576).
- edge-candidate-agent and edge-pipeline-orchestrator: export `panic_reversal` strategies with their dispatch block, record a rejected draft as an export failure instead of aborting the run (#533), and route news-reaction candidates to the research-only pool (#568). An invalid `--as-of` date exits 1 (#565).
- edge-signal-aggregator: aggregation is idempotent, so re-ingesting the same evidence no longer inflates scores, and out-of-range or non-finite scores are rejected. Output `schema_version` is now `1.1`, and `merge_bonus_per_duplicate` is deprecated and ignored (#528).
- futures-position-sizer: when the risk budget cannot afford one contract, the guidance keeps the setup stop and suggests a smaller contract instead of a wider stop (#581).
- market-top-detector: label the risk score as heuristic and reject weak historical analogues (#574).
- pair-trade-screener: cointegration results serialize to JSON, and the ASCII chart title renders correctly (#562).
- portfolio-manager: add an offline CSV allocation review for users without broker credentials (#583, part of #512). Reconciliation errors name the failing source without exposing input contents (#563).
- position-sizer: risk is reported for the method that sized the trade (#596). A stop price of zero or below is rejected, and risk is computed exactly and rounded half-up (#602). `nan`, `inf` or `-inf` for any numeric argument exits 2 with an error naming the argument, and `--win-rate 1.0` is rejected instead of recommending half the account (#656).
- breadth-chart-analyst: `detect_uptrend_ratio --json` no longer crashes on numpy values, and blank sector status no longer crashes the CSV report (#565).
- skill-designer: a malformed idea JSON prints a one-line error and exits 1 (#567).
- trading-skills-navigator: keep goal matches whose workflow is unavailable, and report paid-API secondary workflows dropped under `--no-api` (#526).
- us-market-bubble-detector: the quick check no longer issues a verdict without the quantitative evaluation (#582).
- Bundled resource references in SKILL.md are validated, so a missing `references/` or `scripts/` file fails the gate (#546, #549).

### Workflows

- Add a tag-driven release process. No GitHub Release has been published by this change.
- The release workflow sets `releases/latest` from SemVer ordering, so an older-line patch tag no longer moves it. Prerelease tags start no run, and release runs are serialized (#597). Metadata and archive validation are hardened (#537).
- `monthly-performance-review`: the final review step consumes the coach artifacts, so the accept/modify/defer decision reaches the decision log and next-month rules (#584).
- `market-regime-daily`: the canonical replay requires provenance for the breadth and uptrend inputs (#576).

### Repository and CI

- All per-skill coverage waivers are retired; every skill meets its coverage floor (#293: #560, #562, #564, #565, #567). Coverage waivers notify before they expire (#544, #557).
- The documented CLI example gate also checks `uv run` scripts, shell examples and unmarked paths in root documents. Wrong documented flags were fixed (#547, #555, #558).
- The weekly quality-dashboard refresh collects attributable evidence and proposes updates as a PR (#571).
- Scheduled automation can send failure notifications, and an offline checker reports missing success heartbeats (#561).
- Add trader-monty public CSV provider contracts and a keyless weekly canary (#589).
- Production unit-test verification evidence is inventoried and narrowed to 12 evidence-verified skills (#559, #588).
- The local gates and test suite pass on Windows. Checkouts use LF line endings (#575).
- The root development environment now requires Python 3.11 or later. Packaged skills keep their Python 3.9 floor (#595).
- The repo-scripts pyarrow pin is derived from `uv.lock` (#535), and pandas-market-calendars is held at the Python 3.9 floor (#550).
- Dependency updates: pyarrow 25.0.1 (#487), ruff 0.17.2 (#551, #593), and pinned GitHub Actions (#548, #592, #594).

### Security

- msgpack 1.2.4 fixes CVE-2026-114613 (#598).
- The Python 3.10 lock fork is retired, which removes pillow, virtualenv and filelock versions with open advisories. certifi is updated (#595).

### Breaking metadata

- None for `skills-index.yaml`, workflow manifests or skillsets. Output contract changes are listed under Skills, for example edge-signal-aggregator `schema_version` 1.1.
