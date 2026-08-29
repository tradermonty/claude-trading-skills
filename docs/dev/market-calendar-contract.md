# Shared Market Calendar Contract

Issue [#331](https://github.com/tradermonty/claude-trading-skills/issues/331)
replaces hand-written weekday and local-clock decisions with one generated,
fail-closed cash-equity calendar contract.

## Authority and compatibility

`config/market-calendar-dependency.yaml` is the only authority for the direct
runtime pin and consumer inventory. `scripts/generate_market_calendar.py`
generates each standalone skill's `_market_calendar.py`, contract test, and
`requirements.txt`; each requirements file also retains that consumer's direct
runtime dependencies. It also generates `scripts/market_calendar/consumers.txt`,
which the clean-room workflow reads directly, and keeps the two weekly-strategy
example mirrors in sync. The generated runtime is self-contained and never
reads repository files.

The direct calendar dependency is `pandas-market-calendars==5.2.2`. Releases 5.2.3 and
5.2.4 declare Python 3.8+ compatibility but fail while importing on Python 3.9
because a PEP 604 union is evaluated at runtime. Version 5.2.2 is therefore
pinned and exercised in a required Python 3.9 clean-room CI job. `uv.lock`
records repository resolutions, but standalone compatibility is guarded by the
direct pin plus behavioral tests rather than a fully locked transitive graph.

The Python 3.9 compatibility job creates one isolated virtual environment per
consumer and installs only that skill's generated requirements. This prevents
one skill's PyYAML, requests, or market-data dependencies from masking another
standalone package's missing declaration.

The calendar library is an external runtime dependency. Its package is installed
from `requirements.txt`; its source or wheel is not embedded in `.skill` files.

## Supported venue contract

| Venue | Provider name | IANA timezone | Notes |
|---|---|---|---|
| `XNYS` | `NYSE` | `America/New_York` | US cash-equity session set |
| `XNAS` | `NASDAQ` | `America/New_York` | The provider resolves this alias to its `NYSE` calendar/session set |
| `XTKS` | `JPX` | `Asia/Tokyo` | Includes the lunch break and the 2024-11-05 close change |
| `XLON` | `LSE` | `Europe/London` | GMT/BST derives from the session instant |

JPX's official cash-equity hours are 09:00-11:30 and 12:30-15:30 JST
([JPX trading hours](https://www.jpx.co.jp/english/equities/trading/domestic/01.html)).
US holiday and early-close fixtures are checked against the
[NYSE hours and calendars](https://www.nyse.com/markets/hours-calendars).

CME/futures and crypto are intentionally not mapped. The audited consumers use
cash-equity sessions only; adding an unused generic `24/7` or CME calendar would
hide product-specific session-label and maintenance-break rules. Add a venue only
with a real consumer and product-specific fixtures.

`session_for_date()` returns `None` for a valid exchange holiday or weekend.
Missing dependencies, unknown venues, provider failures, and incomplete schedule
rows raise an explicit error. Search functions use a 370-day finite horizon.
All datetimes are timezone-aware. Opens are inclusive, closes are exclusive, and
the JPX lunch break is closed.

## Day-count boundaries

| Consumer | Start | End | Reverse/past behavior |
|---|---|---|---|
| Market environment event countdown | inclusive | exclusive | past event returns `0` |
| Market-top freshness | exclusive | inclusive | reverse returns legacy sentinel `-1` |
| Parabolic earnings age | exclusive | inclusive | reverse keeps the legacy negative calendar-day invalid sentinel |
| Theme/uptrend freshness | exclusive | inclusive | future source date is stale/anomalous |

The shared `count_sessions()` requires both inclusion flags as keyword arguments
and rejects reverse ranges. Consumer adapters own their documented legacy
sentinels so no ambiguous default can introduce an off-by-one error.

## `as-of` and point-in-time boundaries

| CLI | Contract |
|---|---|
| Market environment | Offset-bearing ISO-8601 timestamp or `Z`; date-only and naive values are rejected because multi-market status needs one instant |
| Breakout planner | Date means 00:00 `America/New_York`; an offset-bearing timestamp is also accepted |
| Drawdown circuit breaker | Existing date/datetime contract; halt expiry is the next XNYS session date at 00:00 ET, not the session open |
| Market-top detector | `YYYY-MM-DD`; historical live replay is rejected because current quotes are not point-in-time |
| Parabolic screener | Strict `YYYY-MM-DD`; fixture runs are deterministic, while historical live runs fail because universe/profile endpoints are not PIT |
| Theme detector | Strict `YYYY-MM-DD`; non-current live runs fail because FINVIZ, quote/profile, and uptrend sources are not PIT |

Provider query windows are not themselves official exchange calendars. Generated
FMP clients may use the live date to bound a request, so consumers filter bars
newer than `as-of`; insufficient history becomes an explicit incomplete/no-data
result. Current quote/profile endpoints are not advertised as historical PIT
sources. Provenance timestamps and output filenames record when an artifact was
created and are not inputs to signal, expiry, event, or freshness calculations.

## Repository audit

| Location | Classification and disposition |
|---|---|
| `market-environment-analysis/market_utils.py` and two example mirrors | Status, session labels, and event countdown use the shared calendar and one aware instant; weekday formatting is display-only |
| `breakout-trade-planner/plan_breakout_trades.py` | Plan validity uses current-or-next XNYS session; default clock is aware UTC |
| `drawdown-circuit-breaker/check_circuit_breaker.py` | Halt dates use XNYS sessions; `weekday()` remains only for calendar-week accounting |
| `market-top-detector/utils.py`, `breadth_csv_client.py` | Freshness uses XNYS sessions; auto breadth selects the latest row at/before `as-of`, and future-dated scored CLI values fail closed |
| `market-top-detector/market_top_detector.py` | Historical CLI replay fails closed; index, leading, and sector histories are all ceiling-filtered before calculators receive them |
| `parabolic-short-trade-planner/market_clock.py`, `screen_parabolic.py` | Intraday state and earnings age use XNYS; live/fixture bars are ceiling-filtered |
| `parabolic-short-trade-planner/adapters/*_market_data_adapter.py` | Alpaca query windows and both live/fixture bar filters use the authoritative XNYS open/close; holidays are empty and early-close after-hours bars are excluded |
| `parabolic-short-trade-planner/ssr_state_tracker.py` | Rule 201 carryover loads the previous XNYS session, including weekend and holiday gaps |
| Other parabolic `datetime.now(timezone.utc)` calls | Provenance, state-write, or live-monitor evaluation timestamps; timezone-aware and not session-day inference |
| `parabolic-short-trade-planner/generate_pre_market_plan.py` | Explicit/Phase-1 `as_of` owns plan date; default clock is a live-only fallback |
| `theme-detector/uptrend_client.py`, `report_generator.py` | Both freshness decisions use identical XNYS boundaries; uptrend rows newer than the validated run date are excluded before scoring |
| `theme-detector/etf_scanner.py` | Provider history windows receive the run-date ceiling and returned FMP/yfinance rows are independently re-filtered before caching or scoring; no-as-of `date.today()` is library live-mode only |
| Theme/market-top generated timestamps and filenames | Provenance only; never used for scoring or freshness |
| Shanghai, Hong Kong, Singapore rows in market environment | Display-only reference text; no session/status/trading-day calculation consumes them |

The drift gate covers the authority file, generated CI inventory, workflow,
generator/smoke inventory agreement, canonical implementation, all six
consumers, both example mirrors, the optional extra, and CI policy.
