# Sector Sensitivity Matrix

This reference organizes, in matrix form, sector-level sensitivity to various event types.
Use it during scenario analysis to quickly identify which sectors are most likely to be affected.

## Legend

**Impact:**
- `++` : Strong positive impact
- `+` : Positive impact
- `0` : Neutral / minimal impact
- `-` : Negative impact
- `--` : Strong negative impact

**Confidence:**
- `H` : High (consistent historical pattern)
- `M` : Medium (situation-dependent)
- `L` : Low (high uncertainty)

---

## 1. Matrix by Monetary-Policy Event

### Rate-Hike Environment

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Financials (banks) | + | H | JPM, BAC, WFC | Higher net interest income |
| Financials (insurance) | + | M | MET, PRU, AIG | Better investment income |
| Technology | - | H | AAPL, MSFT, NVDA | High-multiple discounts |
| Consumer Discretionary | - | H | AMZN, HD, NKE | Higher borrowing costs |
| Real Estate (REITs) | -- | H | AMT, PLD, EQIX | Rate-sensitive; higher financing costs |
| Utilities | - | H | NEE, DUK, SO | Reduced bond-proxy appeal |
| Healthcare | 0 | M | UNH, JNJ, PFE | Relatively defensive |
| Consumer Staples | 0 | M | PG, KO, WMT | Relatively defensive |
| Energy | 0 | L | XOM, CVX, COP | Macro-environment dependent |
| Materials | - | M | LIN, APD, ECL | Cyclical |
| Industrials | - | M | CAT, DE, HON | Capex slowdown concerns |
| Communication Services | 0 | M | GOOGL, META, DIS | Idiosyncratic factors dominate |

### Rate-Cut Environment

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Technology | ++ | H | AAPL, MSFT, NVDA | Multiple expansion for growth |
| Real Estate (REITs) | ++ | H | AMT, PLD, EQIX | Lower financing costs |
| Utilities | + | H | NEE, DUK, SO | Relative appeal of dividend yield |
| Consumer Discretionary | + | H | AMZN, HD, NKE | Stimulates consumption |
| Financials (banks) | - | H | JPM, BAC, WFC | Lower net interest income |
| Healthcare | 0 | M | UNH, JNJ, PFE | Relatively defensive |
| Consumer Staples | 0 | M | PG, KO, WMT | Relatively defensive |
| Energy | 0 | L | XOM, CVX, COP | Macro-environment dependent |

---

## 2. Matrix by Geopolitical Event

### Wars / Armed Conflicts

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Defense | ++ | H | LMT, RTX, NOC, GD | Higher military spending |
| Energy | + | H | XOM, CVX, COP | Higher prices on supply concerns |
| Gold (miners) | ++ | H | NEM, GOLD, AEM | Safe-haven demand |
| Airlines | -- | H | DAL, UAL, AAL | Fuel costs, weaker demand |
| Travel / leisure | -- | H | MAR, HLT, BKNG | Demand destruction |
| Insurance | - | M | AIG, TRV, ALL | Geopolitical-risk reserves |
| Semiconductors | - | M | NVDA, AMD, INTC | Supply-chain risk |
| Shipping | +/- | L | ZIM, DAC, MATX | Route-dependent |

### Tariffs / Trade Friction (vs. China)

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Semi equipment | -- | H | AMAT, LRCX, KLAC | Restrictions on China market |
| China-exposed consumer | - | H | NKE, AAPL | Affected on both production and sales |
| Agriculture | - | H | DE, ADM, BG | Lower exports to China |
| Mexico-based producers | + | M | - | Supply-chain alternative beneficiaries |
| US-based manufacturers | + | M | - | Onshoring beneficiaries |

---

## 3. Matrix by Regulatory / Policy Change

### Tighter Environmental Rules

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Renewables (solar) | ++ | H | ENPH, SEDG, FSLR | Expanded policy support |
| Renewables (wind) | ++ | H | NEE, AES | Expanded policy support |
| EV | ++ | H | TSLA, RIVN, LCID | Regulation-driven demand |
| Lithium / batteries | ++ | H | ALB, LTHM | Linked to EV demand |
| Oil & gas | -- | H | XOM, CVX, COP | Stranded-asset risk |
| Coal | -- | H | - | Accelerated phase-out |
| Airlines | - | M | DAL, UAL, AAL | SAF mandate costs |
| Legacy autos | - | M | F, GM | EV-transition costs |

### Tighter Financial Regulation

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Large banks | - | H | JPM, BAC, C | Higher capital requirements squeeze profits |
| Regional banks | -- | H | - | Heavier compliance burden |
| Fintech | +/- | M | SQ, PYPL | Benefits or hurts depending on rules |
| Crypto-related | - | M | COIN | Regulatory uncertainty |

### Tighter Antitrust

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Big tech | - | M | GOOGL, META, AMZN, AAPL | Risk of forced breakups |
| Telecom | - | M | T, VZ | Risk that M&A is blocked |
| Small/mid tech | + | M | - | Better competitive landscape |

---

## 4. Matrix by Technology Shift

### AI Revolution Acceleration

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Semis (GPU) | ++ | H | NVDA, AMD | AI training / inference chip demand |
| Semis (memory) | ++ | H | MU, WDC | HBM demand |
| Cloud infra | ++ | H | MSFT, AMZN, GOOGL | AI platform providers |
| Enterprise SW | + | H | CRM, NOW, ADBE | AI feature integration |
| Data-center REITs | ++ | H | EQIX, DLR | Surging demand |
| Utilities | + | M | NEE, SO | Power demand from data centers |
| BPO / outsourcing | -- | M | - | Replaced by AI automation |

### EV Adoption Acceleration

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| EV manufacturers | ++ | H | TSLA, RIVN | Market expansion |
| Batteries / lithium | ++ | H | ALB, LTHM, LAC | Materials demand |
| Charging infra | ++ | H | CHPT, BLNK | Infrastructure investment |
| Utilities | + | M | NEE, SO | Higher electricity demand |
| Legacy autos | - | M | F, GM | Transition costs |
| Auto parts (engines) | -- | H | - | Demand structural shift |
| Oil refining | - | M | VLO, PSX | Lower gasoline demand |

---

## 5. Matrix by Commodity Shock

### Crude-Oil Surge ($100+/bbl)

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Oil majors | ++ | H | XOM, CVX, COP | Earnings surge |
| Shale companies | ++ | H | PXD, EOG, DVN | Sharp profitability gains |
| Oilfield services | ++ | H | SLB, HAL, BKR | More drilling activity |
| Airlines | -- | H | DAL, UAL, AAL | Sharply higher fuel costs |
| Transportation | -- | H | UPS, FDX | Higher fuel costs |
| Chemicals | - | H | DOW, LYB | Higher feedstock costs |
| Consumer goods | - | M | broad | Lower consumer purchasing power |

### Crude-Oil Plunge ($50-/bbl)

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Oil majors | -- | H | XOM, CVX, COP | Lower earnings; capex cuts |
| Shale companies | -- | H | PXD, EOG, DVN | Risk of margin breakeven |
| Airlines | ++ | H | DAL, UAL, AAL | Lower fuel costs |
| Consumer goods | + | M | broad | Higher disposable income |
| Chemicals | + | M | DOW, LYB | Lower feedstock costs |

### Gold-Price Surge

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Gold miners | ++ | H | NEM, GOLD, AEM | Leverage to gold prices |
| Silver miners | ++ | H | PAAS, AG, HL | Linked to precious metals |
| Jewelry | 0 | M | SIG, TIF | Lower demand offset by inventory revaluation |

---

## 6. Matrix by Economic Cycle

### Expansion Phase

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Technology | ++ | H | AAPL, MSFT, NVDA | Higher corporate IT spending |
| Consumer Discretionary | ++ | H | AMZN, HD, NKE | Expanding consumption |
| Industrials | ++ | H | CAT, DE, HON | Higher capex |
| Materials | + | H | LIN, APD, FCX | Higher demand |
| Financials | + | H | JPM, BAC, GS | Credit growth, active M&A |

### Recession Phase

| Sector | Impact | Confidence | Representative tickers | Notes |
|--------|--------|------------|------------------------|-------|
| Consumer Staples | + | H | PG, KO, WMT | Defensive |
| Healthcare | + | H | UNH, JNJ, PFE | Non-discretionary spending |
| Utilities | + | H | NEE, DUK, SO | Stable dividends |
| Consumer Discretionary | -- | H | AMZN, HD, NKE | Discretionary spending cuts |
| Industrials | -- | H | CAT, DE, HON | Capex frozen |
| Financials | - | H | JPM, BAC | Higher loan-loss concerns |

---

## How to Use

1. **Identify the event type**: Determine the event category from the headline
2. **Look up the relevant matrix**: Pick the appropriate matrix above
3. **Check impact and confidence**: Review the sector-level impact
4. **Use representative tickers as a starting point**: Use as the entry point for deeper analysis
5. **Combine matrices for compound scenarios**: Reference multiple matrices when several events overlap

## Caveats

- **Single-stock context**: Sector-level impact may differ from individual-stock impact
- **Timing**: Distinguish between immediate and delayed effects
- **Magnitude**: Impact varies with the size of the event
- **Pricing-in**: Reactions are muted when the event is already discounted
