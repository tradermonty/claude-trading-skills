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

## Customization & Contribution
- Update `SKILL.md` files to tweak trigger descriptions or capability notes; ensure the frontmatter name matches the folder name when zipping.
- Extend reference documents or add scripts inside each skill folder to support new workflows.
- When distributing updates, regenerate the matching ZIP in `zip-packages/` so web-app users get the latest version.

## API Requirements

Several skills require API keys for data access:

- **Economic Calendar Fetcher** & **Earnings Calendar**: Require [Financial Modeling Prep (FMP) API](https://financialmodelingprep.com) key
  - Free tier: 250 requests/day
  - Set environment variable: `export FMP_API_KEY=your_key_here`
  - Or provide key via command-line argument when prompted

## Support & Further Reading
- Claude Skills launch overview: https://www.anthropic.com/news/skills
- Claude Code Skills how-to: https://docs.claude.com/en/docs/claude-code/skills
- Financial Modeling Prep API: https://financialmodelingprep.com/developer/docs

Questions or suggestions? Open an issue or include guidance alongside the relevant skill folder so future users know how to get the most from these trading assistants.

## License

All skills and reference materials in this repository are provided for educational and research purposes.
