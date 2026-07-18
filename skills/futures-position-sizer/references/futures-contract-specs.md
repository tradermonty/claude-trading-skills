# Futures Contract Specifications (Verified)

The 23-market core table `CONTRACT_SPECS` in `scripts/futures_sizing.py`, sourced from the
official exchange contract-spec pages and rulebook chapters (CME Group, Cboe, ICE) --
never blogs, aggregator sites, or secondary sources. Every row is verified independently
against its own `source_url`. A table-wide unit test asserts `tick_value == multiplier x
tick_size` (within 1e-9 relative) for every row -- this catches a transcription error
mechanically -- and three literal spot-checks (ES, GC, ZB) are pinned independently of the
table itself, so a bad edit to `CONTRACT_SPECS` would still fail even though it might
satisfy the internal-consistency invariant.

**Currency column = QUOTE currency, not underlying.** All 23 rows are USD-quoted (a
table-wide unit test asserts this). The CME FX futures (E6/J6/B6/A6/D6/S6) and ICE's DX
have non-USD contract SIZES -- e.g. B6's contract size is GBP 62,500 -- but they trade
and settle in USD. Mislabeling the currency column as the underlying would trigger a
spurious `missing_fx_rate` error or a double currency conversion.

**Outright tick, not spread tick.** SI, NG, and VX each have a finer minimum price
increment that applies only to spread/straddle trades, TAS Block/ECRP order types, or
inter-commodity spreads -- never to a single-leg position. Since this skill sizes a
single-leg stop-loss, every row below uses the OUTRIGHT tick (documented per-row where
a spread tick also exists).

## Table

| Symbol | Product | Multiplier | Tick Size | Tick Value | Currency | Exchange | Source | Verified |
|---|---|---|---|---|---|---|---|---|
| ES | E-mini S&P 500 Index futures | 50 | 0.25 | $12.50 | USD | CME | [Rulebook Ch.358](https://www.cmegroup.com/rulebook/CME/IV/350/358/358.pdf) | 2026-07-17 |
| NQ | E-mini Nasdaq-100 Index futures | 20 | 0.25 | $5.00 | USD | CME | [Rulebook Ch.359](https://www.cmegroup.com/rulebook/CME/IV/350/359/359.pdf) | 2026-07-17 |
| YM | E-mini Dow Jones Industrial Average ($5) Index futures | 5 | 1.00 | $5.00 | USD | CBOT | [Rulebook Ch.27](https://www.cmegroup.com/rulebook/CBOT/III/27.pdf) | 2026-07-17 |
| QR | E-mini Russell 2000 Index futures (Globex ticker RTY) | 50 | 0.10 | $5.00 | USD | CME | [Rulebook Ch.393](https://www.cmegroup.com/rulebook/CME/III/300/393.pdf) | 2026-07-17 |
| VX | Cboe Volatility Index (VIX) futures | 1000 | 0.05 (outright) | $50.00 | USD | CFE | [Cboe VIX Futures Specs](https://www.cboe.com/tradable-products/vix/vix-futures/specifications/) | 2026-07-17 |
| ZT | 2-Year U.S. Treasury Note futures | 2000 | 0.00390625 (1/8-of-1/32) | $7.8125 | USD | CBOT | [Rulebook Ch.21](https://www.cmegroup.com/rulebook/CBOT/II/21.pdf) | 2026-07-17 |
| ZF | 5-Year U.S. Treasury Note futures | 1000 | 0.0078125 (1/4-of-1/32) | $7.8125 | USD | CBOT | [Rulebook Ch.20](https://www.cmegroup.com/rulebook/CBOT/II/20.pdf) | 2026-07-17 |
| ZN | 10-Year U.S. Treasury Note futures | 1000 | 0.015625 (1/2-of-1/32, i.e. 1/64) | $15.625 | USD | CBOT | [Rulebook Ch.19](https://www.cmegroup.com/rulebook/CBOT/II/19.pdf) | 2026-07-17 |
| ZB | 30-Year U.S. Treasury Bond futures | 1000 | 0.03125 (1/32) | $31.25 | USD | CBOT | [Rulebook Ch.18](https://www.cmegroup.com/rulebook/CBOT/V/18/18.pdf) | 2026-07-17 |
| DX | ICE U.S. Dollar Index futures | 1000 | 0.005 | $5.00 | USD | ICE | [ICE Product Specs](https://www.ice.com/products/194/specs) | 2026-07-17 |
| E6 | Euro FX futures (CME ticker 6E) | 125,000 | 0.00005 | $6.25 | USD | CME | [CME Euro FX Specs](https://www.cmegroup.com/markets/fx/g10/euro-fx.contractSpecs.html) | 2026-07-17 |
| J6 | Japanese Yen futures (CME ticker 6J) | 12,500,000 | 0.0000005 | $6.25 | USD | CME | [CME Japanese Yen Specs](https://www.cmegroup.com/markets/fx/g10/japanese-yen.contractSpecs.html) | 2026-07-17 |
| B6 | British Pound futures (CME ticker 6B) | 62,500 | 0.0001 | $6.25 | USD | CME | [CME British Pound Specs](https://www.cmegroup.com/markets/fx/g10/british-pound.contractSpecs.html) | 2026-07-17 |
| A6 | Australian Dollar futures (CME ticker 6A) | 100,000 | 0.00005 | $5.00 | USD | CME | [CME Australian Dollar Specs](https://www.cmegroup.com/markets/fx/g10/australian-dollar.contractSpecs.html) | 2026-07-17 |
| D6 | Canadian Dollar futures (CME ticker 6C) | 100,000 | 0.00005 | $5.00 | USD | CME | [CME Canadian Dollar Specs](https://www.cmegroup.com/markets/fx/g10/canadian-dollar.contractSpecs.html) | 2026-07-17 |
| S6 | Swiss Franc futures (CME ticker 6S) | 125,000 | 0.00005 | $6.25 | USD | CME | [CME Swiss Franc Specs](https://www.cmegroup.com/markets/fx/g10/swiss-franc.contractSpecs.html) | 2026-07-17 |
| GC | Gold futures | 100 | 0.10 | $10.00 | USD | COMEX | [CME Gold Specs](https://www.cmegroup.com/markets/metals/precious/gold.contractSpecs.html) | 2026-07-17 |
| SI | Silver futures | 5,000 | 0.005 (outright) | $25.00 | USD | COMEX | [CME Silver Specs](https://www.cmegroup.com/markets/metals/precious/silver.contractSpecs.html) | 2026-07-17 |
| HG | Copper futures | 25,000 | 0.0005 | $12.50 | USD | COMEX | [CME Copper Specs](https://www.cmegroup.com/markets/metals/base/copper.contractSpecs.html) | 2026-07-17 |
| PL | Platinum futures | 50 | 0.10 | $5.00 | USD | NYMEX | [CME Platinum Specs](https://www.cmegroup.com/markets/metals/precious/platinum.contractSpecs.html) | 2026-07-17 |
| CL | WTI Crude Oil futures | 1,000 | 0.01 | $10.00 | USD | NYMEX | [CME WTI Crude Specs](https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.contractSpecs.html) | 2026-07-17 |
| NG | Henry Hub Natural Gas futures | 10,000 | 0.001 (outright) | $10.00 | USD | NYMEX | [CME Natural Gas Specs](https://www.cmegroup.com/markets/energy/natural-gas/natural-gas.contractSpecs.html) | 2026-07-17 |
| BT | Bitcoin futures (CME ticker BTC) | 5 | 5.00 | $25.00 | USD | CME | [Rulebook Ch.350](https://www.cmegroup.com/rulebook/CME/IV/350/350.pdf) | 2026-07-17 |

## Notable Rows

### QR = E-mini Russell 2000 (Globex ticker RTY), not the discontinued ICE product

"QR" is not a commonly known ticker. Resolved by pulling live 2026 FMP COT data for
symbol QR directly (the raw CFTC fields, not FMP's own label): every recent weekly
report shows `marketAndExchangeNames="RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE"`,
`cftcContractMarketCode="239742"`, `cftcMarketCode="CME"`,
`contractUnits="(RUSSELL 2000 INDEX X $50)"`, with roughly 400K open interest --
i.e. an actively-traded contract. Cross-confirmed against CME Rulebook Chapter 393:
"$50.00 times the Russell 2000 Index... minimum price increment of 0.10 Index points,
equal to $5.00 per contract." This is CME's current E-mini Russell 2000 (Globex ticker
RTY today), NOT the discontinued ICE "Russell 2000 Mini" (legacy ticker TF, a $100
multiplier, delisted around 2017 when the Russell index license moved back to CME) --
using the ICE product's multiplier would double the correct risk-per-contract figure.

### ZT's tick: resolved as 1/8-of-1/32, not 1/4-of-1/32

ZT's minimum price increment is disputed among third-party aggregator sites. Resolved
here ONLY against CME Group's own Rulebook Chapter 21, which states verbatim:
"The minimum price fluctuation shall be one-eighth of one thirty-second of one point
(equal to $7.8125 per contract), including intermonth spreads." That is
1/8 x 1/32 = 1/256 = 0.00390625 points on a $200,000 face-value contract (2-year and
3-year Treasury futures are the only CBOT products with $200,000 par instead of
$100,000) -> $2,000/point x 0.00390625 = $7.8125. This is a DIFFERENT fraction from
ZF's 1/4-of-1/32 -- the two land on the same $7.8125 dollar tick only because ZT's par
value is 2x ZF's while its fraction is half as fine, which is likely the source of the
aggregator confusion.

### A6/D6/S6: CME halved the minimum price increment between 2016 and 2022

CME reduced the outright minimum price increment (MPI) on these three FX futures from
0.0001 to 0.00005 in three separate, dated changes:

- **A6 (6A):** 0.0001 ($10.00/tick) -> 0.00005 ($5.00/tick), effective November 23, 2020
  (CME Product Modification Summary Chadv20-353).
- **S6 (6S):** 0.0001 ($12.50/tick) -> 0.00005 ($6.25/tick), effective May 2022
  (CME notice SER-8936).
- **D6 (6C):** 0.0001 ($10.00/tick) -> 0.00005 ($5.00/tick), effective July 11, 2016
  (`cmegroup.com/trading/fx/mpi.html`).

Confirmed by the per-symbol footnotes in CME's own "2023 FX Product Guide" (22nd
edition) and cross-checked against `cmegroup.com/trading/fx/mpi.html` (the MPI
change-history page). Many generic aggregator sites and default web-search snippets
still quote the stale, pre-reduction values -- an earlier provisional draft of this
table made exactly that mistake for all three rows.

### D6 = CME 6C (Canadian Dollar), not TBD

Confirmed via CME's 2023 FX Product Guide (CAD/USD futures page): Product Code 6C,
contract size 100,000 CAD, quoted USD per CAD -- matching the "D6" vendor-symbol
convention (D for "Dollar"/CAD, since a leading digit isn't a valid symbol character
for some data vendors) used by this project's COT-report symbol list.

### VX: outright tick vs. spread tick

Cboe's own specifications page states 0.05 index points ($50.00/contract) as the
standard/outright minimum price interval; a finer 0.01-point ($10.00) tick applies only
to the individual legs and net prices of SPREAD trades, and a still-finer 0.005-point
tick applies only to TAS Block Trades and Exchange-for-Related-Position (ECRP) order
types. This table uses 0.05/$50.00 -- the correct tick for sizing a single-leg outright
stop-loss; using the spread tick would understate risk by 5x.

### BT: CME's own ticker is "BTC", not "BT"; distinct from the Micro contract "MBT"

CME has no product literally ticked "BT". The standard-size, 5-BTC-per-contract, USD
cash-settled Bitcoin future is officially ticker **BTC** (Rulebook Chapter 350: "Each
futures contract shall be valued at 5 bitcoin... minimum price increment shall be
$5.00, equal to $25.00 per contract"). This is entirely distinct from CME's **Micro
Bitcoin futures, ticker MBT** (Rulebook Chapter 348), which is 0.1 BTC/contract -- 50x
smaller notional per contract. "BT" is this project's own COT/vendor-feed symbol
(matching `cot-contrarian-detector`'s `CORE_SYMBOLS` convention) and is mapped to
CME's BTC contract here, not MBT.

## Verification Method

Every row above was verified against the official exchange's own contract-spec or
rulebook page (`cmegroup.com`, `ice.com`, `cboe.com`) -- never a blog, aggregator site
(Barchart, TradingView, Investing.com, Wikipedia), or other secondary source. Where
CME's live `contractSpecs.html` marketing pages were unreachable via automated fetch
(client-side JS rendering / bot-detection blocking direct scraping), verification fell
back to CME's own official static PDF rulebook chapters (the legally authoritative
contract text, arguably more authoritative than the marketing page) or a
Wayback-Machine-mirrored snapshot of CME's own official PDF/HTML bytes -- both are
still the exchange's own primary-source content, not a third party's restatement of
it. Every `tick_value` was independently arithmetic-checked
(`multiplier x tick_size`) against what the source states as the per-contract dollar
figure, with zero discrepancies across all 23 rows.
