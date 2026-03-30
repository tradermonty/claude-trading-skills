---
layout: default
title: Skill Catalog
parent: English
nav_order: 2
lang_peer: /ja/skill-catalog/
permalink: /en/skill-catalog/
---

# Skill Catalog
{: .no_toc }

A comprehensive catalog of all 50 Claude Trading Skills organized by category. Badge indicators show API requirements at a glance.
{: .fs-6 .fw-300 }

> Use English skill names ("CANSLIM", "VCP", "FinViz", etc.) for best search results on this page.
{: .note }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Badge Legend

| Badge | Meaning |
|-------|---------|
| <span class="badge badge-free">No API</span> | Works without any external API keys |
| <span class="badge badge-api">FMP Required</span> | Requires a Financial Modeling Prep API key |
| <span class="badge badge-optional">FMP Optional</span> | FMP key enhances functionality but is not required |
| <span class="badge badge-optional">FINVIZ Optional</span> | FINVIZ Elite improves speed and coverage |
| <span class="badge badge-api">Alpaca Required</span> | Requires an Alpaca brokerage account |
| <span class="badge badge-workflow">Workflow</span> | Workflow skill that coordinates other skills |

---

## 1. Stock Screening

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **[CANSLIM Screener]({{ '/en/skills/canslim-screener/' | relative_url }})** | Full 7-component CANSLIM growth stock scoring (C, A, N, S, L, I, M). Composite 0-100 ratings with bear market protection. Phase 3 implements 100% of O'Neil's methodology | <span class="badge badge-api">FMP Required</span> |
| **[VCP Screener]({{ '/en/skills/vcp-screener/' | relative_url }})** | Detects Mark Minervini's Volatility Contraction Pattern. 3-phase pipeline: Pre-filter, Trend Template, VCP Detection with pivot points and trade setups | <span class="badge badge-api">FMP Required</span> |
| **[FinViz Screener]({{ '/en/skills/finviz-screener/' | relative_url }})** | Translates natural language (Japanese/English) into FinViz filter URLs. 500+ filter codes across fundamentals, technicals, and descriptives. **Theme cross-screening** (30+ themes × 268 sub-themes) for narrative-based searches like "AI × Logistics" or "Data Centers × Power". Opens results in Chrome | <span class="badge badge-free">No API</span> <span class="badge badge-optional">FINVIZ Optional</span> |
| **Value Dividend Screener** | Multi-phase dividend stock screening: value characteristics (P/E, P/B), income (yield), growth (3-year trends), sustainability, and quality scoring | <span class="badge badge-api">FMP Required</span> <span class="badge badge-optional">FINVIZ Optional</span> |
| **Dividend Growth Pullback Screener** | Finds dividend growth stocks (12%+ annual growth, 1.5%+ yield) at oversold technical levels (RSI <= 40). Two-stage FINVIZ + FMP pipeline | <span class="badge badge-api">FMP Required</span> <span class="badge badge-optional">FINVIZ Optional</span> |
| **Earnings Trade Analyzer** | Scores post-earnings stocks using 5 weighted factors: Gap Size (25%), Pre-Earnings Trend (30%), Volume Trend (20%), MA200 Position (15%), MA50 Position (10%). A/B/C/D grades | <span class="badge badge-api">FMP Required</span> |
| **PEAD Screener** | Screens for Post-Earnings Announcement Drift patterns using weekly candle analysis. Stage-based monitoring: MONITORING, SIGNAL_READY, BREAKOUT, EXPIRED | <span class="badge badge-api">FMP Required</span> |
| **FTD Detector** | Detects Follow-Through Day signals for market bottom confirmation using William O'Neil's methodology. Dual-index tracking with quality scoring (0-100) | <span class="badge badge-api">FMP Required</span> |
| **Institutional Flow Tracker** | Tracks institutional ownership changes using 13F SEC filings. Tier-based quality framework weights superinvestors (Berkshire, Baupost) higher than index funds | <span class="badge badge-api">FMP Required</span> |

---

## 2. Market Analysis

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **Sector Analyst** | Analyzes sector/industry performance charts to assess market positioning and rotation patterns based on market cycle theory (Early/Mid/Late Cycle, Recession) | <span class="badge badge-free">No API</span> |
| **Breadth Chart Analyst** | Analyzes S&P 500 Breadth Index and Uptrend Stock Ratio charts for market health. Identifies bull market phases: Healthy Breadth, Narrowing, Distribution | <span class="badge badge-free">No API</span> |
| **Technical Analyst** | Pure technical analysis of weekly price charts. Identifies trends, support/resistance, chart patterns, and momentum indicators. Covers Elliott Wave, Dow Theory, candlesticks | <span class="badge badge-free">No API</span> |
| **[Market News Analyst]({{ '/en/skills/market-news-analyst/' | relative_url }})** | Collects and analyzes market-moving news from the past 10 days via WebSearch. Impact scoring: (Price Impact x Breadth) x Forward Significance | <span class="badge badge-free">No API</span> |
| **Market Environment Analysis** | Comprehensive global macro briefing covering equity indices, FX, commodities, yields, and sentiment with structured reporting templates | <span class="badge badge-free">No API</span> |
| **[Market Breadth Analyzer]({{ '/en/skills/market-breadth-analyzer/' | relative_url }})** | Quantifies market breadth health using a data-driven 6-component scoring system (0-100) from publicly available CSV data | <span class="badge badge-free">No API</span> |
| **Uptrend Analyzer** | Diagnoses breadth health using Uptrend Ratio Dashboard tracking ~2,800 US stocks across 11 sectors. 5-component composite scoring with warning overlays | <span class="badge badge-free">No API</span> |
| **Macro Regime Detector** | Detects structural macro regime transitions (1-2 year horizon) using 6-component cross-asset ratio analysis (RSP/SPY, yield curve, credit, size factor, sector rotation) | <span class="badge badge-api">FMP Required</span> |
| **[US Market Bubble Detector]({{ '/en/skills/us-market-bubble-detector/' | relative_url }})** | Data-driven bubble risk assessment using Minsky/Kindleberger framework. Two-phase evaluation: quantitative scoring (0-12) + strict qualitative adjustment (0-3). Five risk phases | <span class="badge badge-free">No API</span> |
| **Market Top Detector** | Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Defensive Rotation. 6-component tactical timing system | <span class="badge badge-free">No API</span> |
| **[Downtrend Duration Analyzer]({{ '/en/skills/downtrend-duration-analyzer/' | relative_url }})** | Analyzes historical downtrend durations (peak-to-trough) and generates interactive HTML histograms segmented by sector and market cap | <span class="badge badge-api">FMP Required</span> |

---

## 3. Theme & Strategy

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **[Theme Detector]({{ '/en/skills/theme-detector/' | relative_url }})** | Detects trending bullish and bearish market themes with 3-dimensional scoring: Theme Heat (0-100), Lifecycle Maturity, and Confidence. 14+ cross-sector themes | <span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span> <span class="badge badge-optional">FINVIZ Optional</span> |
| **[Scenario Analyzer]({{ '/en/skills/scenario-analyzer/' | relative_url }})** | Builds 18-month scenario projections from news headlines. Dual-agent architecture with 1st/2nd/3rd order effects and recommended tickers | <span class="badge badge-free">No API</span> |
| **[Backtest Expert]({{ '/en/skills/backtest-expert/' | relative_url }})** | Professional-grade strategy validation framework with hypothesis definition, parameter robustness checks, walk-forward testing, and failure post-mortems | <span class="badge badge-free">No API</span> |
| **Options Strategy Advisor** | Educational options tool using Black-Scholes pricing. Calculates Greeks (Delta, Gamma, Theta, Vega, Rho), supports 17+ strategies, P/L simulation | <span class="badge badge-optional">FMP Optional</span> |
| **Pair Trade Screener** | Statistical arbitrage via cointegration testing. Calculates hedge ratios, mean-reversion speed (half-life), and z-score entry/exit signals | <span class="badge badge-api">FMP Required</span> |
| **Stanley Druckenmiller Investment** | Encodes Druckenmiller's macro positioning philosophy: liquidity analysis, asymmetric risk/reward, conviction sizing, and loss-cutting discipline | <span class="badge badge-free">No API</span> |
| **Strategy Pivot Designer** | Detects backtest stagnation and generates structurally different pivot proposals. 4 deterministic triggers, 3 pivot techniques across 8 strategy archetypes | <span class="badge badge-free">No API</span> |

---

## 4. Portfolio & Execution

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **Portfolio Manager** | Portfolio analysis with Alpaca MCP Server integration. Asset allocation, sector diversification, risk metrics, HOLD/ADD/TRIM/SELL recommendations, rebalancing plans | <span class="badge badge-api">Alpaca Required</span> |
| **[Trader Memory Core]({{ '/en/skills/trader-memory-core/' | relative_url }})** | Persistent thesis lifecycle tracker: register screener outputs as IDEA, manage state transitions through ENTRY_READY → ACTIVE → CLOSED, attach position sizing, schedule reviews, and generate postmortem reports with MAE/MFE | <span class="badge badge-optional">FMP Optional</span> |
| **[Position Sizer]({{ '/en/skills/position-sizer/' | relative_url }})** | Risk-based position sizing using Fixed Fractional, ATR-based, and Kelly Criterion methods. Portfolio constraints (max position %, max sector %). Works offline | <span class="badge badge-free">No API</span> |
| **[Exposure Coach]({{ '/en/skills/exposure-coach/' | relative_url }})** | Synthesizes outputs from breadth, regime, top-risk, and flow skills into a one-page Market Posture summary with net exposure ceiling (0-100%), growth-vs-value bias, and NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY recommendation | <span class="badge badge-optional">FMP Optional</span> |
| **[US Stock Analysis]({{ '/en/skills/us-stock-analysis/' | relative_url }})** | Comprehensive US equity research: fundamentals, technicals, peer comparisons, and structured investment memos with bull/bear cases | <span class="badge badge-free">No API</span> |
| **Earnings Calendar** | Fetches upcoming earnings announcements via FMP API. Focuses on mid-cap+ companies (>$2B market cap), organized by date and timing (BMO/AMC) | <span class="badge badge-api">FMP Required</span> |
| **Economic Calendar Fetcher** | Fetches economic events (FOMC, NFP, CPI, GDP) for 7-90 days via FMP API. Impact assessment (High/Medium/Low) with market implications analysis | <span class="badge badge-api">FMP Required</span> |

---

## 5. Dividend Investing

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **Kanchi Dividend SOP** | Converts Kanchi-style 5-step dividend investing into a repeatable US-stock workflow. Screening, quality checks, valuation mapping, profit filters, pullback entry planning | <span class="badge badge-free">No API</span> |
| **Kanchi Dividend Review Monitor** | Forced-review anomaly detection for T1-T5 triggers with deterministic OK/WARN/REVIEW outputs. Local rule-engine script with unit tests for trigger boundaries | <span class="badge badge-free">No API</span> |
| **Kanchi Dividend US Tax Accounting** | US dividend tax classification and account-location workflow. Qualified vs ordinary assumptions, holding-period checks, and account placement tradeoffs | <span class="badge badge-free">No API</span> |

---

## 6. Edge Research Pipeline

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **Edge Candidate Agent** | Converts daily market observations into reproducible research tickets. Exports `strategy.yaml` + `metadata.json` with interface contract validation | <span class="badge badge-free">No API</span> |
| **Edge Hint Extractor** | Extracts hints from market summary and anomaly data into `hints.yaml` for downstream concept synthesis | <span class="badge badge-free">No API</span> |
| **Edge Concept Synthesizer** | Synthesizes research tickets and hints into unified `edge_concepts.yaml` for strategy design | <span class="badge badge-free">No API</span> |
| **Edge Strategy Designer** | Designs strategy drafts (`strategy_drafts/*.yaml`) from edge concepts with entry/exit rules and risk parameters | <span class="badge badge-free">No API</span> |
| **Edge Strategy Reviewer** | Deterministic quality gate evaluating 8 criteria (C1-C8): edge plausibility, overfitting risk, sample adequacy, regime dependency, exit calibration, risk concentration, execution realism, invalidation quality. PASS/REVISE/REJECT verdicts | <span class="badge badge-free">No API</span> |
| **Edge Pipeline Orchestrator** | Orchestrates the full edge research pipeline end-to-end with review-revision feedback loop (max 2 iterations). Supports resume, review-only, and dry-run modes | <span class="badge badge-free">No API</span> |
| **[Edge Signal Aggregator]({{ '/en/skills/edge-signal-aggregator/' | relative_url }})** | Aggregates outputs from edge-candidate-agent, theme-detector, sector-analyst, and institutional-flow-tracker with configurable weighting, deduplication, and contradiction handling into a ranked conviction dashboard | <span class="badge badge-free">No API</span> |
| **[Signal Postmortem]({{ '/en/skills/signal-postmortem/' | relative_url }})** | Records and analyzes post-trade outcomes for signals generated by edge pipeline and screeners. Classifies outcomes (true positive, false positive, regime mismatch), generates weight feedback for edge-signal-aggregator and skill improvement backlog entries | <span class="badge badge-optional">FMP Optional</span> |

---

## 7. Quality & Workflow

| Skill | Description | API Requirements |
|-------|-------------|-----------------|
| **Data Quality Checker** | Validates market analysis documents for price scale inconsistencies, date/weekday mismatches, allocation total errors, and unit mismatches. Advisory mode (warnings only) | <span class="badge badge-free">No API</span> |
| **Dual-Axis Skill Reviewer** | Reviews skill quality using dual-axis method: deterministic auto scoring (5-category, 0-100) + optional LLM deep review. Powers the automated skill improvement loop | <span class="badge badge-free">No API</span> |
| **Skill Designer** | Designs new Claude skills from structured idea specifications. Produces complete skill directories (SKILL.md, references, scripts, tests) following repository conventions | <span class="badge badge-free">No API</span> |
| **Skill Idea Miner** | Mines Claude Code session logs for skill idea candidates. Extracts, scores, and backlogs new skill ideas from recent coding sessions | <span class="badge badge-free">No API</span> |
| **Skill Integration Tester** | Validates multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), and handoff integrity | <span class="badge badge-free">No API</span> |
| **[Trade Hypothesis Ideator]({{ '/en/skills/trade-hypothesis-ideator/' | relative_url }})** | Generates falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets with ranked hypothesis cards and optional strategy.yaml export | <span class="badge badge-free">No API</span> |
| **Weekly Trade Strategy** | Structured template and workflow for weekly trade strategy reports | <span class="badge badge-workflow">Workflow</span> |

---

## Which Skill Should I Use?

### I want to find growth stocks

- **[CANSLIM Screener]({{ '/en/skills/canslim-screener/' | relative_url }})** -- O'Neil's 7-component growth stock scoring
- **[VCP Screener]({{ '/en/skills/vcp-screener/' | relative_url }})** -- Minervini's volatility contraction breakout patterns
- **[FinViz Screener]({{ '/en/skills/finviz-screener/' | relative_url }})** -- Flexible natural language screening for any growth criteria

### I want dividend income

- **Value Dividend Screener** -- High-yield value stocks with sustainability checks
- **Dividend Growth Pullback Screener** -- Growth-focused dividend stocks at oversold entry points
- **Kanchi Dividend SOP** -- Systematic 5-step dividend stock selection process

### I want to understand market conditions

- **Breadth Chart Analyst** -- Market breadth health diagnosis
- **Sector Analyst** -- Sector rotation pattern assessment
- **Market Environment Analysis** -- Comprehensive global macro briefing
- **Uptrend Analyzer** -- Quantified breadth scoring across 11 sectors

### I want to analyze a specific stock

- **[US Stock Analysis]({{ '/en/skills/us-stock-analysis/' | relative_url }})** -- Full fundamental and technical research report
- **Technical Analyst** -- Pure chart-based analysis with pattern identification

### I want to manage my portfolio

- **Portfolio Manager** -- Real-time holdings analysis and rebalancing with Alpaca integration
- **[Position Sizer]({{ '/en/skills/position-sizer/' | relative_url }})** -- Risk-based position sizing with portfolio constraints
- **[Trader Memory Core]({{ '/en/skills/trader-memory-core/' | relative_url }})** -- Track theses from idea to postmortem with persistent state

### I want to find trending themes

- **[Theme Detector]({{ '/en/skills/theme-detector/' | relative_url }})** -- Cross-sector theme detection with lifecycle assessment
- **[Scenario Analyzer]({{ '/en/skills/scenario-analyzer/' | relative_url }})** -- News-driven 18-month scenario projections

### I want to trade earnings momentum

- **Earnings Trade Analyzer** -- 5-factor scoring of post-earnings reactions
- **PEAD Screener** -- Post-earnings pullback-to-breakout pattern detection
- **Earnings Calendar** -- Upcoming earnings dates with timing information

### I want to validate a strategy

- **[Backtest Expert]({{ '/en/skills/backtest-expert/' | relative_url }})** -- Professional-grade backtesting framework
- **Strategy Pivot Designer** -- Generate new approaches when optimization stalls

---

## API Requirements Matrix

| Skill | FMP | FINVIZ Elite | Alpaca |
|-------|-----|-------------|--------|
| CANSLIM Screener | Required | -- | -- |
| VCP Screener | Required | -- | -- |
| FinViz Screener | -- | Optional | -- |
| Value Dividend Screener | Required | Recommended | -- |
| Dividend Growth Pullback Screener | Required | Recommended | -- |
| Earnings Trade Analyzer | Required | -- | -- |
| PEAD Screener | Required | -- | -- |
| FTD Detector | Required | -- | -- |
| Institutional Flow Tracker | Required | -- | -- |
| Sector Analyst | -- | -- | -- |
| Breadth Chart Analyst | -- | -- | -- |
| Technical Analyst | -- | -- | -- |
| Market News Analyst | -- | -- | -- |
| Market Environment Analysis | -- | -- | -- |
| Market Breadth Analyzer | -- | -- | -- |
| Uptrend Analyzer | -- | -- | -- |
| Macro Regime Detector | Required | -- | -- |
| US Market Bubble Detector | -- | -- | -- |
| Market Top Detector | -- | -- | -- |
| Theme Detector | Optional | Recommended | -- |
| Scenario Analyzer | -- | -- | -- |
| Backtest Expert | -- | -- | -- |
| Options Strategy Advisor | Optional | -- | -- |
| Pair Trade Screener | Required | -- | -- |
| Stanley Druckenmiller Investment | -- | -- | -- |
| Strategy Pivot Designer | -- | -- | -- |
| Portfolio Manager | -- | -- | Required |
| Trader Memory Core | Optional | -- | -- |
| Position Sizer | -- | -- | -- |
| US Stock Analysis | -- | -- | -- |
| Earnings Calendar | Required | -- | -- |
| Economic Calendar Fetcher | Required | -- | -- |
| Kanchi Dividend SOP | -- | -- | -- |
| Kanchi Dividend Review Monitor | -- | -- | -- |
| Kanchi Dividend US Tax Accounting | -- | -- | -- |
| Edge Candidate Agent | -- | -- | -- |
| Edge Hint Extractor | -- | -- | -- |
| Edge Concept Synthesizer | -- | -- | -- |
| Edge Strategy Designer | -- | -- | -- |
| Edge Strategy Reviewer | -- | -- | -- |
| Edge Pipeline Orchestrator | -- | -- | -- |
| Data Quality Checker | -- | -- | -- |
| Dual-Axis Skill Reviewer | -- | -- | -- |
| Weekly Trade Strategy | -- | -- | -- |
| Edge Signal Aggregator | -- | -- | -- |
| Skill Designer | -- | -- | -- |
| Skill Idea Miner | -- | -- | -- |
| Skill Integration Tester | -- | -- | -- |
| Trade Hypothesis Ideator | -- | -- | -- |
| Exposure Coach | Optional | -- | -- |
| Signal Postmortem | Optional | -- | -- |
| Downtrend Duration Analyzer | Required | -- | -- |

"--" means not required. "Optional" means functionality is enhanced but the skill works without it.
