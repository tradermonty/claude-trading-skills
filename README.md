# Claude Trading Skills

Curated Claude skills for equity investors and traders. Each skill bundles prompts, knowledge, and optional helper scripts so Claude can assist with systematic backtesting, market analysis, technical charting, economic calendar monitoring, and US stock research. The repository packages skills for both Claude's web app and Claude Code workflows.

日本語版READMEは[`README.ja.md`](README.ja.md)をご覧ください。

## Repository Layout
- `<skill-name>/` – Source folder for each trading skill. Contains `SKILL.md`, reference material, and any helper scripts.
- `zip-packages/` – Pre-built ZIP archives ready to upload to Claude's web app **Skills** tab.

## Getting Started
### Use with Claude Web App
1. Download the ZIP that matches the skill you want from `zip-packages/`.
2. Open Claude in your browser, go to **Settings → Skills**, and upload the ZIP (see Anthropic's [Skills launch post](https://www.anthropic.com/news/skills) for feature overview).
3. Enable the skill inside the conversation where you need it.

### Use with Claude Code (desktop or CLI)
1. Clone or download this repository.
2. Copy the desired skill folder (e.g., `backtest-expert`) into your Claude Code **Skills** directory (open Claude Code → **Settings → Skills → Open Skills Folder**, per the [Claude Code Skills documentation](https://docs.claude.com/en/docs/claude-code/skills)).
3. Restart or reload Claude Code so the new skill is detected.

> Tip: The source folders and ZIPs contain identical content. Edit a source folder if you want to customize a skill, then re-zip it before uploading to the web app.

## Skill Catalog

### Market Analysis & Research

- **Sector Analyst** (`sector-analyst`)
  - Analyzes sector and industry performance charts to assess market positioning and rotation patterns based on market cycle theory.
  - Evaluates 1-week and 1-month performance charts to identify Early/Mid/Late Cycle or Recession positioning.
  - Generates scenario-based probability assessments for sector rotation strategies.
  - References include comprehensive sector rotation patterns across all market cycle phases.

- **Breadth Chart Analyst** (`breadth-chart-analyst`)
  - Analyzes S&P 500 Breadth Index and US Stock Market Uptrend Stock Ratio charts to assess market health and positioning.
  - Provides medium-term strategic and short-term tactical market outlook based on breadth indicators.
  - Identifies bull market phases (Healthy Breadth, Narrowing Breadth, Distribution) and bear market signals.
  - Includes detailed breadth interpretation framework and historical pattern references.

- **Technical Analyst** (`technical-analyst`)
  - Analyzes weekly price charts for stocks, indices, cryptocurrencies, and forex pairs using pure technical analysis.
  - Identifies trends, support/resistance levels, chart patterns, and momentum indicators without fundamental bias.
  - Generates scenario-based probability assessments with specific trigger levels for trend changes.
  - References cover Elliott Wave, Dow Theory, Japanese candlesticks, and technical indicator interpretation.

- **Market News Analyst** (`market-news-analyst`)
  - Analyzes recent market-moving news events from the past 10 days using automated WebSearch/WebFetch collection.
  - Focuses on FOMC decisions, central bank policy, mega-cap earnings, geopolitical events, and commodity market drivers.
  - Produces impact-ranked reports using quantitative scoring framework (Price Impact × Breadth × Forward Significance).
  - References include trusted news sources guide, event pattern analysis, and geopolitical-commodity correlations.

- **US Stock Analysis** (`us-stock-analysis`)
  - Comprehensive US equity research assistant covering fundamentals, technicals, peer comparisons, and investment memo generation.
  - Analyzes financial metrics, valuation ratios, growth trajectories, and competitive positioning.
  - Generates structured investment memos with bull/bear cases and risk assessments.
  - Reference library documents analytical frameworks (`fundamental-analysis.md`, `technical-analysis.md`, `financial-metrics.md`, `report-template.md`).

- **Market Environment Analysis** (`market-environment-analysis`)
  - Guides Claude through comprehensive global macro briefings covering equity indices, FX, commodities, yields, and market sentiment.
  - Provides structured reporting templates for daily/weekly market reviews with indicator-based assessments.
  - Includes indicator cheat sheets (`references/indicators.md`) and analysis patterns.
  - Helper script `scripts/market_utils.py` assists with report formatting and data visualization.

- **Market Breadth Analyzer** (`market-breadth-analyzer`)
  - Quantifies market breadth health using TraderMonty's public CSV data with a data-driven 6-component scoring system (0-100).
  - Components: Overall Breadth, Sector Participation, Sector Rotation, Momentum, Mean Reversion Risk, and Historical Context.
  - Measures how broadly the market is participating in a rally or decline (100 = maximum health, 0 = critical weakness).
  - No API key required - uses freely available CSV data from GitHub.

- **Uptrend Analyzer** (`uptrend-analyzer`)
  - Diagnoses market breadth health using Monty's Uptrend Ratio Dashboard, tracking ~2,800 US stocks across 11 sectors.
  - 5-component composite scoring (0-100): Market Breadth, Sector Participation, Sector Rotation, Momentum, Historical Context.
  - Warning overlay system: Late Cycle and High Selectivity flags tighten exposure guidance and add cautionary actions.
  - Sector-level fallback: automatically constructs sector summary from timeseries data when sector_summary.csv is unavailable.
  - No API key required - uses free GitHub CSV data.

- **Macro Regime Detector** (`macro-regime-detector`)
  - Detects structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis.
  - 6-component analysis: RSP/SPY concentration, yield curve, credit conditions, size factor, equity-bond relationship, and sector rotation.
  - Identifies regimes: Concentration, Broadening, Contraction, Inflationary, and Transitional states.
  - FMP API required for cross-asset ETF data (RSP, SPY, IWM, HYG, LQD, TLT, XLE, XLU, etc.).

- **Institutional Flow Tracker** (`institutional-flow-tracker`)
  - Tracks institutional investor ownership changes using 13F SEC filings data to identify "smart money" accumulation and distribution patterns.
  - Screens stocks with significant institutional ownership changes (>10-15% QoQ) and analyzes multi-quarter trends.
  - Tier-based quality framework weights superinvestors (Berkshire, Baupost) 3.0-3.5x vs index funds 0.0-0.5x.
  - Deep dive analysis on individual stocks: quarterly ownership trends, top holders, new/increased/decreased/closed positions.
  - Concentration risk analysis and position change categorization (new buyers, increasers, decreasers, exits).
  - FMP API integration with free tier sufficient for quarterly portfolio reviews (250 calls/day).
  - Follow specific institutions like Warren Buffett (Berkshire), Cathie Wood (ARK), Bill Ackman (Pershing Square).
  - Comprehensive reference guides: 13F filings, institutional investor types, interpretation framework with signal strength matrix.

- **Theme Detector** (`theme-detector`)
  - Detects trending market themes (bullish and bearish) by analyzing FINVIZ industry/sector performance across multiple timeframes.
  - 3-dimensional scoring: Theme Heat (0-100, momentum/volume/uptrend/breadth), Lifecycle Maturity (0-100, duration/RSI extremity/price extremes/valuation/ETF proliferation), and Confidence (Low/Medium/High).
  - Direction-aware analysis: bearish themes scored with equal sensitivity as bullish themes using inverted indicators.
  - Cross-sector theme detection (AI/Semis, Clean Energy, Gold, Cybersecurity, etc.) and vertical sector concentration identification.
  - Lifecycle stages: Emerging, Accelerating, Trending, Mature, Exhausting — with representative stocks and proxy ETFs per theme.
  - Integrates Monty's Uptrend Ratio Dashboard as supplementary breadth signal (3-point evaluation: ratio + MA10 + slope).
  - No API key required for core functionality (FINVIZ public + yfinance). FMP/FINVIZ Elite optional for enhanced stock selection.

### Economic & Earnings Calendars

- **Economic Calendar Fetcher** (`economic-calendar-fetcher`)
  - Fetches upcoming economic events using Financial Modeling Prep (FMP) API for next 7-90 days.
  - Retrieves central bank decisions, employment reports (NFP), inflation data (CPI/PPI), GDP releases, and other market-moving indicators.
  - Generates chronological markdown reports with impact assessment (High/Medium/Low) and market implications analysis.
  - Supports flexible API key management (environment variable or user input) with comprehensive error handling.

- **Earnings Calendar** (`earnings-calendar`)
  - Retrieves upcoming earnings announcements for US stocks using FMP API with focus on mid-cap+ companies (>$2B market cap).
  - Organizes earnings by date and timing (Before Market Open, After Market Close, During Market Hours).
  - Provides clean markdown table format for weekly earnings review and portfolio monitoring.
  - Flexible API key management supporting CLI, Desktop, and Web environments.

### Strategy & Risk Management

- **Scenario Analyzer** (`scenario-analyzer`)
  - Analyzes news headlines to build 18-month scenario projections with sector impacts and stock picks.
  - Dual-agent architecture: scenario-analyst for primary analysis, strategy-reviewer for second opinion.
  - Generates comprehensive reports including 1st/2nd/3rd order effects, recommended tickers, and critical review.
  - No API key required - uses WebSearch for news gathering.

- **Backtest Expert** (`backtest-expert`)
  - Framework for professional-grade strategy validation with hypothesis definition, parameter robustness checks, and walk-forward testing.
  - Emphasizes realistic assumptions: slippage modeling, transaction costs, survivorship bias elimination, and out-of-sample validation.
  - References cover detailed methodology (`references/methodology.md`) and failure post-mortems (`references/failed_tests.md`).
  - Guides systematic approach from idea generation through production deployment with quality gates.

- **Stanley Druckenmiller Investment Advisor** (`stanley-druckenmiller-investment`)
  - Encodes Druckenmiller's investment philosophy for macro positioning, liquidity analysis, and asymmetric risk/reward assessment.
  - Focuses on "bet big when you have high conviction" approach with strict loss-cutting discipline.
  - Reference pack provides philosophy deep dives, market analysis workflows, and historical case studies (content in Japanese and English).
  - Emphasizes macro theme identification, technical confirmation, and position sizing strategies.

- **US Market Bubble Detector** (`us-market-bubble-detector`) - **v2.1 Updated**
  - Data-driven bubble risk assessment using revised Minsky/Kindleberger framework with mandatory quantitative metrics (Put/Call, VIX, margin debt, breadth, IPO data).
  - Two-phase evaluation: Quantitative scoring (0-12 points) → Strict qualitative adjustment (0-3 points, reduced from +5 in v2.0).
  - Confirmation bias prevention with measurable evidence requirements for all qualitative adjustments.
  - Granular risk phases: Normal (0-4) → Caution (5-7) → Elevated Risk (8-9) → Euphoria (10-12) → Critical (13-15).
  - Actionable risk budgets and profit-taking strategies for each phase with specific short-selling criteria.
  - Supplemented by historical case files, quick-reference checklists (JP/EN), and implementation guide with strict scoring criteria.

- **Options Strategy Advisor** (`options-strategy-advisor`)
  - Educational options trading tool providing theoretical pricing, strategy analysis, and risk management guidance using Black-Scholes model.
  - Calculates all Greeks (Delta, Gamma, Theta, Vega, Rho) and supports 17+ options strategies (covered calls, spreads, iron condors, straddles, etc.).
  - Uses FMP API for free stock data + Black-Scholes pricing to simulate strategies without expensive real-time options data ($99-500/month).
  - P/L simulation and visualization for comparing strategies side-by-side with earnings strategy integration.
  - Theoretical prices approximate market mid-prices; users can input actual IV from broker for better accuracy.
  - Ideal for learning options mechanics, understanding Greeks, and strategy planning before live trading.

- **Portfolio Manager** (`portfolio-manager`)
  - Comprehensive portfolio analysis and management with Alpaca MCP Server integration for real-time holdings data.
  - Multi-dimensional analysis: Asset allocation, sector diversification, risk metrics (beta, volatility, drawdown), and performance review.
  - Position-level evaluation with HOLD/ADD/TRIM/SELL recommendations based on thesis validation and valuation.
  - Generates detailed rebalancing plans with specific actions to optimize portfolio allocation toward target models.
  - Supports model portfolios (Conservative/Moderate/Growth/Aggressive) for benchmark comparison.
  - Requires Alpaca brokerage account (paper or live) and configured Alpaca MCP Server; manual data entry also supported.

- **Edge Candidate Agent** (`edge-candidate-agent`)
  - Converts daily market observations into reproducible research tickets and exports Phase I-compatible candidate specs for `trade-strategy-pipeline`.
  - Generates `strategy.yaml` + `metadata.json` artifacts from structured research tickets with interface contract validation (`edge-finder-candidate/v1`).
  - Supports two entry families: `pivot_breakout` (with VCP detection) and `gap_up_continuation` (with gap detection).
  - Includes preflight validation against pipeline schema with `uv run` subprocess fallback for cross-environment compatibility.
  - Guardrails enforce schema bounds (risk limits, exit rules, non-empty conditions) and deterministic metadata with interface versioning.
  - No API key required — operates on local YAML files and validates against local pipeline repository.

### Market Timing & Bottom Detection

- **Market Top Detector** (`market-top-detector`)
  - Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defensive Rotation.
  - 6-component tactical timing system for identifying distribution and topping patterns.

- **FTD Detector** (`ftd-detector`)
  - Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology.
  - Dual-index tracking (S&P 500 + NASDAQ) with state machine for rally attempt, FTD qualification, and post-FTD health monitoring.
  - Complementary to Market Top Detector: this skill is offensive (bottom confirmation) while Market Top Detector is defensive (distribution detection).
  - Generates quality score (0-100) with exposure guidance for re-entering the market after corrections.
  - FMP API required for index price data.

### Earnings Momentum Screening

- **Earnings Trade Analyzer** (`earnings-trade-analyzer`)
  - Scores recent post-earnings stocks using a 5-factor weighted system: Gap Size (25%), Pre-Earnings Trend (30%), Volume Trend (20%), MA200 Position (15%), MA50 Position (10%).
  - Assigns A/B/C/D grades (A: 85+, B: 70-84, C: 55-69, D: <55) with composite score 0-100.
  - BMO/AMC timing-aware gap calculation — different base prices depending on when earnings were announced.
  - Optional entry quality filter excludes low-win-rate patterns (low price range, extreme gap + high score combinations).
  - API call budget management with `--max-api-calls` flag (default: 200) and automatic candidate trimming.
  - Outputs JSON with `schema_version: "1.0"` for downstream consumption by PEAD Screener.
  - FMP API required (free tier sufficient for typical 2-day lookback screening).

- **PEAD Screener** (`pead-screener`)
  - Screens post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns using weekly candle analysis.
  - Stage-based monitoring: MONITORING → SIGNAL_READY (red candle found) → BREAKOUT (price breaks above red candle high) → EXPIRED (>5 weeks).
  - 4-component scoring: Setup Quality (30%), Breakout Strength (25%), Liquidity (25%), Risk/Reward (20%).
  - Two input modes: Mode A (FMP earnings calendar, standalone) and Mode B (earnings-trade-analyzer JSON output, pipeline).
  - Weekly candle aggregation using ISO week (Monday start) with earnings week splitting and partial week handling.
  - Liquidity filters: ADV20 >= $25M, avg volume >= 1M shares, price >= $10.
  - Trade setup output: entry price, stop (red candle low), target (2R), risk/reward ratio.
  - FMP API required (free tier sufficient for 14-day lookback screening).

### Stock Screening & Selection

- **VCP Screener** (`vcp-screener`)
  - Screens S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP).
  - Identifies Stage 2 uptrend stocks forming tight bases with contracting volatility near breakout pivot points.
  - Multi-stage filtering: Trend Template → VCP Base Detection → Contraction Analysis → Pivot Point Calculation.
  - FMP API required (free tier sufficient for default screening of top 100 candidates).

- **CANSLIM Stock Screener** (`canslim-screener`) - **Phase 2**
  - Screens US stocks using William O'Neil's proven CANSLIM growth stock methodology for identifying multi-bagger candidates.
  - **Phase 2** implements 6 of 7 components (80% coverage): C (Current Earnings), A (Annual Growth), N (Newness/New Highs), **S (Supply/Demand)**, **I (Institutional Sponsorship)**, M (Market Direction).
  - Composite scoring (0-100) with weighted components: C 19%, A 25%, N 19%, **S 19%**, **I 13%**, M 6% (renormalized for 6 components).
  - **NEW**: Volume-based accumulation/distribution analysis (S component) - detects institutional buying patterns via up-day vs down-day volume ratios.
  - **NEW**: Institutional ownership tracking (I component) - analyzes holder count + ownership % with **automatic Finviz fallback** when FMP data incomplete.
  - **Finviz integration**: Free web scraping for institutional data (beautifulsoup4), improves I component accuracy from 35/100 to 60-100/100.
  - Interpretation bands: Exceptional+ (90-100), Exceptional (80-89), Strong (70-79), Above Average (60-69).
  - Bear market protection: M component gates all buy recommendations (M=0 triggers "raise cash" warning).
  - FMP API + Finviz integration: Free tier sufficient for 40 stocks (~1 minute 40 seconds execution time).
  - Comprehensive knowledge base: O'Neil's methodology (now includes S and I), scoring formulas, interpretation guide, portfolio construction rules.
  - Future Phase 3 will add L (Leadership/RS Rank) component for full 7-component CANSLIM (100% coverage).

- **Value Dividend Screener** (`value-dividend-screener`)
  - Screens US stocks for high-quality dividend opportunities using Financial Modeling Prep (FMP) API.
  - Multi-phase filtering: Value characteristics (P/E ≤20, P/B ≤2) + Income (Yield ≥3.5%) + Growth (3-year dividend/revenue/EPS uptrends).
  - Advanced analysis: Dividend sustainability (payout ratios, FCF coverage), financial health (D/E, liquidity), quality scores (ROE, margins).
  - Composite scoring system ranks stocks by overall attractiveness balancing value, growth, and quality factors.
  - Generates top 20 ranked stocks with detailed fundamental analysis and portfolio construction guidance.
  - Includes comprehensive screening methodology documentation and FMP API usage guide.

- **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`)
  - Finds high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) experiencing temporary pullbacks.
  - Combines fundamental dividend analysis with technical timing indicators (RSI ≤40 oversold conditions).
  - Targets stocks with exceptional dividend growth rates that compound wealth through dividend increases rather than high current yield.
  - Two-stage screening approach: FINVIZ Elite for fast RSI pre-screening + FMP API for detailed fundamental analysis.
  - Optimized for long-term dividend growth investors seeking entry opportunities during short-term market weakness.
  - Generates ranked lists of quality dividend growers at attractive technical entry points.

- **Kanchi Dividend SOP** (`kanchi-dividend-sop`)
  - Converts Kanchi-style 5-step dividend investing into a repeatable US-stock workflow.
  - Covers screening, deep-dive quality checks, valuation mapping, one-off profit filters, and pullback entry planning.
  - Includes reusable defaults for safety thresholds, valuation interpretation, and one-page stock memo output.
  - Designed as the first step in the Kanchi dividend workflow stack.

- **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`)
  - Implements forced-review anomaly detection for T1-T5 triggers with deterministic `OK/WARN/REVIEW` outputs.
  - Focuses on alerting and review-ticket generation, never auto-selling.
  - Includes a local rule-engine script (`build_review_queue.py`) and unit tests for trigger boundaries.
  - Designed as the ongoing monitoring layer after candidate selection.

- **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`)
  - Provides US dividend tax classification and account-location workflow for income portfolios.
  - Covers qualified vs ordinary assumptions, holding-period checks, and account placement tradeoffs.
  - Includes templates for annual planning memos and unresolved tax-assumption tracking.
  - Designed as the portfolio-implementation layer after screening and monitoring.

- **Pair Trade Screener** (`pair-trade-screener`)
  - Statistical arbitrage tool for identifying and analyzing pair trading opportunities using cointegration testing.
  - Tests for long-term equilibrium relationships between stock pairs within same sector or industry.
  - Calculates hedge ratios, mean-reversion speed (half-life), and generates z-score-based entry/exit signals.
  - Market-neutral strategy profiting from relative price movements regardless of overall market direction.
  - Supports sector-wide screening and custom pair analysis with statistical rigor (ADF tests, correlation analysis).
  - FMP API integration with JSON output for structured results and further analysis.

## Workflow Examples

### Daily Market Monitoring
1. Use **Economic Calendar Fetcher** to check today's high-impact events (FOMC, NFP, CPI releases)
2. Use **Earnings Calendar** to identify major companies reporting today
3. Use **Market News Analyst** to review overnight developments and their market impact
4. Use **Breadth Chart Analyst** to assess overall market health and positioning

### Weekly Strategy Review
1. Use **Sector Analyst** with weekly performance charts to identify rotation patterns
2. Use **Technical Analyst** on key indices and positions for trend confirmation
3. Use **Market Environment Analysis** for comprehensive macro briefing
4. Use **US Market Bubble Detector** to assess speculative excess and risk levels

### Individual Stock Research
1. Use **US Stock Analysis** for comprehensive fundamental and technical review
2. Use **Earnings Calendar** to check upcoming earnings dates
3. Use **Market News Analyst** to review recent company-specific news and sector developments
4. Use **Backtest Expert** to validate entry/exit strategies before position sizing

### Strategic Positioning
1. Use **Stanley Druckenmiller Investment Advisor** for macro theme identification
2. Use **Economic Calendar Fetcher** to time entries around major data releases
3. Use **Breadth Chart Analyst** and **Technical Analyst** for confirmation signals
4. Use **US Market Bubble Detector** for risk management and profit-taking guidance

### Earnings Momentum Trading
1. Use **Earnings Trade Analyzer** to score recent earnings reactions (gap size, trend, volume, MA position)
2. Use **PEAD Screener** (Mode B) with analyzer output to find PEAD setups (red candle pullbacks → breakout signals)
3. Use **Technical Analyst** to confirm weekly chart patterns and support/resistance levels
4. Use **Liquidity** filters in PEAD Screener to ensure position sizing feasibility
5. Monitor SIGNAL_READY stocks for breakout entries with defined stop-loss (red candle low) and 2R targets

### Income Portfolio Construction
1. Use **Value Dividend Screener** to identify high-quality dividend stocks with sustainable yields
2. Use **Dividend Growth Pullback Screener** to find growth-focused dividend stocks at attractive technical entry points
3. Use **US Stock Analysis** for deep-dive fundamental analysis on top candidates
4. Use **Earnings Calendar** to track upcoming earnings for portfolio holdings
5. Use **Market Environment Analysis** to assess macro conditions for dividend strategies
6. Use **Backtest Expert** to validate dividend capture or growth strategies

### Kanchi Dividend Workflow (US Stocks)
1. Use **Kanchi Dividend SOP** to run Kanchi's 5-step process and create buy plans with invalidation conditions
2. Use **Kanchi Dividend Review Monitor** on a daily/weekly/quarterly cadence to generate `OK/WARN/REVIEW` queues
3. Use **Kanchi Dividend US Tax Accounting** to align holdings with qualified-dividend assumptions and account location
4. Feed `REVIEW` findings back into **Kanchi Dividend SOP** before adding to positions

### Options Strategy Development
1. Use **Options Strategy Advisor** to simulate and compare options strategies using Black-Scholes pricing
2. Use **Technical Analyst** to identify optimal entry timing and support/resistance levels
3. Use **Earnings Calendar** to plan earnings-based options strategies
4. Use **US Stock Analysis** to validate fundamental thesis before deploying capital
5. Review Greeks and P/L scenarios to select optimal strategy (covered calls, spreads, straddles, etc.)

### Portfolio Review & Rebalancing
1. Use **Portfolio Manager** to fetch current holdings via Alpaca MCP and analyze portfolio health
2. Review asset allocation, sector diversification, and risk metrics (beta, volatility, concentration)
3. Evaluate position-level recommendations (HOLD/ADD/TRIM/SELL) based on thesis validation
4. Use **Market Environment Analysis** and **US Market Bubble Detector** to assess macro conditions
5. Execute rebalancing plan with specific buy/sell actions to optimize allocation

### Statistical Arbitrage Opportunities
1. Use **Pair Trade Screener** to identify cointegrated stock pairs within sectors
2. Analyze mean-reversion metrics (half-life, z-score) and hedge ratios
3. Use **Technical Analyst** to confirm technical setups for both legs of the pair
4. Monitor entry/exit signals based on z-score thresholds
5. Track spread convergence and manage market-neutral positions

### Skill Quality & Automation

- **Dual-Axis Skill Reviewer** (`dual-axis-skill-reviewer`)
  - Reviews skill quality using a dual-axis method: deterministic auto scoring (structure, workflow, execution safety, artifacts, tests) and optional LLM deep review.
  - 5-category auto axis (0-100): Metadata & Use Case (20), Workflow Coverage (25), Execution Safety & Reproducibility (25), Supporting Artifacts (10), Test Health (20).
  - Detects `knowledge_only` skills (no scripts, references only) and adjusts scoring expectations to avoid unfair penalties.
  - Optional LLM axis for qualitative review (correctness, risk, missing logic, maintainability) with configurable weight blending.
  - Supports `--all` flag to review every skill at once, `--skip-tests` for quick triage, and `--project-root` for cross-project review.
  - No API key required.

## Skill Self-Improvement Loop

An automated pipeline that continuously reviews and improves skill quality. A daily `launchd` job picks one skill, scores it with the dual-axis reviewer, and if the score is below 90/100, invokes `claude -p` to apply improvements and open a PR.

### How It Works

1. **Round-robin selection** — cycles through all skills (excluding the reviewer itself), persisted in `logs/.skill_improvement_state.json`.
2. **Auto scoring** — runs `run_dual_axis_review.py` to get a deterministic score (0-100).
3. **Improvement gate** — if `auto_review.score < 90`, Claude CLI applies fixes to SKILL.md and references.
4. **Quality gate** — re-scores after improvement (with tests enabled); rolls back if the score didn't improve.
5. **PR creation** — commits changes to a feature branch and opens a GitHub PR for human review.
6. **Daily summary** — writes results to `reports/skill-improvement-log/YYYY-MM-DD_summary.md`.

### Manual Execution

```bash
# Dry-run: score one skill without applying improvements or creating PRs
python3 scripts/run_skill_improvement_loop.py --dry-run

# Review all skills in dry-run mode
python3 scripts/run_skill_improvement_loop.py --dry-run --all

# Full run: score, improve if needed, and open PR
python3 scripts/run_skill_improvement_loop.py
```

### launchd Setup (macOS)

The loop runs daily at 05:00 local time via macOS `launchd`:

```bash
# Install the agent
cp launchd/com.trade-analysis.skill-improvement.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-improvement.plist

# Verify
launchctl list | grep skill-improvement

# Manual trigger
launchctl start com.trade-analysis.skill-improvement
```

### Key Files

| File | Purpose |
|------|---------|
| `scripts/run_skill_improvement_loop.py` | Orchestration script (selection, scoring, improvement, PR) |
| `scripts/run_skill_improvement.sh` | Thin shell wrapper for launchd |
| `launchd/com.trade-analysis.skill-improvement.plist` | macOS launchd agent configuration |
| `skills/dual-axis-skill-reviewer/` | Reviewer skill (scoring engine) |
| `logs/.skill_improvement_state.json` | Round-robin state and history |
| `reports/skill-improvement-log/` | Daily summary reports |

## Customization & Contribution
- Update `SKILL.md` files to tweak trigger descriptions or capability notes; ensure the frontmatter name matches the folder name when zipping.
- Extend reference documents or add scripts inside each skill folder to support new workflows.
- When distributing updates, regenerate the matching ZIP in `zip-packages/` so web-app users get the latest version.

## API Requirements

Several skills require API keys for data access:

### Skills Requiring APIs

| Skill | FMP API | FINVIZ Elite | Alpaca | Notes |
|-------|---------|--------------|--------|-------|
| **Economic Calendar Fetcher** | ✅ Required | ❌ Not used | ❌ Not used | Fetches economic events |
| **Earnings Calendar** | ✅ Required | ❌ Not used | ❌ Not used | Fetches earnings dates |
| **Institutional Flow Tracker** | ✅ Required | ❌ Not used | ❌ Not used | 13F filings analysis, free tier sufficient |
| **Value Dividend Screener** | ✅ Required | 🟡 Optional | ❌ Not used | FINVIZ reduces execution time 70-80% |
| **Dividend Growth Pullback Screener** | ✅ Required | 🟡 Optional | ❌ Not used | FINVIZ for RSI pre-screening |
| **Kanchi Dividend SOP** | ❌ Not used | ❌ Not used | ❌ Not used | Knowledge workflow; uses outputs from other skills or manual lists |
| **Kanchi Dividend Review Monitor** | ❌ Not used | ❌ Not used | ❌ Not used | Local rule engine; consumes normalized input JSON |
| **Kanchi Dividend US Tax Accounting** | ❌ Not used | ❌ Not used | ❌ Not used | Knowledge workflow for classification/account location |
| **Pair Trade Screener** | ✅ Required | ❌ Not used | ❌ Not used | Statistical arbitrage analysis |
| **Options Strategy Advisor** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP for stock data; theoretical pricing works without |
| **Portfolio Manager** | ❌ Not used | ❌ Not used | ✅ Required | Real-time holdings via Alpaca MCP |
| **CANSLIM Stock Screener** | ✅ Required | ❌ Not used | ❌ Not used | Phase 2 (6 components); free tier sufficient; Finviz web scraping for institutional data |
| **VCP Screener** | ✅ Required | ❌ Not used | ❌ Not used | Stage 2 + VCP pattern screening; free tier sufficient |
| **FTD Detector** | ✅ Required | ❌ Not used | ❌ Not used | Index price data for rally/FTD detection |
| **Macro Regime Detector** | ✅ Required | ❌ Not used | ❌ Not used | Cross-asset ETF ratio analysis |
| **Market Breadth Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Uses free GitHub CSV data |
| **Uptrend Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Uses free GitHub CSV data |
| **Theme Detector** | 🟡 Optional | 🟡 Optional | ❌ Not used | Core: FINVIZ public + yfinance (free). FMP for ETF holdings, FINVIZ Elite for stock lists |
| **Edge Candidate Agent** | ❌ Not used | ❌ Not used | ❌ Not used | Local YAML generation; validates against local pipeline repo |
| Dual-Axis Skill Reviewer | ❌ Not used | ❌ Not used | ❌ Not used | Deterministic scoring + optional LLM review |

### API Setup

**Financial Modeling Prep (FMP) API:**
- Free tier: 250 requests/day (sufficient for most use cases)
- Sign up: https://financialmodelingprep.com/developer/docs
- Set environment variable: `export FMP_API_KEY=your_key_here`
- Or provide key via command-line argument when prompted

**FINVIZ Elite API:**
- Subscription: $39.99/month or $329.99/year
- Sign up: https://elite.finviz.com/
- Set environment variable: `export FINVIZ_API_KEY=your_key_here`
- Provides fast pre-screening for dividend screeners

**Alpaca Trading API:**
- Free paper trading account available
- Sign up: https://alpaca.markets/
- Requires Alpaca MCP Server configuration
- Set environment variables:
  ```bash
  export ALPACA_API_KEY="your_api_key_id"
  export ALPACA_SECRET_KEY="your_secret_key"
  export ALPACA_PAPER="true"  # or "false" for live trading
  ```

## Support & Further Reading
- Claude Skills launch overview: https://www.anthropic.com/news/skills
- Claude Code Skills how-to: https://docs.claude.com/en/docs/claude-code/skills
- Financial Modeling Prep API: https://financialmodelingprep.com/developer/docs

Questions or suggestions? Open an issue or include guidance alongside the relevant skill folder so future users know how to get the most from these trading assistants.

## License

All skills and reference materials in this repository are provided for educational and research purposes.
