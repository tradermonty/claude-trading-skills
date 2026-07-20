---
name: crypto-regime-analyzer
description: Quantifies crypto market regime health using free, keyless public data (CoinGecko + Binance funding). Generates a 0-100 composite score across 6 components (100 = risk-on) with a posture recommendation. No API key required. Use when user asks about crypto market conditions, whether it's alt season, BTC dominance, crypto risk-on vs risk-off, funding rates, or whether crypto exposure should be increased or reduced.
---

# Crypto Regime Analyzer Skill

## Purpose

Quantify the crypto market regime using a data-driven 6-component scoring system (0-100). This is the crypto analog of `market-breadth-analyzer` + `exposure-coach`: it answers "what posture does the crypto market currently support?" before any coin-level analysis happens.

**Score direction:** 100 = Maximum risk-on health (broad participation, healthy trend, sane leverage), 0 = Critical risk-off.

**No API key required** — uses CoinGecko's free public API and Binance's public futures endpoint.

## When to Use This Skill

- User asks "Is crypto risk-on or risk-off right now?" or "How healthy is the crypto market?"
- User asks "Is it alt season?" or about BTC dominance direction
- User asks whether funding rates are overheated
- User wants an exposure posture for a crypto sleeve before screening individual coins
- User wants a daily crypto regime check alongside the equity `market-regime-daily` workflow

## What This Skill Does NOT Do

- No coin picks, no buy/sell signals, no price targets
- No execution or portfolio changes — regime description only
- Human decision gates remain central, consistent with the project vision

## Prerequisites

- **Python 3.9+** with `requests` (live mode only; offline mode is stdlib-only)
- **Internet access** to `api.coingecko.com` and `fapi.binance.com` (live mode)
- **No API keys required**

## Component Model

| # | Component | Weight | Question it answers |
|---|---|---|---|
| 1 | BTC Trend Structure | 25% | Is the reserve asset's primary trend intact? (price vs 50/200DMA stack, 200DMA slope) |
| 2 | Alt Breadth Participation | 20% | How broadly are alts participating? (% of top-N above 200DMA, 50DMA confirmation) |
| 3 | BTC Dominance Regime | 15% | Where is capital rotating? (dominance direction interpreted jointly with BTC trend) |
| 4 | Perpetual Funding Regime | 15% | How crowded is leverage? (avg funding across majors; contrarian at extremes) |
| 5 | Drawdown & Volatility Position | 15% | Where are we in the cycle? (drawdown from 1y high, realized vol percentile) |
| 6 | Momentum Thrust / Washout | 10% | Short-horizon confirmation (% of universe positive over 30d) |

Missing components have their weight proportionally redistributed (same convention as `market-breadth-analyzer`). Full scoring logic: `references/crypto_regime_methodology.md`.

### Regime Zones

| Score | Zone | Posture |
|---|---|---|
| 80-100 | RISK_ON | Broad risk-on conditions observed; review risk limits before decisions |
| 40-79 | NEUTRAL | Mixed conditions observed; no strong regime conclusion |
| 0-39 | RISK_OFF | Defensive market conditions observed; review existing risk controls |

These are heuristic descriptive bands, not validated allocation rules. See
`references/VALIDATION.md` for the current evidence boundary and the artifacts
required before making quantitative performance claims.

---

## Execution Workflow

### Phase 1: Run the Analysis Script

**Live mode** (fetches CoinGecko + Binance; first run of the day takes ~2-4 minutes at the default `--top-n 20` due to free-tier rate-limit throttling; same-day re-runs hit the cache and are instant):

```bash
mkdir -p reports/<routine-or-date>
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --output-dir reports/<routine-or-date>
```

**Offline mode** (no network; snapshot schema in the methodology reference):

```bash
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --input-json snapshot.json \
  --output-dir reports/<routine-or-date>
```

Options: `--top-n <int>` universe size (default 20), `--cache-dir <path>` fetch cache location (default `.crypto_regime_cache`), `--quiet`.

### Phase 2: Interpret the Output

The script writes `crypto_regime.json` (machine-readable, for chaining into other skills) and `crypto_regime.md` (one-page report), and prints a one-line summary:

```
CRYPTO REGIME: NEUTRAL (score 68.4/100) — Mixed conditions observed; no strong regime conclusion
```

When presenting results, lead with the zone and posture, then explain the 1-2 components most responsible for the score using their `signal` strings. Flag any components reporting `data_available: false` and what that means for confidence.

### Phase 3 (optional): Feed Downstream

The JSON composite can slot into an `exposure-coach`-style posture summary as
one descriptive crypto-market input. It must not independently authorize,
block, size, or execute a trade.

## Output

The script writes two artifacts to `--output-dir` and prints a one-line summary for workflow chaining:

- `crypto_regime.json` — full machine-readable analysis: `metadata`, per-component results (`score`, `signal`, `data_available`, component-specific fields), and the `composite` block (`score`, `zone`, `guidance`, `effective_weights`).
- `crypto_regime.md` — one-page report: composite score with zone bar, posture line, per-component table (weight / score / signal), and confidence notes.
- Console: `CRYPTO REGIME: <ZONE> (score <N>/100) — <posture>` plus warnings for any skipped components.

## Resources

- `references/VALIDATION.md` — validation status, evidence boundary, and reproduction requirements.
- `references/crypto_regime_methodology.md` — full scoring rationale, every threshold table, the offline snapshot JSON schema, and the live data-source endpoint list.
- `scripts/crypto_regime_analyzer.py` — CLI orchestrator (entry point).
- `scripts/data_client.py` — CoinGecko/Binance fetchers, per-day cache, dominance history accumulator, offline loader.
- `scripts/calculators/` — one module per component; pure functions, fully unit-tested.
- `scripts/scorer.py` — weighted composite with proportional weight redistribution.
- `scripts/tests/` — tests covering every component, the scorer, sparse-data fail-closed behavior, and end-to-end bull/bear/degraded snapshots.

## Known Limitations

- **Dominance history accumulates locally.** CoinGecko's free tier only exposes *current* dominance, so the client stores one observation per run-day in the cache dir. The dominance component reports `data_available: false` until 31 daily observations exist (weight is redistributed until then). Seed it faster via `--input-json`.
- **Funding is best-effort.** If Binance's endpoint is unreachable (geo-restrictions, outage), the component is skipped gracefully.
- **Universe is top-N by market cap** with stablecoins and wrapped/staked assets excluded; it is not a fixed index, so composition drifts with the market.
- Thresholds are heuristic and documented in the methodology reference; they are conservative defaults, not backtested optima.

## Disclaimer

Educational and process-improvement use only. This skill describes market conditions; it does not provide financial advice, signals, or buy/sell instructions. All decisions remain the user's responsibility.
