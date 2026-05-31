---
layout: default
title: Getting Started
parent: English
nav_order: 1
lang_peer: /ja/getting-started/
permalink: /en/getting-started/
---

# Getting Started
{: .no_toc }

Installation instructions, API key setup, and a hands-on tutorial to run your first skill.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Prerequisites

| Item | Required | Description |
|------|----------|-------------|
| Claude Account | Yes | Pro, Team, or Enterprise plan (plans that support the Skills feature) |
| Python 3.9+ | Yes | Required for helper scripts. Most skills use Python-based data fetching |
| FMP API Key | Optional | Financial Modeling Prep API. Required by screening skills (free tier available) |
| FINVIZ Elite | Optional | Speeds up dividend screeners 70-80% and improves Theme Detector coverage |
| Alpaca Account | Optional | Required only for Portfolio Manager skill (free paper trading available) |

---

## Installation

### Claude Web App

1. Download the `.skill` file (ZIP format) for the skill you want from the [`skill-packages/`](https://github.com/tradermonty/claude-trading-skills/tree/main/skill-packages) directory.
2. Open Claude in your browser and navigate to **Settings > Skills**.
3. Upload the downloaded `.skill` file.
4. The skill activates automatically in new conversations.

> See Anthropic's [Skills launch post](https://www.anthropic.com/news/skills) for a feature overview.
{: .note }

### Claude Code (Desktop / CLI)

```bash
# 1. Clone the repository
git clone https://github.com/tradermonty/claude-trading-skills.git

# 2. Copy the desired skill folder to your Claude Code Skills directory
#    (Find the path via Claude Code -> Settings -> Skills -> Open Skills Folder)
cp -r claude-trading-skills/skills/finviz-screener /path/to/skills-directory/

# 3. Restart or reload Claude Code to detect the new skill
```

> `.skill` packages are built from source folders with tests and local build artifacts omitted. Edit a source folder to customize a skill, then run `python3 scripts/package_skills.py --skill <skill-name>` before distributing it via the web app.
{: .tip }

---

## API Key Setup

### Financial Modeling Prep (FMP)

The primary data API used by most screening skills for fundamentals, quotes, and historical prices.

| Plan | Cost | API Calls/Day | Best For |
|------|------|---------------|----------|
| Free | $0 | 250 | Occasional screening, small universes |
| Starter | $29.99/mo | 750 | Full CANSLIM screening (40 stocks) |
| Professional | $79.99/mo | 2,000 | Large-scale screening, multiple skills |

**Sign up:** [https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

```bash
# Set via environment variable (recommended)
export FMP_API_KEY=your_key_here

# Or pass as a command-line argument when running scripts
python3 scripts/screen_canslim.py --api-key YOUR_KEY
```

### FINVIZ Elite

Speeds up dividend screener execution (70-80% faster) and provides full industry coverage for Theme Detector.

| Plan | Cost | Notes |
|------|------|-------|
| Monthly | $39.50/mo | Real-time data, fast API access |
| Annual | $299.50/yr (~$24.96/mo) | Best value with annual discount |

**Sign up:** [https://elite.finviz.com/](https://elite.finviz.com/)

```bash
export FINVIZ_API_KEY=your_key_here
```

### Alpaca Trading

Required for the Portfolio Manager skill to fetch real-time holdings and execute trades.

| Plan | Cost | Notes |
|------|------|-------|
| Paper Trading | Free | Simulated environment, full API access |
| Live Trading | Free (no commissions) | Stocks and ETFs |

**Sign up:** [https://alpaca.markets/](https://alpaca.markets/)

```bash
export ALPACA_API_KEY="your_api_key_id"
export ALPACA_SECRET_KEY="your_secret_key"
export ALPACA_PAPER="true"  # set to "false" for live trading
```

---

## Your First Skill -- FinViz Screener

FinViz Screener is the easiest skill to try because it requires **no API key**. You describe screening criteria in natural language, and Claude builds a FinViz filter URL and opens the results in Chrome.

### Example Prompt

Tell Claude:

```
Find stocks with EPS growth > 25% and price above SMA200
```

### What Claude Does

1. **Parses** your natural language and maps it to FinViz filter codes:
   - `fa_epsqoq_o25` (Quarterly EPS growth > 25%)
   - `ta_sma200_pa` (Price above SMA200)
2. **Presents** the selected filters in a table for your confirmation.
3. **Builds** the URL and opens the FinViz screener results page in Chrome.

### Expected Output

- Chrome opens with the FinViz Screener results matching your criteria.
- Stocks are displayed in a sortable table.
- Switch between Overview, Valuation, Financial, and Technical views for deeper analysis.

> For advanced usage including Japanese input, programmatic mode, and 14+ pre-built recipes, see the [FinViz Screener Guide]({{ '/en/skills/finviz-screener/' | relative_url }}).
{: .tip }

---

## Troubleshooting

### Skill Not Loading

| Cause | Fix |
|-------|-----|
| `name` field in SKILL.md does not match the folder name | Verify that `name` in the YAML frontmatter exactly matches the skill folder name |
| Skill folder placed in the wrong directory | Confirm the folder is inside Claude Code's Skills directory |
| Claude Code not restarted | Restart Claude Code after adding a new skill |

### API Key Errors

```
ERROR: FMP API key not found. Set FMP_API_KEY environment variable or use --api-key argument.
```

**Fix:**
1. Verify the environment variable is set: `echo $FMP_API_KEY`
2. Add `export FMP_API_KEY=your_key` to your shell config (`.zshrc` or `.bashrc`) and reload it
3. As a fallback, pass the key directly with `--api-key YOUR_KEY`

### Python Dependency Errors

```
ModuleNotFoundError: No module named 'requests'
```

**Fix:**

```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

> Required dependencies vary by skill. Check the Prerequisites section in each skill's guide for specifics.
{: .note }

### FMP API Rate Limit

```
ERROR: 429 Too Many Requests - Rate limit exceeded
```

**Fix:**
1. The script automatically retries after 60 seconds.
2. If you hit the free tier limit (250 calls/day), it resets at midnight UTC.
3. Reduce the analysis scope with `--max-candidates` to lower API usage.
4. For frequent use, consider upgrading to FMP Starter ($29.99/mo, 750 calls/day).
