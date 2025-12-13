# Claude Trading Skills

[![Run in Smithery](https://smithery.ai/badge/skills/tradermonty)](https://smithery.ai/skills?ns=tradermonty&utm_source=github&utm_medium=badge)


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

- **Institutional Flow Tracker** (`institutional-flow-tracker`)
  - Tracks institutional investor ownership changes using 13F SEC filings data to identify "smart money" accumulation and distribution patterns.
  - Screens stocks with significant institutional ownership changes (>10-15% QoQ) and analyzes multi-quarter trends.
  - Tier-based quality framework weights superinvestors (Berkshire, Baupost) 3.0-3.5x vs index funds 0.0-0.5x.
  - Deep dive analysis on individual stocks: quarterly ownership trends, top holders, new/increased/decreased/closed positions.
  - Concentration risk analysis and position change categorization (new buyers, increasers, decreasers, exits).
  - FMP API integration with free tier sufficient for quarterly portfolio reviews (250 calls/day).
  - Follow specific institutions like Warren Buffett (Berkshire), Cathie Wood (ARK), Bill Ackman (Pershing Square).
  - Comprehensive reference guides: 13F filings, institutional investor types, interpretation framework with signal strength matrix.

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

### Stock Screening & Selection

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

### Income Portfolio Construction
1. Use **Value Dividend Screener** to identify high-quality dividend stocks with sustainable yields
2. Use **Dividend Growth Pullback Screener** to find growth-focused dividend stocks at attractive technical entry points
3. Use **US Stock Analysis** for deep-dive fundamental analysis on top candidates
4. Use **Earnings Calendar** to track upcoming earnings for portfolio holdings
5. Use **Market Environment Analysis** to assess macro conditions for dividend strategies
6. Use **Backtest Expert** to validate dividend capture or growth strategies

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
| **Pair Trade Screener** | ✅ Required | ❌ Not used | ❌ Not used | Statistical arbitrage analysis |
| **Options Strategy Advisor** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP for stock data; theoretical pricing works without |
| **Portfolio Manager** | ❌ Not used | ❌ Not used | ✅ Required | Real-time holdings via Alpaca MCP |

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
