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
| Weekly long-term portfolio review | [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core | Alpaca required; manual CSV is a degraded fallback |
| Find swing candidates only when risk is allowed | [`swing-opportunity-daily`](workflows/swing-opportunity-daily.yaml) | vcp-screener, technical-analyst, position-sizer | FMP for screeners |
| Record and learn from every closed trade | [`trade-memory-loop`](workflows/trade-memory-loop.yaml) | trader-memory-core, signal-postmortem | No API for manual path |
| Review monthly performance and adjust rules | [`monthly-performance-review`](workflows/monthly-performance-review.yaml) | trader-memory-core, signal-postmortem, backtest-expert | No API for manual path |

See [`workflows/README.md`](workflows/README.md) for how to read a manifest and run it manually. For a one-page "which workflow fits my situation?" guide, see [Find Your Workflow](docs/en/find-your-workflow.md) ([日本語](docs/ja/find-your-workflow.md)).

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
- `skillsets/` – Purpose-specific install bundles defining required / recommended / optional skills for major goals (4 core skillsets shipped: market-regime, core-portfolio, swing-opportunity, trade-memory; consumed by the Navigator).

## Getting Started
### Use with Claude Web App
1. Download the `.skill` file that matches the skill you want from `skill-packages/`.
2. Open Claude in your browser, go to **Settings → Skills**, and upload the ZIP (see Anthropic's [Skills launch post](https://www.anthropic.com/news/skills) for feature overview).
3. Enable the skill inside the conversation where you need it.

### Use with Claude Code (desktop or CLI)
1. Clone or download this repository.
2. Copy the desired skill folder (e.g., `backtest-expert`) into your Claude Code **Skills** directory (open Claude Code → **Settings → Skills → Open Skills Folder**, per the [Claude Code Skills documentation](https://docs.claude.com/en/docs/claude-code/skills)).
3. Restart or reload Claude Code so the new skill is detected.

> Tip: `.skill` packages are built from the source folders with tests and local build artifacts omitted. Edit a source folder if you want to customize a skill, then run `python3 scripts/package_skills.py --skill <skill-name>` before uploading to the web app.

## Companion Work Package

Want a ready-to-run agent-style workflow? See the companion
[Hermes Trading Research Agent Work Package](https://github.com/tradermonty/hermes-trading-research-agent-work-package).

It packages these skills into a Hermes profile with task-oriented slash-command routines such as
`/pre-market-routine`, `/after-close-review`, `/trade-journal`, `/weekly-portfolio-review`, and
`/monthly-performance-review`.

This is a research, journaling, and risk-review assistant, **not** an automated trading system.
It does **not** place orders, provide a signal service, or run hidden scheduled jobs;
**human decision gates remain central**.

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
| **Macro Regime Detector** (`macro-regime-detector`) | Detect structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis. | `yfinance_or_csv` _recommended_, `fred` optional | production |
| **Market Breadth Analyzer** (`market-breadth-analyzer`) | Quantifies market breadth health using TraderMonty's public CSV data. | `public_csv` **required** | production |
| **Market Environment Analysis** (`market-environment-analysis`) | Comprehensive market environment analysis and reporting tool. | `websearch` **required**, `chart_image` optional | production |
| **Market News Analyst** (`market-news-analyst`) | This skill should be used when analyzing recent market-moving news events and their impact on equity markets and commodities. | `websearch` **required**, `gdelt` optional | production |
| **Market Top Detector** (`market-top-detector`) | Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defensive Sector Rotation. | `public_csv` **required** | production |
| **Morning Note Briefing** (`morning-note-briefing`) | Assemble a fixed-format, two-minute pre-market morning note by composing the JSON outputs of existing skills — overnight earnings (earnings-calendar), pre-market movers and sector performance (sector-analyst plus a price feed), today's macro calendar (economic-calendar-fetcher), and live catalysts (market-news-analyst / gdelt-news-catalyst) — leading with the single most important development, a directional Top Call, and actionable long/short ideas. | `local_calculation` — | beta |
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
| **Finviz Screener** (`finviz-screener`) | Build and open FinViz screener URLs from natural language requests. | `finviz` optional, `yfinance` optional | production |
| **Index Futures Weekly Income** (`index-futures-weekly-income`) | Core-satellite ES/NQ system backtested on 25 years of Yahoo data - core leg holds above the 200d SMA with a hysteresis channel + 52-week-high crash brake (beats buy-and-hold at 1.5-2x futures leverage with ~half the drawdown); satellite legs are regime-gated weekly setups (long-only pullback/breakout, put-credit-spread income) with stand-aside calls in downtrends and stressed vol; plain-language trade plans hand off to position-sizer, technical-analyst, and trader-memory-core. | `yfinance` **required** | beta |
| **Stockbee Exhaustion Hammer Screener** (`stockbee-exhaustion-hammer-screener`) | Screen US stocks for Stockbee-style selling-exhaustion hammer candidates using quality/liquidity gates, prior momentum, pullback depth, undercut/reclaim, hammer geometry, volume confirmation, market gate, and risk-distance filters. | `fmp` **required**, `prices_json` optional, `profiles_json` optional, `local_calculation` — | beta |
| **Stockbee Momentum Burst Screener** (`stockbee-momentum-burst-screener`) | Screen US stocks for Stockbee-style 3-5 day momentum burst candidates using 4% breakout, dollar breakout, range expansion, volume expansion, setup quality, and risk-distance filters. | `fmp` **required**, `prices_json` optional, `local_calculation` — | beta |
| **Swing Setup Screener** (`swing-setup-screener`) | Seven-in-one after-hours screener over keyless Yahoo daily bars - swing-trend longs and shorts (SMA50/200 alignment with Pullback/Breakout/Extended or Bear-Flag/Breakdown/Oversold triggers), 52-week-high strength leaders with SMA20 pullback plans, high-ATR% volatility candidates, and three next-session RVOL watchlists (in-play movers, unusual-volume accumulation/distribution quadrant, weakness on selling volume); A-D grades from documented factor weights with a hard timing contract (last completed session only, RVOL screens explicitly labeled next-session watchlists) and hand-offs to position-sizer, technical-analyst, and short-squeeze-radar. | `yfinance` **required** | beta |
| **Theme Detector** (`theme-detector`) | Detect and analyze trending market themes across sectors. | `fmp` optional, `finviz` _recommended_ | production |
| **Trend Reclaim Screener** (`trend-reclaim-screener`) | After-hours screener for long-side SMA50 reclaim setups - stocks that pulled back below the 50-day average, reset, and recently re-established above it; hard invalidations plus a 5-factor weighted grade (reclaim quality / momentum / structure / volume / trend alignment) rank top-3 picks with next-open entry, stop, and T1 plan levels that hand off to position-sizer, technical-analyst, and trader-memory-core. | `yfinance` **required** | beta |
| **VCP Screener** (`vcp-screener`) | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). | `fmp` **required** | production |

### Trade Planning

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Adversarial Trade Debate** (`adversarial-trade-debate`) | Turn a screener candidate into a decisive conviction rating and a sized, risk-vetted trade decision through two staged adversarial debates — a bull-vs-bear debate judged into a 5-tier rating, then an aggressive/conservative/neutral risk debate judged by a Portfolio Manager into a final, possibly-resized decision. | `local_calculation` — | beta |
| **Dynamic Exit Engine** (`dynamic-exit-engine`) | Manage an adaptive trailing exit for an open long equity position via a two-phase trailing-stop FSM (hard stop -> ratcheting profit floor) with breakeven lock, stale-flat timeout, ATR noise band, and consecutive-breach confirmation. Replays deterministically over an OHLCV price series and persists a JSON tracker snapshot. | `fmp` optional, `local_calculation` — | beta |
| **Josh Trade Monitor** (`josh-trade-monitor`) | Monitor Stocks-With-Josh leaderboard traders and emit only newly posted entries and closes since the prior run. Supports multiple trader targets, per-target state, session-cookie authentication, and a machine-readable event contract for downstream Robinhood or broker execution skills. | `local_calculation` — | beta |
| **Position Sizer** (`position-sizer`) | Calculate risk-based position sizes for long stock trades. | `local_calculation` —, `yfinance` optional, `fmp` optional | production |
| **Robinhood Trade Executor** (`robinhood-trade-executor`) | Execute upstream Robinhood trade recommendations for equity and single-leg option opens and closes. Canonical, Josh monitor, and social-signal inputs are planned deterministically with idempotency-ledger deduplication, then placed through the Robinhood MCP connector. Real-money, fully automated, no human confirmation gate. | `robinhood` **required** | beta |
| **Technical Analyst** (`technical-analyst`) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. | `chart_image` **required** | production |
| **US Stock Analysis** (`us-stock-analysis`) | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. | `user_input` **required** | production |

### Trade Memory

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Signal Postmortem** (`signal-postmortem`) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills. | `local_calculation` — | production |
| **Stockbee Setup Fluency Trainer** (`stockbee-setup-fluency-trainer`) | Build a Stockbee-style setup model book from momentum-burst screener candidates, then update 3-day and 5-day forward outcomes with MFE/MAE, stop-hit status, outcome tags, and cohort statistics. | `prices_json` optional, `fmp` optional, `local_calculation` — | beta |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets with ranked hypothesis cards and optional strategy.yaml export. | `local_calculation` — | production |
| **Trade Performance Coach** (`trade-performance-coach`) | Review closed trades, partial exits, and monthly aggregates for process adherence, risk discipline, execution quality, and evidence-based trading behavior patterns, then produce next-session operating rules. | `local_calculation` — | beta |
| **Trader Memory Core** (`trader-memory-core`) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem. | `fmp` optional | production |
| **Weekly Performance Digest** (`weekly-performance-digest`) | Generate a weekly performance summary from closed trades with win rate, expectancy, and pattern analysis. | `local_calculation` — | production |

### Strategy Research

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Backtest Expert** (`backtest-expert`) | Expert guidance for systematic backtesting of trading strategies. | `user_input` **required** | production |
| **Edge Candidate Agent** (`edge-candidate-agent`) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. | `fmp` optional | production |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export. | `local_calculation` — | production |
| **Edge Hint Extractor** (`edge-hint-extractor`) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonical hints.yaml for downstream concept synthesis and auto detection. | `local_calculation` — | production |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and export. | `local_calculation` — | production |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradicti... | `local_calculation` — | production |
| **Edge Social Aggregator** (`edge-social-aggregator`) | Score and consolidate social trading signals (YouTube/X/Reddit) from social-signal-ingestor into a per-ticker feed for edge-signal-aggregator, applying recency x corroboration (source-count) scoring and deduping each ticker across videos. Does not redo cross-source merge or ranking. | `local_calculation` — | beta |
| **Edge Strategy Designer** (`edge-strategy-designer`) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation. | `local_calculation` — | production |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size adequacy, and execution realism. | `local_calculation` — | production |
| **Retail Sentiment Ingestor** (`retail-sentiment-ingestor`) | Ingest real-time retail sentiment for a list of tickers from keyless StockTwits cashtag streams and Reddit (r/wallstreetbets, r/stocks, r/investing), plus an optional X path, and emit one deterministically-scored signal note per ticker into the shared social vault with sentiment band, 0-10 score, cross-source divergence, and a >=90/10 StockTwits over-extension flag. | `stocktwits` **required**, `reddit` **required**, `x` optional, `local_calculation` — | beta |
| **Scenario Analyzer** (`scenario-analyzer`) | Analyze 18-month scenarios from news headlines via scenario-analyst agent with strategy-reviewer second opinion; outputs primary/secondary/tertiary impact analysis and stock picks. | `websearch` **required**, `polymarket` optional | production |
| **Social Signal Ingestor** (`social-signal-ingestor`) | Ingest trading signals from YouTube channels via yt-dlp transcripts, extract one structured signal note per ticker into a local vault, and emit a machine-readable signal index for the edge pipeline. YouTube is v1; X/Reddit plug in later via Agent-Reach. | `youtube` **required**, `local_calculation` — | beta |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market Top, Macro Regime, FTD Detector, VCP Screener, Theme Detector, CANSLIM Screener) into a unified conviction score (0-100),... | `local_calculation` — | production |
| **Stockbee 20% Study** (`stockbee-20pct-study`) | Build a daily Stockbee-style +20%/-20% mover event study, classify catalysts and setup context, update forward outcomes, and export evidence-backed edge hints without treating movers as buy/sell signals. | `fmp` **required**, `prices_json` optional, `news_events_json` optional, `websearch` optional, `local_calculation` — | beta |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum. | `local_calculation` — | production |
| **Ticker Enricher** (`ticker-enricher`) | Enrich ticker signals with company name / sector / industry and recommendation-date + current price via Yahoo Finance, and emit a records file for a generic writer such as write-supabase (the dashboard derives gain percent and days held). Reusable by any producer with tickers. | `yahoo_finance` **required**, `local_calculation` — | beta |

### Advanced Satellite

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Dealer Gamma Analyzer** (`dealer-gamma-analyzer`) | Quantify dealer options gamma (GEX) positioning for an equity or index from free CBOE ~15-minute-delayed options data — signed dealer gamma per strike, total GEX under two dealer conventions, call/put walls as S/R levels, gamma-flip strike, max pain, and positive/negative-gamma regime classification. No paid feed required. | `cboe` **required**, `local_calculation` — | beta |
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). | `fmp` **required**, `yfinance` optional | production |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. | `fmp` **required** | production |
| **Intrinsic Value (DCF)** (`intrinsic-value-dcf`) | Produce a triangulated intrinsic-value estimate for a US ticker by blending a discounted-cash-flow model (CAPM WACC, 5-year FCFF fade, dual terminal value, recalculated WACC x terminal-growth sensitivity grid), peer-median relative multiples, and an optional sum-of-the-parts, with Bull/Base/Bear scenarios, guardrail gates, and sector-aware method routing. | `fmp` **required**, `yfinance` optional, `local_calculation` — | beta |
| **Momentum DCA Bot** (`momentum-dca-bot`) | Fully mechanical daily momentum DCA sleeve - screens momentum-pullback stocks (YTD +50%, above 20/50/200 SMA, weekly pullback, within 10% of 52-week high), buys a fixed $300 notional of the top-ranked name via Alpaca (paper by default) only while SPY closes above its 50DMA, books profits by selling half at +20%, and exits fully on a 50DMA break or 15% trailing stop; every action lands in an append-only trade log. | `yfinance` **required**, `alpaca` **required**, `finviz` optional | beta |
| **Options Strategy Advisor** (`options-strategy-advisor`) | Options trading strategy analysis and simulation tool. | `fmp` optional | production |
| **Pair Trade Screener** (`pair-trade-screener`) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities. | `fmp` **required** | production |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate intraday trigger fires from live 5-min bars. | `fmp` **required**, `alpaca` optional | production |
| **PEAD Screener** (`pead-screener`) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. | `fmp` **required** | production |
| **Short-Squeeze Radar** (`short-squeeze-radar`) | Rank US equities by short-squeeze potential from free FINRA data — Reg SHO daily short-volume files (rising short-volume-ratio inflection) plus optional bi-monthly short interest for days-to-cover ranking — classifying each name as crowded-short / neutral / low-pressure. No API key required. | `finra` **required**, `short_interest_file` optional, `local_calculation` — | beta |
| **Stockbee Episodic Pivot Analyzer** (`stockbee-episodic-pivot-analyzer`) | Analyze Stockbee-style Day 1 Episodic Pivot candidates from earnings, guidance, M&A, FDA, analyst, contract, product, short-squeeze, and story/theme catalysts using catalyst quality, gap/range expansion, volume shock, neglect/revaluation context, liquidity, and EP-day-low risk. | `catalyst_events_json` **required**, `fmp` optional, `local_calculation` — | beta |

### Meta / Development Tooling

| Skill | Summary | Integrations | Status |
|---|---|---|---|
| **Data Quality Checker** (`data-quality-checker`) | Validate data quality in market analysis documents and blog articles before publication. | `local_calculation` —, `yfinance` optional, `fmp` optional | production |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. | `local_calculation` — | production |
| **Earnings Calendar** (`earnings-calendar`) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. | `fmp` **required** | production |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | Fetch upcoming economic events and data releases using FMP API. | `fmp` **required** | production |
| **Live Analytics Dashboard** (`live-analytics-dashboard`) | Render another skill's reports/*.json (watchlist, breadth, or portfolio monitors) as a dashboard — detect the report shape, build a KPI + sortable-table view, and either publish it as a snapshot Artifact or serve it as a live-refreshing local page. Every generated page is CSP-safety gated before serving. | `local_calculation` — | beta |
| **Skill Designer** (`skill-designer`) | Design new Claude skills from structured idea specifications. | `local_calculation` — | production |
| **Skill Idea Miner** (`skill-idea-miner`) | Mine Claude Code session logs for skill idea candidates. | `local_calculation` — | production |
| **Skill Integration Tester** (`skill-integration-tester`) | Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. | `local_calculation` — | production |
| **Trading Skills Navigator** (`trading-skills-navigator`) | Recommend the right workflow, skillset, API profile, and setup path from a natural-language trading goal. | `local_calculation` — | production |
| **Write Supabase** (`write-supabase`) | Generic Supabase table writer. Reads a records JSON file and upserts or inserts the rows into a caller-named Supabase table with a caller-supplied conflict key. Domain-agnostic and reusable by any workflow that needs to persist records to Supabase. | `supabase` **required** | beta |
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
1. Use **Stanley Druckenmiller Investment** for macro theme identification
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
- When distributing updates, regenerate the matching `.skill` file in `skill-packages/` so web-app users get the latest version:
  ```bash
  python3 scripts/package_skills.py --skill <skill-name>
  ```

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
| **Intrinsic Value (DCF)** | ✅ Required | ❌ Not used | ❌ Not used | FMP fundamentals + 10Y UST risk-free rate; keyless yfinance fallback (`--yfinance`) or `--input-json` offline |
| **Dynamic Exit Engine** | 🟡 Optional | ❌ Not used | ❌ Not used | Offline trailing-stop FSM; FMP daily OHLCV optional, `--bars-source fixture` (Alpaca/Robinhood/FMP export) is keyless |
| **Dealer Gamma Analyzer** | ❌ Not used | ❌ Not used | ❌ Not used | Free ~15-min delayed CBOE options JSON; no API key |
| **Short-Squeeze Radar** | ❌ Not used | ❌ Not used | ❌ Not used | Free FINRA Reg SHO daily files + optional short-interest export; no API key |
| **Retail Sentiment Ingestor** | ❌ Not used | ❌ Not used | ❌ Not used | Keyless StockTwits + Reddit; optional X path via `X_API_KEY` |

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
