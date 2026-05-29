---
layout: default
title: Quant Strategy Framework
parent: English
nav_order: 10
lang_peer: /ja/playbooks/quant-strategy-framework/
permalink: /en/playbooks/quant-strategy-framework/
---

# Cross-Asset Quant Strategy — Pre / During / Post Framework
{: .no_toc }

The playbook that wires this project's skills + API clients into one process across equities, forex (research-only), commodities, options, and thematic plays.
{: .fs-6 .fw-300 }

**This framework is research-and-decision-support only.** All execution stays manual — every artifact carries `manual_review_required: true` and a `data_gaps[]` array. You always pull the trigger.

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## The spine — applies to every asset class

Three loops run continuously:

| Loop | Cadence | Output |
|---|---|---|
| Macro regime | Weekly | Risk-on / risk-off / transitioning posture |
| Idea generation | Daily | Ranked candidates with hypothesis cards |
| Position lifecycle | Per trade | Pre → During → Post |

### The 7-layer signal stack

A trade only earns capital if **layers 1–5 align**:

```
1. Macro regime          → BISClient, BLSClient, BEAClient, EIAClient
2. Theme / sector        → theme-detector, sector-analyst
3. Asset-class screener  → VCP / CANSLIM / PEAD / Dividend / Parabolic
4. Setup confirmation    → technical-analyst (chart), breakout-trade-planner
5. What's priced in      → PolymarketClient, NewsClient, FMP consensus
                          (see references/what-is-priced-in-framework.md)
6. Sizing                → position-sizer (R-multiples), exposure-coach
7. Postmortem            → signal-postmortem, trader-memory-core
```

### The kill rule

Every trade must have a **written thesis** before entry, a **kill criterion** (what makes this wrong), and a **journal entry** after exit. No exceptions. This *is* the manual review gate.

---

## 1. Equities — Industry / Single Stock / Sector

**Scope:** US-listed stocks + sector/thematic ETFs. Swing (3–30 days) or position (1–6 months).

### PRE

| Step | Tool | Output |
|---|---|---|
| 1. Idea source | `vcp-screener` (bullish swing), `canslim-screener` (growth), `pead-screener` (earnings drift), `parabolic-short-trade-planner` (mean-reversion shorts), `dividend-growth-pullback-screener` (quality dip) | Ranked candidates |
| 2. Theme context | `theme-detector` | Filter to top-3 accelerating themes |
| 3. Chart confirmation | `technical-analyst` (chart image) | Yes/no on visual pattern |
| 4. Trigger levels | `breakout-trade-planner` | 5-min ORL, breakout extension, invalidation level |
| 5. Earnings reaction history | `earnings-trade-analyzer` | Don't fight buy-rumor-sell-news patterns |
| 6. What's priced in | `PolymarketClient`, `NewsClient`, FMP consensus vs your estimate | Gap = (your view − consensus) × reaction function |
| 7. Hypothesis card | `trade-hypothesis-ideator` → `trader-memory-core` IDEA → ENTRY_READY | Thesis + kill criterion + R-target + time-stop |
| 8. Sizing | `position-sizer` (stop-loss or Kelly) | Shares + dollar risk |
| 9. Portfolio check | `exposure-coach` | Sector cap, breadth posture, ceiling % |

### DURING

- **Daily morning:** run `market-regime-daily` workflow (breadth + uptrend + exposure). If composite drops a tier → tighten stops, no new entries.
- **News monitor:** `NewsClient.get_market_news(tickers=[...], days=1)` — any thesis-killing headline.
- **PEAD plays:** watch SIGNAL_READY → BREAKOUT transitions.
- **Earnings during hold:** size down to ⅓ or close before print, unless earnings *is* the thesis.

### POST

- `trader-memory-core` → CLOSED with realized R, MAE/MFE.
- `signal-postmortem`: what worked, what didn't, was the kill criterion respected, was sizing correct.
- Roll lessons into `monthly-performance-review`.

---

## 2. Forex — Research Only

**Scope:** Directional bias for USD/JPY, EUR/USD, GBP/USD, AUD/USD, USD/CAD. **Output is a research artifact**, not orders. Execution lives in a separate project; this project must never import from it.

### PRE (research)

| Step | Tool | Signal |
|---|---|---|
| 1. Rate differential | `BISClient.rate_differential("US", "JP")` | Carry tailwind / headwind in pp |
| 2. US macro | `BLSClient.get_named("unemployment_rate")`, `BLSClient.get_named("cpi_core")`, `BEAClient.real_gdp_growth()` | Fed hawkish/dovish bias |
| 3. Counterparty macro | `EStatClient.cpi_national()` for JPY; commodity for AUD/CAD | Cross-country surprise potential |
| 4. Commodity beta | `EIAClient.natural_gas_spot()`, `CommodityClient.latest(["WTI", "GOLD"])` | AUD = iron-ore + copper; CAD = WTI; gold = USD inverse |
| 5. Catalyst pricing | `PolymarketClient.search_markets("Fed cut")` | Implied probability of policy move |
| 6. Research artifact | Markdown report with `manual_review_required: true` + `data_gaps[]` | Directional bias score (−5 … +5), no trade ticket |

### DURING (monitoring research)

- Watch BLS NFP, CPI prints (Finnhub econ calendar)
- BIS rate revisions monthly
- News via `NewsClient`

### POST (research calibration)

- Did the rate-differential thesis play out?
- Calibrate: which BIS countries / BLS series have the highest hit rate for predicting direction?
- Log to `trader-memory-core` with `research_only: true`

### Explicitly OUT

Order placement, stops, broker code — lives in the separate forex project. Release gate enforces this.

---

## 3. Commodities

**Scope:** Energy (WTI, Brent, nat gas), precious (gold, silver), industrial (copper). Trade via **equity proxy ETFs/stocks** (XLE, USO, GLD, GDX, FCX) — futures are out of scope.

### PRE

| Step | Tool | Signal |
|---|---|---|
| 1. Fundamental driver | `EIAClient.electricity_demand("PJM")` (AI power demand), `EIAClient.natural_gas_spot()` (gas), `EIAClient.power_demand_yoy()` | YoY inflection? |
| 2. Spot prices | `CommodityClient.latest(["BRENT", "GOLD", "COPPER"])` | Where are we vs 30-day range |
| 3. Series trend | `CommodityClient.time_series("BRENT", start, end)` | Direction over last 30d |
| 4. Theme context | `theme-detector` — Oil & Gas, Gold & Precious Metals, Power Infrastructure | Confirm theme heat ≥ 60, lifecycle = Accelerating |
| 5. Spark spread (for IPPs) | `(power_price) − (gas_price × heat_rate)` using EIA data | Widening = bullish VST/NRG/TLN; compressing = bearish |
| 6. Equity expression | Pick proxies — energy long: XLE/XOP/OIH or VST/CEG/EQT; gold: GDX/GLD/NEM; copper: FCX | One equity per thesis |
| 7. What's priced in | Polymarket OPEC + Fed cut markets, implied vol of commodity ETF | Surprise potential |

### DURING

- Spark spread on a weekly watch — widening confirms thesis on IPPs
- News for geopolitical (Mid-East, Russia, OPEC) via `NewsClient`
- EIA inventory prints (weekly)

### POST

- Did EIA prints confirm the demand thesis?
- Calibrate your power-demand model vs actual
- Roll to `trader-memory-core`

---

## 4. Options

**Scope:** Defined-risk strategies on liquid US tickers. **No naked options** (uncapped risk).

### PRE

**1. Underlying must already be a §1 high-conviction equity setup.** Options are an *expression*, not a thesis source.

**2. Strategy selection — decision tree:**

| Bias | IV regime | Strategy |
|---|---|---|
| Bullish | High IV | **Bull put spread** (sell premium, defined risk) |
| Bullish | Low IV | **Bull call spread** or **long call** (buy cheap directional) |
| Bullish + own stock | any | **Covered call** (yield enhancement) |
| Range-bound | High IV | **Iron condor** |
| Bearish | High IV | **Bear call spread** |
| Bearish | Low IV | **Bear put spread** or **long put** |

**3. Validation:** `options-strategy-advisor` for Black-Scholes pricing + Greeks + scenario analysis. **Probability of profit ≥ 60%** as the floor.

**4. Sizing:** max loss per trade = `position-sizer` R amount. Net debit OR max-loss of credit spread ≤ R.

**5. What's priced in:** IV percentile vs 1Y range (premium-rich vs cheap). At earnings: straddle price = market's expected move — compare to your own move estimate.

### DURING

- Monitor **delta** (directional risk) and **theta** (decay benefit)
- **Close winners at 50% max profit** (don't squeeze last 25%)
- Adjust on **tested short strike**: roll out + down/up
- **Earnings during hold:** close or roll. Never hold short-vol through binary event.

### POST

- Realized P&L vs theoretical max
- **Greek attribution**: how much P&L came from delta vs theta vs vega
- `signal-postmortem` with IV regime context

---

## 5. Thematic / Sector Rotation

**Scope:** Multi-week thematic plays via ETFs or basket of top constituents.

### PRE

| Step | Tool | Output |
|---|---|---|
| 1. Theme scan | `theme-detector --dynamic-stocks` | Ranked themes by heat + lifecycle |
| 2. Lifecycle filter | Avoid **Exhausting**, favor **Emerging / Accelerating** | Late-cycle is crowded trade risk |
| 3. Constituent picks | Top 3-5 stocks per theme by relative strength | Equal-weight basket |
| 4. ETF expression | Proxy ETF from `skills/theme-detector/references/cross_sector_themes.md` | Single-line expression |
| 5. Industry confirmation | Industry rank top quartile on FINVIZ | Cross-check on theme detector output |
| 6. Volume confirmation | `PolygonClient.get_grouped_daily()` | Real institutional flow |

### DURING

- Daily breadth check (`market-breadth-analyzer`) — themes are first to roll when breadth contracts
- Theme lifecycle drift watch: **exit before Exhausting**, not after

### POST

- Did the proxy ETF outperform SPY by ≥ 5% over the hold?
- Update theme model with realized success/failure

---

## Cadence — when each routine runs

| When | Routine | Skills / Workflows |
|---|---|---|
| **15 min before US open** | Daily regime check | `market-regime-daily` workflow |
| **Daily, post-close** | News scan, position monitor | `NewsClient.get_market_news(tickers=open_positions)` |
| **Daily (post-regime)** | Multi-asset opportunity scan | `multi-asset-opportunity-daily` workflow (this playbook in flow form) |
| **Weekly (Sunday)** | Fresh candidates + macro refresh | `swing-opportunity-daily`, `theme-detector`, BIS/BLS/BEA refresh |
| **Monthly** | Performance + calibration | `monthly-performance-review`, `signal-postmortem` aggregation |
| **Per trade — Pre** | Hypothesis card + sizing | `trade-hypothesis-ideator`, `position-sizer`, `exposure-coach`, `trader-memory-core` IDEA → ENTRY_READY |
| **Per trade — During** | Daily kill check, news monitor | `trader-memory-core` review-due, `NewsClient` |
| **Per trade — Post** | Close, MAE/MFE, lessons | `trader-memory-core` CLOSED, `signal-postmortem` |

---

## Toolchain map — every step has exactly one tool

| Need | Tool |
|---|---|
| OHLCV (replace yfinance) | `PolygonClient.get_aggs()` |
| US macro (GDP, savings) | `BEAClient` |
| US labor + inflation | `BLSClient` |
| Cross-country rates | `BISClient.rate_differential()` |
| Energy / power | `EIAClient` |
| Commodity spot | `CommodityClient.latest()` |
| Japan macro | `EStatClient` |
| News + sentiment | `NewsClient` (Marketaux + Newsdata) |
| Catalyst probability | `PolymarketClient` |
| Calendars (econ + earnings) | `FinnhubClient` (free) or FMP |
| Theme detection | `theme-detector` skill |
| Stock screening | VCP / CANSLIM / PEAD / Dividend / Parabolic skills |
| Hypothesis card | `trade-hypothesis-ideator` |
| Sizing | `position-sizer` |
| Posture / exposure | `exposure-coach` |
| Memory / journal | `trader-memory-core` |
| Postmortem | `signal-postmortem` |
| Backtest | `backtest-expert` |

---

## Out-of-scope (the manual review gate)

- Auto-trade / broker execution / order placement
- OANDA / forex execution (lives in a separate project)
- Binance / crypto auto-trade
- Any closed-loop without human sign-off

Every artifact this framework produces carries `manual_review_required: true` and `data_gaps[]`. You always pull the trigger.

---

## Reference docs in the project

- `skills/theme-detector/references/cross_sector_themes.md` — theme definitions + constituents
- `skills/theme-detector/references/energy-power-market-signals.md` — spark spread, capacity auctions, LMP mechanics
- `skills/trade-hypothesis-ideator/references/what-is-priced-in-framework.md` — three model-to-trade frameworks
- `scripts/api_clients/README.md` — full API client catalog
- `workflows/` — canonical workflow definitions
