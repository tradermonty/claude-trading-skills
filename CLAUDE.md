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

**MANDATORY: After creating or committing a new skill, update both READMEs:**
1. Add skill description to the appropriate category in `README.md` (English)
2. Add skill description to the matching category in `README.ja.md` (Japanese)
3. If the skill requires API keys, add it to the API Requirements table in `README.md` and the API要件 section in `README.ja.md`
4. If a new category is needed, create it in both files

### Packaging Skills for Distribution

Skills are packaged as ZIP files for Claude web app users:

```bash
# Use the skill-creator's packaging script
python3 ~/.claude/plugins/marketplaces/anthropic-agent-skills/skill-creator/scripts/package_skill.py <skill-name>
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

### API Key Management

⚠️ **IMPORTANT:** Several skills require paid API subscriptions to function. Review the requirements below before using these skills.

#### API Requirements by Skill

| Skill | FMP API | FINVIZ Elite | Alpaca | Notes |
|-------|---------|--------------|--------|-------|
| **Economic Calendar Fetcher** | ✅ Required | ❌ Not used | ❌ Not used | Fetches economic events from FMP |
| **Earnings Calendar** | ✅ Required | ❌ Not used | ❌ Not used | Fetches earnings dates from FMP |
| **Institutional Flow Tracker** | ✅ Required | ❌ Not used | ❌ Not used | 13F filings analysis; free tier sufficient |
| **Value Dividend Screener** | ✅ Required | 🟡 Optional (Recommended) | ❌ Not used | FMP for analysis; FINVIZ reduces execution time by 70-80% |
| **Dividend Growth Pullback Screener** | ✅ Required | 🟡 Optional (Recommended) | ❌ Not used | FMP for analysis; FINVIZ for RSI pre-screening |
| **Pair Trade Screener** | ✅ Required | ❌ Not used | ❌ Not used | Statistical arbitrage analysis |
| **Earnings Trade Analyzer** | ✅ Required | ❌ Not used | ❌ Not used | 5-factor earnings scoring; free tier sufficient |
| **PEAD Screener** | ✅ Required | ❌ Not used | ❌ Not used | Weekly candle PEAD analysis; free tier sufficient |
| **Options Strategy Advisor** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP for stock data; Black-Scholes works without |
| **Portfolio Manager** | ❌ Not used | ❌ Not used | ✅ Required | Real-time holdings via Alpaca MCP Server |
| Sector Analyst | ❌ Not required | ❌ Not used | ❌ Not used | Image-based chart analysis |
| Technical Analyst | ❌ Not required | ❌ Not used | ❌ Not used | Image-based chart analysis |
| Breadth Chart Analyst | ❌ Not required | ❌ Not used | ❌ Not used | Image-based chart analysis |
| Market News Analyst | ❌ Not required | ❌ Not used | ❌ Not used | Uses WebSearch/WebFetch |
| US Stock Analysis | ❌ Not required | ❌ Not used | ❌ Not used | User provides data |
| Backtest Expert | ❌ Not required | ❌ Not used | ❌ Not used | User provides strategy parameters |
| US Market Bubble Detector | ❌ Not required | ❌ Not used | ❌ Not used | User provides indicators |
| **Theme Detector** | 🟡 Optional | 🟡 Optional (Recommended) | ❌ Not used | FINVIZ for dynamic stocks; FMP for ETF holdings fallback |
| **FinViz Screener** | ❌ Not required | 🟡 Optional | ❌ Not used | Public screener free; Elite auto-detected from env var |
| **Position Sizer** | ❌ Not required | ❌ Not used | ❌ Not used | Pure calculation; works offline |
| **Data Quality Checker** | ❌ Not required | ❌ Not used | ❌ Not used | Local markdown validation; works offline |
| **Edge Strategy Reviewer** | ❌ Not required | ❌ Not used | ❌ Not used | Deterministic scoring on local YAML drafts |
| **Edge Pipeline Orchestrator** | ❌ Not required | ❌ Not used | ❌ Not used | Orchestrates local edge skills via subprocess |
| Dual-Axis Skill Reviewer | ❌ Not required | ❌ Not used | ❌ Not used | Deterministic scoring + optional LLM review |

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
- **Elite Subscription:** $39.99/month or $329.99/year (~$27.50/month)
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
python3 portfolio-manager/scripts/test_alpaca_connection.py

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

Skills are designed to be combined for comprehensive analysis:

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
