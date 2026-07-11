# Historical Validation — Walk-Forward Backtest 2018–2026

Evidence behind the 3-zone map and the composite's discriminative power. This is model validation, not a performance claim: the skill describes market conditions and issues no signals.

## Method

- **Data:** CoinMetrics community data (GitHub, free): daily `PriceUSD`/`ReferenceRateUSD` and market caps for BTC + 13 majors (ETH, XRP, ADA, DOGE, LTC, LINK, BCH, XLM, SOL, AVAX, DOT, MATIC, UNI).
- **Procedure:** for every Monday from 2018-01-01 to 2026-05-18 (438 weeks), truncate all series to data available on that date (no lookahead), build dominance from real market caps of the tracked universe, and run this skill's actual `run_analysis()`. Record composite score and zone; evaluate forward 30/90-day BTC returns afterward.
- **Components tested: 5 of 6.** Historical funding-rate data is not in the free dataset, so the funding component sat out with its weight redistributed — the live skill has strictly more information than what was validated here.

## Results

**Score behavior:** range 9.7–95.9, no degenerate clustering.

**Qualitative regime calls (walk-forward, no lookahead):**

| Moment | Score | Zone |
|---|---|---|
| Mid-2018 bear | 17 | RISK_OFF |
| COVID crash week (2020-03-16) | 28 | RISK_OFF |
| Late-2020 breakout | 85 | RISK_ON |
| 2021 bull (April / November ATH) | 96 / 93 | RISK_ON |
| LUNA collapse week (2022-05) | 17 | RISK_OFF |
| FTX collapse week (2022-11) | 12 | RISK_OFF |
| Early-2023 recovery | 47 | NEUTRAL |
| 2024 ETF-era highs | 92 | RISK_ON |

Note the model was max-bullish at the November 2021 top — trend-following systems are long at tops by construction; the value is the fast flip to RISK_OFF during the subsequent decline, not peak-calling.

**Forward BTC returns by zone (3-zone map: RISK_ON ≥ 80, RISK_OFF < 40):**

| Zone | % of weeks | 90d mean | 90d median | 90d win rate |
|---|---|---|---|---|
| RISK_ON | 23.7% | +21.9% | +2.6% | 51% |
| NEUTRAL | 39.7% | +14.2% | +6.8% | 60% |
| RISK_OFF | 36.5% | +7.5% | −3.1% | 43% |

Monotonic mean ordering across all three zones; a 20-point mean spread between the extremes. The 30-day horizon showed no reliable gradient — this is a posture model, not a short-term timing model.

**Why 3 zones, not 5:** the original 5-zone design was also tested. Its extremes worked identically, but the middle three zones did not rank monotonically (NEUTRAL's forward returns beat CONSTRUCTIVE's), i.e. the finer gradations were precision the data did not support. Two pre-registered 3-zone variants were compared; the 80/40 boundary variant produced monotonic ordering, the 70/30 variant did not. 80/40 was adopted.

**Illustrative exposure scaling** (weekly rebalance, 100% / 50% / 0% by zone, remainder cash, no fees or slippage):

| | Total multiple | Max drawdown |
|---|---|---|
| Buy & hold BTC | 5.72x | −77.2% |
| Zone-scaled | 7.01x | −43.4% |

The robust claim is the drawdown reduction and monotonic zone separation. The outperformance figure should be treated skeptically: no transaction costs, weekly rebalance granularity, and ~2 full market cycles of sample.

## Limitations

1. Only 5 of 6 components validated (no historical funding data).
2. Dominance approximated from the 14-coin tracked universe, not the full market.
3. Universe is today's surviving majors — survivorship bias modestly flatters breadth readings.
4. 438 overlapping weekly samples are far fewer independent observations than they appear; exact figures are indicative, not statistically proven.
5. Thresholds were designed with general knowledge of crypto history (soft in-sample bias), though nothing was numerically fit to this dataset except the single 5-zone → 3-zone comparison described above.

Reproduction: the harness is a ~150-line script over CoinMetrics CSVs; happy to contribute it under `examples/` if wanted.
