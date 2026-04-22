# Indicator Interpretation Guide

How to read each series when presenting the dashboard to the user.

## NFCI (National Financial Conditions Index)

Published weekly (Wednesdays) by the Chicago Fed. Composite of 105 underlying
indicators covering money markets, equity/debt markets, and banking system.

- **< -0.5:** Very loose (historically associated with strong equity returns)
- **-0.5 to 0:** Loose/neutral (normal)
- **0 to 0.5:** Tightening (caution)
- **> 0.5:** Tight (equity drawdown risk elevated)
- **> 1.0:** Crisis-level tight (2008, COVID March 2020)

NFCI leads the real economy by 3-6 months. A sustained push above zero while
growth is still positive is one of the earliest warnings of an economic
slowdown.

## Yield Curve (T10Y3M)

The NY Fed's preferred recession indicator.

- **> 1.0:** Steep, normal expansion
- **0.25 to 1.0:** Flattening (late cycle)
- **0 to 0.25:** Near-inverted (caution)
- **< 0:** Inverted (recession signal, typically 6-18 months lead time)
- **< -1.0:** Deeply inverted (stronger signal)

Historically, every US recession since 1960 has been preceded by T10Y3M
inversion, with exactly one false positive (1966).

## Unemployment Rate (UNRATE) + Sahm Rule

The Sahm Rule fires when the 3-month moving average of UNRATE rises >=0.5pp
above its trailing 12-month minimum. Historical track record since 1970: 100%
hit rate, no false positives.

When Sahm fires:
- A recession has almost certainly begun (it's a coincident indicator).
- Equity drawdowns from this point average -20 to -30% before bottom.
- The Fed typically cuts rates within 1-3 months.

## Initial Jobless Claims (ICSA)

Weekly, Thursday morning.

- **< 250k:** Very healthy labor market
- **250-325k:** Normal
- **325-400k:** Softening
- **> 400k:** Recession territory

Use 4-week moving average to filter weekly noise. A sustained push above 325k
is usually an early recession warning, 1-3 months before the NBER officially
declares.

## High Yield Credit Spread (BAMLH0A0HYM2)

The market's real-time stress gauge. Tighter = more risk-on.

- **< 3%:** Very tight (late cycle exuberance)
- **3-4%:** Normal expansion
- **4-6%:** Elevated (caution)
- **> 6%:** Distressed (recession/crisis)
- **> 10%:** Full crisis (2008, COVID peak, 2022 trough)

Pair with IG (BAMLC0A0CM). If IG spreads widen while HY stays tight, something
is breaking in the "safe" segment first - that's unusual and bearish.

## Inflation (Core PCE)

The Fed's preferred measure. Target: 2% YoY.

- **< 1.5%:** Disinflation concern (deflationary risk)
- **1.5-2.5%:** Target range (equity sweet spot)
- **2.5-3.5%:** Above target (Fed leans hawkish)
- **> 3.5%:** Problematic (Fed aggressive, equity multiple compression risk)

Check the 3-month annualized rate vs YoY to see direction. If 3M ann < YoY,
inflation is cooling.

## 5-Year Breakeven (T5YIE)

Market's forward inflation expectations. Calculated as 5Y Treasury yield minus
5Y TIPS yield.

- **< 1.5%:** Deflation scare
- **1.5-2.5%:** Anchored around target
- **> 2.5%:** De-anchoring risk
- **> 3.0%:** Expectations breaking loose

When breakevens rise above 2.5% while core PCE is already above 3%, the Fed
usually gets aggressive.

## M2 Money Supply

Annual growth rate matters more than level.

- **YoY > 10%:** Very loose (liquidity flooding, asset prices rise)
- **YoY 4-8%:** Normal expansion
- **YoY 0-4%:** Tight
- **YoY < 0%:** Contraction (rare, seen in 2022-23 for first time since 1930s)

M2 contraction is a strong deflationary signal and typically precedes growth
scares.

## Overnight Reverse Repo (RRPONTSYD)

How much cash the Fed is absorbing from money funds overnight. Indirect
liquidity gauge.

- **> $1.5T:** Excess liquidity parked (loose conditions)
- **$500B - $1.5T:** Normal
- **< $500B:** Liquidity tightening (reserves scarce)
- **< $100B:** Stress (reserves being drained aggressively)

RRP balances collapsing typically coincides with equity volatility as bank
reserves become scarce.

## Presenting to the User

When delivering the dashboard, lead with:
1. Current regime (one word) + confidence
2. Risk-on score (0-100) + direction vs last run
3. The 2-3 most anomalous indicators (largest absolute z-scores)
4. One-sentence "what changed since last run"
5. Any regime-change alerts

Avoid dumping raw numbers. The orchestrator needs the JSON; the user needs the
narrative.
