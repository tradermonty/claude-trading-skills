---
layout: default
title: 技能指南
parent: 简体中文
nav_order: 3
has_children: true
lang_peer: /en/skills/
permalink: /zh/skills/
---

# 技能指南

各技能的实践指南，包含具体使用示例、工作流说明和进阶使用技巧。

手写指南（标有 ★）采用 10 个章节的详细结构；自动生成的指南则从每个技能的 SKILL.md 中提取概要、前提条件、工作流和资源清单。

> 建议用英文技能名（如 "CANSLIM"、"VCP"、"FinViz"）搜索。中文部分匹配搜索存在一定限制。
{: .note }

---

## 可用指南

| 技能 | 概要 | API |
|------|------|-----|
| [Backtest Expert]({{ '/zh/skills/backtest-expert/' | relative_url }}) ★ | Expert guidance for systematic backtesting of trading strategies | <span class="badge badge-free">无需 API</span> |
| [Breadth Chart Analyst]({{ '/zh/skills/breadth-chart-analyst/' | relative_url }}) | This skill should be used when analyzing market breadth charts, specifically the S&P 500 Breadth Index (200-Day MA ba... | <span class="badge badge-free">无需 API</span> |
| [Breakout Trade Planner]({{ '/zh/skills/breakout-trade-planner/' | relative_url }}) | Generate Minervini-style breakout trade plans from VCP screener output with worst-case risk calculation, portfolio he... | <span class="badge badge-free">无需 API</span> |
| [CANSLIM Screener]({{ '/zh/skills/canslim-screener/' | relative_url }}) ★ | Screen US stocks using William O'Neil's CANSLIM growth stock methodology | <span class="badge badge-api">FMP 必需</span> |
| [Data Quality Checker]({{ '/zh/skills/data-quality-checker/' | relative_url }}) | Validate data quality in market analysis documents and blog articles before publication | <span class="badge badge-free">无需 API</span> |
| [Dividend Growth Pullback Screener]({{ '/zh/skills/dividend-growth-pullback-screener/' | relative_url }}) | Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1 | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| [Downtrend Duration Analyzer]({{ '/zh/skills/downtrend-duration-analyzer/' | relative_url }}) | Analyze historical downtrend durations and generate interactive HTML histograms showing typical correction lengths by... | <span class="badge badge-free">无需 API</span> |
| [Dual Axis Skill Reviewer]({{ '/zh/skills/dual-axis-skill-reviewer/' | relative_url }}) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests... | <span class="badge badge-free">无需 API</span> |
| [Earnings Calendar]({{ '/zh/skills/earnings-calendar/' | relative_url }}) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API | <span class="badge badge-api">FMP 必需</span> |
| [Earnings Trade Analyzer]({{ '/zh/skills/earnings-trade-analyzer/' | relative_url }}) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA20... | <span class="badge badge-api">FMP 必需</span> |
| [Economic Calendar Fetcher]({{ '/zh/skills/economic-calendar-fetcher/' | relative_url }}) | Fetch upcoming economic events and data releases using FMP API | <span class="badge badge-api">FMP 必需</span> |
| [Edge Candidate Agent]({{ '/zh/skills/edge-candidate-agent/' | relative_url }}) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready c... | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> |
| [Edge Concept Synthesizer]({{ '/zh/skills/edge-concept-synthesizer/' | relative_url }}) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playb... | <span class="badge badge-free">无需 API</span> |
| [Edge Hint Extractor]({{ '/zh/skills/edge-hint-extractor/' | relative_url }}) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonica... | <span class="badge badge-free">无需 API</span> |
| [Edge Pipeline Orchestrator]({{ '/zh/skills/edge-pipeline-orchestrator/' | relative_url }}) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and e... | <span class="badge badge-free">无需 API</span> |
| [Edge Signal Aggregator]({{ '/zh/skills/edge-signal-aggregator/' | relative_url }}) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, i... | <span class="badge badge-free">无需 API</span> |
| [Edge Strategy Designer]({{ '/zh/skills/edge-strategy-designer/' | relative_url }}) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-a... | <span class="badge badge-free">无需 API</span> |
| [Edge Strategy Reviewer]({{ '/zh/skills/edge-strategy-reviewer/' | relative_url }}) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size ad... | <span class="badge badge-free">无需 API</span> |
| [Exposure Coach]({{ '/zh/skills/exposure-coach/' | relative_url }}) | Generate a one-page Market Posture summary with net exposure ceiling, growth-vs-value bias, participation breadth, an... | <span class="badge badge-free">无需 API</span> |
| [Finviz Screener]({{ '/zh/skills/finviz-screener/' | relative_url }}) ★ | Build and open FinViz screener URLs from natural language requests | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| [FTD Detector]({{ '/zh/skills/ftd-detector/' | relative_url }}) | Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology | <span class="badge badge-api">FMP 必需</span> |
| [Ibd Distribution Day Monitor]({{ '/zh/skills/ibd-distribution-day-monitor/' | relative_url }}) | Detect IBD-style Distribution Days for QQQ/SPY (close down at least 0 | <span class="badge badge-api">FMP 必需</span> |
| [Institutional Flow Tracker]({{ '/zh/skills/institutional-flow-tracker/' | relative_url }}) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data | <span class="badge badge-api">FMP 必需</span> |
| [Kanchi Dividend Review Monitor]({{ '/zh/skills/kanchi-dividend-review-monitor/' | relative_url }}) | Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIE... | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> |
| [Kanchi Dividend SOP]({{ '/zh/skills/kanchi-dividend-sop/' | relative_url }}) | Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> |
| [Kanchi Dividend US Tax Accounting]({{ '/zh/skills/kanchi-dividend-us-tax-accounting/' | relative_url }}) | Provide US dividend tax and account-location workflow for Kanchi-style income portfolios | <span class="badge badge-free">无需 API</span> |
| [Macro Regime Detector]({{ '/zh/skills/macro-regime-detector/' | relative_url }}) | Detect structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis | <span class="badge badge-free">无需 API</span> |
| [Market Breadth Analyzer]({{ '/zh/skills/market-breadth-analyzer/' | relative_url }}) ★ | Quantifies market breadth health using TraderMonty's public CSV data | <span class="badge badge-free">无需 API</span> |
| [Market Environment Analysis]({{ '/zh/skills/market-environment-analysis/' | relative_url }}) | Comprehensive market environment analysis and reporting tool | <span class="badge badge-free">无需 API</span> |
| [Market News Analyst]({{ '/zh/skills/market-news-analyst/' | relative_url }}) ★ | This skill should be used when analyzing recent market-moving news events and their impact on equity markets and comm... | <span class="badge badge-free">无需 API</span> |
| [Market Top Detector]({{ '/zh/skills/market-top-detector/' | relative_url }}) | Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defen... | <span class="badge badge-free">无需 API</span> |
| [Options Strategy Advisor]({{ '/zh/skills/options-strategy-advisor/' | relative_url }}) | Options trading strategy analysis and simulation tool | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> |
| [Pair Trade Screener]({{ '/zh/skills/pair-trade-screener/' | relative_url }}) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities | <span class="badge badge-api">FMP 必需</span> |
| [Parabolic Short Trade Planner]({{ '/zh/skills/parabolic-short-trade-planner/' | relative_url }}) | Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate i... | <span class="badge badge-api">FMP 必需</span> |
| [PEAD Screener]({{ '/zh/skills/pead-screener/' | relative_url }}) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns | <span class="badge badge-api">FMP 必需</span> |
| [Portfolio Manager]({{ '/zh/skills/portfolio-manager/' | relative_url }}) | Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze as... | <span class="badge badge-api">Alpaca 必需</span> |
| [Position Sizer]({{ '/zh/skills/position-sizer/' | relative_url }}) ★ | Calculate risk-based position sizes for long stock trades | <span class="badge badge-free">无需 API</span> |
| [Scenario Analyzer]({{ '/zh/skills/scenario-analyzer/' | relative_url }}) | Skill that analyzes 18-month scenarios from a news headline | <span class="badge badge-free">无需 API</span> |
| [Sector Analyst]({{ '/zh/skills/sector-analyst/' | relative_url }}) | This skill should be used when analyzing sector rotation patterns and market cycle positioning | <span class="badge badge-free">无需 API</span> |
| [Signal Postmortem]({{ '/zh/skills/signal-postmortem/' | relative_url }}) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills | <span class="badge badge-free">无需 API</span> |
| [Skill Designer]({{ '/zh/skills/skill-designer/' | relative_url }}) | Design new Claude skills from structured idea specifications | <span class="badge badge-free">无需 API</span> |
| [Skill Idea Miner]({{ '/zh/skills/skill-idea-miner/' | relative_url }}) | Mine Claude Code session logs for skill idea candidates | <span class="badge badge-free">无需 API</span> |
| [Skill Integration Tester]({{ '/zh/skills/skill-integration-tester/' | relative_url }}) | Validate multi-skill workflows defined in CLAUDE | <span class="badge badge-free">无需 API</span> |
| [Stanley Druckenmiller Investment]({{ '/zh/skills/stanley-druckenmiller-investment/' | relative_url }}) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market To... | <span class="badge badge-free">无需 API</span> |
| [Stockbee Momentum Burst Screener]({{ '/zh/skills/stockbee-momentum-burst-screener/' | relative_url }}) | Screen US stocks for Stockbee-style short-term Momentum Burst setups using 4% breakout, dollar breakout, range expans... | <span class="badge badge-api">FMP 必需</span> |
| [Strategy Pivot Designer]({{ '/zh/skills/strategy-pivot-designer/' | relative_url }}) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuni... | <span class="badge badge-free">无需 API</span> |
| [Technical Analyst]({{ '/zh/skills/technical-analyst/' | relative_url }}) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs | <span class="badge badge-free">无需 API</span> |
| [Theme Detector]({{ '/zh/skills/theme-detector/' | relative_url }}) ★ | Detect and analyze trending market themes across sectors | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| [Trade Hypothesis Ideator]({{ '/zh/skills/trade-hypothesis-ideator/' | relative_url }}) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets | <span class="badge badge-free">无需 API</span> |
| [Trade Performance Coach]({{ '/zh/skills/trade-performance-coach/' | relative_url }}) | Review closed trades, partial exits, and monthly trade aggregates for process adherence, risk discipline, execution q... | <span class="badge badge-free">无需 API</span> |
| [Trader Memory Core]({{ '/zh/skills/trader-memory-core/' | relative_url }}) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem | <span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span> |
| [Trading Skills Navigator]({{ '/zh/skills/trading-skills-navigator/' | relative_url }}) | Recommend the right trading workflow, skillset, API profile, and setup path from a natural-language goal | <span class="badge badge-free">无需 API</span> |
| [Uptrend Analyzer]({{ '/zh/skills/uptrend-analyzer/' | relative_url }}) | Analyzes market breadth using Monty's Uptrend Ratio Dashboard data to diagnose the current market environment | <span class="badge badge-free">无需 API</span> |
| [US Market Bubble Detector]({{ '/zh/skills/us-market-bubble-detector/' | relative_url }}) ★ | Evaluates market bubble risk through quantitative data-driven analysis using the revised Minsky/Kindleberger framewor... | <span class="badge badge-free">无需 API</span> |
| [US Stock Analysis]({{ '/zh/skills/us-stock-analysis/' | relative_url }}) ★ | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), tech... | <span class="badge badge-free">无需 API</span> |
| [Value Dividend Screener]({{ '/zh/skills/value-dividend-screener/' | relative_url }}) | Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B rat... | <span class="badge badge-api">FMP 必需</span> <span class="badge badge-optional">FINVIZ 可选</span> |
| [VCP Screener]({{ '/zh/skills/vcp-screener/' | relative_url }}) ★ | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP) and detect historical VCPs in a singl... | <span class="badge badge-api">FMP 必需</span> |
| [Weekly Performance Digest]({{ '/zh/skills/weekly-performance-digest/' | relative_url }}) | Generate a weekly performance summary from closed trader-memory-core theses — win rate, expectancy, profit factor, R-... | <span class="badge badge-free">无需 API</span> |
