# Issue #495: original 20-skill FMP migration acceptance

This matrix describes the prepared integration branch, not a claim that the changes have already landed on main. Main had 17 targets; the branch preserves the exact #861/#862 changes and adds theme-detector as target 20. The new integration PR must be approved and merged before #495 is closed. Automatic approval review requires explicit final merge authorization; none is inferred from preparing this document.

Every original target is registered, ships a generated client and has runtime delegation plus fake-transport evidence. Pure strategy calculations, native/live provider entitlement and trading accuracy are separate claims.

| Original skill | Runtime delegation | Fake HTTP/client regression evidence | Integration source |
|---|---|---|---|
| cot-contrarian-detector | `skills/cot-contrarian-detector/scripts/screen_cot_crowding.py` | `skills/cot-contrarian-detector/scripts/tests/test_fmp_client_contract.py` | main (prior migration) |
| dividend-growth-pullback-screener | `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` | `scripts/tests/test_dividend_fmp_migration.py` | main (prior migration) |
| downtrend-duration-analyzer | `skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py`, `skills/downtrend-duration-analyzer/scripts/downtrend_fmp_client.py` | `skills/downtrend-duration-analyzer/scripts/tests/test_generated_transport.py` | main (prior migration) |
| earnings-calendar | `skills/earnings-calendar/scripts/fetch_earnings_fmp.py` | `skills/earnings-calendar/scripts/tests/test_fmp_client_transport.py` | main (prior migration) |
| economic-calendar-fetcher | `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py` | `skills/economic-calendar-fetcher/scripts/tests/test_fmp_client_contract.py` | main (prior migration) |
| institutional-flow-tracker | `skills/institutional-flow-tracker/scripts/analyze_single_stock.py`, `skills/institutional-flow-tracker/scripts/track_institutional_flow.py` | `skills/institutional-flow-tracker/scripts/tests/test_fmp_client_transport.py` | main (prior migration) |
| kanchi-dividend-sop | `skills/kanchi-dividend-sop/scripts/build_entry_signals.py` | `scripts/tests/test_dividend_fmp_migration.py` | main (prior migration) |
| news-reaction-failure-analyzer | `skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py` | `skills/news-reaction-failure-analyzer/scripts/tests/test_generated_transport.py` | integrated PR #862 |
| options-strategy-advisor | `skills/options-strategy-advisor/scripts/black_scholes.py` | `skills/options-strategy-advisor/scripts/tests/test_generated_market_data.py` | integrated PR #861 |
| pair-trade-screener | `skills/pair-trade-screener/scripts/analyze_spread.py`, `skills/pair-trade-screener/scripts/find_pairs.py`, `skills/pair-trade-screener/scripts/pair_fmp_client.py` | `skills/pair-trade-screener/scripts/tests/test_generated_transport.py` | main (prior migration) |
| signal-postmortem | `skills/signal-postmortem/scripts/postmortem_fmp_client.py`, `skills/signal-postmortem/scripts/postmortem_recorder.py` | `skills/signal-postmortem/scripts/tests/test_generated_transport.py` | main (prior migration) |
| stockbee-20pct-study | `skills/stockbee-20pct-study/scripts/run_20pct_study.py` | `scripts/tests/test_stockbee_fmp_migration.py` | main (prior migration) |
| stockbee-episodic-pivot-analyzer | `skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py` | `scripts/tests/test_stockbee_fmp_migration.py` | main (prior migration) |
| stockbee-exhaustion-hammer-screener | `skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py` | `scripts/tests/test_stockbee_fmp_migration.py` | main (prior migration) |
| stockbee-momentum-burst-screener | `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py` | `scripts/tests/test_stockbee_fmp_migration.py` | main (prior migration) |
| stockbee-setup-fluency-trainer | `skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py` | `scripts/tests/test_stockbee_fmp_migration.py` | main (prior migration) |
| technical-analyst | `skills/technical-analyst/scripts/check_weekly_price_action.py` | `skills/technical-analyst/scripts/tests/test_generated_transport.py` | main (prior migration) |
| theme-detector | `skills/theme-detector/scripts/fmp_adapter.py` | `skills/theme-detector/scripts/tests/test_generated_transport.py` | final integration change |
| trader-memory-core | `skills/trader-memory-core/scripts/fmp_price_adapter.py` | `skills/trader-memory-core/scripts/tests/test_fmp_price_adapter.py` | main (prior migration) |
| value-dividend-screener | `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` | `scripts/tests/test_dividend_fmp_migration.py` | main (prior migration) |

## Gates and packages

- `python3 scripts/check_fmp_migration.py`: exact original 20 inventory, generated ownership/runtime import references and unreviewed legacy-reference refusal. Hidden runnable example snapshots are included; tests are excluded.
- `python3 scripts/generate_fmp_client.py --check`: exact canonical rendering for every registered target, including generated compatibility shims.
- `python3 scripts/package_skills.py --check`: all distributable skills, not just the FMP subset. Local/CI FMP mirror commands also cover the full current registry; generic source/package patterns avoid target-list trigger omissions.
- `python3 scripts/check_provider_contracts.py check`, relevant fake-HTTP suites, dependencies, package imports, pre-commit and the full pre-push matrix validate the integration head. Hosted CI is recorded independently in the PR.

## Precise legacy exceptions

The checked source of truth is [fmp-legacy-exceptions.json](fmp-legacy-exceptions.json). Each exception pins an exact relative file and complete source line with a nonempty reason; removed, duplicated or newly changed lines fail the gate. Registry-generated clients and compatibility shims are excluded by exact registry output path, never filename alone. Canonical templates intentionally retain generated compatibility support.

The remaining exceptions are not unconverted original target callers:

- CoinGecko v3 belongs to another provider.
- Three historical schema/endpoint explanations do not execute requests.
- Four frozen weekly-trade-strategy calendar snapshots (including hidden `.claude` copies) are historical examples; current installations use the canonical generated calendar skills.
- `scripts/weekly_core_collect.py` is a separate weekly portfolio utility outside the original 20. Its tested legacy-account compatibility fallback is retained explicitly, not silently treated as migrated.
- `parabolic-short-trade-planner/scripts/check_live_apis.py` is an independent endpoint/shape diagnostic outside the 20 targets. Its explicit legacy capability probes are retained; analysis uses that skill's generated runtime client.
- The gate's own search literal is not a network endpoint.

This is the reasoned exception path explicitly permitted by #495's legacy-reference acceptance criterion. New production callers or new legacy references receive no blanket exemption. Diagnostics that inspect raw provider shapes are intentionally distinct from runtime client normalization; FINVIZ and yfinance transports are outside this FMP migration.

## Evidence limits and integration

All transport regressions use fictional keys/data and fake HTTP. No live provider or brokerage state is used. Old affected verification evidence is conservatively reset; green tests are not renewed security, native execution or strategy certification. Shared transport repairs in PR #859 are not incorporated. If that core changes first, regenerate and repackage the final integration head and rerun gates.
