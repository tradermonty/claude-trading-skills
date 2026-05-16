# Claude Trading Skills

Claude Trading Skills started as a personal project to use AI to improve my own trading process.

Claude Trading Skills is a Claude Skills-based trading workflow toolkit for time-constrained individual investors.

It is designed for investors who use long-term investing, ETFs, and dividend stocks as their core, while using disciplined swing trading as a satellite strategy when market conditions are favorable.

The goal is not to outsource buy/sell decisions to AI. The goal is to structure market review, risk management, trade planning, journaling, and continuous improvement. It is open source because the workflows, checklists, and review habits behind better trading decisions can improve through shared practice.

This is not a signal service or a promise of profitability. It is a toolkit for traders who want to build a better decision process.

The project follows a **first for self, open for others** stance: it is built first as a practical workflow the author uses, then shared openly for others who face similar constraints.

📖 **Documentation site:** <https://tradermonty.github.io/claude-trading-skills/>

**Project vision:** [`PROJECT_VISION.md`](PROJECT_VISION.md)

日本語版READMEは[`README.ja.md`](README.ja.md)をご覧ください。

## Disclaimer

This repository is for educational, research, and process-improvement purposes only. It is not financial advice, investment advisory service, tax advice, legal advice, a signal service, or a broker execution platform. Trading and investing involve risk, including loss of principal. Past performance, backtests, screens, reports, and AI-generated analysis do not guarantee future results. All trading decisions, position sizing, tax/regulatory compliance, and broker usage are the user's responsibility.

The project is provided under the MIT License, **AS IS, WITHOUT WARRANTY**.

## Who This Is For

This repository is designed for:

- Time-constrained individual investors
- Long-term investors who also want disciplined swing-trading upside
- Dividend and ETF investors who want structured portfolio review
- Traders who want to manage risk before finding trade candidates
- Investors who want to journal and improve their decision process

It is not designed for fully automated trading, signal outsourcing, or short-term scalping.

## Recommended Starting Path

New users should start with one of these operational workflows. Each link points to a machine-readable manifest under [`workflows/`](workflows/) that names the exact skills, decision gates, and artifacts in order.

| Goal | Workflow | Anchor Skills | API Profile |
| --- | --- | --- | --- |
| 15-minute daily market check | [`market-regime-daily`](workflows/market-regime-daily.yaml) | market-breadth-analyzer, uptrend-analyzer, exposure-coach | No API for basic path |
| Weekly long-term portfolio review | [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core | Alpaca optional/required by input |
| Find swing candidates only when risk is allowed | [`swing-opportunity-daily`](workflows/swing-opportunity-daily.yaml) | vcp-screener, technical-analyst, position-sizer | FMP for screeners |
| Record and learn from every closed trade | [`trade-memory-loop`](workflows/trade-memory-loop.yaml) | trader-memory-core, signal-postmortem | No API for manual path |
| Review monthly performance and adjust rules | [`monthly-performance-review`](workflows/monthly-performance-review.yaml) | trader-memory-core, signal-postmortem, backtest-expert | No API for manual path |

See [`workflows/README.md`](workflows/README.md) for how to read a manifest and run it manually.

### No API Key Starter Path

If you do not have FMP / FINVIZ / Alpaca subscriptions, start with these five skills and run them manually:

1. `market-breadth-analyzer` — public CSV breadth scoring; no API key
2. `uptrend-analyzer` — public CSV uptrend participation; no API key
3. `position-sizer` — pure calculation; no I/O
4. `trader-memory-core` — local YAML journaling
5. `signal-postmortem` — review framework

This path lets you review market conditions, size trades, journal decisions, and review outcomes **without paid data APIs**. Note: "no API" does not mean "no external data" — these skills still need public CSVs, chart screenshots, or local files. See each skill's `integrations:` entry in [`skills-index.yaml`](skills-index.yaml) for exact input requirements.

> **Canonical source:** [`skills-index.yaml`](skills-index.yaml) is the authoritative index of all skills. If this README, `CLAUDE.md`, or docs disagree with the index, the index is correct. The same applies to multi-skill workflows — [`workflows/*.yaml`](workflows/) is canonical.

## Repository Layout
- `skills/<skill-name>/` – Source folder for each trading skill. Contains `SKILL.md`, reference material, and any helper scripts.
- `skills-index.yaml` – Canonical metadata index for every skill (id, category, integrations, workflows back-references).
- `workflows/` – Operational workflow manifests for the Core + Satellite routines (canonical, validator-enforced via `--strict-workflows`).
- `skill-packages/` – Pre-built `.skill` archives ready to upload to Claude's web app **Skills** tab.
- `docs/` – Documentation site content, generated skill pages, and `docs/dev/metadata-and-workflow-schema.md` (schema spec).
- `scripts/` – Repository-level automation, including the schema validator and one-shot bootstrap helper.
- `skillsets/` – Planned skillset manifests for bundled workflows (vision Phase 2, not yet present).

## Getting Started
### Use with Claude Web App
1. Download the `.skill` file that matches the skill you want from `skill-packages/`.
2. Open Claude in your browser, go to **Settings → Skills**, and upload the ZIP (see Anthropic's [Skills launch post](https://www.anthropic.com/news/skills) for feature overview).
3. Enable the skill inside the conversation where you need it.

### Use with Claude Code (desktop or CLI)
1. Clone or download this repository.
2. Copy the desired skill folder (e.g., `backtest-expert`) into your Claude Code **Skills** directory (open Claude Code → **Settings → Skills → Open Skills Folder**, per the [Claude Code Skills documentation](https://docs.claude.com/en/docs/claude-code/skills)).
3. Restart or reload Claude Code so the new skill is detected.

> Tip: The source folders and ZIPs contain identical content. Edit a source folder if you want to customize a skill, then re-zip it before uploading to the web app.

## Core Skill Areas

This repository contains skills across the following areas:

| Area | Example Skills |
| --- | --- |
| Market Regime | `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach` |
| Core Portfolio | `portfolio-manager`, `value-dividend-screener`, `kanchi-dividend-sop` |
| Swing Opportunities | `vcp-screener`, `canslim-screener`, `breakout-trade-planner` |
| Trade Planning | `position-sizer`, `technical-analyst` |
| Trade Memory | `trader-memory-core`, `signal-postmortem` |
| Strategy Research | `backtest-expert`, `edge-pipeline-orchestrator` |
| Advanced Satellite | `parabolic-short-trade-planner`, `earnings-trade-analyzer`, `options-strategy-advisor` |

The detailed catalog below is **auto-generated** from `skills-index.yaml` by `scripts/generate_catalog_from_index.py`. To update a skill's description, edit its `skills-index.yaml` entry and re-run the generator (`python3 scripts/generate_catalog_from_index.py`). For a more navigable version, use the documentation site.

## Detailed Skill Catalog

<!-- skills-index:start name="catalog-en" -->
<!-- This section is auto-generated from skills-index.yaml by scripts/generate_catalog_from_index.py. Do not edit by hand — edit the index and re-run the generator. -->

### Market Regime

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Breadth Chart Analyst** (`breadth-chart-analyst`) | This skill should be used when analyzing market breadth charts, specifically the S&P 500 Breadth Index (200-Day MA based) and the US Stock Market Uptrend Stock Ratio charts. | `chart_image` **required** | production |
| **Downtrend Duration Analyzer** (`downtrend-duration-analyzer`) | Analyze historical downtrend durations and generate interactive HTML histograms showing typical correction lengths by sector and market cap. | `local_calculation` — | production |
| **Exposure Coach** (`exposure-coach`) | Generate a one-page Market Posture summary with net exposure ceiling, growth-vs-value bias, participation breadth, and new-entry-allowed vs cash-priority recommendation by integrating signals from breadth, regime, and flow analysis skills. | `local_calculation` — | production |
| **FTD Detector** (`ftd-detector`) | Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology. | `fmp` **required** | production |
| **IBD Distribution Day Monitor** (`ibd-distribution-day-monitor`) | Detect IBD-style Distribution Days for QQQ/SPY (close down at least 0.2% on higher volume), track 25-session expiration and 5% invalidation, count d5/d15/d25 clusters, classify market risk (NORMAL/CAUTION/HIGH/SEVERE), and emit TQQQ/QQQ... | `fmp` **required** | production |
| **Macro Regime Detector** (`macro-regime-detector`) | Detect structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis. | `yfinance_or_csv` _recommended_ | production |
| **Market Breadth Analyzer** (`market-breadth-analyzer`) | Quantifies market breadth health using TraderMonty's public CSV data. | `public_csv` **required** | production |
| **Market Environment Analysis** (`market-environment-analysis`) | Comprehensive market environment analysis and reporting tool. | `websearch` **required**, `chart_image` optional | production |
| **Market News Analyst** (`market-news-analyst`) | This skill should be used when analyzing recent market-moving news events and their impact on equity markets and commodities. | `websearch` **required** | production |
| **Market Top Detector** (`market-top-detector`) | Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defensive Sector Rotation. | `public_csv` **required** | production |
| **Sector Analyst** (`sector-analyst`) | This skill should be used when analyzing sector rotation patterns and market cycle positioning. | `chart_image` **required** | production |
| **Uptrend Analyzer** (`uptrend-analyzer`) | Analyzes market breadth using Monty's Uptrend Ratio Dashboard data to diagnose the current market environment. | `public_csv` **required** | production |
| **US Market Bubble Detector** (`us-market-bubble-detector`) | Evaluates market bubble risk through quantitative data-driven analysis using the revised Minsky/Kindleberger framework v2.1. | `user_input` **required** | production |

### Core Portfolio

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`) | Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) that are experiencing temporary pullbacks, identified by RSI oversold conditions (RSI ≤40). | `fmp` **required**, `finviz` _recommended_ | production |
| **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`) | Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIEW states without auto-selling. | `fmp` _recommended_ | production |
| **Kanchi Dividend SOP** (`kanchi-dividend-sop`) | Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. | `fmp` _recommended_ | production |
| **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`) | Provide US dividend tax and account-location workflow for Kanchi-style income portfolios. | `local_calculation` — | production |
| **Portfolio Manager** (`portfolio-manager`) | Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. | `alpaca` **required** | production |
| **Value Dividend Screener** (`value-dividend-screener`) | Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). | `fmp` **required**, `finviz` _recommended_ | production |

### Swing Opportunity

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Breakout Trade Planner** (`breakout-trade-planner`) | Generate Minervini-style breakout trade plans from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates (stop-limit bracket for pre-placement, limit bracket for post-confi... | `local_calculation` — | production |
| **CANSLIM Screener** (`canslim-screener`) | Screen US stocks using William O'Neil's CANSLIM growth stock methodology. | `fmp` **required** | production |
| **Finviz Screener** (`finviz-screener`) | Build and open FinViz screener URLs from natural language requests. | `finviz` optional | production |
| **Theme Detector** (`theme-detector`) | Detect and analyze trending market themes across sectors. | `fmp` optional, `finviz` _recommended_ | production |
| **VCP Screener** (`vcp-screener`) | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). | `fmp` **required** | production |

### Trade Planning

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Position Sizer** (`position-sizer`) | Calculate risk-based position sizes for long stock trades. | `local_calculation` — | production |
| **Technical Analyst** (`technical-analyst`) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. | `chart_image` **required** | production |
| **US Stock Analysis** (`us-stock-analysis`) | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. | `user_input` **required** | production |

### Trade Memory

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Signal Postmortem** (`signal-postmortem`) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills. | `local_calculation` — | production |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets with ranked hypothesis cards and optional strategy.yaml export. | `local_calculation` — | production |
| **Trader Memory Core** (`trader-memory-core`) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem. | `fmp` optional | production |

### Strategy Research

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Backtest Expert** (`backtest-expert`) | Expert guidance for systematic backtesting of trading strategies. | `user_input` **required** | production |
| **Edge Candidate Agent** (`edge-candidate-agent`) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. | `fmp` optional | production |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export. | `local_calculation` — | production |
| **Edge Hint Extractor** (`edge-hint-extractor`) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonical hints.yaml for downstream concept synthesis and auto detection. | `local_calculation` — | production |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and export. | `local_calculation` — | production |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradicti... | `local_calculation` — | production |
| **Edge Strategy Designer** (`edge-strategy-designer`) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation. | `local_calculation` — | production |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size adequacy, and execution realism. | `local_calculation` — | production |
| **Scenario Analyzer** (`scenario-analyzer`) | Analyze 18-month scenarios from news headlines via scenario-analyst agent with strategy-reviewer second opinion; outputs primary/secondary/tertiary impact analysis and stock picks in Japanese. | `websearch` **required** | production |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market Top, Macro Regime, FTD Detector, VCP Screener, Theme Detector, CANSLIM Screener) into a unified conviction score (0-100),... | `local_calculation` — | production |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum. | `local_calculation` — | production |

### Advanced Satellite

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). | `fmp` **required** | production |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. | `fmp` **required** | production |
| **Options Strategy Advisor** (`options-strategy-advisor`) | Options trading strategy analysis and simulation tool. | `fmp` optional | production |
| **Pair Trade Screener** (`pair-trade-screener`) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities. | `fmp` **required** | production |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate intraday trigger fires from live 5-min bars. | `fmp` **required**, `alpaca` optional | production |
| **PEAD Screener** (`pead-screener`) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. | `fmp` **required** | production |

### Meta / Development Tooling

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Data Quality Checker** (`data-quality-checker`) | Validate data quality in market analysis documents and blog articles before publication. | `local_calculation` — | production |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. | `local_calculation` — | production |
| **Earnings Calendar** (`earnings-calendar`) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. | `fmp` **required** | production |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | Fetch upcoming economic events and data releases using FMP API. | `fmp` **required** | production |
| **Skill Designer** (`skill-designer`) | Design new Claude skills from structured idea specifications. | `local_calculation` — | production |
| **Skill Idea Miner** (`skill-idea-miner`) | Mine Claude Code session logs for skill idea candidates. | `local_calculation` — | production |
| **Skill Integration Tester** (`skill-integration-tester`) | Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. | `local_calculation` — | production |
| **Trading Skills Navigator** (`trading-skills-navigator`) | Recommend the right workflow, skillset, API profile, and setup path from a natural-language trading goal. | `local_calculation` — | production |
<!-- skills-index:end name="catalog-en" -->

## Additional Workflow Examples

The main Core + Satellite starting path is described above. The examples below show additional ways to compose skills, including advanced satellite and contributor workflows.

### Daily Market Monitoring
1. Use **Economic Calendar Fetcher** to check today's high-impact events (FOMC, NFP, CPI releases)
2. Use **Earnings Calendar** to identify major companies reporting today
3. Use **Market News Analyst** to review overnight developments and their market impact
4. Use **Breadth Chart Analyst** to assess overall market health and positioning

### Weekly Strategy Review
1. Use **Sector Analyst** to fetch CSV data and identify rotation patterns (optionally provide charts)
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
3. Review position-level flags (HOLD/ADD/TRIM/SELL candidates) based on thesis validation
4. Use **Market Environment Analysis** and **US Market Bubble Detector** to assess macro conditions
5. Review a rebalancing plan and decide manually which actions, if any, to take

### Statistical Arbitrage Opportunities
1. Use **Pair Trade Screener** to identify cointegrated stock pairs within sectors
2. Analyze mean-reversion metrics (half-life, z-score) and hedge ratios
3. Use **Technical Analyst** to confirm technical setups for both legs of the pair
4. Monitor entry/exit signals based on z-score thresholds
5. Track spread convergence and manage market-neutral positions

### Skill Quality & Automation

- **Data Quality Checker** (`data-quality-checker`)
  - Validates data quality in market analysis documents and blog articles before publication.
  - 5 check categories: price scale inconsistencies (ETF vs futures digit hints), instrument notation consistency, date/weekday mismatches (English + Japanese), allocation total errors (section-limited), and unit mismatches.
  - Advisory mode — flags issues as warnings for human review, exit 0 even with findings.
  - Supports full-width Japanese characters (％, 〜), range notation (50-55%), and year inference for dates without explicit year.
  - No API key required — works offline on local markdown files.

- **Skill Designer** (`skill-designer`)
  - Generates Claude CLI prompts for designing new skills from structured idea specifications.
  - Embeds repository conventions (structure guide, quality checklist, SKILL.md template) into the prompt.
  - Lists existing skills to prevent duplication. Used by the skill auto-generation pipeline's daily flow.
  - No API key required.

- **Dual-Axis Skill Reviewer** (`dual-axis-skill-reviewer`)
  - Reviews skill quality using a dual-axis method: deterministic auto scoring (structure, workflow, execution safety, artifacts, tests) and optional LLM deep review.
  - 5-category auto axis (0-100): Metadata & Use Case (20), Workflow Coverage (25), Execution Safety & Reproducibility (25), Supporting Artifacts (10), Test Health (20).
  - Detects `knowledge_only` skills (no scripts, references only) and adjusts scoring expectations to avoid unfair penalties.
  - Optional LLM axis for qualitative review (correctness, risk, missing logic, maintainability) with configurable weight blending.
  - Supports `--all` flag to review every skill at once, `--skip-tests` for quick triage, and `--project-root` for cross-project review.
  - No API key required.

- **Skill Idea Miner** (`skill-idea-miner`)
  - Mines Claude Code session logs for skill idea candidates, scores them for novelty/feasibility/trading value, and maintains a prioritized backlog.
  - Used by the weekly skill auto-generation pipeline. Can also be run manually.
  - No API key required.

## Skill Self-Improvement Loop

This section is contributor-oriented. New users can skip it and start with the Core + Satellite path above.

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

## Skill Auto-Generation Pipeline

This section is contributor-oriented. It describes repository maintenance automation, not a required trading workflow.

An automated pipeline that mines session logs for skill ideas (weekly) and designs, reviews, and creates new skills as PRs (daily). Works alongside the Self-Improvement Loop to continuously expand the skill catalog.

### How It Works

1. **Weekly mining** — scans Claude Code session logs for recurring patterns that could become skills, scores each idea for novelty, feasibility, and trading value.
2. **Backlog scoring** — ranked ideas are stored in `logs/.skill_generation_backlog.yaml` with status tracking (`pending`, `in_progress`, `completed`, `design_failed`, `review_failed`, `pr_failed`).
3. **Daily selection** — picks the highest-scoring `pending` idea; retries `design_failed` / `pr_failed` once (but `review_failed` is terminal).
4. **Design & review** — the Skill Designer builds a complete skill (SKILL.md, references, scripts), then the Dual-Axis Reviewer scores it. If the score is too low, the idea is marked `review_failed`.
5. **PR creation** — commits the new skill to a feature branch and opens a GitHub PR for human review.

### Manual Execution

```bash
# Weekly: mine ideas from session logs and score them
python3 scripts/run_skill_generation_pipeline.py --mode weekly --dry-run

# Daily: design a skill from the highest-scoring backlog idea
python3 scripts/run_skill_generation_pipeline.py --mode daily --dry-run

# Full daily run (creates branch, designs skill, opens PR)
python3 scripts/run_skill_generation_pipeline.py --mode daily
```

### launchd Setup (macOS)

Two `launchd` agents handle the weekly and daily schedules:

```bash
# Install both agents
cp launchd/com.trade-analysis.skill-generation-weekly.plist ~/Library/LaunchAgents/
cp launchd/com.trade-analysis.skill-generation-daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-weekly.plist
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-daily.plist

# Verify
launchctl list | grep skill-generation

# Manual trigger
launchctl start com.trade-analysis.skill-generation-weekly
launchctl start com.trade-analysis.skill-generation-daily
```

### Key Files

| File | Purpose |
|------|---------|
| `scripts/run_skill_generation_pipeline.py` | Orchestration script (mining, selection, design, review, PR) |
| `scripts/run_skill_generation.sh` | Thin shell wrapper for launchd |
| `launchd/com.trade-analysis.skill-generation-weekly.plist` | Weekly mining schedule (Saturday 06:00) |
| `launchd/com.trade-analysis.skill-generation-daily.plist` | Daily generation schedule (07:00) |
| `skills/skill-idea-miner/` | Mining and scoring skill |
| `skills/skill-designer/` | Skill design prompt builder |
| `logs/.skill_generation_backlog.yaml` | Scored idea backlog with status tracking |
| `logs/.skill_generation_state.json` | Run history and state |
| `reports/skill-generation-log/` | Daily generation summary reports |

## Customization & Contribution
- Update `SKILL.md` files to tweak trigger descriptions or capability notes; ensure the frontmatter name matches the folder name when zipping.
- Extend reference documents or add scripts inside each skill folder to support new workflows.
- When distributing updates, regenerate the matching `.skill` file in `skill-packages/` so web-app users get the latest version.

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
| **CANSLIM Stock Screener** | ✅ Required | ❌ Not used | ❌ Not used | Phase 3.1 (7 components, multi-period RS); free tier sufficient for 35 stocks; Finviz web scraping for institutional data |
| **VCP Screener** | ✅ Required | ❌ Not used | ❌ Not used | Stage 2 + VCP pattern screening; free tier sufficient |
| **Parabolic Short Trade Planner** | ✅ Required | ❌ Not used | ✅ Phase 3 / 🟡 Phase 2 | FMP for Phase 1 screener; Alpaca required for Phase 3 intraday bars (paper feed OK), optional for Phase 2 borrow checks. No SDK — `requests` direct |
| **FTD Detector** | ✅ Required | ❌ Not used | ❌ Not used | Index price data for rally/FTD detection |
| **IBD Distribution Day Monitor** | ✅ Required | ❌ Not used | ❌ Not used | Daily QQQ/SPY OHLCV for Distribution Day detection |
| **Macro Regime Detector** | ✅ Required | ❌ Not used | ❌ Not used | Cross-asset ETF ratio analysis |
| **Market Breadth Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Uses free GitHub CSV data |
| **Uptrend Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Uses free GitHub CSV data |
| **Sector Analyst** | ❌ Not used | ❌ Not used | ❌ Not used | Uses free GitHub CSV data; optional chart images |
| **Theme Detector** | 🟡 Optional | 🟡 Optional | ❌ Not used | Core: FINVIZ public + yfinance (free). FMP for ETF holdings, FINVIZ Elite for stock lists |
| **FinViz Screener** | ❌ Not used | 🟡 Optional | ❌ Not used | Public screener free; FINVIZ Elite auto-detected from `$FINVIZ_API_KEY` |
| **Edge Candidate Agent** | ❌ Not used | ❌ Not used | ❌ Not used | Local YAML generation; validates against local pipeline repo |
| **Trade Hypothesis Ideator** | ❌ Not used | ❌ Not used | ❌ Not used | Local JSON hypothesis pipeline with optional strategy export |
| **Edge Strategy Reviewer** | ❌ Not used | ❌ Not used | ❌ Not used | Deterministic scoring on local YAML drafts |
| **Edge Pipeline Orchestrator** | ❌ Not used | ❌ Not used | ❌ Not used | Orchestrates local edge skills via subprocess |
| **Edge Signal Aggregator** | ❌ Not used | ❌ Not used | ❌ Not used | Aggregates local edge-skill JSON/YAML outputs into weighted ranked signals |
| **Trader Memory Core** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP only for MAE/MFE in postmortem; core features work offline |
| **Exposure Coach** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP only when institutional-flow-tracker data is included |
| **Signal Postmortem** | 🟡 Optional | ❌ Not used | ❌ Not used | FMP for fetching realized returns; manual price entry also supported |
| Dual-Axis Skill Reviewer | ❌ Not used | ❌ Not used | ❌ Not used | Deterministic scoring + optional LLM review |

### API Setup

**Financial Modeling Prep (FMP) API:**
- Free tier: 250 requests/day (sufficient for most use cases)
- Sign up: https://financialmodelingprep.com/developer/docs
- Set environment variable: `export FMP_API_KEY=your_key_here`
- Or provide key via command-line argument when prompted

**FINVIZ Elite API:**
- Subscription: $39.50/month or $299.50/year
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
