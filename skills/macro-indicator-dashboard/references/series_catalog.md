# FRED Series Catalog

The 18 series pulled by `fetch_fred_data.py`, organized by indicator family. Each
series is described, told how often it updates, what "good" and "bad" look like
for equities, and which regime it feeds.

## Rates & Yield Curve

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| FEDFUNDS | Effective Federal Funds Rate | Monthly | Falling or below neutral (~2.5%) | Policy stance |
| DGS2 | 2-Year Treasury Constant Maturity | Daily | Falling, below 10Y | Rate cycle |
| DGS10 | 10-Year Treasury Constant Maturity | Daily | Rising modestly | Growth proxy |
| T10Y2Y | 10Y-2Y Yield Spread | Daily | Positive and steepening | Recession leading indicator |
| T10Y3M | 10Y-3M Yield Spread | Daily | Positive | Stronger recession signal than T10Y2Y |

**Why both T10Y2Y and T10Y3M?** The NY Fed recession model uses T10Y3M (stronger
predictor). Traders watch T10Y2Y (faster moving). We score both and take the
worse of the two.

## Credit Conditions

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| BAMLH0A0HYM2 | ICE BofA US High Yield Option-Adjusted Spread | Daily | Tight (<4%) | Credit stress |
| BAMLC0A0CM | ICE BofA US Corporate Master OAS | Daily | Tight (<1.5%) | IG credit stress |
| NFCI | Chicago Fed National Financial Conditions Index | Weekly | Negative (loose) | Master financial conditions gauge |

NFCI is the single best all-in-one financial conditions indicator. Negative = easy,
positive = tight. Moves around zero. It gets 2x weight in the composite score.

## Labor Market

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| PAYEMS | Nonfarm Payrolls (level) | Monthly | Growing | Growth signal |
| UNRATE | Unemployment Rate | Monthly | Low/stable | Cycle signal |
| ICSA | Initial Jobless Claims | Weekly | Low/stable | Leading recession signal |

Rule-of-thumb: the Sahm Rule fires when 3-month avg UNRATE rises >=0.5pp above
its 12-month low. That's a recession signal with a clean historical record.

## Real Economy

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| INDPRO | Industrial Production Index | Monthly | Rising | Growth signal |
| PAYEMS | (see above) | | | |

## Inflation

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| CPIAUCSL | CPI All Urban Consumers | Monthly | YoY in 1.5-3% band | Inflation level |
| CPILFESL | CPI Core (ex food & energy) | Monthly | YoY in 1.5-3% band | Sticky inflation |
| PCEPI | PCE Price Index (Fed's preferred) | Monthly | YoY ~2% | Fed target |
| T5YIE | 5-Year Breakeven Inflation | Daily | ~2% | Market inflation expectations |

## Monetary

| FRED ID | Description | Frequency | Risk-on when | Regime signal |
|---------|-------------|-----------|--------------|---------------|
| M2SL | M2 Money Supply | Monthly | Growing YoY | Liquidity |
| RRPONTSYD | Overnight Reverse Repo Facility Usage | Daily | Falling (cash moving to risk) | Liquidity |

## Composite Weighting

Each family contributes to the 0-100 risk-on score:

- Credit Conditions (NFCI + HY + IG OAS): 30%
- Yield Curve (T10Y2Y + T10Y3M): 15%
- Labor (UNRATE + ICSA + PAYEMS): 20%
- Real Economy (INDPRO): 10%
- Inflation (core PCE YoY + breakevens): 15%
- Liquidity (M2 YoY + RRP): 10%

See `economic_regime_framework.md` for how these feed the regime classifier.
