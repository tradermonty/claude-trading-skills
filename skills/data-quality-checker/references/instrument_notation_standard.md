# Instrument Notation Standard

Reference document for consistent instrument naming across market analysis documents.

## Standard Notation Table

| Asset | Ticker (ETF) | Ticker (Futures) | Full Name (EN) | Japanese | Notes |
|-------|-------------|-------------------|----------------|----------|-------|
| Gold | GLD | GC | Gold | 金 / ゴールド / 金先物 | GLD = SPDR Gold Shares ETF; GC = COMEX Gold Futures |
| Silver | SLV | SI | Silver | 銀 | SLV = iShares Silver Trust; SI = COMEX Silver Futures |
| S&P 500 | SPY | ES | S&P 500 | S&P500 | SPY = SPDR S&P 500 ETF; SPX = index; ES = E-mini Futures |
| S&P 500 Index | -- | SPX | S&P 500 Index | S&P500指数 | Cash index, not tradable directly |
| Volatility | -- | VIX | CBOE VIX | 恐怖指数 / VIX | VIX = index; VXX/UVXY = ETPs |
| US Treasuries | TLT | ZB | 20+ Year Treasury | 米国債 / 10年債 | TLT = iShares 20+ Year; ZB = 30Y futures |
| Crude Oil | USO | CL | WTI Crude Oil | 原油 / WTI | USO = United States Oil Fund; CL = NYMEX WTI Futures |

## Digit-Count Hints (Price Scale Validation)

The digit-count hint system validates whether a reported price is in the correct
order of magnitude for a given instrument. It counts the number of digits before
the decimal point.

| Instrument | Digit Range | Typical Price Range | Example Valid | Example Invalid |
|------------|------------|---------------------|---------------|-----------------|
| GLD | 2-3 | $100 - $999 | GLD: $268 | GLD: $2,800 (futures price) |
| GC | 3-4 | $1,000 - $9,999 | GC: $2,650 | GC: $265 (ETF price) |
| SPY | 2-3 | $100 - $999 | SPY: $580 | SPY: $5,800 (index price) |
| SPX | 4-5 | $1,000 - $99,999 | SPX: $5,800 | SPX: $580 (ETF price) |
| VIX | 1-2 | $1 - $99 | VIX: $18 | VIX: $180 |
| TLT | 2-3 | $10 - $999 | TLT: $92 | TLT: $9 |
| SLV | 2-2 | $10 - $99 | SLV: $28 | SLV: $280 |
| SI | 2-2 | $10 - $99 | SI: $31 | SI: $3,100 (total contract) |
| USO | 2-2 | $10 - $99 | USO: $72 | USO: $720 |
| CL | 2-3 | $10 - $999 | CL: $78 | CL: $7 |

### Common Mistakes

1. **ETF/Futures confusion**: Labeling a price as GLD when it is actually GC
   (gold futures), or vice versa. Gold ETF ~$260 vs Gold Futures ~$2,600.
2. **Index/ETF confusion**: Labeling a price as SPY when it is SPX, or vice
   versa. SPY ~$580 vs SPX ~$5,800.
3. **Per-share vs per-contract**: Futures prices are typically per unit (e.g.,
   per troy ounce for gold), while ETF prices are per share.

## Currency Pair Notation

| Standard | Alternatives | Avoid |
|----------|-------------|-------|
| USD/JPY | USDJPY, ドル円 | JPY/USD (reversed) |
| EUR/USD | EURUSD, ユーロドル | USD/EUR (reversed) |
| GBP/USD | GBPUSD, ポンドドル | USD/GBP (reversed) |

**Convention**: Base currency / Quote currency. The price tells you how many
units of the quote currency you need to buy one unit of the base currency.

## Index Notation

| Preferred | Alternatives | Context |
|-----------|-------------|---------|
| S&P 500 | S&P500, SP500 | General references |
| SPX | S&P 500 Index | When citing the cash index value |
| SPY | SPDR S&P 500 ETF | When citing the ETF price |
| Dow | DJIA, Dow Jones, DJI | Dow Jones Industrial Average |
| Nasdaq | COMP, QQQ, NDX | Nasdaq Composite (COMP) vs Nasdaq-100 (NDX/QQQ) |
| Russell 2000 | RUT, IWM | RUT = index, IWM = ETF |

## Commodity Notation

| Commodity | Futures Ticker | ETF Ticker | Japanese |
|-----------|---------------|------------|----------|
| Gold | GC | GLD, IAU | 金, ゴールド |
| Silver | SI | SLV | 銀 |
| Crude Oil (WTI) | CL | USO | 原油, WTI |
| Natural Gas | NG | UNG | 天然ガス |
| Copper | HG | COPX | 銅 |

## Best Practices

1. **Pick one notation per document** and use it consistently.
2. **On first mention**, spell out the full name with ticker:
   "SPDR Gold Shares (GLD) traded at $268."
3. **Do not mix ETF and futures tickers** for the same asset without
   explicit labeling (e.g., "GLD (ETF) vs GC (futures)").
4. **Japanese documents** may use Japanese names, but should include
   the ticker on first mention: "金（GLD）は$268で取引。"
