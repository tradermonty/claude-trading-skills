---
name: finviz-screener
description: Build and open FinViz screener URLs from natural language requests. Use when user wants to screen stocks, find stocks matching criteria, filter by fundamentals or technicals, or asks to open FinViz with specific conditions. Supports both Japanese and English input (e.g., "高配当で成長している小型株を探したい", "Find oversold large caps with high ROE").
---

# FinViz Screener

## Overview

Translate natural-language stock screening requests into FinViz screener filter codes, build the URL, and open it in Chrome. No API key required for public screener; FINVIZ Elite is auto-detected from `$FINVIZ_API_KEY` for enhanced functionality.

**Key Features:**
- Natural language → filter code mapping (Japanese + English)
- URL construction with view type and sort order selection
- Elite/Public auto-detection (environment variable or explicit flag)
- Chrome-first browser opening with OS-appropriate fallbacks
- Strict filter validation to prevent URL injection

---

## When to Use This Skill

**Explicit Triggers:**
- "高配当で成長している小型株を探したい"
- "Find oversold large caps near 52-week lows"
- "テクノロジーセクターの割安株をスクリーニングしたい"
- "Screen for stocks with insider buying"
- "FinVizでブレイクアウト候補を表示して"
- "Show me high-growth small caps on FinViz"
- "配当利回り5%以上でROE15%以上の銘柄を探して"

**Implicit Triggers:**
- User describes stock screening criteria using fundamental or technical terms
- User mentions FinViz screener or stock filtering
- User asks to find stocks matching specific financial characteristics

**When NOT to Use:**
- Deep fundamental analysis of a specific stock (use us-stock-analysis)
- Portfolio review with holdings (use portfolio-manager)
- Chart pattern analysis on images (use technical-analyst)
- Earnings-based screening (use earnings-trade-analyzer or pead-screener)

---

## Workflow

### Step 1: Load Filter Reference

Read the filter knowledge base:

```bash
cat references/finviz_screener_filters.md
```

### Step 2: Interpret User Request

Map the user's natural-language request to FinViz filter codes. Use the Common Concept Mapping table below for quick translation, and reference the full filter list for precise code selection.

**Note:** For range criteria (e.g., "dividend 3-8%", "P/E between 10 and 20"), use the `{from}to{to}` range syntax as a single filter token (e.g., `fa_div_3to8`, `fa_pe_10to20`) instead of combining separate `_o` and `_u` filters.

**Common Concept Mapping:**

| User Concept (EN) | User Concept (JP) | Filter Codes |
|---|---|---|
| High dividend | 高配当 | `fa_div_o3` or `fa_div_o5` |
| Small cap | 小型株 | `cap_small` |
| Mid cap | 中型株 | `cap_mid` |
| Large cap | 大型株 | `cap_large` |
| Mega cap | 超大型株 | `cap_mega` |
| Value / cheap | 割安 | `fa_pe_u20,fa_pb_u2` |
| Growth stock | 成長株 | `fa_epsqoq_o25,fa_salesqoq_o15` |
| Oversold | 売られすぎ | `ta_rsi_os30` |
| Overbought | 買われすぎ | `ta_rsi_ob70` |
| Near 52W high | 52週高値付近 | `ta_highlow52w_b0to5h` |
| Near 52W low | 52週安値付近 | `ta_highlow52w_a0to5l` |
| Breakout | ブレイクアウト | `ta_highlow52w_b0to5h,sh_relvol_o1.5` |
| Technology | テクノロジー | `sec_technology` |
| Healthcare | ヘルスケア | `sec_healthcare` |
| Energy | エネルギー | `sec_energy` |
| Financial | 金融 | `sec_financial` |
| Semiconductors | 半導体 | `ind_semiconductors` |
| Biotechnology | バイオテク | `ind_biotechnology` |
| US stocks | 米国株 | `geo_usa` |
| Profitable | 黒字 | `fa_pe_profitable` |
| High ROE | 高ROE | `fa_roe_o15` or `fa_roe_o20` |
| Low debt | 低負債 | `fa_debteq_u0.5` |
| Insider buying | インサイダー買い | `sh_insidertrans_verypos` |
| Short squeeze | ショートスクイーズ | `sh_short_o20,sh_relvol_o2` |
| Dividend growth | 増配 | `fa_divgrowth_3yo10` |
| Deep value | ディープバリュー | `fa_pb_u1,fa_pe_u10` |
| Momentum | モメンタム | `ta_perf_13wup,ta_sma50_pa,ta_sma200_pa` |
| Defensive | ディフェンシブ | `ta_beta_u0.5` or `sec_utilities,sec_consumerdefensive` |
| Liquid / high volume | 高出来高 | `sh_avgvol_o500` or `sh_avgvol_o1000` |
| Fallen angel | 急落後反発 | `ta_highlow52w_b20to30h,ta_rsi_os40` |
| AI theme | AIテーマ | `theme_artificialintelligence` |
| Cybersecurity theme | サイバーセキュリティ | `theme_cybersecurity` |
| Yield 3-8% (trap excluded) | 配当3-8%（トラップ除外）| `fa_div_3to8` |
| Mid-range P/E | 適正PER帯 | `fa_pe_10to20` |
| EV undervalued | EV割安 | `fa_evebitda_u10` |
| Earnings next week | 来週決算 | `earningsdate_nextweek` |
| IPO recent | 直近IPO | `ipodate_thismonth` |
| Target price above | 目標株価以上 | `targetprice_a20` |
| Recent news | 最新ニュースあり | `news_date_today` |
| High institutional | 機関保有率高 | `sh_instown_o60` |
| Low float | 浮動株少 | `sh_float_u20` |
| Near all-time high | 史上最高値付近 | `ta_alltime_b0to5h` |
| High ATR | 高ボラティリティ | `ta_averagetruerange_o1.5` |

### Step 3: Present Filter Selection

Before executing, present the selected filters in a table for user confirmation:

```markdown
| Filter Code | Meaning |
|---|---|
| cap_small | Small Cap ($300M–$2B) |
| fa_div_o3 | Dividend Yield > 3% |
| fa_pe_u20 | P/E < 20 |
| geo_usa | USA |

View: Overview (v=111)
Mode: Public / Elite (auto-detected)
```

Ask the user to confirm or adjust before proceeding.

### Step 4: Execute Script

Run the screener script to build the URL and open Chrome:

```bash
python3 scripts/open_finviz_screener.py \
  --filters "cap_small,fa_div_o3,fa_pe_u20,geo_usa" \
  --view overview
```

**Script arguments:**
- `--filters` (required): Comma-separated filter codes
- `--elite`: Force Elite mode (auto-detected from `$FINVIZ_API_KEY` if not set)
- `--view`: View type — overview, valuation, financial, technical, ownership, performance, custom
- `--order`: Sort order (e.g., `-marketcap`, `dividendyield`, `-change`)
- `--url-only`: Print URL without opening browser

### Step 5: Report Results

After opening the screener, report:
1. The constructed URL
2. Elite or Public mode used
3. Summary of applied filters
4. Suggested next steps (e.g., "Sort by dividend yield", "Switch to Financial view for detailed ratios")

---

## Resources

- `references/finviz_screener_filters.md` — Complete filter code reference with natural language keywords (includes industry code examples; full 142-code list is in the Industry Codes section)
- `scripts/open_finviz_screener.py` — URL builder and Chrome opener
