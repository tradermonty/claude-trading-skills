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
| Pullback from high | 高値からの押し目 | `ta_highlow52w_10to30-bhx` |
| Near 52W low reversal | 安値圏リバーサル | `ta_highlow52w_10to30-alx` |
| Fallen angel | 急落後反発 | `ta_highlow52w_b20to30h,ta_rsi_os40` |
| AI theme | AIテーマ | `--themes "artificialintelligence"` |
| Cybersecurity theme | サイバーセキュリティ | `--themes "cybersecurity"` |
| AI + Cybersecurity | AI＆サイバーセキュリティ | `--themes "artificialintelligence,cybersecurity"` |
| AI Cloud sub-theme | AIクラウド | `--subthemes "aicloud"` |
| AI Compute sub-theme | AI半導体 | `--subthemes "aicompute"` |
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
| Type | Value | Meaning |
|---|---|---|
| Theme | artificialintelligence | Artificial Intelligence |
| Sub-theme | aicloud | AI - Cloud & Infrastructure |
| Filter | cap_small | Small Cap ($300M–$2B) |
| Filter | fa_div_o3 | Dividend Yield > 3% |
| Filter | fa_pe_u20 | P/E < 20 |
| Filter | geo_usa | USA |

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

# Theme-only screening (no --filters required)
python3 scripts/open_finviz_screener.py \
  --themes "artificialintelligence,cybersecurity" \
  --url-only

# Theme + sub-theme + filters combined
python3 scripts/open_finviz_screener.py \
  --themes "artificialintelligence" \
  --subthemes "aicloud,aicompute" \
  --filters "cap_midover" \
  --url-only
```

**Script arguments:**
- `--filters` (optional): Comma-separated filter codes. **Note:** `theme_*` and `subtheme_*` tokens are not allowed here — use `--themes` / `--subthemes` instead.
- `--themes` (optional): Comma-separated theme slugs (e.g., `artificialintelligence,cybersecurity`). Accepts bare slugs or `theme_`-prefixed values.
- `--subthemes` (optional): Comma-separated sub-theme slugs (e.g., `aicloud,aicompute`). Accepts bare slugs or `subtheme_`-prefixed values.
- `--elite`: Force Elite mode (auto-detected from `$FINVIZ_API_KEY` if not set)
- `--view`: View type — overview, valuation, financial, technical, ownership, performance, custom
- `--order`: Sort order (e.g., `-marketcap`, `dividendyield`, `-change`)
- `--url-only`: Print URL without opening browser

At least one of `--filters`, `--themes`, or `--subthemes` must be provided.

### Step 5: Report Results

After opening the screener, report:
1. The constructed URL
2. Elite or Public mode used
3. Summary of applied filters
4. Suggested next steps (e.g., "Sort by dividend yield", "Switch to Financial view for detailed ratios")

---

## Usage Recipes

Real-world screening patterns distilled from repeated use. Each recipe includes a starter filter set, recommended view, and tips for iterative refinement.

### Recipe 1: High-Dividend Growth Stocks (Kanchi-Style)

**Goal:** High yield + dividend growth + earnings growth, excluding yield traps.

```
--filters "fa_div_3to8,fa_sales5years_pos,fa_eps5years_pos,fa_divgrowth_5ypos,fa_payoutratio_u60,geo_usa"
--view financial
```

| Filter Code | Purpose |
|---|---|
| `fa_div_3to8` | Yield 3-8% (caps high-yield traps) |
| `fa_sales5years_pos` | Positive 5Y revenue growth |
| `fa_eps5years_pos` | Positive 5Y EPS growth |
| `fa_divgrowth_5ypos` | Positive 5Y dividend growth |
| `fa_payoutratio_u60` | Payout ratio < 60% (sustainability) |
| `geo_usa` | US-listed stocks |

**Iterative refinement:** Start broad with `fa_div_o3` → review results → add `fa_div_3to8` to cap yield → add `fa_payoutratio_u60` to exclude traps → switch to `financial` view for payout and growth columns.

### Recipe 2: Minervini Trend Template + VCP

**Goal:** Stocks in a Stage 2 uptrend with volatility contraction (VCP setup).

```
--filters "ta_sma50_pa,ta_sma200_pa,ta_sma200_sb50,ta_highlow52w_0to25-bhx,ta_perf_26wup,sh_avgvol_o300,cap_midover"
--view technical
```

| Filter Code | Purpose |
|---|---|
| `ta_sma50_pa` | Price above 50-day SMA |
| `ta_sma200_pa` | Price above 200-day SMA |
| `ta_sma200_sb50` | 200 SMA below 50 SMA (uptrend) |
| `ta_highlow52w_0to25-bhx` | Within 25% of 52W high |
| `ta_perf_26wup` | Positive 26-week performance |
| `sh_avgvol_o300` | Avg volume > 300K |
| `cap_midover` | Mid cap and above |

**VCP tightening filters (add to narrow):** `ta_volatility_wo3,ta_highlow20d_b0to5h,sh_relvol_u1` — low weekly volatility, near 20-day high, below-average relative volume (contraction signal).

### Recipe 3: Unfairly Sold-Off Growth Stocks

**Goal:** Fundamentally strong companies with recent sharp declines — potential mean reversion candidates.

```
--filters "fa_sales5years_o5,fa_eps5years_o10,fa_roe_o15,fa_salesqoq_pos,fa_epsqoq_pos,ta_perf_13wdown,ta_highlow52w_10to30-bhx,cap_large,sh_avgvol_o200"
--view overview
```

| Filter Code | Purpose |
|---|---|
| `fa_sales5years_o5` | 5Y sales growth > 5% |
| `fa_eps5years_o10` | 5Y EPS growth > 10% |
| `fa_roe_o15` | ROE > 15% |
| `fa_salesqoq_pos` | Positive QoQ sales growth |
| `fa_epsqoq_pos` | Positive QoQ EPS growth |
| `ta_perf_13wdown` | Negative 13-week performance |
| `ta_highlow52w_10to30-bhx` | 10-30% below 52W high |
| `cap_large` | Large cap |
| `sh_avgvol_o200` | Avg volume > 200K |

**After review:** Switch to `valuation` view to check P/E and P/S for entry attractiveness.

### Recipe 4: Turnaround Stocks

**Goal:** Companies with previously declining earnings now showing recovery — bottom-fishing with fundamental confirmation.

```
--filters "fa_eps5years_neg,fa_epsqoq_pos,fa_salesqoq_pos,ta_highlow52w_b30h,ta_perf_13wup,cap_smallover,sh_avgvol_o200"
--view performance
```

| Filter Code | Purpose |
|---|---|
| `fa_eps5years_neg` | Negative 5Y EPS growth (prior decline) |
| `fa_epsqoq_pos` | Positive QoQ EPS growth (recovery) |
| `fa_salesqoq_pos` | Positive QoQ sales growth (recovery) |
| `ta_highlow52w_b30h` | Within 30% of 52W high (not at bottom) |
| `ta_perf_13wup` | Positive 13-week performance |
| `cap_smallover` | Small cap and above |
| `sh_avgvol_o200` | Avg volume > 200K |

### Recipe 5: Momentum Trade Candidates

**Goal:** Short-term momentum leaders near 52W highs with increasing volume.

```
--filters "ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to3h,ta_perf_4wup,sh_relvol_o1.5,sh_avgvol_o1000,cap_midover"
--view technical
```

| Filter Code | Purpose |
|---|---|
| `ta_sma50_pa` | Price above 50-day SMA |
| `ta_sma200_pa` | Price above 200-day SMA |
| `ta_highlow52w_b0to3h` | Within 3% of 52W high |
| `ta_perf_4wup` | Positive 4-week performance |
| `sh_relvol_o1.5` | Relative volume > 1.5x |
| `sh_avgvol_o1000` | Avg volume > 1M |
| `cap_midover` | Mid cap and above |

### Recipe 6: Theme Screening (AI + Sub-theme Drill-Down)

**Goal:** Find mid-cap+ AI stocks focused on cloud infrastructure and compute acceleration.

```
--themes "artificialintelligence"
--subthemes "aicloud,aicompute"
--filters "cap_midover"
--view overview
```

| Type | Value | Purpose |
|---|---|---|
| Theme | `artificialintelligence` | AI theme universe |
| Sub-theme | `aicloud` | Cloud & Infrastructure vertical |
| Sub-theme | `aicompute` | Compute & Acceleration vertical |
| Filter | `cap_midover` | Mid cap and above |

**Multi-theme example:** `--themes "artificialintelligence,cybersecurity"` selects stocks tagged with either theme (OR logic via `|` grouping).

### Tips: Iterative Refinement Pattern

Screening works best as a dialogue, not a one-shot query:

1. **Start broad** — use 3-4 core filters to get an initial result set
2. **Review count** — if too many results (>100), add tightening filters; if too few (<5), relax constraints
3. **Switch views** — start with `overview` for a quick scan, then switch to `financial` or `valuation` for deeper inspection
4. **Layer in technicals** — after confirming fundamental quality, add `ta_` filters to time entries
5. **Save and iterate** — bookmark the URL, then adjust one filter at a time to understand its impact

---

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `screen_candidate` | `ScreenCandidate` | Screened stock with scoring rationale and action state |

Schema: `schemas/json/screen_candidate.json`

## Resources

- `references/finviz_screener_filters.md` — Complete filter code reference with natural language keywords (includes industry code examples; full 142-code list is in the Industry Codes section)
- `scripts/open_finviz_screener.py` — URL builder and Chrome opener
