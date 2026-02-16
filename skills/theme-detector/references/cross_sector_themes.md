# Cross-Sector Theme Definitions

This reference defines market themes by their constituent FINVIZ industries, sectors, proxy ETFs, and representative stocks. The theme_classifier.py script reads these definitions to map industry-level data into theme-level aggregations.

**Usage Notes:**
- Industry names must exactly match FINVIZ industry names (see `finviz_industry_codes.md`)
- `min_matching_industries`: Minimum number of constituent industries that must show activity for the theme to be detected
- `static_stocks`: Fallback representative stocks used when industry-level data is insufficient
- `proxy_etfs`: Used for quick volume/momentum checks and as user-facing exposure recommendations

---

## AI & Semiconductors

- **Direction bias**: Bullish (typically)
- **Industries**: Semiconductors, Software - Application, Software - Infrastructure, Information Technology Services, Electronic Components, Computer Hardware, Scientific & Technical Instruments
- **Sectors**: Technology (primary), Communication Services, Industrials
- **Proxy ETFs**: SMH, SOXX, AIQ, BOTZ, CHAT
- **Static stocks**: NVDA, AVGO, AMD, INTC, QCOM, MRVL, AMAT, LRCX, KLAC, TSM, MU, ARM, SNPS, CDNS, MCHP
- **Min matching industries**: 2

---

## Clean Energy & EV

- **Direction bias**: Bullish (typically)
- **Industries**: Solar, Utilities - Renewable, Auto Manufacturers, Auto Parts, Electrical Equipment & Parts, Specialty Chemicals
- **Sectors**: Utilities, Consumer Cyclical, Industrials, Basic Materials
- **Proxy ETFs**: ICLN, QCLN, TAN, DRIV, LIT
- **Static stocks**: ENPH, SEDG, FSLR, RUN, TSLA, RIVN, LCID, NIO, PLUG, BE, CHPT, ALB, SQM, LAC, LTHM
- **Min matching industries**: 2

---

## Cybersecurity

- **Direction bias**: Bullish (typically)
- **Industries**: Software - Infrastructure, Information Technology Services, Software - Application, Communication Equipment
- **Sectors**: Technology (primary)
- **Proxy ETFs**: CIBR, HACK, BUG
- **Static stocks**: CRWD, PANW, FTNT, ZS, NET, S, OKTA, CYBR, QLYS, RPD, TENB, VRNS, SAIL, MNDT, DDOG
- **Min matching industries**: 2

**Note:** Cybersecurity overlaps with broader software industries. Theme classification uses proxy ETF volume and static stock performance to differentiate from general software themes.

---

## Cloud Computing & SaaS

- **Direction bias**: Bullish (typically)
- **Industries**: Software - Application, Software - Infrastructure, Information Technology Services
- **Sectors**: Technology (primary), Communication Services
- **Proxy ETFs**: SKYY, WCLD, CLOU
- **Static stocks**: CRM, NOW, SNOW, DDOG, TEAM, MDB, ESTC, NET, ZS, HUBS, BILL, TTD, PLTR, DOCN, DT
- **Min matching industries**: 2

**Note:** Cloud/SaaS overlaps significantly with Cybersecurity and AI themes. When multiple themes share the same industries, proxy ETF performance differentiates them.

---

## Biotech & Genomics

- **Direction bias**: Bullish (typically, but highly volatile)
- **Industries**: Biotechnology, Drug Manufacturers - Specialty & Generic, Medical Devices, Diagnostics & Research, Drug Manufacturers - General
- **Sectors**: Healthcare (primary)
- **Proxy ETFs**: XBI, IBB, ARKG, GNOM
- **Static stocks**: AMGN, GILD, VRTX, REGN, MRNA, BIIB, ILMN, CRSP, NTLA, BEAM, EDIT, EXAS, TWST, SGEN, BMRN
- **Min matching industries**: 2

---

## Infrastructure & Construction

- **Direction bias**: Bullish (typically, policy-driven)
- **Industries**: Engineering & Construction, Building Materials, Industrial Distribution, Farm & Heavy Construction Machinery, Steel, Specialty Industrial Machinery, Railroads, Waste Management
- **Sectors**: Industrials (primary), Basic Materials
- **Proxy ETFs**: PAVE, IFRA, SIMS
- **Static stocks**: CAT, DE, VMC, MLM, URI, PWR, EME, MTZ, GVA, AECOM, STRL, GBX, NUE, CLF, RS
- **Min matching industries**: 3

---

## Gold & Precious Metals

- **Direction bias**: Bullish (typically in risk-off or inflation)
- **Industries**: Gold, Silver, Other Precious Metals & Mining
- **Sectors**: Basic Materials (primary)
- **Proxy ETFs**: GDX, GDXJ, RING, SIL
- **Static stocks**: NEM, GOLD, AEM, FNV, WPM, RGLD, KGC, AGI, AU, HMY, PAAS, CDE, HL, MAG, EQX
- **Min matching industries**: 2

---

## Oil & Gas (Energy Sector)

- **Direction bias**: Varies (cyclical)
- **Industries**: Oil & Gas E&P, Oil & Gas Equipment & Services, Oil & Gas Midstream, Oil & Gas Refining & Marketing, Oil & Gas Integrated, Oil & Gas Drilling
- **Sectors**: Energy (primary)
- **Proxy ETFs**: XLE, XOP, OIH
- **Static stocks**: XOM, CVX, COP, EOG, SLB, HAL, PXD, DVN, MPC, VLO, PSX, OXY, FANG, HES, WMB
- **Min matching industries**: 2

---

## Financial Services & Banks

- **Direction bias**: Varies (rate-sensitive)
- **Industries**: Banks - Diversified, Banks - Regional, Capital Markets, Insurance - Diversified, Insurance - Property & Casualty, Financial Data & Stock Exchanges, Credit Services, Asset Management, Insurance Brokers, Mortgage Finance
- **Sectors**: Financial Services (primary)
- **Proxy ETFs**: XLF, KBE, KRE, IAI
- **Static stocks**: JPM, BAC, WFC, GS, MS, C, SCHW, BLK, AXP, ICE, CME, MCO, SPGI, BX, KKR
- **Min matching industries**: 3

---

## Healthcare & Pharma

- **Direction bias**: Varies (defensive in downturns)
- **Industries**: Drug Manufacturers - General, Health Care Plans, Medical Care Facilities, Health Information Services, Medical Distribution, Medical Instruments & Supplies, Pharmaceutical Retailers
- **Sectors**: Healthcare (primary)
- **Proxy ETFs**: XLV, IHE, IHI
- **Static stocks**: UNH, JNJ, LLY, PFE, ABT, TMO, DHR, MDT, ISRG, SYK, BSX, EW, HCA, CVS, CI
- **Min matching industries**: 3

**Note:** Healthcare & Pharma is distinct from Biotech & Genomics. Healthcare focuses on established pharma, insurance, and medical devices; Biotech focuses on emerging drug development and genomics.

---

## Defense & Aerospace

- **Direction bias**: Bullish (typically in geopolitical tension)
- **Industries**: Aerospace & Defense, Airlines, Security & Protection Services
- **Sectors**: Industrials (primary)
- **Proxy ETFs**: ITA, PPA, ROKT, ARKX
- **Static stocks**: LMT, RTX, NOC, BA, GD, LHX, HII, TDG, HWM, AXON, LDOS, BWXT, KTOS, RKLB, SPR
- **Min matching industries**: 2

---

## Real Estate & REITs

- **Direction bias**: Varies (rate-sensitive)
- **Industries**: REIT - Residential, REIT - Industrial, REIT - Retail, REIT - Office, REIT - Healthcare Facilities, REIT - Diversified, REIT - Hotel & Motel, REIT - Specialty, Real Estate Services, Real Estate - Diversified, Real Estate - Development
- **Sectors**: Real Estate (primary)
- **Proxy ETFs**: VNQ, XLRE, IYR
- **Static stocks**: PLD, AMT, CCI, EQIX, SPG, O, WELL, DLR, PSA, VICI, EXR, AVB, ARE, MAA, IRM
- **Min matching industries**: 3

---

## Retail & Consumer

- **Direction bias**: Varies (consumer sentiment driven)
- **Industries**: Internet Retail, Specialty Retail, Apparel Retail, Home Improvement Retail, Department Stores, Discount Stores, Luxury Goods, Restaurants, Leisure, Resorts & Casinos, Gambling, Apparel Manufacturing, Footwear & Accessories
- **Sectors**: Consumer Cyclical (primary), Consumer Defensive
- **Proxy ETFs**: XLY, XRT, XLP, IBUY
- **Static stocks**: AMZN, HD, LOW, TJX, COST, WMT, TGT, NKE, SBUX, MCD, DPZ, LULU, ROST, BURL, DECK
- **Min matching industries**: 3

---

## Crypto & Blockchain

- **Direction bias**: Bullish (typically in risk-on)
- **Industries**: Capital Markets, Software - Application, Financial Data & Stock Exchanges, Information Technology Services
- **Sectors**: Financial Services, Technology
- **Proxy ETFs**: BITO, BLOK, BITQ, IBIT, DAPP
- **Static stocks**: COIN, MSTR, MARA, RIOT, CLSK, HUT, BITF, SQ, PYPL, HOOD, CIFR, IREN, HIVE, CORZ, BTBT
- **Min matching industries**: 2

**Note:** Crypto theme uses proxy ETFs and static stocks as primary signals rather than industry classification, since blockchain companies span multiple traditional industries.

---

## Nuclear Energy

- **Direction bias**: Bullish (policy-driven, AI data center demand)
- **Industries**: Uranium, Utilities - Independent Power Producers, Specialty Industrial Machinery, Electrical Equipment & Parts
- **Sectors**: Energy, Utilities, Industrials
- **Proxy ETFs**: URA, URNM, NLR, NUKZ
- **Static stocks**: CCJ, UEC, NXE, DNN, UUUU, LEU, SMR, OKLO, BWX, GEV, CEG, VST, TLN, NRG, BWXT
- **Min matching industries**: 2

---

## Uranium

- **Direction bias**: Bullish (supply deficit narrative)
- **Industries**: Uranium, Other Industrial Metals & Mining
- **Sectors**: Energy (primary), Basic Materials
- **Proxy ETFs**: URA, URNM, URNJ
- **Static stocks**: CCJ, UEC, NXE, DNN, UUUU, LEU, URG, GLATF, EU, PALAF, SRUUF, LTBR, FCUUF, AEC, WSTRF
- **Min matching industries**: 1

**Note:** Uranium is a sub-theme of Nuclear Energy but tracked separately due to its distinct commodity-driven dynamics. Requires only 1 matching industry due to narrow sector focus.

---

## Obesity & GLP-1

- **Direction bias**: Bullish (medical innovation)
- **Industries**: Drug Manufacturers - General, Drug Manufacturers - Specialty & Generic, Medical Devices, Biotechnology
- **Sectors**: Healthcare (primary)
- **Proxy ETFs**: SLIM, HRTS
- **Static stocks**: LLY, NVO, AMGN, VKTX, ALT, GPCR, SMLR, RVMD, PTGX, IVA
- **Min matching industries**: 2

**Note:** Obesity/GLP-1 is a narrow theme that overlaps with Healthcare & Pharma. It is differentiated primarily through proxy ETF volume and static stock performance rather than industry classification.

---

## Summary Table

| Theme | Industries | Sectors | Proxy ETFs | Static Stocks | Min Industries |
|-------|-----------|---------|-----------|--------------|----------------|
| AI & Semiconductors | 7 | 3 | 5 | 15 | 2 |
| Clean Energy & EV | 6 | 4 | 5 | 15 | 2 |
| Cybersecurity | 4 | 1 | 3 | 15 | 2 |
| Cloud Computing & SaaS | 3 | 2 | 3 | 15 | 2 |
| Biotech & Genomics | 5 | 1 | 4 | 15 | 2 |
| Infrastructure & Construction | 8 | 2 | 3 | 15 | 3 |
| Gold & Precious Metals | 3 | 1 | 4 | 15 | 2 |
| Oil & Gas (Energy) | 6 | 1 | 3 | 15 | 2 |
| Financial Services & Banks | 10 | 1 | 4 | 15 | 3 |
| Healthcare & Pharma | 7 | 1 | 3 | 15 | 3 |
| Defense & Aerospace | 3 | 1 | 4 | 15 | 2 |
| Real Estate & REITs | 11 | 1 | 3 | 15 | 3 |
| Retail & Consumer | 13 | 2 | 4 | 15 | 3 |
| Crypto & Blockchain | 4 | 2 | 5 | 15 | 2 |
| Nuclear Energy | 4 | 3 | 4 | 15 | 2 |
| Uranium | 2 | 2 | 3 | 15 | 1 |
| Obesity & GLP-1 | 4 | 1 | 2 | 10 | 2 |

**Total: 17 themes** covering all major market narratives.

---

## Theme Overlap Matrix

Some industries contribute to multiple themes. When scoring, each industry's data is used in all applicable themes:

| Industry | Themes |
|----------|--------|
| Software - Application | AI, Cybersecurity, Cloud, Crypto |
| Software - Infrastructure | AI, Cybersecurity, Cloud |
| Drug Manufacturers - General | Healthcare, Biotech, Obesity |
| Biotechnology | Biotech, Obesity |
| Capital Markets | Financial Services, Crypto |
| Electrical Equipment & Parts | Clean Energy, Nuclear |
| Uranium | Nuclear, Uranium |

This overlap is intentional - a strong software industry may boost multiple themes simultaneously, reflecting the interconnected nature of market narratives.
