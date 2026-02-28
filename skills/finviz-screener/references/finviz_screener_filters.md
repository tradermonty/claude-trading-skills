# FinViz Screener Filter Reference


This reference maps FinViz screener filter codes to their meanings and natural-language keywords (English + Japanese). Claude uses this document to translate user intent into valid FinViz filter codes.


---


## URL Format


**Public (free):**

```

https://finviz.com/screener.ashx?v={view}&f={filters}&o={order}&s={signal}

```


**Elite (paid subscription):**

```

https://elite.finviz.com/screener.ashx?v={view}&f={filters}&o={order}&s={signal}

```


**Parameters:**

- `v` — View type code (see View Types below)

- `f` — Comma-separated filter codes (e.g., `cap_small,fa_div_o3,fa_pe_u20`)

- `o` — Sort order (optional; prefix `-` for descending, e.g., `-marketcap`)

**Range Filter Pattern `{from}to{to}`:**

Many filters support a range syntax: `{prefix}_{from}to{to}`. This creates a single filter that means "between {from} and {to}".

- Example: `fa_div_3to8` = Dividend Yield 3% to 8%
- Example: `fa_pe_10to20` = P/E 10 to 20
- Example: `ta_beta_0.5to1.5` = Beta 0.5 to 1.5

This range syntax is supported on the FinViz website but is **not registered in the finviz Python library**. Use range codes directly in the URL `f=` parameter. Range filters are more precise than combining two separate `_o` / `_u` filters, and they work as a single filter token.

- `t` — Ticker symbols (optional; comma-separated, e.g., `AAPL,MSFT`)

- `s` — Signal filter (optional; see Signal Filters below)


---


## Signal Filters (`s=` parameter)


Signals are passed via the `s=` URL parameter (not in the `f=` filter string).

Common signals:


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_topgainers` | Top Gainers | gainers, 値上がり上位 |
| `ta_toplosers` | Top Losers | losers, 値下がり上位 |
| `ta_newhigh` | New High | new high, 新高値 |
| `ta_newlow` | New Low | new low, 新安値 |
| `ta_mostvolatile` | Most Volatile | volatile, 高ボラ |
| `ta_mostactive` | Most Active | active, 活発 |
| `ta_unusualvolume` | Unusual Volume | unusual volume, 異常出来高 |
| `ta_overbought` | Overbought | overbought, 買われすぎ |
| `ta_oversold` | Oversold | oversold, 売られすぎ |
| `ta_downgrades` | Downgrades | downgrade, 格下げ |
| `ta_upgrades` | Upgrades | upgrade, 格上げ |
| `ta_earnbefore` | Earnings Before | earnings before market |
| `ta_earnafter` | Earnings After | earnings after market |
| `n_majornews` | Major News | major news, 重大ニュース |
| `ta_p_wedgeup` | Wedge Up |  |
| `ta_p_wedgedown` | Wedge Down |  |
| `ta_p_tri_ascending` | Triangle Ascending |  |
| `ta_p_tri_descending` | Triangle Descending |  |
| `ta_p_channelup` | Channel Up |  |
| `ta_p_channeldown` | Channel Down |  |
| `ta_p_channel` | Channel |  |
| `ta_p_doubletop` | Double Top |  |
| `ta_p_doublebottom` | Double Bottom |  |
| `ta_p_headandshoulders` | Head and Shoulders |  |
| `ta_p_headandshouldersinv` | Head and Shoulders Inverse |  |

---


## View Types


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `111` | Overview — ticker, company, sector, industry, country, market cap, P/E, price, change, volume | overview, 概要, 一覧 |
| `121` | Valuation — market cap, P/E, Forward P/E, PEG, P/S, P/B, P/Cash, P/FCF, EPS, dividend yield | valuation, バリュエーション, 割安度 |
| `131` | Ownership — market cap, outstanding shares, float, insider/institutional ownership, short float | ownership, 所有, 株主構成 |
| `141` | Performance — performance periods (day to 10Y), volatility, RSI, SMA | performance, パフォーマンス, 騰落率 |
| `152` | Custom — user-defined columns | custom, カスタム |
| `161` | Financial — market cap, dividend yield, ROA, ROE, ROI, ratios, margins | financial, 財務, ファイナンシャル |
| `171` | Technical — RSI, SMA20/50/200, 52W High/Low, pattern, candlestick, beta, ATR | technical, テクニカル, チャート指標 |

---


## Sort Order Codes


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ticker` | Ticker A→Z | ticker, ティッカー |
| `-ticker` | Ticker Z→A |  |
| `company` | Company name A→Z | company, 会社名 |
| `sector` | Sector | sector, セクター |
| `industry` | Industry | industry, 業種 |
| `country` | Country | country, 国 |
| `marketcap` | Market Cap (ascending) | market cap, 時価総額, 小さい順 |
| `-marketcap` | Market Cap (descending) | 時価総額大きい順 |
| `pe` | P/E (ascending) | PE, PER |
| `-pe` | P/E (descending) |  |
| `forwardpe` | Forward P/E (ascending) | forward PE |
| `eps` | EPS (ascending) | EPS |
| `dividendyield` | Dividend Yield (ascending) | dividend, 配当, 利回り |
| `-dividendyield` | Dividend Yield (descending) | 高配当順 |
| `price` | Price (ascending) | price, 株価 |
| `-price` | Price (descending) |  |
| `change` | Change (ascending) | change, 変動率 |
| `-change` | Change (descending) |  |
| `volume` | Volume (ascending) | volume, 出来高 |
| `-volume` | Volume (descending) | 出来高大きい順 |
| `recom` | Analyst Recommendation | recommendation, アナリスト推奨 |
| `earningsdate` | Earnings Date | earnings date, 決算日 |
| `targetprice` | Target Price | target price, 目標株価 |
| `shortfloat` | Short Float | short float |
| `averagevolume` | Average Volume | average volume |
| `relativevolume` | Relative Volume | relative volume |

---


## Descriptive Filters


### Exchange (`exch_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `exch_amex` | AMEX | AMEX |
| `exch_cboe` | CBOE | CBOE |
| `exch_nasd` | NASDAQ | NASDAQ, ナスダック |
| `exch_nyse` | NYSE | NYSE, ニューヨーク証券取引所 |

### Index (`idx_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `idx_sp500` | S&P 500 | S&P 500, S&P500 |
| `idx_dji` | Dow Jones | Dow, ダウ, ダウ工業 |
| `idx_ndx` | NASDAQ 100 | NASDAQ 100, ナスダック100 |
| `idx_rut` | Russell 2000 | Russell 2000, ラッセル2000, 小型株指数 |

### Sector (`sec_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sec_basicmaterials` | Basic Materials | basic materials, 素材, 原材料 |
| `sec_communicationservices` | Communication Services | communication, 通信, メディア |
| `sec_consumercyclical` | Consumer Cyclical | consumer cyclical, 一般消費財, 景気敏感消費 |
| `sec_consumerdefensive` | Consumer Defensive | consumer defensive, 生活必需品, ディフェンシブ消費 |
| `sec_energy` | Energy | energy, エネルギー, 石油 |
| `sec_financial` | Financial | financial, 金融, 銀行 |
| `sec_healthcare` | Healthcare | healthcare, ヘルスケア, 医療 |
| `sec_industrials` | Industrials | industrials, 資本財, 産業 |
| `sec_realestate` | Real Estate | real estate, 不動産, REIT |
| `sec_technology` | Technology | technology, テクノロジー, ハイテク, IT |
| `sec_utilities` | Utilities | utilities, 公益, 電力, ガス |

### Market Cap (`cap_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `cap_mega` | Mega ($200B+) | mega cap, メガキャップ, 超大型 |
| `cap_large` | Large ($10B–$200B) | large cap, ラージキャップ, 大型 |
| `cap_mid` | Mid ($2B–$10B) | mid cap, ミッドキャップ, 中型 |
| `cap_small` | Small ($300M–$2B) | small cap, スモールキャップ, 小型 |
| `cap_micro` | Micro ($50M–$300M) | micro cap, マイクロキャップ, 超小型 |
| `cap_nano` | Nano (under $50M) | nano cap, ナノキャップ |
| `cap_largeover` | +Large ($10B+) | large+, 大型以上 |
| `cap_midover` | +Mid ($2B+) | mid+, 中型以上 |
| `cap_smallover` | +Small ($300M+) | small+, 小型以上 |
| `cap_microover` | +Micro ($50M+) | micro+, 超小型以上 |
| `cap_largeunder` | -Large (under $200B) | large以下 |
| `cap_midunder` | -Mid (under $10B) | mid以下 |
| `cap_smallunder` | -Small (under $2B) | small以下 |
| `cap_microunder` | -Micro (under $300M) | micro以下 |

### Country (`geo_`)


Common countries:


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `geo_usa` | USA | USA, アメリカ, 米国 |
| `geo_notusa` | Foreign (ex-USA) | foreign, 外国, 海外, ADR |
| `geo_asia` | Asia | Asia, アジア |
| `geo_europe` | Europe | Europe, ヨーロッパ, 欧州 |
| `geo_latinamerica` | Latin America | Latin America, 中南米 |
| `geo_bric` | BRIC | BRIC |
| `geo_china` | China | China, 中国 |
| `geo_chinahongkong` | China & Hong Kong |  |
| `geo_japan` | Japan | Japan, 日本 |
| `geo_india` | India | India, インド |
| `geo_unitedkingdom` | United Kingdom | UK, イギリス |
| `geo_canada` | Canada | Canada, カナダ |
| `geo_germany` | Germany | Germany, ドイツ |
| `geo_france` | France | France, フランス |
| `geo_brazil` | Brazil | Brazil, ブラジル |
| `geo_southkorea` | South Korea | South Korea, 韓国 |
| `geo_taiwan` | Taiwan | Taiwan, 台湾 |
| `geo_israel` | Israel | Israel, イスラエル |
| `geo_australia` | Australia | Australia, オーストラリア |
| `geo_switzerland` | Switzerland | Switzerland, スイス |
| `geo_netherlands` | Netherlands | Netherlands, オランダ |
| `geo_ireland` | Ireland | Ireland, アイルランド |
| `geo_singapore` | Singapore | Singapore, シンガポール |

Additional countries: Argentina, Bahamas, Belgium, BeNeLux, Bermuda, Cayman Islands, Chile, Colombia, Cyprus, Denmark, Finland, Greece, Hong Kong, Hungary, Iceland, Indonesia, Italy, Jordan, Kazakhstan, Luxembourg, Malaysia, Malta, Mexico, Monaco, New Zealand, Norway, Panama, Peru, Philippines, Portugal, Russia, South Africa, Spain, Sweden, Thailand, Turkey, UAE, Uruguay, Vietnam


### IPO Date (`ipodate_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ipodate_today` | Today | IPO today, 今日IPO |
| `ipodate_yesterday` | Yesterday |  |
| `ipodate_prevweek` | In the last week | recent IPO, 最近のIPO |
| `ipodate_prevmonth` | In the last month |  |
| `ipodate_prevquarter` | In the last quarter |  |
| `ipodate_prevyear` | In the last year |  |
| `ipodate_prev2yrs` | In the last 2 years |  |
| `ipodate_prev3yrs` | In the last 3 years |  |
| `ipodate_prev5yrs` | In the last 5 years |  |
| `ipodate_more1` | More than a year ago |  |
| `ipodate_more5` | More than 5 years ago | established, 安定企業 |
| `ipodate_more10` | More than 10 years ago |  |
| `ipodate_more15` | More than 15 years ago |  |
| `ipodate_more20` | More than 20 years ago |  |
| `ipodate_more25` | More than 25 years ago |  |

### Earnings Date (`earningsdate_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `earningsdate_today` | Today | earnings today, 今日決算 |
| `earningsdate_todaybefore` | Today Before Market Open | 寄り前決算 |
| `earningsdate_todayafter` | Today After Market Close | 引け後決算 |
| `earningsdate_tomorrow` | Tomorrow | earnings tomorrow, 明日決算 |
| `earningsdate_tomorrowbefore` | Tomorrow Before Market Open |  |
| `earningsdate_tomorrowafter` | Tomorrow After Market Close |  |
| `earningsdate_yesterday` | Yesterday | 昨日決算 |
| `earningsdate_yesterdaybefore` | Yesterday Before Market Open |  |
| `earningsdate_yesterdayafter` | Yesterday After Market Close |  |
| `earningsdate_thisweek` | This Week | earnings this week, 今週決算 |
| `earningsdate_nextweek` | Next Week | earnings next week, 来週決算 |
| `earningsdate_prevweek` | Previous Week | 先週決算 |
| `earningsdate_nextdays5` | Next 5 Days | 今後5日以内決算 |
| `earningsdate_prevdays5` | Previous 5 Days | 過去5日決算 |
| `earningsdate_thismonth` | This Month | earnings this month, 今月決算 |

---


## Fundamental Filters (`fa_`)


### P/E Ratio (`fa_pe_`)


Pattern: `fa_pe_u{N}` (under N), `fa_pe_o{N}` (over N), `fa_pe_{from}to{to}` (range, e.g., `fa_pe_10to20`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_pe_low` | Low (<15) | low PE, 低PER |
| `fa_pe_profitable` | Profitable (>0) | profitable, 黒字 |
| `fa_pe_high` | High (>50) | high PE, 高PER |
| `fa_pe_u5` | Under 5 | PE<5 |
| `fa_pe_u10` | Under 10 | PE<10 |
| `fa_pe_u15` | Under 15 | PE<15 |
| `fa_pe_u20` | Under 20 | PE<20, 割安 |
| `fa_pe_u25` | Under 25 | PE<25 |
| `fa_pe_u30` | Under 30 | PE<30 |
| `fa_pe_u35` | Under 35 |  |
| `fa_pe_u40` | Under 40 | PE<40 |
| `fa_pe_u45` | Under 45 |  |
| `fa_pe_u50` | Under 50 | PE<50 |
| `fa_pe_o5` | Over 5 | PE>5 |
| `fa_pe_o10` | Over 10 | PE>10 |
| `fa_pe_o15` | Over 15 | PE>15 |
| `fa_pe_o20` | Over 20 | PE>20 |
| `fa_pe_o25` | Over 25 | PE>25 |
| `fa_pe_o30` | Over 30 | PE>30 |
| `fa_pe_o35` | Over 35 |  |
| `fa_pe_o40` | Over 40 | PE>40 |
| `fa_pe_o45` | Over 45 |  |
| `fa_pe_o50` | Over 50 | PE>50 |

### Forward P/E (`fa_fpe_`)


Pattern: `fa_fpe_u{N}` (under N), `fa_fpe_o{N}` (over N), `fa_fpe_{from}to{to}` (range, e.g., `fa_fpe_10to20`). Same thresholds as P/E (5–50).

Special: `fa_fpe_low` (Low <15), `fa_fpe_profitable` (>0), `fa_fpe_high` (>50)


### PEG Ratio (`fa_peg_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_peg_low` | Low (<1) | PEG<1, 成長割安 |
| `fa_peg_high` | High (>2) | PEG>2 |
| `fa_peg_u1` | Under 1 | PEG<1 |
| `fa_peg_u2` | Under 2 | PEG<2 |
| `fa_peg_u3` | Under 3 | PEG<3 |
| `fa_peg_o1` | Over 1 | PEG>1 |
| `fa_peg_o2` | Over 2 | PEG>2 |
| `fa_peg_o3` | Over 3 | PEG>3 |

### P/S Ratio (`fa_ps_`)


Pattern: `fa_ps_u{N}` (under N), `fa_ps_o{N}` (over N), `fa_ps_{from}to{to}` (range, e.g., `fa_ps_1to5`). Range: 1–10.

Special: `fa_ps_low` (Low <1), `fa_ps_high` (High >10)


### P/B Ratio (`fa_pb_`)


Pattern: `fa_pb_u{N}` (under N), `fa_pb_o{N}` (over N), `fa_pb_{from}to{to}` (range, e.g., `fa_pb_1to3`). Range: 1–10.

Special: `fa_pb_low` (Low <1, 簿価割れ), `fa_pb_high` (High >5)


### P/Cash (`fa_pc_`)


Pattern: `fa_pc_u{N}` (under N), `fa_pc_o{N}` (over N), `fa_pc_{from}to{to}` (range, e.g., `fa_pc_3to10`). Range: 1–50.

Special: `fa_pc_low` (Low <3), `fa_pc_high` (High >50)


### P/Free Cash Flow (`fa_pfcf_`)


Pattern: `fa_pfcf_u{N}` (under N), `fa_pfcf_o{N}` (over N), `fa_pfcf_{from}to{to}` (range, e.g., `fa_pfcf_10to30`). Range: 5–100.

Special: `fa_pfcf_low` (Low <15, FCF割安), `fa_pfcf_high` (High >50)


### EV/EBITDA (`fa_evebitda_`)


Pattern: `fa_evebitda_u{N}` (under N), `fa_evebitda_o{N}` (over N), `fa_evebitda_{from}to{to}` (range, e.g., `fa_evebitda_5to15`). Range: 5–50.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_evebitda_negative` | Negative (<0) | EV/EBITDA negative |
| `fa_evebitda_low` | Low (<15) | low EV/EBITDA, EV/EBITDA割安 |
| `fa_evebitda_profitable` | Profitable (>0) | EV/EBITDA profitable |
| `fa_evebitda_high` | High (>50) | high EV/EBITDA |
| `fa_evebitda_u5` | Under 5 | EV/EBITDA<5 |
| `fa_evebitda_u10` | Under 10 | EV/EBITDA<10 |
| `fa_evebitda_u15` | Under 15 | EV/EBITDA<15 |
| `fa_evebitda_u20` | Under 20 | EV/EBITDA<20 |
| `fa_evebitda_u25` | Under 25 |  |
| `fa_evebitda_u30` | Under 30 |  |
| `fa_evebitda_u35` | Under 35 |  |
| `fa_evebitda_u40` | Under 40 |  |
| `fa_evebitda_u45` | Under 45 |  |
| `fa_evebitda_u50` | Under 50 |  |
| `fa_evebitda_o5` | Over 5 |  |
| `fa_evebitda_o10` | Over 10 |  |
| `fa_evebitda_o15` | Over 15 |  |
| `fa_evebitda_o20` | Over 20 |  |
| `fa_evebitda_o25` | Over 25 |  |
| `fa_evebitda_o30` | Over 30 |  |
| `fa_evebitda_o35` | Over 35 |  |
| `fa_evebitda_o40` | Over 40 |  |
| `fa_evebitda_o45` | Over 45 |  |
| `fa_evebitda_o50` | Over 50 |  |

### EV/Sales (`fa_evsales_`)


Pattern: `fa_evsales_u{N}` (under N), `fa_evsales_o{N}` (over N). Range: 1–10.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_evsales_negative` | Negative (<0) | EV/Sales negative |
| `fa_evsales_low` | Low (<1) | low EV/Sales |
| `fa_evsales_positive` | Positive (>0) | EV/Sales positive |
| `fa_evsales_high` | High (>10) | high EV/Sales |
| `fa_evsales_u1` | Under 1 | EV/Sales<1 |
| `fa_evsales_u2` | Under 2 | EV/Sales<2 |
| `fa_evsales_u3` | Under 3 |  |
| `fa_evsales_u5` | Under 5 |  |
| `fa_evsales_u10` | Under 10 |  |
| `fa_evsales_o1` | Over 1 |  |
| `fa_evsales_o2` | Over 2 |  |
| `fa_evsales_o3` | Over 3 |  |
| `fa_evsales_o5` | Over 5 |  |
| `fa_evsales_o10` | Over 10 |  |

### Dividend Yield (`fa_div_`)


Pattern: `fa_div_o{N}` (over N%), `fa_div_{from}to{to}` (range, e.g., `fa_div_3to8` = 3% to 8%)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_div_none` | None (0%) | no dividend, 無配 |
| `fa_div_pos` | Positive (>0%) | has dividend, 配当あり |
| `fa_div_high` | High (>5%) | high dividend, 高配当 |
| `fa_div_veryhigh` | Very High (>10%) | very high dividend, 超高配当 |
| `fa_div_o1` | Over 1% | 配当1%以上 |
| `fa_div_o2` | Over 2% | 配当2%以上 |
| `fa_div_o3` | Over 3% | 配当3%以上 |
| `fa_div_o4` | Over 4% | 配当4%以上 |
| `fa_div_o5` | Over 5% | 配当5%以上 |
| `fa_div_o6` | Over 6% | 配当6%以上 |
| `fa_div_o7` | Over 7% | 配当7%以上 |
| `fa_div_o8` | Over 8% | 配当8%以上 |
| `fa_div_o9` | Over 9% | 配当9%以上 |
| `fa_div_o10` | Over 10% | 配当10%以上 |

### Dividend Growth (`fa_divgrowth_`)


Pattern: `fa_divgrowth_{period}o{N}` where period = `1y`/`3y`/`5y` and N = 5/10/15/20/25/30.

Positive: `fa_divgrowth_{period}pos`. Growing streak: `fa_divgrowth_cy{N}` (N = 1–9 years).


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_divgrowth_1ypos` | 1 Year Positive | 1Y配当増配 |
| `fa_divgrowth_1yo5` | 1 Year Over 5% | 1Y DG>5% |
| `fa_divgrowth_1yo10` | 1 Year Over 10% | 1Y DG>10% |
| `fa_divgrowth_3ypos` | 3 Years Positive | 3Y配当増配 |
| `fa_divgrowth_3yo10` | 3 Years Over 10% | 3Y DG>10% |
| `fa_divgrowth_5ypos` | 5 Years Positive | 5Y配当増配 |
| `fa_divgrowth_5yo10` | 5 Years Over 10% | 5Y DG>10% |
| `fa_divgrowth_cy1` | Growing 1+ Year | 1年以上連続増配 |
| `fa_divgrowth_cy3` | Growing 3+ Years | 3年以上連続増配 |
| `fa_divgrowth_cy5` | Growing 5+ Years | 5年以上連続増配, 連続増配株 |
| `fa_divgrowth_cy7` | Growing 7+ Years | 7年以上連続増配 |
| `fa_divgrowth_cy9` | Growing 9+ Years | 9年以上連続増配 |

### Payout Ratio (`fa_payoutratio_`)


Pattern: `fa_payoutratio_u{N}` (under N%), `fa_payoutratio_o{N}` (over N%), `fa_payoutratio_{from}to{to}` (range, e.g., `fa_payoutratio_20to60`). Range: 0–100.

Special: `fa_payoutratio_none` (0%), `fa_payoutratio_pos` (>0%), `fa_payoutratio_low` (<20%), `fa_payoutratio_high` (>50%)


### EPS Growth


All EPS growth filters follow the same pattern: `neg` (negative), `pos` (positive), `poslow` (0-10%), `high` (>25%), `o{N}` (over N%), `u{N}` (under N%). N = 5/10/15/20/25/30.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_epsqoq_*` | EPS Growth Q/Q | EPS QoQ, 四半期EPS成長, 増益 |
| `fa_epsyoy_*` | EPS Growth This Year | EPS this year, 今年のEPS成長 |
| `fa_epsyoy1_*` | EPS Growth Next Year | EPS next year, 来年のEPS成長予想 |
| `fa_epsyoyttm_*` | EPS Growth TTM | EPS TTM, 直近12ヶ月EPS成長 |
| `fa_eps3years_*` | EPS Growth Past 3 Years | 3Y EPS成長 |
| `fa_eps5years_*` | EPS Growth Past 5 Years | 5Y EPS成長 |
| `fa_estltgrowth_*` | EPS Growth Next 5 Years | 5Y EPS成長予想, 長期成長 |

**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_epsqoq_pos` | EPS Q/Q Positive | 増益 |
| `fa_epsqoq_o25` | EPS Q/Q Over 25% | 高成長株 |
| `fa_epsyoy_high` | EPS This Year High (>25%) |  |
| `fa_epsyoy1_pos` | EPS Next Year Positive | 来年増益予想 |
| `fa_epsyoyttm_o10` | EPS TTM Over 10% |  |
| `fa_eps3years_pos` | EPS Past 3Y Positive |  |
| `fa_eps5years_o20` | EPS Past 5Y Over 20% |  |
| `fa_estltgrowth_o15` | EPS Next 5Y Over 15% | 長期高成長 |

### Sales Growth


Same pattern as EPS Growth: `neg`, `pos`, `poslow`, `high`, `o{N}`, `u{N}`.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_salesqoq_*` | Sales Growth Q/Q | 売上QoQ, 増収 |
| `fa_salesyoyttm_*` | Sales Growth TTM | 売上TTM, 直近12ヶ月売上成長 |
| `fa_sales3years_*` | Sales Growth Past 3 Years | 3Y売上成長 |
| `fa_sales5years_*` | Sales Growth Past 5 Years | 5Y売上成長 |

**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_salesqoq_pos` | Sales Q/Q Positive | 増収 |
| `fa_salesqoq_o25` | Sales Q/Q Over 25% | 高成長 |
| `fa_salesyoyttm_o10` | Sales TTM Over 10% |  |
| `fa_sales3years_high` | Sales Past 3Y High (>25%) |  |
| `fa_sales5years_pos` | Sales Past 5Y Positive |  |

### Earnings & Revenue Surprise (`fa_epsrev_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_epsrev_bp` | Both Positive (>0%) | positive surprise, ポジティブサプライズ, 決算好調 |
| `fa_epsrev_bm` | Both Met (0%) | met estimates, 予想一致 |
| `fa_epsrev_bn` | Both Negative (<0%) | negative surprise, ネガティブサプライズ, 決算不振 |

### Profitability — ROE, ROA, ROIC


All return metrics follow the pattern: `pos` (>0%), `neg` (<0%), `o{N}` (over N%), `u-{N}` (under -N%).

Special labels: `verypos` (ROE >30%, ROA >15%, ROIC >25%), `veryneg` (ROE <-15%, ROA <-15%, ROIC <-10%)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_roe_*` | Return on Equity | ROE, 自己資本利益率 |
| `fa_roa_*` | Return on Assets | ROA, 総資産利益率 |
| `fa_roi_*` | Return on Invested Capital (ROIC) | ROI, ROIC, 投下資本利益率 |

**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_roe_o15` | ROE Over 15% | ROE>15%, 高収益 |
| `fa_roe_o30` | ROE Over 30% | ROE>30% |
| `fa_roa_o10` | ROA Over 10% | ROA>10% |
| `fa_roi_o20` | ROIC Over 20% | ROIC>20% |
| `fa_roi_verypos` | ROIC Very Positive (>25%) | 高ROIC |

### Margins


Pattern: `pos` (>0%), `neg` (<0%), `high` (gross >50%, operating >25%, net >20%), `veryneg` (<-20%), `o{N}` (over N%), `u{N}` (under N%), `u-{N}` (under -N%).

N range: 0–90 (5-point intervals).


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_grossmargin_*` | Gross Margin | gross margin, 粗利率 |
| `fa_opermargin_*` | Operating Margin | operating margin, 営業利益率 |
| `fa_netmargin_*` | Net Profit Margin | net margin, 純利益率 |

**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_grossmargin_o50` | Gross Margin Over 50% | 高粗利 |
| `fa_opermargin_o20` | Operating Margin Over 20% | 高営業利益率 |
| `fa_netmargin_pos` | Net Margin Positive | 黒字 |
| `fa_netmargin_o10` | Net Margin Over 10% |  |
| `fa_grossmargin_u-10` | Gross Margin Under -10% | 赤字 |

### Debt & Liquidity


**LT Debt/Equity** (`fa_ltdebteq_`): `u{N}` / `o{N}`, N = 0.1–1.0. Special: `low` (<0.1), `high` (>0.5)

**Total Debt/Equity** (`fa_debteq_`): Same pattern. Special: `low` (<0.1), `high` (>0.5)

**Current Ratio** (`fa_curratio_`): `u{N}` / `o{N}`, N = 0.5–10. Special: `low` (<1), `high` (>3)

**Quick Ratio** (`fa_quickratio_`): `u{N}` / `o{N}`, N = 0.5–10. Special: `low` (<0.5), `high` (>3)


**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `fa_ltdebteq_u0.5` | LT D/E Under 0.5 | 低負債 |
| `fa_debteq_low` | Total D/E Low (<0.1) | 超低負債 |
| `fa_curratio_o2` | Current Ratio Over 2 | 高流動性 |
| `fa_quickratio_o1` | Quick Ratio Over 1 |  |

---


## Technical Filters (`ta_`)


### RSI 14-day (`ta_rsi_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_rsi_ob90` | Overbought (90) | extremely overbought, 超過熱 |
| `ta_rsi_ob80` | Overbought (80) | overbought, 過熱 |
| `ta_rsi_ob70` | Overbought (70) | overbought, 買われすぎ |
| `ta_rsi_ob60` | Overbought (60) |  |
| `ta_rsi_os40` | Oversold (40) | slightly oversold |
| `ta_rsi_os30` | Oversold (30) | oversold, 売られすぎ |
| `ta_rsi_os20` | Oversold (20) | deeply oversold, 深い売られすぎ |
| `ta_rsi_os10` | Oversold (10) | extremely oversold |
| `ta_rsi_nob60` | Not Overbought (<60) |  |
| `ta_rsi_nob50` | Not Overbought (<50) |  |
| `ta_rsi_nos40` | Not Oversold (>40) |  |
| `ta_rsi_nos50` | Not Oversold (>50) |  |

### Moving Averages (`ta_sma20_`, `ta_sma50_`, `ta_sma200_`)


Each SMA has the following options:

- `pa` / `pb` — Price above/below SMA

- `pa{N}` / `pb{N}` — Price N% above/below SMA (N = 10,20,30,40,50 for SMA20/50; up to 100 for SMA200)

- `pc` / `pca` / `pcb` — Price crossed / crossed above / crossed below SMA

- `sa{X}` / `sb{X}` — SMA above/below other SMA (X = 20,50,200)

- `cross{X}` / `cross{X}a` / `cross{X}b` — SMA crossed / crossed above / crossed below other SMA


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_sma20_pa` | Price Above SMA20 | above 20MA, 20日線の上 |
| `ta_sma20_pb` | Price Below SMA20 | below 20MA, 20日線の下 |
| `ta_sma20_pca` | Price Crossed Above SMA20 | break above 20MA, 20日線突破 |
| `ta_sma20_pcb` | Price Crossed Below SMA20 | break below 20MA, 20日線割れ |
| `ta_sma50_pa` | Price Above SMA50 | above 50MA, 50日線の上 |
| `ta_sma50_pb` | Price Below SMA50 | below 50MA, 50日線の下 |
| `ta_sma50_pca` | Price Crossed Above SMA50 | break above 50MA, 50日線突破 |
| `ta_sma50_pcb` | Price Crossed Below SMA50 | break below 50MA, 50日線割れ |
| `ta_sma200_pa` | Price Above SMA200 | above 200MA, 200日線の上, 長期上昇 |
| `ta_sma200_pb` | Price Below SMA200 | below 200MA, 200日線の下, 長期下落 |
| `ta_sma200_pca` | Price Crossed Above SMA200 | break above 200MA, ゴールデンクロス |
| `ta_sma200_pcb` | Price Crossed Below SMA200 | break below 200MA, デッドクロス |
| `ta_sma200_sa50` | SMA200 Above SMA50 | death cross, デッドクロス配置 |
| `ta_sma200_sb50` | SMA200 Below SMA50 | golden cross, ゴールデンクロス配置 |
| `ta_sma50_cross200a` | SMA50 Crossed SMA200 Above | golden cross発生 |
| `ta_sma50_cross200b` | SMA50 Crossed SMA200 Below | death cross発生 |

### Change (`ta_change_`)


Today's price change. Pattern: `ta_change_u{N}` (up N%), `ta_change_d{N}` (down N%). N = 1–20.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_change_u` | Up | 今日上昇 |
| `ta_change_d` | Down | 今日下落 |
| `ta_change_u1` | Up 1% |  |
| `ta_change_u5` | Up 5% | 今日大幅上昇 |
| `ta_change_u10` | Up 10% | 今日急騰 |
| `ta_change_u15` | Up 15% |  |
| `ta_change_u20` | Up 20% |  |
| `ta_change_d1` | Down 1% |  |
| `ta_change_d5` | Down 5% | 今日大幅下落 |
| `ta_change_d10` | Down 10% | 今日急落 |
| `ta_change_d15` | Down 15% |  |
| `ta_change_d20` | Down 20% |  |

### Change from Open (`ta_changeopen_`)


Same pattern as Change: `ta_changeopen_u{N}` / `ta_changeopen_d{N}`. N = 1–20.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_changeopen_u` | Up from Open | 始値から上昇 |
| `ta_changeopen_d` | Down from Open | 始値から下落 |
| `ta_changeopen_u5` | Up 5% from Open |  |
| `ta_changeopen_d5` | Down 5% from Open |  |

### 52-Week High/Low (`ta_highlow52w_`)


Pattern: `nh` (new high), `nl` (new low), `b{range}h` (below high), `a{range}h` (above low)

Ranges below high: `0to3`, `0to5`, `0to10`, `5`, `10`, `15`, `20`, `30`, `40`, `50`, `60`, `70`, `80`, `90`

Ranges above low: same pattern

**Custom range:** For arbitrary ranges not in the preset list, FinViz supports custom range suffixes:

- `-bhx` (below high, custom): `ta_highlow52w_{from}to{to}-bhx` = {from}–{to}% below 52-week high
- `-alx` (above low, custom): `ta_highlow52w_{from}to{to}-alx` = {from}–{to}% above 52-week low

Examples:
- `ta_highlow52w_10to30-bhx` = 52-week high から 10-30% 下落
- `ta_highlow52w_10to30-alx` = 52-week low から 10-30% 上昇

This syntax is generated by FinViz's custom range UI (requires `&ft=4` in URL for custom filter type). Not registered in the finviz Python library.

**Strategy guide — choosing `-bhx` vs `-alx`:**

| Strategy | Suffix | Use When | Example |
|---|---|---|---|
| Pullback buy (押し目買い) | `-bhx` | Growth + quality stocks in temporary correction. Uptrend intact. | `ta_highlow52w_10to30-bhx` with `fa_epsqoq_pos` |
| Reversal / deep value (リバーサル) | `-alx` | Turnaround or bottom-fishing plays. Higher risk of continued decline. | `ta_highlow52w_10to30-alx` with `fa_pb_u1` |

Rule of thumb: Pair `-bhx` with growth/quality filters (EPS growth, sales growth). Pair `-alx` with deep value filters (low P/B, low EV/EBITDA).


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_highlow52w_nh` | New High | 52-week high, 52週高値, 新高値 |
| `ta_highlow52w_nl` | New Low | 52-week low, 52週安値, 新安値 |
| `ta_highlow52w_b0to3h` | 0-3% Below High | near high, 高値付近 |
| `ta_highlow52w_b0to5h` | 0-5% Below High | near high |
| `ta_highlow52w_b0to10h` | 0-10% Below High | close to high |
| `ta_highlow52w_b10h` | 10%+ Below High | pullback, 調整中 |
| `ta_highlow52w_b20h` | 20%+ Below High | correction, 修正局面 |
| `ta_highlow52w_b30h` | 30%+ Below High | deep correction |
| `ta_highlow52w_b50h` | 50%+ Below High | bear territory, 暴落 |
| `ta_highlow52w_a0to3h` | 0-3% Above Low | near low, 安値付近 |
| `ta_highlow52w_a0to5h` | 0-5% Above Low | near low |
| `ta_highlow52w_a20h` | 20%+ Above Low | recovering |
| `ta_highlow52w_a50h` | 50%+ Above Low | strong recovery |
| `ta_highlow52w_a100h` | 100%+ Above Low | doubled from low |

### 20-Day High/Low (`ta_highlow20d_`)


Same pattern as 52-Week: `nh`, `nl`, `b{range}h` (below high), `a{range}h` (above low).

Ranges: `0to3`, `0to5`, `0to10`, `5`, `10`, `15`, `20`, `30`, `40`, `50`.

Custom range also supported: `ta_highlow20d_{from}to{to}-bhx` / `-alx` (see 52-Week section).


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_highlow20d_nh` | 20-Day New High | 20日新高値 |
| `ta_highlow20d_nl` | 20-Day New Low | 20日新安値 |
| `ta_highlow20d_b0to5h` | 0-5% Below 20D High | 20日高値付近 |

### 50-Day High/Low (`ta_highlow50d_`)


Same pattern as 20-Day High/Low. `nh`, `nl`, `b{range}h`, `a{range}h`.


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_highlow50d_nh` | 50-Day New High | 50日新高値 |
| `ta_highlow50d_nl` | 50-Day New Low | 50日新安値 |

### All-Time High/Low (`ta_alltime_`)


Same structure as 52-Week High/Low. Ranges up to 500% above low. Custom range also supported: `ta_alltime_{from}to{to}-bhx` / `-alx`.


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_alltime_nh` | All-Time High | all-time high, 史上最高値, ATH |
| `ta_alltime_nl` | All-Time Low | all-time low, 史上最安値 |
| `ta_alltime_b0to3h` | 0-3% Below ATH | ATH付近 |
| `ta_alltime_b0to5h` | 0-5% Below ATH | ATH付近 |
| `ta_alltime_b10h` | 10%+ Below ATH | ATHから10%下落 |
| `ta_alltime_b20h` | 20%+ Below ATH | ATHから20%下落 |
| `ta_alltime_b50h` | 50%+ Below ATH | ATHから半値 |

### Performance (`ta_perf_`)


Pattern: `ta_perf_{period}{direction}{threshold}`

Periods: `d` (today), `1w` (week), `4w` (month), `13w` (quarter), `26w` (half), `52w` (year), `ytd` (YTD), `3y`, `5y`, `10y`

Directions: `up`/`down` (any), `{N}o` (+N%), `{N}u` (-N%)


**Key codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_perf_dup` | Today Up | today up, 今日上昇 |
| `ta_perf_ddown` | Today Down | today down, 今日下落 |
| `ta_perf_d5o` | Today +5% | big up today |
| `ta_perf_d5u` | Today -5% | big down today |
| `ta_perf_1wup` | Week Up | week up, 週間上昇 |
| `ta_perf_1wdown` | Week Down | week down, 週間下落 |
| `ta_perf_4wup` | Month Up | month up, 月間上昇 |
| `ta_perf_4wdown` | Month Down | month down, 月間下落 |
| `ta_perf_13wup` | Quarter Up | quarter up, 四半期上昇 |
| `ta_perf_13wdown` | Quarter Down | quarter down |
| `ta_perf_26wup` | Half Year Up | half up, 半年上昇 |
| `ta_perf_52wup` | Year Up | year up, 年間上昇 |
| `ta_perf_52wdown` | Year Down | year down, 年間下落 |
| `ta_perf_ytdup` | YTD Up | YTD up, 年初来上昇 |
| `ta_perf_ytddown` | YTD Down | YTD down, 年初来下落 |
| `ta_perf_3yup` | 3 Years Up | 3Y up |
| `ta_perf_5yup` | 5 Years Up | 5Y up |
| `ta_perf_10yup` | 10 Years Up | 10Y up |
| `ta_perf_52w100o` | Year +100% | 年間2倍 |
| `ta_perf_52w50u` | Year -50% | 年間半値 |

### Performance 2 (`ta_perf2_`)


Identical structure to Performance but allows a second independent performance filter.

Prefix: `ta_perf2_` instead of `ta_perf_`. Same periods and thresholds.

Use case: Filter stocks that are up this quarter AND down this month.


### Gap (`ta_gap_`)


Pattern: `ta_gap_u{N}` (gap up N%), `ta_gap_d{N}` (gap down N%). N = 0–20.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_gap_u` | Gap Up | gap up, ギャップアップ |
| `ta_gap_d` | Gap Down | gap down, ギャップダウン |
| `ta_gap_u0` | Gap Up 0%+ |  |
| `ta_gap_u3` | Gap Up 3%+ |  |
| `ta_gap_u5` | Gap Up 5%+ | big gap up |
| `ta_gap_u10` | Gap Up 10%+ |  |
| `ta_gap_d0` | Gap Down 0%+ |  |
| `ta_gap_d3` | Gap Down 3%+ |  |
| `ta_gap_d5` | Gap Down 5%+ | big gap down |
| `ta_gap_d10` | Gap Down 10%+ |  |

### Beta (`ta_beta_`)


Pattern: `ta_beta_u{N}` (under N), `ta_beta_o{N}` (over N). Also ranges: `0to0.5`, `0to1`, `0.5to1`, `0.5to1.5`, `1to1.5`, `1to2`.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_beta_u0` | Beta Under 0 | negative beta |
| `ta_beta_u0.5` | Beta Under 0.5 | low beta, 低ベータ, ディフェンシブ |
| `ta_beta_u1` | Beta Under 1 | below market |
| `ta_beta_o1` | Beta Over 1 | above market |
| `ta_beta_o1.5` | Beta Over 1.5 | high beta, 高ベータ |
| `ta_beta_o2` | Beta Over 2 | very high beta |
| `ta_beta_o3` | Beta Over 3 | extremely high beta |

### Volatility (`ta_volatility_`)


Pattern: `ta_volatility_{period}_{direction}{N}` where period = w (week) / m (month), N = 2–15.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_volatility_mo10` | Month - Over 10% |  |
| `ta_volatility_mo12` | Month - Over 12% |  |
| `ta_volatility_mo15` | Month - Over 15% |  |
| `ta_volatility_mo2` | Month - Over 2% |  |
| `ta_volatility_mo3` | Month - Over 3% |  |
| `ta_volatility_mo4` | Month - Over 4% |  |
| `ta_volatility_mo5` | Month - Over 5% |  |
| `ta_volatility_mo6` | Month - Over 6% |  |
| `ta_volatility_mo7` | Month - Over 7% |  |
| `ta_volatility_mo8` | Month - Over 8% |  |
| `ta_volatility_mo9` | Month - Over 9% |  |
| `ta_volatility_wo10` | Week - Over 10% |  |
| `ta_volatility_wo12` | Week - Over 12% |  |
| `ta_volatility_wo15` | Week - Over 15% |  |
| `ta_volatility_wo2` | Week - Over 2% |  |
| `ta_volatility_wo3` | Week - Over 3% |  |
| `ta_volatility_wo4` | Week - Over 4% |  |
| `ta_volatility_wo5` | Week - Over 5% |  |
| `ta_volatility_wo6` | Week - Over 6% |  |
| `ta_volatility_wo7` | Week - Over 7% |  |
| `ta_volatility_wo8` | Week - Over 8% |  |
| `ta_volatility_wo9` | Week - Over 9% |  |

### Average True Range (`ta_averagetruerange_`)


Pattern: `ta_averagetruerange_o{N}` (over N), `ta_averagetruerange_u{N}` (under N). N = 0.25–5.0.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_averagetruerange_o0.5` | ATR Over 0.5 | ATR>0.5 |
| `ta_averagetruerange_o1` | ATR Over 1 | ATR>1 |
| `ta_averagetruerange_o2` | ATR Over 2 | high ATR, 高ATR |
| `ta_averagetruerange_o3` | ATR Over 3 | very high ATR |
| `ta_averagetruerange_o5` | ATR Over 5 | extreme ATR |
| `ta_averagetruerange_u0.5` | ATR Under 0.5 | low ATR, 低ATR |
| `ta_averagetruerange_u1` | ATR Under 1 |  |
| `ta_averagetruerange_u2` | ATR Under 2 |  |

### Chart Patterns (`ta_pattern_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_pattern_channel` | Channel |  |
| `ta_pattern_channel2` | Channel (Strong) |  |
| `ta_pattern_channeldown` | Channel Down | falling channel, 下降チャネル |
| `ta_pattern_channeldown2` | Channel Down (Strong) |  |
| `ta_pattern_channelup` | Channel Up | rising channel, 上昇チャネル |
| `ta_pattern_channelup2` | Channel Up (Strong) |  |
| `ta_pattern_doublebottom` | Double Bottom | double bottom, ダブルボトム |
| `ta_pattern_doubletop` | Double Top | double top, ダブルトップ |
| `ta_pattern_headandshoulders` | Head & Shoulders | H&S, ヘッドアンドショルダー |
| `ta_pattern_headandshouldersinv` | Head & Shoulders Inverse | inverse H&S, 逆H&S |
| `ta_pattern_horizontal` | Horizontal S/R | horizontal channel, レンジ |
| `ta_pattern_horizontal2` | Horizontal S/R (Strong) |  |
| `ta_pattern_multiplebottom` | Multiple Bottom | multiple bottom |
| `ta_pattern_multipletop` | Multiple Top | multiple top |
| `ta_pattern_tlresistance` | TL Resistance |  |
| `ta_pattern_tlresistance2` | TL Resistance (Strong) |  |
| `ta_pattern_tlsupport` | TL Support |  |
| `ta_pattern_tlsupport2` | TL Support (Strong) |  |
| `ta_pattern_wedge` | Wedge |  |
| `ta_pattern_wedge2` | Wedge (Strong) |  |
| `ta_pattern_wedgedown` | Wedge Down | falling wedge |
| `ta_pattern_wedgedown2` | Wedge Down (Strong) |  |
| `ta_pattern_wedgeresistance` | Triangle Ascending | ascending triangle |
| `ta_pattern_wedgeresistance2` | Triangle Ascending (Strong) |  |
| `ta_pattern_wedgesupport` | Triangle Descending | descending triangle |
| `ta_pattern_wedgesupport2` | Triangle Descending (Strong) |  |
| `ta_pattern_wedgeup` | Wedge Up | rising wedge |
| `ta_pattern_wedgeup2` | Wedge Up (Strong) |  |

### Candlestick (`ta_candlestick_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ta_candlestick_d` | Doji | doji, 十字線 |
| `ta_candlestick_dd` | Dragonfly Doji | dragonfly doji, トンボ |
| `ta_candlestick_gd` | Gravestone Doji | gravestone doji |
| `ta_candlestick_h` | Hammer | hammer, ハンマー |
| `ta_candlestick_ih` | Inverted Hammer | inverted hammer |
| `ta_candlestick_lls` | Long Lower Shadow | long lower shadow, 下ヒゲ |
| `ta_candlestick_lus` | Long Upper Shadow | long upper shadow, 上ヒゲ |
| `ta_candlestick_mb` | Marubozu Black | marubozu black, 陰の丸坊主 |
| `ta_candlestick_mw` | Marubozu White | marubozu white, 陽の丸坊主 |
| `ta_candlestick_stb` | Spinning Top Black | spinning top black |
| `ta_candlestick_stw` | Spinning Top White | spinning top white |

---


## Share Filters (`sh_`)


### Average Volume (`sh_avgvol_`)


Pattern: `sh_avgvol_o{N}` (over NK), `sh_avgvol_u{N}` (under NK). Also ranges: `100to500`, `100to1000`, `500to1000`, `500to10000`.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_avgvol_u50` | Under 50K | very low volume |
| `sh_avgvol_u100` | Under 100K | low volume |
| `sh_avgvol_o100` | Over 100K |  |
| `sh_avgvol_o200` | Over 200K | min volume, 流動性確保 |
| `sh_avgvol_o500` | Over 500K |  |
| `sh_avgvol_o1000` | Over 1M | high volume, 高出来高 |
| `sh_avgvol_o2000` | Over 2M | very high volume |
| `sh_avgvol_100to500` | 100K to 500K |  |
| `sh_avgvol_500to1000` | 500K to 1M |  |

### Relative Volume (`sh_relvol_`)


Pattern: `sh_relvol_o{N}` (over N), `sh_relvol_u{N}` (under N). N = 0.1–10.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_relvol_u0.5` | Under 0.5 | low relative volume |
| `sh_relvol_u1` | Under 1 | below avg volume |
| `sh_relvol_o1` | Over 1 | above avg volume |
| `sh_relvol_o1.5` | Over 1.5 | elevated volume |
| `sh_relvol_o2` | Over 2 | volume surge, 出来高急増 |
| `sh_relvol_o3` | Over 3 | very high relative vol |
| `sh_relvol_o5` | Over 5 | extreme volume |
| `sh_relvol_o10` | Over 10 | unusual volume, 異常出来高 |

### Current Volume (`sh_curvol_`)


Pattern: `sh_curvol_o{N}`. No predefined dropdown options in screener UI; use with `f=` parameter.


### Price (`sh_price_`)


Pattern: `sh_price_u{N}` (under $N), `sh_price_o{N}` (over $N). Also ranges: `1to5`, `1to10`, `5to10`, `5to20`, `10to20`, `10to50`, `20to50`, `50to100`.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_price_u1` | Under $1 | penny stock, ペニーストック |
| `sh_price_u5` | Under $5 | low price, 低価格 |
| `sh_price_u10` | Under $10 |  |
| `sh_price_u20` | Under $20 |  |
| `sh_price_u50` | Under $50 | mid price |
| `sh_price_o5` | Over $5 |  |
| `sh_price_o10` | Over $10 |  |
| `sh_price_o20` | Over $20 |  |
| `sh_price_o50` | Over $50 |  |
| `sh_price_o100` | Over $100 | expensive, 高額株 |
| `sh_price_5to50` | $5 to $50 |  |
| `sh_price_10to50` | $10 to $50 | 中価格帯 |

### Float (`sh_float_`)


Pattern: `sh_float_u{N}` (under NM), `sh_float_o{N}` (over NM). Also percentage: `sh_float_u{N}p` / `sh_float_o{N}p`.


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_float_u1` | Under 1M | very low float |
| `sh_float_u5` | Under 5M | low float, 低フロート |
| `sh_float_u10` | Under 10M |  |
| `sh_float_u20` | Under 20M |  |
| `sh_float_o50` | Over 50M |  |
| `sh_float_o100` | Over 100M |  |
| `sh_float_o500` | Over 500M | high float |
| `sh_float_o1000` | Over 1000M |  |
| `sh_float_u10p` | Under 10% of Outstanding | very low float % |
| `sh_float_u20p` | Under 20% |  |
| `sh_float_o50p` | Over 50% |  |
| `sh_float_o80p` | Over 80% | high float % |

### Short Float (`sh_short_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_short_low` | Low (<5%) | low short interest |
| `sh_short_high` | High (>20%) | heavily shorted, 空売り大量 |
| `sh_short_u5` | Under 5% |  |
| `sh_short_u10` | Under 10% |  |
| `sh_short_o5` | Over 5% | some short interest |
| `sh_short_o10` | Over 10% | high short, ショートスクイーズ候補 |
| `sh_short_o15` | Over 15% |  |
| `sh_short_o20` | Over 20% | heavily shorted |
| `sh_short_o25` | Over 25% | very heavily shorted |
| `sh_short_o30` | Over 30% | extreme short interest |

### Shares Outstanding (`sh_outstanding_`)


Pattern: `sh_outstanding_u{N}` (under NM), `sh_outstanding_o{N}` (over NM).


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_outstanding_u1` | Under 1M |  |
| `sh_outstanding_u5` | Under 5M |  |
| `sh_outstanding_u10` | Under 10M | very low shares |
| `sh_outstanding_u50` | Under 50M |  |
| `sh_outstanding_u100` | Under 100M |  |
| `sh_outstanding_o10` | Over 10M |  |
| `sh_outstanding_o50` | Over 50M |  |
| `sh_outstanding_o100` | Over 100M |  |
| `sh_outstanding_o200` | Over 200M |  |
| `sh_outstanding_o500` | Over 500M |  |
| `sh_outstanding_o1000` | Over 1000M | high shares outstanding |

### Option/Short (`sh_opt_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_opt_option` | Optionable | optionable, オプション取引可能 |
| `sh_opt_short` | Shortable | shortable, 空売り可能 |
| `sh_opt_notoption` | Not Optionable | オプション不可 |
| `sh_opt_notshort` | Not Shortable | 空売り不可 |
| `sh_opt_optionshort` | Optionable and Shortable | オプション・空売り両方可能 |
| `sh_opt_optionnotshort` | Optionable and Not Shortable |  |
| `sh_opt_notoptionshort` | Not Optionable and Shortable |  |
| `sh_opt_notoptionnotshort` | Not Optionable and Not Shortable |  |

### Insider Ownership (`sh_insiderown_`)


Pattern: `sh_insiderown_o{N}` (over N%). Special: `low` (<5%), `high` (>30%), `veryhigh` (>50%)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_insiderown_low` | Low (<5%) | low insider |
| `sh_insiderown_high` | High (>30%) | insider owned |
| `sh_insiderown_veryhigh` | Very High (>50%) | majority insider |
| `sh_insiderown_o10` | Over 10% | インサイダー保有10%+ |
| `sh_insiderown_o20` | Over 20% |  |
| `sh_insiderown_o30` | Over 30% |  |
| `sh_insiderown_o50` | Over 50% | 過半数インサイダー |
| `sh_insiderown_o70` | Over 70% |  |
| `sh_insiderown_o90` | Over 90% |  |

### Insider Transactions (`sh_insidertrans_`)


Pattern: `sh_insidertrans_o{N}` (over +N%), `sh_insidertrans_u-{N}` (under -N%). N = 5–90.

Special: `pos` (>0%), `neg` (<0%), `verypos` (>20%), `veryneg` (<20%)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_insidertrans_pos` | Positive (>0%) | insider buying, インサイダー買い |
| `sh_insidertrans_neg` | Negative (<0%) | insider selling, インサイダー売り |
| `sh_insidertrans_verypos` | Very Positive (>20%) | heavy insider buying, インサイダー大量買い |
| `sh_insidertrans_veryneg` | Very Negative (<20%) | heavy insider selling |

### Institutional Ownership (`sh_instown_`)


Pattern: `sh_instown_o{N}` (over N%), `sh_instown_u{N}` (under N%). N = 10–90.

Special: `low` (<5%), `high` (>90%)


### Institutional Transactions (`sh_insttrans_`)


Pattern: `sh_insttrans_o{N}` (over +N%), `sh_insttrans_u-{N}` (under -N%). N = 5–50.

Special: `pos` (>0%), `neg` (<0%), `verypos` (>20%), `veryneg` (<20%)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `sh_insttrans_pos` | Positive (>0%) | institutional buying, 機関買い |
| `sh_insttrans_neg` | Negative (<0%) | institutional selling |

---


## Analyst Filters (`an_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `an_recom_strongbuy` | Strong Buy (1) | strong buy, 強い買い推奨 |
| `an_recom_buybetter` | Buy or better (1-2) | buy, 買い推奨 |
| `an_recom_buy` | Buy (2) |  |
| `an_recom_holdbetter` | Hold or better (1-3) | hold, ホールド以上 |
| `an_recom_hold` | Hold (3) |  |
| `an_recom_holdworse` | Hold or worse (3-5) |  |
| `an_recom_sell` | Sell (4) |  |
| `an_recom_sellworse` | Sell or worse (4-5) | sell, 売り推奨 |
| `an_recom_strongsell` | Strong Sell (5) | strong sell, 強い売り |

---


## Target Price (`targetprice_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `targetprice_above` | Above Price | target above, 目標株価以上 |
| `targetprice_below` | Below Price | target below, 目標株価以下 |
| `targetprice_a5` | 5% Above Price |  |
| `targetprice_a10` | 10% Above Price |  |
| `targetprice_a20` | 20% Above Price | 割安, 上昇余地 |
| `targetprice_a30` | 30% Above Price |  |
| `targetprice_a40` | 40% Above Price |  |
| `targetprice_a50` | 50% Above Price | 大幅割安 |
| `targetprice_b5` | 5% Below Price |  |
| `targetprice_b10` | 10% Below Price |  |
| `targetprice_b20` | 20% Below Price |  |
| `targetprice_b30` | 30% Below Price |  |
| `targetprice_b40` | 40% Below Price |  |
| `targetprice_b50` | 50% Below Price | 大幅割高 |

---


## Latest News (`news_date_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `news_date_today` | Today | news today, 今日のニュース |
| `news_date_todayafter` | Aftermarket Today |  |
| `news_date_yesterday` | Yesterday |  |
| `news_date_yesterdayafter` | In the Aftermarket Yesterday |  |
| `news_date_sinceyesterday` | Since Yesterday |  |
| `news_date_sinceyesterdayafter` | Since Aftermarket Yesterday |  |
| `news_date_prevminutes5` | In the last 5 minutes | 直近5分 |
| `news_date_prevminutes30` | In the last 30 minutes | 直近30分 |
| `news_date_prevhours1` | In the last hour | 直近1時間 |
| `news_date_prevhours24` | In the last 24 hours | 直近24時間 |
| `news_date_prevdays7` | In the last 7 days | 直近1週間 |
| `news_date_prevmonth` | In the last month | 直近1ヶ月 |

---


## Thematic Filters


### Theme (`theme_`)


| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `theme_agingpopulationlongevity` | Aging Population & Longevity |  |
| `theme_agriculturefoodtech` | Agriculture & FoodTech |  |
| `theme_artificialintelligence` | Artificial Intelligence | AI, 人工知能 |
| `theme_autonomoussystems` | Autonomous Systems | autonomous, 自律システム |
| `theme_bigdata` | Big Data | big data, ビッグデータ |
| `theme_biometrics` | Biometrics |  |
| `theme_cloudcomputing` | Cloud Computing | cloud, クラウド |
| `theme_commoditiesagriculture` | Commodities - Agriculture |  |
| `theme_commoditiesenergy` | Commodities - Energy |  |
| `theme_commoditiesmetals` | Commodities - Metals |  |
| `theme_consumergoods` | Consumer Goods |  |
| `theme_cryptoblockchain` | Crypto & Blockchain | crypto, 暗号通貨, ブロックチェーン |
| `theme_cybersecurity` | Cybersecurity | cybersecurity, サイバーセキュリティ |
| `theme_defenseaerospace` | Defense & Aerospace |  |
| `theme_digitalentertainment` | Digital Entertainment |  |
| `theme_ecommerce` | E-commerce | e-commerce, EC |
| `theme_educationtechnology` | Education Technology |  |
| `theme_electricvehicles` | Electric Vehicles | EV, 電気自動車 |
| `theme_energyrenewable` | Energy - Renewable | renewable, 再生可能エネルギー |
| `theme_energytraditional` | Energy - Traditional |  |
| `theme_environmentalsustainability` | Environmental Sustainability |  |
| `theme_fintech` | FinTech | fintech, フィンテック |
| `theme_hardware` | Hardware | hardware, ハードウェア |
| `theme_healthcarebiotech` | Healthcare & Biotech | biotech, バイオテック |
| `theme_healthyfoodnutrition` | Healthy Food & Nutrition |  |
| `theme_industrialautomation` | Industrial Automation |  |
| `theme_internetofthings` | Internet of Things | IoT |
| `theme_nanotechnology` | Nanotechnology |  |
| `theme_quantumcomputing` | Quantum Computing | quantum, 量子コンピューティング |
| `theme_realestatereits` | Real Estate & REITs | REITs, 不動産投資信託 |
| `theme_robotics` | Robotics | robotics, ロボティクス |
| `theme_semiconductors` | Semiconductors | semiconductors, 半導体 |
| `theme_smarthome` | Smart Home |  |
| `theme_socialmedia` | Social Media |  |
| `theme_software` | Software | software, ソフトウェア |
| `theme_spacetech` | Space Tech | space, 宇宙 |
| `theme_telecommunications` | Telecommunications |  |
| `theme_transportationlogistics` | Transportation & Logistics |  |
| `theme_virtualaugmentedreality` | Virtual & Augmented Reality | VR, AR, メタバース |
| `theme_wearables` | Wearables |  |

### Sub-theme (`subtheme_`)


268 sub-themes available. Pattern: `subtheme_{category}{subtopic}`.

Categories include: `ai`, `automation`, `autonomous`, `bigdata`, `blockchain`, `cloud`, `cybersecurity`, `defense`, `ecommerce`, `education`, `energy`, `entertainment`, `environmental`, `evs`, `fintech`, `hardware`, `healthcare`, `iot`, `longevity`, `nanotech`, `nutrition`, `quantum`, `realestate`, `robotics`, `semis`, `smarthome`, `social`, `software`, `space`, `telecom`.


**Example codes:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `subtheme_aicompute` | AI - Compute & Acceleration | AI半導体 |
| `subtheme_aicloud` | AI - Cloud & Infrastructure | AIクラウド |
| `subtheme_aimodels` | AI - Foundation Models & Platforms | AIモデル |
| `subtheme_semiscompute` | Semis - Logic & CPUs, GPUs, Accelerators | 半導体ロジック |
| `subtheme_semsmemory` | Semis - Memory & Storage | 半導体メモリ |
| `subtheme_evsbatteries` | EVs - Batteries & Materials | EVバッテリー |
| `subtheme_evscharging` | EVs - Charging & Infrastructure | EV充電 |
| `subtheme_cybersecuritycloud` | Cybersecurity - Cloud Security | クラウドセキュリティ |
| `subtheme_healthcaregenomics` | Healthcare - Genomics & Personalized Medicine | ゲノム |

---


## ETF Filters (`etf_`)


ETF-specific filters appear when screening ETFs (industry = Exchange Traded Fund).


### Annualized Return (`etf_return_`)


Pattern: `etf_return_{period}o{N}` (over N%), `etf_return_{period}u{N}` (under -N%). Periods: `1y`, `3y`, `5y`. N = 0, 05, 10, 25.


### Net Expense Ratio (`etf_netexpense_`)


Pattern: `etf_netexpense_u{NN}` (under N.N%). NN = 01–10 (0.1%–1.0%).


### Net Fund Flows (`etf_fundflows_`)


Pattern: `etf_fundflows_{period}o{N}` / `etf_fundflows_{period}u{N}`. Periods: `1m`, `3m`, `ytd`. N = 0, 10, 25, 50.


### Asset Type (`etf_assettype_`)


28 asset types: bonds, commodities, equities, currency, crypto, MLP, preferred stock, SPAC, multi-asset, target date.


### Single Category (`etf_category_`)


34 categories for fine-grained ETF classification (bonds, commodities, currency, equity subtypes).


### Sponsor (`etf_sponsor_`)


437 ETF sponsors (e.g., `etf_sponsor_blackrockishares`, `etf_sponsor_vanguard`, `etf_sponsor_schwab`, `etf_sponsor_fidelity`).


---


## Industry Codes (`ind_`)


150 industry codes. Pattern: `ind_{lowercasename}` with spaces, hyphens, and special characters removed.


**Common examples:**

| Code | Meaning | Natural Language Keywords |
|------|---------|---------------------------|
| `ind_stocksonly` | Stocks only (ex-Funds) | funds除外, 株式のみ |
| `ind_exchangetradedfund` | Exchange Traded Fund | ETF |
| `ind_semiconductors` | Semiconductors | 半導体 |
| `ind_softwareapplication` | Software - Application | アプリ |
| `ind_softwareinfrastructure` | Software - Infrastructure | インフラソフト |
| `ind_biotechnology` | Biotechnology | バイオテクノロジー |
| `ind_banksregional` | Banks - Regional | 地銀 |
| `ind_banksdiversified` | Banks - Diversified | メガバンク |
| `ind_oilgasep` | Oil & Gas E&P | 石油ガス探鉱 |
| `ind_oilgasintegrated` | Oil & Gas Integrated | 統合石油 |
| `ind_reitindustrial` | REIT - Industrial | 物流REIT |
| `ind_reitresidential` | REIT - Residential | 住宅REIT |
| `ind_utilitiesregulatedelectric` | Utilities - Regulated Electric | 規制電力 |
| `ind_insurancepropertycasualty` | Insurance - Property & Casualty | 損保 |
| `ind_capitalmarkets` | Capital Markets | 資本市場 |
| `ind_drugmanufacturersgeneral` | Drug Manufacturers - General | 大手製薬 |
| `ind_medicaldevices` | Medical Devices | 医療機器 |
| `ind_aerospacedefense` | Aerospace & Defense | 航空宇宙・防衛 |
| `ind_restaurants` | Restaurants | 外食 |
| `ind_internetretail` | Internet Retail | ネット通販 |
| `ind_gold` | Gold | 金鉱 |
| `ind_steel` | Steel | 鉄鋼 |

For the complete list of 150 industry codes, use the finviz screener dropdown or the `finviz` Python library.


---


## Common Screening Recipes


### High Dividend Value (高配当バリュー)

```

f=cap_midover,fa_div_o3,fa_pe_u20,fa_pb_u2,fa_roe_o10,geo_usa

```

Mid-cap+ US stocks with 3%+ yield, P/E under 20, P/B under 2, ROE over 10%.


### Small-Cap Growth (小型成長株)

```

f=cap_small,fa_epsqoq_o25,fa_salesqoq_o15,fa_roe_o15,sh_avgvol_o200

```

Small-cap with 25%+ quarterly EPS growth, 15%+ sales growth, 15%+ ROE, adequate liquidity.


### Oversold Large-Cap (売られすぎ大型株)

```

f=cap_largeover,ta_rsi_os30,ta_sma200_pa,fa_pe_profitable,sh_avgvol_o500

```

Large-cap+ with RSI below 30 but still above 200-day MA, profitable, liquid.


### Breakout Candidates (ブレイクアウト候補)

```

f=cap_midover,ta_highlow52w_b0to5h,sh_relvol_o1.5,ta_sma50_pa,sh_avgvol_o300

```

Mid-cap+ within 5% of 52-week high, above-average volume, above 50-day MA.


### Insider Buying (インサイダー買い)

```

f=cap_smallover,sh_insidertrans_verypos,fa_pe_profitable,sh_avgvol_o100

```

Small-cap+ with very positive insider transactions, profitable, minimum volume.


### Short Squeeze Candidates (ショートスクイーズ候補)

```

f=sh_short_o20,sh_relvol_o2,ta_perf_1wup,cap_smallover

```

20%+ short float, 2x+ relative volume, up this week, small-cap or larger.


### Dividend Growth (配当成長)

```

f=fa_div_o2,fa_divgrowth_3yo10,fa_payoutratio_u60,fa_roe_o15,cap_midover,geo_usa

```

2%+ yield, 3Y dividend growth 10%+, payout under 60%, ROE 15%+, mid-cap+ US stocks.


### Deep Value (ディープバリュー)

```

f=fa_pb_u1,fa_pe_u10,fa_curratio_o1.5,fa_netmargin_pos,sh_avgvol_o100,cap_smallover

```

P/B under 1, P/E under 10, current ratio over 1.5, profitable, liquid.


### Momentum Leaders (モメンタムリーダー)

```

f=ta_perf_13wup,ta_perf_26wup,ta_sma50_pa,ta_sma200_pa,sh_relvol_o1,cap_midover

```

Up over 13 and 26 weeks, above 50 and 200 MA, above-average volume, mid-cap+.


### Fallen Angels (急落後リバウンド候補)

```

f=cap_largeover,ta_highlow52w_b20h,ta_rsi_os40,fa_pe_profitable,sh_avgvol_o500

```

Large-cap+ down 20%+ from 52W high, RSI under 40, profitable, liquid.


### AI Theme (AIテーマ)

```

f=theme_artificialintelligence,cap_midover,ta_perf_13wup

```

AI-themed stocks, mid-cap+, up this quarter.


### Earnings Positive Surprise (決算好調)

```

f=fa_epsrev_bp,cap_midover,sh_avgvol_o200

```

Both EPS and Revenue beat estimates, mid-cap+, liquid.


### Near All-Time High (最高値付近)

```

f=ta_alltime_b0to5h,cap_largeover,sh_avgvol_o500

```

Within 5% of all-time high, large-cap+, liquid.


### Low EV/EBITDA Value (低EV/EBITDA)

```

f=fa_evebitda_u10,fa_evebitda_profitable,cap_midover,fa_roe_o10

```

EV/EBITDA under 10 and profitable, mid-cap+, ROE over 10%.
