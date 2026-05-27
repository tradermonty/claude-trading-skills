---
layout: default
title: "Institutional Flow Tracker"
grand_parent: English
parent: Skill Guides
nav_order: 33
lang_peer: /ja/skills/institutional-flow-tracker/
permalink: /en/skills/institutional-flow-tracker/
---

# Institutional Flow Tracker
{: .no_toc }

Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. Analyzes hedge funds, mutual funds, and other institutional holders to identify stocks with significant smart money accumulation or distribution. Helps discover stocks before major moves by following where sophisticated investors are deploying capital.
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP Required</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/institutional-flow-tracker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/institutional-flow-tracker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

This skill tracks institutional investor activity through 13F SEC filings to identify "smart money" flows into and out of stocks. By analyzing quarterly changes in institutional ownership, you can discover stocks that sophisticated investors are accumulating before major price moves, or identify potential risks when institutions are reducing positions.

**Key Insight:** Institutional investors (hedge funds, pension funds, mutual funds) manage trillions of dollars and conduct extensive research. Their collective buying/selling patterns often precede significant price movements by 1-3 quarters.

---

## 2. When to Use

Use this skill when:
- Validating investment ideas (checking if smart money agrees with your thesis)
- Discovering new opportunities (finding stocks institutions are accumulating)
- Risk assessment (identifying stocks institutions are exiting)
- Portfolio monitoring (tracking institutional support for your holdings)
- Following specific investors (tracking Warren Buffett, Cathie Wood, etc.)
- Sector rotation analysis (identifying where institutions are rotating capital)

**Do NOT use when:**
- Seeking real-time intraday signals (13F data has 45-day reporting lag)
- Analyzing micro-cap stocks (<$100M market cap with limited institutional interest)
- Looking for short-term trading signals (<3 months horizon)

---

## 3. Prerequisites

- **FMP API Key:** Set `FMP_API_KEY` environment variable or pass `--api-key` to scripts
- **Python 3.8+:** Required for running analysis scripts
- **Dependencies:** `pip install requests` (scripts handle missing dependencies gracefully)

---

## 4. Quick Start

```bash
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

---

## 5. Workflow

### Step 1: Identify Stocks with Significant Institutional Changes

Execute the main screening script to find stocks with notable institutional activity:

**Quick scan (top 50 stocks by institutional change):**
```bash
python3 scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

**Sector-focused scan:**
```bash
python3 scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

**Custom screening:**
```bash
python3 scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_flow_results.json
```

**Output includes:**
- Stock ticker and company name
- Current institutional ownership % (of shares outstanding)
- Quarter-over-quarter change in shares held
- Number of institutions holding
- Change in number of institutions (new buyers vs sellers)
- Top institutional holders

### Step 2: Deep Dive on Specific Stocks

For detailed analysis of a specific stock's institutional ownership:

```bash
python3 scripts/analyze_single_stock.py AAPL
```

**This generates:**
- Historical institutional ownership trend (8 quarters)
- List of all institutional holders with position changes
- Concentration analysis (top 10 holders' % of total institutional ownership)
- New positions vs increased vs decreased positions
- Data quality assessment with reliability grade

**Key metrics to evaluate:**
- **Ownership %:** Higher institutional ownership (>70%) = more stability but limited upside
- **Ownership Trend:** Rising ownership = bullish, falling = bearish
- **Concentration:** High concentration (top 10 > 50%) = risk if they sell
- **Quality of Holders:** Presence of quality long-term investors (Berkshire, Fidelity) vs momentum funds

### Step 3: Track Specific Institutional Investors

> **Note:** `track_institution_portfolio.py` is **not yet implemented**. FMP API organizes
> institutional holder data by stock (not by institution), making full portfolio reconstruction
> impractical via this API alone.

**Alternative approach — use `analyze_single_stock.py` to check if a specific institution holds a stock:**
```bash
# Analyze a stock and look for a specific institution in the output
python3 institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
# Then search the report for "Berkshire" or "ARK" in the Top 20 holders table
```

**For full institution-level portfolio tracking, use these external resources:**
1. **WhaleWisdom:** https://whalewisdom.com (free tier available, 13F portfolio viewer)
2. **SEC EDGAR:** https://www.sec.gov/cgi-bin/browse-edgar (official 13F filings)
3. **DataRoma:** https://www.dataroma.com (superinvestor portfolio tracker)

### Step 4: Interpretation and Action

Read the references for interpretation guidance:
- `references/13f_filings_guide.md` - Understanding 13F data and limitations
- `references/institutional_investor_types.md` - Different investor types and their strategies
- `references/interpretation_framework.md` - How to interpret institutional flow signals

**Signal Strength Framework:**

**Strong Bullish (Consider buying):**
- Institutional ownership increasing >15% QoQ
- Number of institutions increasing >10%
- Quality long-term investors adding positions
- Low current ownership (<40%) with room to grow
- Accumulation happening across multiple quarters

**Moderate Bullish:**
- Institutional ownership increasing 5-15% QoQ
- Mix of new buyers and sellers, net positive
- Current ownership 40-70%

**Neutral:**
- Minimal change in ownership (<5%)
- Similar number of buyers and sellers
- Stable institutional base

**Moderate Bearish:**
- Institutional ownership decreasing 5-15% QoQ
- More sellers than buyers
- High ownership (>80%) limiting new buyers

**Strong Bearish (Consider selling/avoiding):**
- Institutional ownership decreasing >15% QoQ
- Number of institutions decreasing >10%
- Quality investors exiting positions
- Distribution happening across multiple quarters
- Concentration risk (top holder selling large position)

### Step 5: Portfolio Application

**For new positions:**
1. Run institutional analysis on your stock idea
2. Look for confirmation (institutions also accumulating)
3. If strong bearish signals, reconsider or reduce position size
4. If strong bullish signals, gain confidence in thesis

**For existing holdings:**
1. Quarterly review after 13F filing deadlines
2. Monitor for distribution (early warning system)
3. If institutions are exiting, re-evaluate your thesis
4. Consider trimming if widespread institutional selling

**Screening workflow integration:**
1. Use Value Dividend Screener or other screeners to find candidates
2. Run Institutional Flow Tracker on top candidates
3. Prioritize stocks with institutional accumulation
4. Avoid stocks with institutional distribution

---

## 6. Resources

**References:**

- `skills/institutional-flow-tracker/references/13f_filings_guide.md`
- `skills/institutional-flow-tracker/references/institutional_investor_types.md`
- `skills/institutional-flow-tracker/references/interpretation_framework.md`

**Scripts:**

- `skills/institutional-flow-tracker/scripts/analyze_single_stock.py`
- `skills/institutional-flow-tracker/scripts/data_quality.py`
- `skills/institutional-flow-tracker/scripts/track_institution_portfolio.py`
- `skills/institutional-flow-tracker/scripts/track_institutional_flow.py`
