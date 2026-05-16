# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository contains Claude Skills for equity investors and traders. Each skill packages domain-specific prompts, knowledge bases, and helper scripts to assist with market analysis, technical charting, economic calendar monitoring, and trading strategy development. Skills are designed to work in both Claude's web app and Claude Code environments.

⚠️ **Important:** Some skills require paid API subscriptions (FMP API and/or FINVIZ Elite) to function. See the [API Key Management](#api-key-management) section for detailed requirements by skill.

## Repository Architecture

### Skill Structure

Each skill follows a standardized directory structure:

```
<skill-name>/
├── SKILL.md              # Required: Skill definition with YAML frontmatter
├── references/           # Knowledge bases loaded into Claude's context
├── scripts/             # Executable Python scripts (not auto-loaded)
└── assets/              # Templates and resources for output generation
```

**SKILL.md Format:**
- YAML frontmatter with `name` and `description` fields
- `name` must match the directory name for proper skill detection
- Description defines when the skill should be triggered
- Body contains workflow instructions written in imperative/infinitive form
- All instructions assume Claude will execute them, not the user

**Progressive Loading:**
1. Metadata (YAML frontmatter) loads first for skill detection
2. SKILL.md body loads when skill is invoked
3. References load conditionally based on analysis needs
4. Scripts execute on demand, never auto-loaded into context

### Key Design Patterns

**Knowledge Base Organization:**
- `references/` contains markdown files with domain knowledge (sector rotation patterns, technical analysis frameworks, news source credibility guides)
- Knowledge bases provide context without requiring Claude to have specialized training
- References are read selectively during skill execution to minimize token usage

**Script vs. Reference Division:**
- Scripts (`scripts/`) are executable code for API calls, data fetching, report generation
- References (`references/`) are documentation for Claude to read and apply
- Scripts handle I/O; references handle knowledge

**Output Generation:**
- Skills generate reports (markdown + JSON) saved to `reports/` directory
- Filename convention: `<skill>_<analysis-type>_<date>.md` (and `.json`)
- Reports use structured templates from `assets/` directories
- Scripts should default `--output-dir` to `reports/` (or pass `--output-dir reports/` when invoking)

## Common Development Tasks

### Creating a New Skill

Use the skill-creator plugin (available in Claude Code):

```bash
# This invokes the skill-creator to guide you through setup
# Follow the 6-step process: Understanding → Planning → Initializing → Editing → Packaging → Iterating
```

The skill-creator will:
1. Ask clarification questions about the skill's purpose
2. Create the directory structure
3. Generate SKILL.md template
4. Set up references and scripts directories
5. Package the skill into a .skill file

**MANDATORY: After creating or committing a new skill, complete ALL of the following:**

1. **Generate documentation pages** (auto-gen handles EN page + JA stub + index updates):
   ```bash
   python3 scripts/generate_skill_docs.py --skill <skill-name>
   ```
2. **Add to catalog category sections** in `docs/en/skill-catalog.md` and `docs/ja/skill-catalog.md`
3. **Add to API Requirements Matrix** in both catalog files
4. **Add to README** descriptions in `README.md` (English) and `README.ja.md` (Japanese)
5. If the skill requires API keys, add to the API Requirements table in `README.md` and the API要件 section in `README.ja.md`
6. If a new category is needed, create it in both READMEs and both catalogs

> **Pre-commit enforcement:** The `docs-completeness` hook blocks commits if any `skills/*/SKILL.md` exists without corresponding `docs/en/skills/<name>.md` and `docs/ja/skills/<name>.md`. Run the generate command above to fix.

### Creating Documentation Site Pages

Generate documentation pages for the Jekyll site at `docs/`.

**Auto-generation (recommended for most skills):**

```bash
# Generate 6-section EN page + JA stub for a specific skill
# Also updates docs/en/skills/index.md and docs/ja/skills/index.md automatically
python3 scripts/generate_skill_docs.py --skill <skill-name>

# Regenerate all auto-generated pages
python3 scripts/generate_skill_docs.py --overwrite
```

**Hand-written ★ guides (for key skills):**

For skills that need detailed documentation with examples, troubleshooting, and CLI reference, create a 10-section guide manually. See `docs/README.md` for the full template and conventions.

Required sections for ★ guides:
1. Overview  2. Prerequisites  3. Quick Start  4. How It Works
5. Usage Examples  6. Understanding the Output  7. Tips & Best Practices
8. Combining with Other Skills  9. Troubleshooting  10. Reference

**What auto-generation handles vs. what requires manual work:**

| Task | Auto-gen | Manual |
|------|----------|--------|
| EN doc page (`docs/en/skills/<name>.md`) | ✅ | -- |
| JA doc stub (`docs/ja/skills/<name>.md`) | ✅ | -- |
| Index table (`docs/{en,ja}/skills/index.md`) | ✅ | -- |
| Catalog category section (`docs/{en,ja}/skill-catalog.md`) | -- | ✅ |
| Catalog API Requirements Matrix | -- | ✅ |
| README.md / README.ja.md | -- | ✅ |

See `docs/README.md` for frontmatter format, badge syntax, and complete checklist.

### Packaging Skills for Distribution

Skills are packaged as ZIP files for Claude web app users:

```bash
# Use the skill-creator's packaging script
python3 ~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/skill-creator/scripts/package_skill.py <skill-name>
```

The packaged .skill files are stored in `skill-packages/` and should be regenerated after any skill modifications.

### Testing Skills

Skills are tested by invoking them in Claude Code conversations:

1. Copy skill folder to Claude Code Skills directory
2. Restart Claude Code to detect the skill
3. Trigger the skill by providing input that matches the skill's description
4. Verify that:
   - Skill loads correctly (check YAML frontmatter)
   - References load when needed
   - Scripts execute with proper error handling
   - Output matches expected format

### Code Generation (TDD)

When generating or modifying code in this repository, use a TDD-first workflow:

1. Write or update tests first (expected to fail initially).
2. Implement the minimal code change needed to pass tests.
3. Refactor while keeping tests green.
4. Run the relevant test suite before finishing.

If no test exists for the changed behavior, add one whenever practical.

### Pre-commit Hooks

This repository uses [pre-commit](https://pre-commit.com/) for automated quality checks. Install after cloning:

```bash
pre-commit install && pre-commit install --hook-type pre-push
```

**Pre-commit hooks (run on every commit):**

| Hook | Source | What it checks |
|------|--------|----------------|
| trailing-whitespace | pre-commit-hooks | Trailing whitespace |
| end-of-file-fixer | pre-commit-hooks | Missing newline at end of file |
| check-yaml | pre-commit-hooks | YAML syntax |
| check-toml | pre-commit-hooks | TOML syntax |
| check-merge-conflict | pre-commit-hooks | Leftover conflict markers |
| check-added-large-files | pre-commit-hooks | Files exceeding 500KB |
| ruff | ruff-pre-commit | Python lint + auto-fix |
| ruff-format | ruff-pre-commit | Python formatting |
| codespell | codespell | Typo detection |
| detect-secrets | detect-secrets | Secret/credential leaks |
| no-absolute-paths | local | `/Users/username/` path leaks in public repo |
| skill-frontmatter | local | SKILL.md `name` matches directory, `description` exists |
| docs-completeness | local | Every `skills/*/SKILL.md` has EN + JA doc pages |

**Pre-push hook:**

| Hook | What it checks |
|------|----------------|
| pytest-pre-push | Runs all skill-level tests via `scripts/run_all_tests.sh` |

**Suppressing false positives:**
- `no-absolute-paths`: Add `# noqa: absolute-path` inline comment, or the hook auto-skips regex definitions and test files
- Config: `.pre-commit-config.yaml`
- Local hook scripts: `scripts/hooks/`

### API Key Management

⚠️ **IMPORTANT:** Several skills require paid API subscriptions to function. Review the requirements below before using these skills.

#### API Requirements by Skill

The table below is **auto-generated** from `skills-index.yaml` by `scripts/generate_catalog_from_index.py`. To update a row, edit the skill's `integrations[]` in the index and re-run the generator. The 3-column shape (FMP / FINVIZ / Alpaca) is preserved so existing setup instructions still apply; non-paid integrations (CSV, image, WebSearch, MCP, calculation-only, etc.) surface in the Notes column.

<!-- skills-index:start name="api-matrix" -->
<!-- This table is auto-generated from skills-index.yaml by scripts/generate_catalog_from_index.py. Do not edit by hand — edit the index and re-run the generator. -->

| Skill | FMP API | FINVIZ Elite | Alpaca | Notes |
|-------|---------|--------------|--------|-------|
| **Backtest Expert** | ❌ Not used | ❌ Not used | ❌ Not used | User provides strategy parameters |
| **Breadth Chart Analyst** | ❌ Not used | ❌ Not used | ❌ Not used | Chart screenshot input |
| **Breakout Trade Planner** | ❌ Not used | ❌ Not used | ❌ Not used | Consumes VCP screener output; pure calculation + Alpaca order templates |
| **CANSLIM Screener** | ✅ Required | ❌ Not used | ❌ Not used | US stock fundamentals via FMP |
| **Data Quality Checker** | ❌ Not used | ❌ Not used | ❌ Not used | Local markdown validation; works offline |
| **Dividend Growth Pullback Screener** | ✅ Required | 🟡 Optional (Recommended) | ❌ Not used | Financial Modeling Prep API |
| **Downtrend Duration Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Duration analysis from market data; pure calculation |
| **Dual Axis Skill Reviewer** | ❌ Not used | ❌ Not used | ❌ Not used | Deterministic scoring + optional LLM review |
| **Earnings Calendar** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Earnings Trade Analyzer** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Economic Calendar Fetcher** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Edge Candidate Agent** | 🟡 Optional | ❌ Not used | ❌ Not used | Optional OHLCV via FMP for edge ticket export |
| **Edge Concept Synthesizer** | ❌ Not used | ❌ Not used | ❌ Not used | Synthesizes detector tickets and hints into edge concepts |
| **Edge Hint Extractor** | ❌ Not used | ❌ Not used | ❌ Not used | Extracts hints from observations/news; pure calculation |
| **Edge Pipeline Orchestrator** | ❌ Not used | ❌ Not used | ❌ Not used | Orchestrates edge pipeline subskills via subprocess |
| **Edge Signal Aggregator** | ❌ Not used | ❌ Not used | ❌ Not used | Aggregates signals from edge-finding skills |
| **Edge Strategy Designer** | ❌ Not used | ❌ Not used | ❌ Not used | Converts edge concepts into strategy drafts |
| **Edge Strategy Reviewer** | ❌ Not used | ❌ Not used | ❌ Not used | Deterministic scoring on local YAML drafts |
| **Exposure Coach** | ❌ Not used | ❌ Not used | ❌ Not used | Synthesizes signals from other skills; pure calculation |
| **FTD Detector** | ✅ Required | ❌ Not used | ❌ Not used | Daily QQQ/SPY OHLCV via FMP |
| **Finviz Screener** | ❌ Not used | 🟡 Optional | ❌ Not used | FINVIZ Elite API |
| **IBD Distribution Day Monitor** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Institutional Flow Tracker** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Kanchi Dividend Review Monitor** | 🟡 Optional (Recommended) | ❌ Not used | ❌ Not used | Dividend / price monitoring via FMP |
| **Kanchi Dividend SOP** | 🟡 Optional (Recommended) | ❌ Not used | ❌ Not used | US dividend stock data via FMP |
| **Kanchi Dividend US Tax Accounting** | ❌ Not used | ❌ Not used | ❌ Not used | US tax workflow guidance; pure calculation |
| **Macro Regime Detector** | ❌ Not used | ❌ Not used | ❌ Not used | Cross-asset ratio data via yfinance or local CSV |
| **Market Breadth Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | TraderMonty public CSV; no API key required |
| **Market Environment Analysis** | ❌ Not used | ❌ Not used | ❌ Not used | Global market data via WebSearch / WebFetch; Optional chart image inputs for technical interpretation |
| **Market News Analyst** | ❌ Not used | ❌ Not used | ❌ Not used | Web search / fetch |
| **Market Top Detector** | ❌ Not used | ❌ Not used | ❌ Not used | Public market data CSVs; no API key required |
| **Options Strategy Advisor** | 🟡 Optional | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **PEAD Screener** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Pair Trade Screener** | ✅ Required | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Parabolic Short Trade Planner** | ✅ Required | ❌ Not used | 🟡 Optional | Financial Modeling Prep API |
| **Portfolio Manager** | ❌ Not used | ❌ Not used | ✅ Required | Alpaca brokerage MCP/API |
| **Position Sizer** | ❌ Not used | ❌ Not used | ❌ Not used | Pure calculation; works offline |
| **Scenario Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Headline / news search via WebSearch |
| **Sector Analyst** | ❌ Not used | ❌ Not used | ❌ Not used | Chart screenshot input |
| **Signal Postmortem** | ❌ Not used | ❌ Not used | ❌ Not used | Postmortem framework; pure calculation |
| **Skill Designer** | ❌ Not used | ❌ Not used | ❌ Not used | Generates skill scaffolding from idea specs |
| **Skill Idea Miner** | ❌ Not used | ❌ Not used | ❌ Not used | Mines session logs for skill ideas |
| **Skill Integration Tester** | ❌ Not used | ❌ Not used | ❌ Not used | Validates multi-skill workflow contracts |
| **Stanley Druckenmiller Investment** | ❌ Not used | ❌ Not used | ❌ Not used | Synthesizes outputs from upstream skills; pure calculation |
| **Strategy Pivot Designer** | ❌ Not used | ❌ Not used | ❌ Not used | Pivot proposal generator; pure calculation |
| **Technical Analyst** | ❌ Not used | ❌ Not used | ❌ Not used | Chart screenshot input |
| **Theme Detector** | 🟡 Optional | 🟡 Optional (Recommended) | ❌ Not used | Financial Modeling Prep API |
| **Trade Hypothesis Ideator** | ❌ Not used | ❌ Not used | ❌ Not used | Hypothesis generation from journal/data inputs; pure calculation |
| **Trader Memory Core** | 🟡 Optional | ❌ Not used | ❌ Not used | Financial Modeling Prep API |
| **Trading Skills Navigator** | ❌ Not used | ❌ Not used | ❌ Not used | Reads local skills-index.yaml + workflows/*.yaml (or bundled snapshot); no network |
| **US Market Bubble Detector** | ❌ Not used | ❌ Not used | ❌ Not used | User provides indicators |
| **US Stock Analysis** | ❌ Not used | ❌ Not used | ❌ Not used | User provides data |
| **Uptrend Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Monty Uptrend Ratio Dashboard CSV; no API key required |
| **VCP Screener** | ✅ Required | ❌ Not used | ❌ Not used | S&P 500 OHLCV via FMP |
| **Value Dividend Screener** | ✅ Required | 🟡 Optional (Recommended) | ❌ Not used | Financial Modeling Prep API |
<!-- skills-index:end name="api-matrix" -->

> Note: a skill listed as `❌ Not used` for FMP / FINVIZ / Alpaca may still need WebSearch, public CSVs, chart screenshots, or other non-paid inputs. See each skill's full `integrations[]` entry in `skills-index.yaml` for the complete picture.

#### API Key Setup

**Financial Modeling Prep (FMP) API:**
```bash
# Set environment variable (preferred method)
export FMP_API_KEY=your_key_here

# Or provide via command-line argument when script runs
python3 scripts/get_economic_calendar.py --api-key YOUR_KEY
```

**FINVIZ Elite API:**
```bash
# Set environment variable
export FINVIZ_API_KEY=your_key_here

# Or provide via command-line argument
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --finviz-api-key YOUR_KEY
```

**Alpaca Trading API:**
```bash
# Set environment variables
export ALPACA_API_KEY="your_api_key_id"
export ALPACA_SECRET_KEY="your_secret_key"
export ALPACA_PAPER="true"  # or "false" for live trading

# Configure Alpaca MCP Server in Claude Code settings
# See portfolio-manager/references/alpaca-mcp-setup.md for detailed setup guide
```

#### API Pricing and Access

**Financial Modeling Prep (FMP):**
- **Free Tier:** 250 API calls/day (sufficient for occasional use)
- **Starter Tier:** $29.99/month - 750 calls/day
- **Professional Tier:** $79.99/month - 2,000 calls/day
- **Sign up:** https://site.financialmodelingprep.com/developer/docs

**FINVIZ Elite:**
- **Elite Subscription:** $39.50/month or $299.50/year (~$24.96/month)
- Provides advanced screeners, real-time data, and API access
- **Sign up:** https://elite.finviz.com/
- **Note:** FINVIZ Elite is optional for dividend screeners but reduces execution time from 10-15 minutes to 2-3 minutes

**Alpaca Trading:**
- **Paper Trading:** Free (simulated money, full API access)
- **Live Trading:** Free brokerage account, no commissions on stocks/ETFs
- **Sign up:** https://alpaca.markets/
- **Required for:** Portfolio Manager skill
- **Note:** Paper trading account recommended for testing MCP integration

**Recommendations by Use Case:**
- **Dividend Screening:** FMP free tier + FINVIZ Elite ($330/year) for optimal performance
- **Budget Dividend Screening:** FMP free tier only (slower execution)
- **Portfolio Management:** Alpaca paper account (free) for practice, live account for production
- **Options Education:** FMP free tier sufficient; Options Strategy Advisor works with theoretical pricing alone

#### API Script Pattern

All API scripts follow this pattern:
1. Check for environment variable first
2. Fall back to command-line argument
3. Provide clear error messages if key missing
4. Support both methods for CLI, Desktop, and Web environments
5. Handle rate limits gracefully with retry logic

### Running Helper Scripts

**Economic Calendar Fetcher:** ⚠️ Requires FMP API key
```bash
# Default: next 7 days
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# Specific date range (max 90 days)
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-11-01 --to 2025-11-30 \
  --api-key YOUR_KEY \
  --format json
```

**Earnings Calendar:** ⚠️ Requires FMP API key
```bash
# Default: next 7 days, market cap > $2B
python3 earnings-calendar/scripts/fetch_earnings_fmp.py --api-key YOUR_KEY

# Custom date range
python3 earnings-calendar/scripts/fetch_earnings_fmp.py \
  --from 2025-11-01 --to 2025-11-07 \
  --api-key YOUR_KEY
```

**Value Dividend Screener:** ⚠️ Requires FMP API key; FINVIZ Elite optional but recommended
```bash
# Two-stage screening (RECOMMENDED - 70-80% faster)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py --use-finviz

# FMP-only screening (no FINVIZ required)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py

# Custom parameters
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --top 50 \
  --output custom_results.json
```

**Dividend Growth Pullback Screener:** ⚠️ Requires FMP API key; FINVIZ Elite optional but recommended
```bash
# Two-stage screening with RSI filter (RECOMMENDED)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --use-finviz

# FMP-only screening (limited to ~40 stocks due to API limits)
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --max-candidates 40

# Custom RSI threshold and dividend growth requirements
python3 dividend-growth-pullback-screener/scripts/screen_dividend_growth.py \
  --use-finviz \
  --rsi-threshold 35 \
  --min-div-growth 15
```

**Pair Trade Screener:** ⚠️ Requires FMP API key
```bash
# Screen for pairs in specific sector
python3 pair-trade-screener/scripts/find_pairs.py --sector Technology

# Analyze specific pair
python3 pair-trade-screener/scripts/analyze_spread.py AAPL MSFT

# Custom cointegration parameters
python3 pair-trade-screener/scripts/find_pairs.py \
  --sector Financials \
  --min-correlation 0.7 \
  --lookback-days 365
```

**Earnings Trade Analyzer:** ⚠️ Requires FMP API key
```bash
# Default: 2-day lookback, top 20 results
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --output-dir reports/

# Custom parameters with entry quality filter
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --lookback-days 3 --top 10 --max-api-calls 200 \
  --apply-entry-filter --output-dir reports/
```

**PEAD Screener:** ⚠️ Requires FMP API key
```bash
# Mode A: FMP earnings calendar (standalone)
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --min-gap 3.0 --max-api-calls 200 \
  --output-dir reports/

# Mode B: Pipeline from earnings-trade-analyzer output
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_*.json \
  --min-grade B --output-dir reports/
```

**Options Strategy Advisor:** 🟡 FMP API optional
```bash
# Calculate Black-Scholes price and Greeks
python3 options-strategy-advisor/scripts/black_scholes.py \
  --ticker AAPL \
  --strike 150 \
  --days-to-expiry 30 \
  --option-type call

# Analyze covered call strategy
python3 options-strategy-advisor/scripts/black_scholes.py \
  --ticker AAPL \
  --strategy covered_call \
  --stock-price 155
```

**Theme Detector:** 🟡 FINVIZ Elite optional; FMP optional
```bash
# Static mode (no API keys required)
python3 skills/theme-detector/scripts/theme_detector.py --output-dir reports/

# Dynamic stock selection (uses FINVIZ Public screener, no key needed)
python3 skills/theme-detector/scripts/theme_detector.py \
  --dynamic-stocks --output-dir reports/

# With FINVIZ Elite (faster, more reliable)
python3 skills/theme-detector/scripts/theme_detector.py \
  --dynamic-stocks --finviz-api-key $FINVIZ_API_KEY --output-dir reports/
```

**Portfolio Manager:** ⚠️ Requires Alpaca MCP Server
```bash
# Test Alpaca connection
python3 skills/portfolio-manager/scripts/check_alpaca_connection.py

# Portfolio analysis is done via Claude with Alpaca MCP tools
# See portfolio-manager/references/alpaca-mcp-setup.md for setup
```

**Position Sizer:** No API key required
```bash
# Basic: stop-loss based sizing
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --stop 148.50 \
  --account-size 100000 --risk-pct 1.0

# ATR-based sizing
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --atr 3.20 --atr-multiplier 2.0 \
  --account-size 100000 --risk-pct 1.0

# Kelly Criterion (budget mode: no --entry)
python3 skills/position-sizer/scripts/position_sizer.py \
  --win-rate 0.55 --avg-win 2.5 --avg-loss 1.0 \
  --account-size 100000

# With portfolio constraints
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --stop 148.50 \
  --account-size 100000 --risk-pct 1.0 \
  --max-position-pct 10 --max-sector-pct 30 \
  --sector Technology --current-sector-exposure 22
```

**Data Quality Checker:** No API key required
```bash
# Check a markdown file
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file reports/weekly_strategy.md

# Run specific checks only
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --checks price_scale,dates,allocations

# With reference date for year inference
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --as-of 2026-02-28 --output-dir reports/
```

**Edge Strategy Reviewer:** No API key required
```bash
# Review all drafts in a directory
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/

# Single draft review with JSON output and markdown summary
python3 skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py \
  --draft reports/edge_strategy_drafts/draft_xxx.yaml \
  --output-dir reports/ --format json --markdown-summary
```

**Edge Pipeline Orchestrator:** No API key required
```bash
# Full pipeline from tickets
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --market-summary /path/to/market_summary.json \
  --anomalies /path/to/anomalies.json \
  --output-dir reports/edge_pipeline/

# Review-only mode with existing drafts
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --review-only \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/edge_pipeline/

# Dry-run (no export)
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --output-dir reports/edge_pipeline/ --dry-run
```

**Trader Memory Core:** 🟡 FMP API optional (for MAE/MFE only)
```bash
# Register screener output as thesis
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# Manual brokerage entry (fractional shares; free-form JSON, single or array)
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source manual --input amd.json --state-dir state/theses/

# Walk an existing broker position to ACTIVE (backdated, fractional shares)
python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
  transition <id> ENTRY_READY --reason "existing position" --event-date 2026-05-02
python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
  open-position <id> --actual-price 142.10 --actual-date 2026-05-02 \
  --shares 7.86 --event-date 2026-05-02
# Partial close (trim): ACTIVE/PARTIALLY_CLOSED → PARTIALLY_CLOSED, or → CLOSED
# when the whole remainder is sold. Cumulative realized P&L in outcome.
python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
  trim <id> --shares-sold 4 --price 120.00 --date 2026-05-10
# close / terminate / attach-position are also CLI subcommands
# (close accepts ACTIVE or PARTIALLY_CLOSED)
python3 skills/trader-memory-core/scripts/thesis_store.py --state-dir state/theses/ \
  close <id> --exit-reason target_hit --actual-price 165.00 --actual-date 2026-06-01

# Query theses
python3 skills/trader-memory-core/scripts/thesis_store.py \
  --state-dir state/theses/ list --ticker AAPL --status ACTIVE

# Check review schedule
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ review-due --as-of 2026-04-15

# Generate postmortem
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1

# Summary statistics
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ summary
```

### Skill Self-Improvement Loop

An automated pipeline reviews and improves skill quality on a daily cadence.

**Architecture:**
- `scripts/run_skill_improvement_loop.py` — orchestrator (round-robin selection, auto scoring, Claude CLI improvement, quality gate, PR creation)
- `skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py` — scoring engine (5-category deterministic auto axis, optional LLM axis)
- `scripts/run_skill_improvement.sh` — thin shell wrapper for launchd
- `launchd/com.trade-analysis.skill-improvement.plist` — macOS launchd agent (daily 05:00)

**Key design decisions:**
- Improvement trigger uses `auto_review.score` (deterministic) instead of `final_review.score` (LLM-influenced) for reproducibility
- Quality gate re-scores after improvement with tests enabled; rolls back if score didn't improve
- PID-based lock file with stale detection prevents concurrent runs
- Git safety checks (clean tree, main branch, `git pull --ff-only`) before any operations
- `knowledge_only` skills (no scripts, references only) get adjusted scoring to avoid unfair penalties

**Running manually:**
```bash
# Dry-run: score one skill without improvements or PRs
python3 scripts/run_skill_improvement_loop.py --dry-run

# Dry-run all skills
python3 scripts/run_skill_improvement_loop.py --dry-run --all

# Full run
python3 scripts/run_skill_improvement_loop.py
```

**Running the reviewer standalone:**
```bash
# Score a random skill
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --output-dir reports/

# Score a specific skill
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --skill backtest-expert --output-dir reports/

# Score all skills
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --all --output-dir reports/
```

**State and output files:**
- `logs/.skill_improvement_state.json` — round-robin state and 60-entry history
- `logs/skill_improvement.log` — execution log (30-day rotation)
- `reports/skill-improvement-log/YYYY-MM-DD_summary.md` — daily summary

**Tests:**
```bash
# Reviewer tests (21 tests)
python3 -m pytest skills/dual-axis-skill-reviewer/scripts/tests/ -v

# Orchestrator tests (20 tests)
python3 -m pytest scripts/tests/test_skill_improvement_loop.py -v
```

### Skill Auto-Generation Pipeline

An automated pipeline that mines session logs for skill ideas (weekly) and designs, reviews, and creates new skills as PRs (daily).

**Architecture:**
- `scripts/run_skill_generation_pipeline.py` — orchestrator (weekly: mine+score, daily: design+review+PR)
- `skills/skill-idea-miner/` — mining and scoring scripts
- `skills/skill-designer/` — design prompt builder with quality references
- `skills/dual-axis-skill-reviewer/` — scoring engine (reused from improvement loop)
- `scripts/run_skill_generation.sh` — thin shell wrapper for launchd
- `launchd/com.trade-analysis.skill-generation-weekly.plist` — weekly mining (Saturday 06:00)
- `launchd/com.trade-analysis.skill-generation-daily.plist` — daily generation (07:00)

**Key design decisions:**
- Weekly mode mines session logs and scores ideas into `logs/.skill_generation_backlog.yaml`
- Daily mode picks the highest-scoring eligible idea and generates a complete skill
- `select_next_idea()` prioritizes pending ideas by composite score; retries `design_failed`/`pr_failed` once
- `review_failed` is terminal (no retry) since it indicates content quality issues
- Runtime dedup checks `skills/<name>/SKILL.md` existence before processing
- `_check_unexpected_changes()` detects modifications outside `skills/<name>/` and `reports/`; preserves branch for manual inspection
- Atomic backlog updates via `tempfile` + `os.replace()`
- `created_branch` flag prevents spurious `git checkout main` in finally block

**Running manually:**
```bash
# Weekly: mine ideas from session logs and score them
python3 scripts/run_skill_generation_pipeline.py --mode weekly --dry-run

# Daily: design a skill from the highest-scoring backlog idea
python3 scripts/run_skill_generation_pipeline.py --mode daily --dry-run

# Full daily run (creates branch, designs skill, opens PR)
python3 scripts/run_skill_generation_pipeline.py --mode daily
```

**State and output files:**
- `logs/.skill_generation_state.json` — run history (60-entry limit)
- `logs/.skill_generation_backlog.yaml` — scored ideas with status tracking
- `logs/skill_generation.log` — execution log (30-day rotation)
- `reports/skill-generation-log/YYYY-MM-DD_daily.md` — daily generation summary

**Tests:**
```bash
# Pipeline tests (42 tests)
python3 -m pytest scripts/tests/test_skill_generation_pipeline.py -v

# Skill designer tests (3 tests)
python3 -m pytest skills/skill-designer/scripts/tests/ -v
```

## Skill Interaction Patterns

### Chart Analysis Skills (Sector Analyst, Breadth Chart Analyst, Technical Analyst)

These skills expect image inputs:
- User provides chart screenshots
- Skill analyzes visual patterns
- Output includes scenario-based probability assessments
- Analysis follows specific frameworks documented in `references/`

**Workflow:**
1. User uploads chart image
2. Skill loads relevant reference framework
3. Analysis generates structured markdown report
4. Report saved to `reports/` directory

### News Analysis Skills (Market News Analyst)

This skill uses automated data collection:
- Executes WebSearch/WebFetch queries to gather news
- Focuses on past 10 days of market-moving events
- Applies impact scoring framework: (Price Impact × Breadth) × Forward Significance
- Ranks events by quantitative score

**Key References:**
- `trusted_news_sources.md`: Source credibility tiers
- `market_event_patterns.md`: Historical reaction patterns
- `geopolitical_commodity_correlations.md`: Event-commodity relationships

### Calendar Skills (Economic Calendar Fetcher, Earnings Calendar)

⚠️ **API Requirement:** These skills require FMP API key to function.

These skills fetch future events via FMP API:
- Execute Python scripts to call FMP API endpoints
- Parse JSON responses
- Generate chronological markdown reports
- Include impact assessment (High/Medium/Low)
- Free tier (250 calls/day) is sufficient for most users

**Output Pattern:**
```markdown
# Economic Calendar
**Period:** YYYY-MM-DD to YYYY-MM-DD
**High Impact Events:** X

## YYYY-MM-DD - Day of Week
### Event Name (Impact Level)
- Country: XX (Currency)
- Time: HH:MM UTC
- Previous: Value
- Estimate: Value
**Market Implications:** Analysis...
```

## Multi-Skill Workflows

> **Canonical source:** `workflows/*.yaml` is the authoritative definition of multi-skill workflows for the Core + Satellite primary user. The prose examples below are quickstart sketches only — if any block here disagrees with a manifest in `workflows/`, the YAML is correct. See [`workflows/README.md`](workflows/README.md) for the manifest schema and `docs/dev/metadata-and-workflow-schema.md` for the full validator rules.

### Canonical workflows (PR2)

| Workflow | Cadence | Required skills |
|---|---|---|
| [`market-regime-daily`](workflows/market-regime-daily.yaml) | daily | market-breadth-analyzer, uptrend-analyzer, exposure-coach |
| [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | weekly | portfolio-manager, trader-memory-core |
| [`swing-opportunity-daily`](workflows/swing-opportunity-daily.yaml) | daily | vcp-screener, technical-analyst, position-sizer, trader-memory-core |
| [`trade-memory-loop`](workflows/trade-memory-loop.yaml) | per closed trade | trader-memory-core, signal-postmortem |
| [`monthly-performance-review`](workflows/monthly-performance-review.yaml) | monthly | trader-memory-core, signal-postmortem |

### Quickstart prose examples (NOT canonical)

The blocks below are informal sketches kept for skills not yet covered by a YAML manifest. They are quickstart help, not contracts. When in doubt, defer to the YAML manifests above.

**Daily Market Monitoring:**
1. Economic Calendar Fetcher → Check today's events
2. Earnings Calendar → Identify reporting companies
3. Market News Analyst → Review overnight developments
4. Breadth Chart Analyst → Assess market health

**Weekly Strategy Review:**
1. Sector Analyst → Identify rotation patterns
2. Technical Analyst → Confirm trends
3. Market Environment Analysis → Macro briefing
4. US Market Bubble Detector → Risk assessment

**Individual Stock Research:**
1. US Stock Analysis → Fundamental/technical review
2. Earnings Calendar → Check earnings dates
3. Market News Analyst → Recent news
4. Backtest Expert → Validate entry/exit strategy

**Options Strategy Development:**
1. Options Strategy Advisor → Simulate and compare strategies
2. Technical Analyst → Identify optimal entry timing
3. Earnings Calendar → Plan earnings-based strategies
4. US Stock Analysis → Validate fundamental thesis

**Portfolio Review & Rebalancing:**
1. Portfolio Manager → Fetch holdings via Alpaca MCP
2. Review asset allocation and risk metrics
3. Market Environment Analysis → Assess macro conditions
4. Execute rebalancing plan with buy/sell actions
> The canonical version of this routine is [`core-portfolio-weekly.yaml`](workflows/core-portfolio-weekly.yaml).

**Earnings Momentum Trading:**
1. Earnings Trade Analyzer → Score recent earnings reactions (5-factor: gap, trend, volume, MA200, MA50)
2. PEAD Screener (Mode B) → Feed analyzer output, screen for red candle pullback → breakout patterns
3. Technical Analyst → Confirm weekly chart setups on SIGNAL_READY/BREAKOUT candidates
4. Monitor BREAKOUT entries with stop-loss (red candle low) and 2R profit targets

**Statistical Arbitrage:**
1. Pair Trade Screener → Identify cointegrated pairs
2. Technical Analyst → Confirm setups for both legs
3. Monitor z-score signals and spread convergence
4. Manage market-neutral positions

**Income Portfolio Construction:**
1. Value Dividend Screener → High-yield opportunities
2. Dividend Growth Pullback Screener → Growth stocks at pullbacks
3. US Stock Analysis → Deep-dive analysis
4. Portfolio Manager → Monitor and rebalance holdings

**Trade Execution Planning:**
1. Screener skills (VCP, CANSLIM, Dividend, Earnings) → Identify candidates
2. Position Sizer → Calculate risk-based share count with portfolio constraints
3. Data Quality Checker → Validate analysis document before publishing
4. Portfolio Manager → Execute and monitor positions

**Kanchi Dividend Workflow (US stocks):**
1. kanchi-dividend-sop → Run Kanchi 5-step screening and pullback entry planning
2. kanchi-dividend-review-monitor → Execute T1-T5 anomaly detection and review queueing
3. kanchi-dividend-us-tax-accounting → Validate qualified/ordinary assumptions and account location
4. Feed REVIEW findings back to kanchi-dividend-sop before any additional buys

**Edge Research Pipeline (end-to-end):**
1. edge-candidate-agent (--ohlcv) → market_summary.json + anomalies.json + tickets/
2. edge-hint-extractor (--market-summary, --anomalies) → hints.yaml
3. edge-concept-synthesizer (--tickets-dir, --hints) → edge_concepts.yaml
4. edge-strategy-designer (--concepts) → strategy_drafts/*.yaml
5. edge-strategy-reviewer (--drafts-dir) → review.yaml (PASS/REVISE/REJECT)
6. [REVISE] → revision → re-review (max 2 cycles)
7. [PASS + export eligible] → edge-candidate-agent export → strategy.yaml + metadata.json
- **Orchestrated mode:** edge-pipeline-orchestrator runs all stages automatically with feedback loop

**Thesis-Driven Trading Pipeline:**
1. Screener skills (kanchi, earnings-trade-analyzer, vcp, pead, canslim) → Generate candidates
2. Trader Memory Core (register) → `thesis_ingest.py --source <skill> --input <report>` creates IDEA thesis
3. US Stock Analysis / Technical Analyst → Deep-dive validation, link report via `link_report()`
4. Trader Memory Core (transition) → IDEA → ENTRY_READY → ACTIVE with `transition()`
5. Position Sizer → Calculate risk-based sizing, attach via `attach_position()`
6. Portfolio Manager → Execute entry, update thesis with actual price/date
7. Trader Memory Core (review) → `list_review_due()` for periodic checks
8. Trader Memory Core (close + postmortem) → Record exit, generate journal entry with MAE/MFE

**Parabolic Short Pipeline (Phase 1 + Phase 2 + Phase 3):**
1. `screen_parabolic.py` (Phase 1) → daily watchlist JSON; 5-factor weighted score (MA Extension 30 / Acceleration 25 / Volume Climax 20 / Range Expansion 15 / Liquidity 10) → A/B/C/D grade. Hard-rejects via `invalidation_rules` (mode-aware), then attaches `state_caps` / `warnings`. `--dry-run --fixture` for offline pipeline verification.
2. Review the `reports/parabolic_short_<date>.md` watchlist and decide which candidates to promote (A/B by default).
3. `generate_pre_market_plan.py` (Phase 2) → reads Phase 1 JSON, filters by `--tradable-min-grade B`, looks up Alpaca short inventory (or `ManualBrokerAdapter` when env vars missing), inherits `prior_close` for SSR Rule 201 evaluation, splits manual-confirmation reasons into blocking vs advisory, and emits three trigger plans per candidate (5-min ORL break, first red 5-min, VWAP fail).
4. Trader confirms `blocking_manual_reasons` are cleared at the broker (HTB locate, premarket high/low resolved, etc.).
5. `monitor_intraday_trigger.py` (Phase 3) → reads the Phase 2 plan, fetches 5-min bars (Alpaca live or fixture), walks each plan's FSM forward by one step (per-trigger evaluator: ORL break, first red, VWAP fail), and writes `parabolic_short_intraday_<date>.json` with `state` (armed/triggered/invalidated/...), bar-derived transition timestamps, and `size_recipe_resolved.shares_actual` when triggered. One-shot — wrap in `watch -n 60 'python3 ...'` or 5-min cron during market hours. Replay-deterministic: re-runs against the same `--now-et` produce byte-identical output.
6. Optional: `trader-memory-core` `thesis_ingest.py --source parabolic-short-trade-planner --input reports/parabolic_short_plan_<date>.json` to register theses for postmortem tracking.

## Important Conventions

### SKILL.md Writing Style

- Use imperative/infinitive verb forms (e.g., "Analyze the chart", "Generate report")
- Write instructions for Claude to execute, not user instructions
- Avoid phrases like "You should..." or "Claude will..." - just state actions directly
- Structure: Overview → When to Use → Workflow → Output Format → Resources

### Reference Document Patterns

- Knowledge bases use declarative statements of fact
- Include historical examples and case studies
- Provide decision frameworks and checklists
- Organize hierarchically (H2 for major sections, H3 for subsections)

### Analysis Output Requirements

All analysis outputs must:
- Be saved to the `reports/` directory (create if it does not exist)
- Include date/time stamps
- Use English language
- Provide probability assessments where applicable
- Include specific trigger levels for actionable scenarios
- Cite references to knowledge base sources

### Error Handling in Scripts

Scripts should:
- Check for API keys before making requests
- Validate date ranges and input parameters
- Provide helpful error messages to stderr
- Return proper exit codes (0 for success, 1 for errors)
- Support retry logic with exponential backoff for rate limits

### No Personal Information in Committed Files

This is a **public repository**. Never hardcode personal information:
- **Absolute paths** containing usernames (e.g., `/Users/username/...`) — use relative paths or dynamic resolution like `Path(__file__).resolve().parents[N]`
- **API keys / secrets** — use environment variables (`$FMP_API_KEY`, `$FINVIZ_API_KEY`) or `.gitignore`-listed config files (`.mcp.json`, `.envrc`)
- **Usernames, email addresses, or other PII**

Files that contain secrets (`.mcp.json`, `.envrc`) must be listed in `.gitignore` and never committed.

## Language Considerations

- All SKILL.md files are in English
- Analysis outputs are in English
- Some reference materials (Stanley Druckenmiller Investment) include Japanese content
- README files available in both English (README.md) and Japanese (README.ja.md)
- User interactions may be in Japanese; analysis outputs remain in English

## Distribution Workflow

When skills are ready for distribution:

1. Test skill thoroughly in Claude Code
2. Package skill using skill-creator packaging script
3. Move .skill file to `skill-packages/`
4. Update README.md and README.ja.md with skill description
   - **Important:** Clearly indicate if the skill requires API subscriptions (FMP, FINVIZ Elite)
   - Include pricing information and sign-up links for required APIs
   - Specify if APIs are required, optional, or not needed
5. Commit changes with descriptive message

ZIP packages allow Claude web app users to upload and use skills without cloning the repository.

⚠️ **API Key Requirements in Distribution:**
- When distributing skills that require API keys, clearly document the requirements in the skill's SKILL.md
- Include setup instructions for both environment variables and command-line arguments
- Provide links to API registration and pricing pages
- Distinguish between required APIs (skill won't work without) and optional APIs (enhances performance)
