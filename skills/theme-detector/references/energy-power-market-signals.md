# Energy Power Market Signals — Equity Implications

This reference translates institutional power-market mechanics (ISO/RTO markets, spark
spreads, capacity auctions, scarcity pricing) into actionable equity signals for swing
traders. Concepts sourced from primary market participants at institutional commodity desks.

---

## How Power Is Priced (LMP Basics)

The US wholesale electricity market is run by ISOs/RTOs (CAISO, PJM, ERCOT, MISO,
ISO-NE, NYISO, SPP). They collect supply offers and demand forecasts, then run a
real-time optimization every 5 minutes to find the economically efficient dispatch.

**Key pricing rule:** The price everyone pays is the cost of the *last* (most expensive)
megawatt dispatched — not the average. If 999 MW come from renewables at $0 and the
1000th MW costs $5,000, everyone pays $5,000/MWh.

**Dispatch order (merit order):** Cheapest generation dispatches first.
- Renewables (solar, wind) → $0 marginal cost, dispatch first
- Nuclear → low variable cost, baseload
- Natural gas (combined cycle) → moderate cost, dispatchable
- Natural gas (simple cycle) → higher cost, fast-response peakers
- Coal → carbon costs increasingly disadvantageous
- Oil / dual fuel → most expensive, last resort

**Equity implication:** When renewables flood the grid (peak solar hours), wholesale
prices collapse. When renewables are absent (cloud cover, calm wind, evening), gas
plants become price-setters. The spread between these extremes is the profit opportunity
for storage operators and peaker plant owners.

---

## Spark Spread — The Primary Signal for Gas Generator Margins

**Definition:** Spark spread = Power price − (Gas price × Heat rate)

The heat rate is a generator's efficiency: how many MMBtu of gas needed to produce
1 MWh. A modern combined cycle unit might have a heat rate of ~7 (efficient). An
older simple cycle peaker might be 10-12 (inefficient).

**Spread types:**
- **7 spark spread** — represents an average-efficiency CCGT; benchmark for combined cycle economics
- **10 spark spread** — represents an inefficient peaker; tells you if peakers are economic
- **Dark spread** — same concept but for coal plants (power price minus coal cost × heat rate)
- **Green spread** — economics for renewables; typically tracks RECs and capacity payments

**Reading the spread:**
| Spark Spread | Signal |
|---|---|
| Widening (power↑ or gas↓) | Improving margins → bullish IPPs |
| Compressing (power↓ or gas↑) | Squeezing margins → bearish IPPs |
| Negative (sustained) | Generators shut down or reduce dispatch; sets up future scarcity |
| Very wide (>$30–40) | Peakers running, grid stressed; watch for scarcity pricing events |

**Equity targets:** VST, NRG, TLN (merchant generators most exposed), CEG (nuclear-heavy,
less gas-price sensitive but benefits from high power prices), GEV (GE Vernova —
turbine manufacturer, benefits from capacity buildout).

**Data sources:** EIA natural gas prices (Henry Hub), regional power prices from CAISO/PJM/ERCOT
market reports, CME spark spread futures (publicly quoted).

---

## Capacity Markets — The Revenue Floor for IPPs

**What they are:** In regulated ISOs (PJM, CAISO, ISO-NE, NYISO), generators receive
periodic payments just to *remain available*, regardless of whether they dispatch.
These capacity payments are auctioned 3 years forward and represent a reliable
revenue stream separate from energy prices.

**How auctions work:**
1. ISO estimates future peak demand plus a reliability reserve margin
2. Generators bid their cost to remain available
3. ISO clears the auction — everyone below the clearing price gets paid the clearing price
4. Auction results are published (PJM publishes BRA results, ISO-NE FCAM, etc.)

**Equity implication — the catalyst pattern:**
- PJM's Base Residual Auction typically runs April-May for the period 3 years out
- When clearing prices come in above consensus → immediate earnings upgrade cycle for PJM-exposed generators
- When prices are weak (as in 2022-2023 when renewables flooded supply) → sell signal
- 2024-2025 PJM auctions cleared at multi-year highs due to AI/data center load growth → strong tailwind for VST, NRG, TLN

**Key difference — ERCOT (Texas):**
Texas has *no capacity market*. Generators are compensated only through energy prices
plus a scarcity pricing mechanism (see below). This is why Texas IPPs have higher
volatility and bigger weather-driven spikes.

---

## Scarcity Pricing — The ERCOT Upside Optionality Event

**Definition:** When supply cannot meet demand, ERCOT allows prices to spike to the
"Value of Lost Load" (currently ~$5,000/MWh) or higher. This is the payoff event
for Texas generators — the equivalent of one critical week in a hot summer can
generate more earnings than the rest of the year combined.

**Trigger conditions:**
- Extreme heat (AC load surge) with low wind (ERCOT is heavily wind-dependent)
- Extreme cold (freeze events; Winter Storm Uri Feb 2021 was the archetype)
- Multiple large generator outages simultaneously

**Trading pattern:**
1. Week 10-14 NOAA temperature forecasts show anomalously hot Texas summer → watch VST, TLN
2. Weather forecasts revise hotter → stocks spike 10-30% in days
3. Event arrives → realize gains or hold through if grid stress confirmed
4. Event miss/moderate temperatures → sharp reversal

**Risk:** ERCOT is implementing market reforms after Uri. Regulatory cap changes
can compress the upside of scarcity events. Track PUCT (Public Utility Commission
of Texas) proceedings.

---

## Duck Curve — The Battery Storage Investment Thesis

**Definition:** The "duck curve" is the intraday power demand shape that emerges as
solar penetration grows. Named for its visual profile on a net demand chart:
- Early morning: moderate demand
- Midday: demand collapses as solar floods the grid (the belly of the duck)
- 5–8pm: solar disappears, demand spikes for cooking/lighting/AC (the neck)

The steeper the neck, the more valuable fast-ramping generation and storage become.

**Investment thesis:**
The duck curve creates a structural arbitrage: buy cheap midday power, sell expensive
evening power. Batteries are the primary vehicle.

**Battery economics (institutional benchmark):**
- 4-hour battery (400 MWh) ≈ $80M capex
- Profit = spread between peak and off-peak prices × utilization × cycle life
- California, Texas, and mid-Atlantic markets have enough spread to justify investment
- Renewable energy credits (RECs) provide additional revenue certainty for project finance

**Equity targets:** FLNC (Fluence Energy — utility-scale storage), BE (Bloom Energy),
STEM, CEG (increasingly co-locating storage with nuclear), VST (battery+gas portfolio),
utilities with large storage procurement mandates (AEP, DTE, ED).

**Behind-the-meter solar complication:**
Rooftop solar does not appear in ISO demand data — it "hides" demand from the grid.
This means true demand growth is chronically understated by official statistics.
When estimating utility load growth, add back estimated behind-the-meter solar growth.

---

## AI / Data Center Power Demand — Structural Theme Mechanics

**The demand driver:**
- A large hyperscale data center draws 100–500 MW continuously (vs. a small city's peak)
- Training clusters for frontier AI models require gigawatts
- Microsoft, Google, Amazon, Meta all signed multi-gigawatt PPAs in 2024-2025
- US power demand growth has been flat for 20 years but is now inflecting up

**Why supply cannot keep up quickly:**
1. **Interconnection queues:** Grid operators process new generator connections one at a
   time. Queues in PJM and MISO stretch 4-7 years. You cannot simply "build more power."
2. **Transmission constraints:** Adding a new data center in a constrained zone forces
   expensive transmission upgrades that the entire rate base must fund.
3. **Equipment scarcity:** Large transformers have 18-24 month lead times; gas turbines
   from GE Vernova / Siemens have 2-3 year backlogs as of 2025.
4. **Regulatory delays:** Air permits, water rights, zoning, environmental review — all
   serialize project timelines.

**Supply chain map for the equity trade:**

| Layer | What They Do | Key Equity Names |
|---|---|---|
| Generation (gas/nuclear) | Produce power for data centers | VST, CEG, TLN, NRG |
| Transmission & grid | Move power, upgrade infrastructure | PWR, MYRG, FIX, LFUS |
| Gas turbine OEM | Build new peaker/CCGT capacity | GEV (GE Vernova), SIEGY |
| Energy storage | Balance intermittent supply | FLNC, STEM, BE |
| Natural gas supply | Fuel for new gas generation buildout | EQT, AR, RRC, SWN |
| Nuclear SMR / advanced | Long-dated next-gen baseload | SMR, OKLO, NuScale equiv. |
| Data center REIT | Own the facilities, long-term PPAs | EQIX, DLR, CONE, SWTX |

**Catalyst calendar for this theme:**
- PJM capacity auction results (April-May, annually)
- FERC interconnection reform proceedings
- Hyperscaler earnings (capex guidance for AI infra)
- EIA monthly electric power data (demand growth confirmation)
- NOAA summer outlook (early May; drives near-term pricing)

---

## Regional Price Congestion — Basis Signals

Power prices are *locational* — a single storm that takes down a transmission line
can create $500/MWh spreads between neighboring zones while the national price is flat.

**Key regional dynamics to track:**

**New York City (Zone J):**
Consistently one of the most expensive US power markets. Upstate nuclear and hydro
(Niagara Falls) cannot reach NYC fully because the transmission lines hit capacity.
NYC is forced to run expensive dual-fuel gas turbines that switch from gas to oil
in winter when heating competes for gas supply. Oil-fired generation is highly
inefficient and expensive — this is why Con Edison (ED) bills spike in January.
*Signal:* Henry Hub gas + oil prices → NYISO Zone J spread → ED earnings pressure.

**California (NP15 / SP15):**
Heavy solar penetration creates extreme duck curve dynamics. Natural gas prices
at SoCal Gas / PG&E Citygate hubs have high seasonality. After-hours demand
spikes are now the primary profit window for CCGTs.
*Signal:* CAISO curtailment data (negative prices) → measure of storage opportunity.

**Texas (ERCOT West):**
West Texas negative prices are structurally common due to wind oversupply and
limited transmission connecting wind generation to load centers in Dallas/Houston.
Data centers sometimes locate here specifically to benefit from negative prices.
*Signal:* ERCOT real-time prices going deeply negative → watch for data center
operators / miners disclosing location advantages.

---

## Negative Power Prices — When Real, When a Trap

Negative prices occur in three situations:

1. **Oversupply with constrained storage/transmission (West Texas, CAISO midday)**
   — This is *real* free money if you are the consumer. Data centers, Bitcoin miners,
   and aluminum smelters position in these regions deliberately.

2. **Renewable subsidy incentive**
   — Wind turbines receive federal Production Tax Credits (PTCs) per MWh generated.
   They will pay to continue generating rather than shut down because the subsidy
   exceeds the negative price. This is not a signal of fundamental value; it is
   a policy artifact.

3. **Shutdown cost trap**
   — Some generators (nuclear, large CCGTs) have high restart costs. They accept
   negative prices for short periods rather than pay to shut down. This is temporary
   and will revert.

**Equity application:** Negative power prices in ERCOT West or CAISO midday are
a bullish signal for battery storage operators — they widen the peak/off-peak
arbitrage spread, improving battery project economics.

---

## Sources and Data Access

- **EIA 860** — every US generator >1 MW: nameplate capacity, fuel, location, heat rate
- **EIA 923** — monthly generation and fuel consumption by generator
- **CAISO OASIS** — real-time and historical California power prices/demand
- **PJM Data Miner** — PJM market data including capacity auction results
- **ERCOT Market Information System** — Texas real-time prices, wind/solar output
- **CME Group** — spark spread futures, Henry Hub futures, power futures
- **FERC eLibrary** — interconnection queue data, transmission filings
