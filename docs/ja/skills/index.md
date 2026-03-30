---
layout: default
title: スキルガイド
parent: 日本語
nav_order: 3
has_children: true
lang_peer: /en/skills/
permalink: /ja/skills/
---

# スキルガイド

各スキルの実践ガイドです。具体的な使用例、ワークフローの解説、活用のコツを含みます。

手動作成ガイド（★マーク）は10セクション構成の詳細ガイドです。自動生成ガイドはSKILL.mdから概要・前提条件・ワークフロー・リソース一覧を抽出したものです。

> 検索は英語スキル名（"CANSLIM", "VCP", "FinViz"等）での検索を推奨します。日本語の部分一致検索は制限があります。
{: .note }

---

## 利用可能なガイド

| スキル | 概要 | API |
|--------|------|-----|
| [Backtest Expert]({{ '/ja/skills/backtest-expert/' | relative_url }}) ★ | Expert guidance for systematic backtesting of trading strategies | <span class="badge badge-free">API不要</span> |
| [Breadth Chart Analyst]({{ '/ja/skills/breadth-chart-analyst/' | relative_url }}) | This skill should be used when analyzing market breadth charts, specifically the S&P 500 Breadth Index (200-Day MA ba... | <span class="badge badge-free">API不要</span> |
| [CANSLIM Screener]({{ '/ja/skills/canslim-screener/' | relative_url }}) ★ | Screen US stocks using William O'Neil's CANSLIM growth stock methodology | <span class="badge badge-free">API不要</span> |
| [Data Quality Checker]({{ '/ja/skills/data-quality-checker/' | relative_url }}) | Validate data quality in market analysis documents and blog articles before publication | <span class="badge badge-free">API不要</span> |
| [Dividend Growth Pullback Screener]({{ '/ja/skills/dividend-growth-pullback-screener/' | relative_url }}) | Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1 | <span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span> |
| [Downtrend Duration Analyzer]({{ '/ja/skills/downtrend-duration-analyzer/' | relative_url }}) | Analyze historical downtrend durations and generate interactive HTML histograms showing typical correction lengths by... | <span class="badge badge-free">API不要</span> |
| [Dual Axis Skill Reviewer]({{ '/ja/skills/dual-axis-skill-reviewer/' | relative_url }}) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests... | <span class="badge badge-free">API不要</span> |
| [Earnings Calendar]({{ '/ja/skills/earnings-calendar/' | relative_url }}) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API | <span class="badge badge-api">FMP必須</span> |
| [Earnings Trade Analyzer]({{ '/ja/skills/earnings-trade-analyzer/' | relative_url }}) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA20... | <span class="badge badge-api">FMP必須</span> |
| [Economic Calendar Fetcher]({{ '/ja/skills/economic-calendar-fetcher/' | relative_url }}) | Fetch upcoming economic events and data releases using FMP API | <span class="badge badge-api">FMP必須</span> |
| [Edge Candidate Agent]({{ '/ja/skills/edge-candidate-agent/' | relative_url }}) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready c... | <span class="badge badge-free">API不要</span> |
| [Edge Concept Synthesizer]({{ '/ja/skills/edge-concept-synthesizer/' | relative_url }}) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playb... | <span class="badge badge-free">API不要</span> |
| [Edge Hint Extractor]({{ '/ja/skills/edge-hint-extractor/' | relative_url }}) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonica... | <span class="badge badge-free">API不要</span> |
| [Edge Pipeline Orchestrator]({{ '/ja/skills/edge-pipeline-orchestrator/' | relative_url }}) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and e... | <span class="badge badge-free">API不要</span> |
| [Edge Signal Aggregator]({{ '/ja/skills/edge-signal-aggregator/' | relative_url }}) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, i... | <span class="badge badge-free">API不要</span> |
| [Edge Strategy Designer]({{ '/ja/skills/edge-strategy-designer/' | relative_url }}) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-a... | <span class="badge badge-free">API不要</span> |
| [Edge Strategy Reviewer]({{ '/ja/skills/edge-strategy-reviewer/' | relative_url }}) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size ad... | <span class="badge badge-free">API不要</span> |
| [Exposure Coach]({{ '/ja/skills/exposure-coach/' | relative_url }}) | Generate a one-page Market Posture summary with net exposure ceiling, growth-vs-value bias, participation breadth, an... | <span class="badge badge-free">API不要</span> |
| [Finviz Screener]({{ '/ja/skills/finviz-screener/' | relative_url }}) ★ | Build and open FinViz screener URLs from natural language requests | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FINVIZ任意</span> |
| [FTD Detector]({{ '/ja/skills/ftd-detector/' | relative_url }}) | Detects Follow-Through Day (FTD) signals for market bottom confirmation using William O'Neil's methodology | <span class="badge badge-free">API不要</span> |
| [Institutional Flow Tracker]({{ '/ja/skills/institutional-flow-tracker/' | relative_url }}) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data | <span class="badge badge-api">FMP必須</span> |
| [Kanchi Dividend Review Monitor]({{ '/ja/skills/kanchi-dividend-review-monitor/' | relative_url }}) | Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIE... | <span class="badge badge-free">API不要</span> |
| [Kanchi Dividend SOP]({{ '/ja/skills/kanchi-dividend-sop/' | relative_url }}) | Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure | <span class="badge badge-free">API不要</span> |
| [Kanchi Dividend US Tax Accounting]({{ '/ja/skills/kanchi-dividend-us-tax-accounting/' | relative_url }}) | Provide US dividend tax and account-location workflow for Kanchi-style income portfolios | <span class="badge badge-free">API不要</span> |
| [Macro Regime Detector]({{ '/ja/skills/macro-regime-detector/' | relative_url }}) | Detect structural macro regime transitions (1-2 year horizon) using cross-asset ratio analysis | <span class="badge badge-free">API不要</span> |
| [Market Breadth Analyzer]({{ '/ja/skills/market-breadth-analyzer/' | relative_url }}) ★ | Quantifies market breadth health using TraderMonty's public CSV data | <span class="badge badge-free">API不要</span> |
| [Market Environment Analysis]({{ '/ja/skills/market-environment-analysis/' | relative_url }}) | Comprehensive market environment analysis and reporting tool | <span class="badge badge-free">API不要</span> |
| [Market News Analyst]({{ '/ja/skills/market-news-analyst/' | relative_url }}) ★ | This skill should be used when analyzing recent market-moving news events and their impact on equity markets and comm... | <span class="badge badge-free">API不要</span> |
| [Market Top Detector]({{ '/ja/skills/market-top-detector/' | relative_url }}) | Detects market top probability using O'Neil Distribution Days, Minervini Leading Stock Deterioration, and Monty Defen... | <span class="badge badge-free">API不要</span> |
| [Options Strategy Advisor]({{ '/ja/skills/options-strategy-advisor/' | relative_url }}) | Options trading strategy analysis and simulation tool | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span> |
| [Pair Trade Screener]({{ '/ja/skills/pair-trade-screener/' | relative_url }}) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities | <span class="badge badge-api">FMP必須</span> |
| [PEAD Screener]({{ '/ja/skills/pead-screener/' | relative_url }}) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns | <span class="badge badge-api">FMP必須</span> |
| [Portfolio Manager]({{ '/ja/skills/portfolio-manager/' | relative_url }}) | Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze as... | <span class="badge badge-api">Alpaca必須</span> |
| [Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }}) ★ | Calculate risk-based position sizes for long stock trades | <span class="badge badge-free">API不要</span> |
| [Scenario Analyzer]({{ '/ja/skills/scenario-analyzer/' | relative_url }}) | ニュースヘッドラインを入力として18ヶ月シナリオを分析するスキル。
scenario-analystエージェントで主分析を実行し、
strategy-reviewerエージェントでセカンドオピニオンを取得。
1次・2次・3次影響、推奨... | <span class="badge badge-free">API不要</span> |
| [Sector Analyst]({{ '/ja/skills/sector-analyst/' | relative_url }}) | This skill should be used when analyzing sector rotation patterns and market cycle positioning | <span class="badge badge-free">API不要</span> |
| [Signal Postmortem]({{ '/ja/skills/signal-postmortem/' | relative_url }}) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills | <span class="badge badge-free">API不要</span> |
| [Skill Designer]({{ '/ja/skills/skill-designer/' | relative_url }}) | Design new Claude skills from structured idea specifications | <span class="badge badge-free">API不要</span> |
| [Skill Idea Miner]({{ '/ja/skills/skill-idea-miner/' | relative_url }}) | Mine Claude Code session logs for skill idea candidates | <span class="badge badge-free">API不要</span> |
| [Skill Integration Tester]({{ '/ja/skills/skill-integration-tester/' | relative_url }}) | Validate multi-skill workflows defined in CLAUDE | <span class="badge badge-free">API不要</span> |
| [Stanley Druckenmiller Investment]({{ '/ja/skills/stanley-druckenmiller-investment/' | relative_url }}) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market To... | <span class="badge badge-free">API不要</span> |
| [Strategy Pivot Designer]({{ '/ja/skills/strategy-pivot-designer/' | relative_url }}) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuni... | <span class="badge badge-free">API不要</span> |
| [Technical Analyst]({{ '/ja/skills/technical-analyst/' | relative_url }}) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs | <span class="badge badge-free">API不要</span> |
| [Theme Detector]({{ '/ja/skills/theme-detector/' | relative_url }}) ★ | Detect and analyze trending market themes across sectors | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span> <span class="badge badge-optional">FINVIZ任意</span> |
| [Trade Hypothesis Ideator]({{ '/ja/skills/trade-hypothesis-ideator/' | relative_url }}) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets | <span class="badge badge-free">API不要</span> |
| [Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }}) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span> |
| [Uptrend Analyzer]({{ '/ja/skills/uptrend-analyzer/' | relative_url }}) | Analyzes market breadth using Monty's Uptrend Ratio Dashboard data to diagnose the current market environment | <span class="badge badge-free">API不要</span> |
| [US Market Bubble Detector]({{ '/ja/skills/us-market-bubble-detector/' | relative_url }}) ★ | Evaluates market bubble risk through quantitative data-driven analysis using the revised Minsky/Kindleberger framewor... | <span class="badge badge-free">API不要</span> |
| [US Stock Analysis]({{ '/ja/skills/us-stock-analysis/' | relative_url }}) ★ | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), tech... | <span class="badge badge-free">API不要</span> |
| [Value Dividend Screener]({{ '/ja/skills/value-dividend-screener/' | relative_url }}) | Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B rat... | <span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span> |
| [VCP Screener]({{ '/ja/skills/vcp-screener/' | relative_url }}) ★ | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP) | <span class="badge badge-free">API不要</span> |

★ = 使用例・トラブルシューティング・CLIリファレンスを含む詳細ガイド

全スキルの一覧は[スキルカタログ]({{ '/ja/skill-catalog/' | relative_url }})を参照してください。
