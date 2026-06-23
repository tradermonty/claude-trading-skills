# Claude Trading Skills

Claude Trading Skills 最初是作者个人的一个项目，目的是用 AI 改进自己的交易流程。

Claude Trading Skills 是一套基于 Claude Skills、面向时间受限的个人投资者的交易工作流工具箱。

它为这样的投资者而设计：以长期投资、ETF 和股息股作为核心（Core），并在市场条件有利时，把有纪律的波段交易作为卫星（Satellite）策略。

它的目标不是把买卖决策外包给 AI，而是把市场复盘、风险管理、交易计划、记录与持续改进结构化。它之所以开源，是因为支撑更好交易决策的工作流、清单与复盘习惯，可以通过共享实践不断改进。

这不是信号服务，也不承诺盈利。它是一套帮助交易者构建更好决策流程的工具箱。

本项目秉持 **first for self, open for others（先为自己，再开放给他人）** 的立场：先作为作者自用的实用工作流来构建，再开放分享给面临类似约束的人。

📖 **文档站点：** <https://tradermonty.github.io/claude-trading-skills/>

**项目愿景：** [`PROJECT_VISION.zh.md`](PROJECT_VISION.zh.md)

English README: [`README.md`](README.md) ・ 日本語版: [`README.ja.md`](README.ja.md)

## 免责声明

本仓库仅用于教育、研究与流程改进目的。它不是财务建议、投资顾问服务、税务建议、法律建议、信号服务，也不是券商执行平台。交易与投资有风险，可能损失本金。过往业绩、回测、筛选、报告及 AI 生成的分析均不保证未来结果。所有交易决策、仓位测算、税务/合规以及券商使用，均由用户自行负责。

本项目以 MIT 许可证提供，**按“原样（AS IS）”、不附带任何担保（WITHOUT WARRANTY）**。

## 适用人群

本仓库为以下人群设计：

- 时间受限的个人投资者
- 既做长期投资、也想在有纪律前提下获取波段收益的投资者
- 想要结构化组合复盘的股息与 ETF 投资者
- 想在寻找交易标的之前先管理风险的交易者
- 想记录交易日志并改进决策流程的投资者

它不为全自动交易、信号外包或短线刷单（scalping）而设计。

## 推荐起步路径

新用户应从以下某条运营工作流开始。每个链接都指向 [`workflows/`](workflows/) 下一份机器可读的 manifest，按顺序列出确切使用的技能、判断关卡与产物。

| 目标 | 工作流 | 锚定技能 | API 配置 |
| --- | --- | --- | --- |
| 15 分钟的每日市场检查 | [`market-regime-daily`](workflows/market-regime-daily.yaml) | market-breadth-analyzer, uptrend-analyzer, exposure-coach | 基础路径无需 API |
| 每周长期组合复盘 | [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core | 需 Alpaca；手动 CSV 为降级回退 |
| 仅在允许冒险时寻找波段候选 | [`swing-opportunity-daily`](workflows/swing-opportunity-daily.yaml) | vcp-screener, technical-analyst, position-sizer | 筛选器需 FMP |
| 记录并从每笔平仓交易中学习 | [`trade-memory-loop`](workflows/trade-memory-loop.yaml) | trader-memory-core, signal-postmortem | 手动路径无需 API |
| 每月复盘绩效并调整规则 | [`monthly-performance-review`](workflows/monthly-performance-review.yaml) | trader-memory-core, signal-postmortem, backtest-expert | 手动路径无需 API |

如何阅读 manifest 并手动运行，请见 [`workflows/README.md`](workflows/README.md)。想要一页式的“哪条工作流适合我？”指南，请见 [选择你的工作流](docs/zh/find-your-workflow.md)（[English](docs/en/find-your-workflow.md) ・ [日本語](docs/ja/find-your-workflow.md)）。

### 无需 API 密钥的起步路径

如果你没有 FMP / FINVIZ / Alpaca 订阅，先从这五个技能开始并手动运行：

1. `market-breadth-analyzer` —— 公开 CSV 的宽度评分；无需 API 密钥
2. `uptrend-analyzer` —— 公开 CSV 的上升趋势参与度；无需 API 密钥
3. `position-sizer` —— 纯计算；无 I/O
4. `trader-memory-core` —— 本地 YAML 记录交易日志
5. `signal-postmortem` —— 复盘框架

这条路径让你**无需付费数据 API** 即可复盘市场状况、测算仓位、记录决策并复盘结果。注意：“无需 API”并不等于“无需外部数据”——这些技能仍需要公开 CSV、图表截图或本地文件。精确的输入要求请见各技能在 [`skills-index.yaml`](skills-index.yaml) 中的 `integrations:` 条目。

> **正本来源：** [`skills-index.yaml`](skills-index.yaml) 是所有技能的权威索引。如果本 README、`CLAUDE.md` 或文档与 index 不一致，以 index 为准。多技能工作流同理——[`workflows/*.yaml`](workflows/) 为正本。

## 仓库结构
- `skills/<skill-name>/` – 每个交易技能的源文件夹。包含 `SKILL.md`、参考材料及任何辅助脚本。
- `skills-index.yaml` – 每个技能的正本元数据索引（id、类别、集成、工作流反向引用）。
- `workflows/` – Core + Satellite 例程的运营工作流 manifest（正本，经 `--strict-workflows` 校验）。
- `skill-packages/` – 预构建的 `.skill` 归档，可直接上传到 Claude Web App 的 **Skills** 标签页。
- `docs/` – 文档站点内容、生成的技能页面，以及 `docs/dev/metadata-and-workflow-schema.md`（schema 规范）。
- `scripts/` – 仓库级自动化，包括 schema 校验器与一键引导脚本。
- `skillsets/` – 按目标划分的安装包，为主要目标定义必需 / 推荐 / 可选技能（已发布 4 个核心技能集：market-regime、core-portfolio、swing-opportunity、trade-memory；由 Navigator 消费）。

## 快速开始
### 在 Claude Web App 中使用
1. 从 `skill-packages/` 下载与你想用的技能对应的 `.skill` 文件。
2. 在浏览器中打开 Claude，进入 **Settings → Skills**，上传该 ZIP（功能概览见 Anthropic 的 [Skills 发布文章](https://www.anthropic.com/news/skills)）。
3. 在需要它的会话中启用该技能。

### 在 Claude Code（桌面端或 CLI）中使用
1. 克隆或下载本仓库。
2. 将想用的技能文件夹（如 `backtest-expert`）复制到 Claude Code 的 **Skills** 目录（打开 Claude Code → **Settings → Skills → Open Skills Folder**，参见 [Claude Code Skills 文档](https://docs.claude.com/en/docs/claude-code/skills)）。
3. 重启或重新加载 Claude Code，使新技能被识别。

> 提示：`.skill` 包由源文件夹构建，并排除测试与本地构建产物。若想自定义某技能，请编辑源文件夹，然后在上传到 Web App 前运行 `python3 scripts/package_skills.py --skill <skill-name>`。

## 配套工作包

想要一套开箱即用的 agent 式工作流？请见配套的
[Hermes Trading Research Agent Work Package](https://github.com/tradermonty/hermes-trading-research-agent-work-package)。

它把这些技能打包进一个 Hermes 配置，提供面向任务的斜杠命令例程，例如
`/pre-market-routine`、`/after-close-review`、`/trade-journal`、`/weekly-portfolio-review` 与
`/monthly-performance-review`。

它是一个研究、记录与风险复盘助手，**而非**自动交易系统。
它**不会**下单、不提供信号服务，也不运行隐藏的定时任务；
**人工判断关卡始终居于核心**。

## 核心技能领域

本仓库包含以下领域的技能：

| 领域 | 示例技能 |
| --- | --- |
| 市场环境 | `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach` |
| 核心组合 | `portfolio-manager`, `value-dividend-screener`, `kanchi-dividend-sop` |
| 波段机会 | `vcp-screener`, `canslim-screener`, `breakout-trade-planner` |
| 交易计划 | `position-sizer`, `technical-analyst` |
| 交易记忆 | `trader-memory-core`, `signal-postmortem` |
| 策略研究 | `backtest-expert`, `edge-pipeline-orchestrator` |
| 进阶卫星 | `parabolic-short-trade-planner`, `earnings-trade-analyzer`, `options-strategy-advisor` |

下方的详细目录由 `scripts/generate_catalog_from_index.py` 从 `skills-index.yaml` **自动生成**。要更新某技能的说明，请编辑其 `skills-index.yaml` 条目并重新运行生成器（`python3 scripts/generate_catalog_from_index.py`）。更便于浏览的版本请使用文档站点。

## 详细技能目录

<!-- skills-index:start name="catalog-zh" -->
<!-- 本节由 scripts/generate_catalog_from_index.py 从 skills-index.yaml 自动生成。请勿手动编辑——请修改 index 并重新运行生成器。 -->

### 市场环境（Market Regime）

| 技能 | 概要 | 依赖 | 状态 |
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

### 核心组合（Core Portfolio）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`) | Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) that are experiencing temporary pullbacks, identified by RSI oversold conditions (RSI ≤40). | `fmp` **required**, `finviz` _recommended_ | production |
| **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`) | Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIEW states without auto-selling. | `fmp` _recommended_ | production |
| **Kanchi Dividend SOP** (`kanchi-dividend-sop`) | Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. | `fmp` _recommended_ | production |
| **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`) | Provide US dividend tax and account-location workflow for Kanchi-style income portfolios. | `local_calculation` — | production |
| **Portfolio Manager** (`portfolio-manager`) | Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. | `alpaca` **required** | production |
| **Value Dividend Screener** (`value-dividend-screener`) | Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). | `fmp` **required**, `finviz` _recommended_ | production |

### 波段机会（Swing Opportunity）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Breakout Trade Planner** (`breakout-trade-planner`) | Generate Minervini-style breakout trade plans from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates (stop-limit bracket for pre-placement, limit bracket for post-confi... | `local_calculation` — | production |
| **CANSLIM Screener** (`canslim-screener`) | Screen US stocks using William O'Neil's CANSLIM growth stock methodology. | `fmp` **required** | production |
| **Finviz Screener** (`finviz-screener`) | Build and open FinViz screener URLs from natural language requests. | `finviz` optional | production |
| **Stockbee Momentum Burst Screener** (`stockbee-momentum-burst-screener`) | Screen US stocks for Stockbee-style 3-5 day momentum burst candidates using 4% breakout, dollar breakout, range expansion, volume expansion, setup quality, and risk-distance filters. | `fmp` **required**, `prices_json` optional, `local_calculation` — | beta |
| **Theme Detector** (`theme-detector`) | Detect and analyze trending market themes across sectors. | `fmp` optional, `finviz` _recommended_ | production |
| **VCP Screener** (`vcp-screener`) | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). | `fmp` **required** | production |

### 交易计划（Trade Planning）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Position Sizer** (`position-sizer`) | Calculate risk-based position sizes for long stock trades. | `local_calculation` — | production |
| **Technical Analyst** (`technical-analyst`) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. | `chart_image` **required** | production |
| **US Stock Analysis** (`us-stock-analysis`) | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. | `user_input` **required** | production |

### 交易记忆（Trade Memory）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Signal Postmortem** (`signal-postmortem`) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills. | `local_calculation` — | production |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets with ranked hypothesis cards and optional strategy.yaml export. | `local_calculation` — | production |
| **Trade Performance Coach** (`trade-performance-coach`) | Review closed trades, partial exits, and monthly aggregates for process adherence, risk discipline, execution quality, and evidence-based trading behavior patterns, then produce next-session operating rules. | `local_calculation` — | beta |
| **Trader Memory Core** (`trader-memory-core`) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem. | `fmp` optional | production |
| **Weekly Performance Digest** (`weekly-performance-digest`) | Generate a weekly performance summary from closed trades with win rate, expectancy, and pattern analysis. | `local_calculation` — | production |

### 策略研究（Strategy Research）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Backtest Expert** (`backtest-expert`) | Expert guidance for systematic backtesting of trading strategies. | `user_input` **required** | production |
| **Edge Candidate Agent** (`edge-candidate-agent`) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. | `fmp` optional | production |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export. | `local_calculation` — | production |
| **Edge Hint Extractor** (`edge-hint-extractor`) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonical hints.yaml for downstream concept synthesis and auto detection. | `local_calculation` — | production |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and export. | `local_calculation` — | production |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradicti... | `local_calculation` — | production |
| **Edge Strategy Designer** (`edge-strategy-designer`) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation. | `local_calculation` — | production |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size adequacy, and execution realism. | `local_calculation` — | production |
| **Scenario Analyzer** (`scenario-analyzer`) | Analyze 18-month scenarios from news headlines via scenario-analyst agent with strategy-reviewer second opinion; outputs primary/secondary/tertiary impact analysis and stock picks. | `websearch` **required** | production |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market Top, Macro Regime, FTD Detector, VCP Screener, Theme Detector, CANSLIM Screener) into a unified conviction score (0-100),... | `local_calculation` — | production |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum. | `local_calculation` — | production |

### 进阶卫星（Advanced Satellite）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). | `fmp` **required** | production |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. | `fmp` **required** | production |
| **Options Strategy Advisor** (`options-strategy-advisor`) | Options trading strategy analysis and simulation tool. | `fmp` optional | production |
| **Pair Trade Screener** (`pair-trade-screener`) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities. | `fmp` **required** | production |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate intraday trigger fires from live 5-min bars. | `fmp` **required**, `alpaca` optional | production |
| **PEAD Screener** (`pead-screener`) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. | `fmp` **required** | production |

### 元 / 开发工具（Meta）

| 技能 | 概要 | 依赖 | 状态 |
|---|---|---|---|
| **Data Quality Checker** (`data-quality-checker`) | Validate data quality in market analysis documents and blog articles before publication. | `local_calculation` — | production |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. | `local_calculation` — | production |
| **Earnings Calendar** (`earnings-calendar`) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. | `fmp` **required** | production |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | Fetch upcoming economic events and data releases using FMP API. | `fmp` **required** | production |
| **Skill Designer** (`skill-designer`) | Design new Claude skills from structured idea specifications. | `local_calculation` — | production |
| **Skill Idea Miner** (`skill-idea-miner`) | Mine Claude Code session logs for skill idea candidates. | `local_calculation` — | production |
| **Skill Integration Tester** (`skill-integration-tester`) | Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. | `local_calculation` — | production |
| **Trading Skills Navigator** (`trading-skills-navigator`) | Recommend the right workflow, skillset, API profile, and setup path from a natural-language trading goal. | `local_calculation` — | production |
<!-- skills-index:end name="catalog-zh" -->

## API 需求

部分技能需要 API 密钥来访问数据：

**Financial Modeling Prep (FMP) API：**
- 免费档：250 次请求/天（多数场景足够）
- 注册：https://financialmodelingprep.com/developer/docs
- 设置环境变量：`export FMP_API_KEY=your_key_here`
- 或在提示时通过命令行参数提供密钥

**FINVIZ Elite API：**
- 订阅：$39.50/月 或 $299.50/年
- 注册：https://elite.finviz.com/
- 设置环境变量：`export FINVIZ_API_KEY=your_key_here`
- 为股息筛选器提供快速预筛选

**Alpaca Trading API：**
- 提供免费的模拟交易账户
- 注册：https://alpaca.markets/
- 需要配置 Alpaca MCP Server
- 设置环境变量：
  ```bash
  export ALPACA_API_KEY="your_api_key_id"
  export ALPACA_SECRET_KEY="your_secret_key"
  export ALPACA_PAPER="true"  # 或 "false" 表示实盘交易
  ```

> 各技能的完整 API 需求矩阵见 [`CLAUDE.md`](CLAUDE.md) 与[技能目录](docs/zh/skill-catalog.md)。

## 自定义与贡献
- 修改 `SKILL.md` 文件可调整触发描述或能力说明；打包成 ZIP 时请确保 frontmatter 的 name 与文件夹名一致。
- 在各技能文件夹内扩展参考文档或添加脚本以支持新的工作流。
- 分发更新时，请重新生成 `skill-packages/` 中对应的 `.skill` 文件，使 Web App 用户拿到最新版本：
  ```bash
  python3 scripts/package_skills.py --skill <skill-name>
  ```

## 支持与延伸阅读
- Claude Skills 发布概览：https://www.anthropic.com/news/skills
- Claude Code Skills 操作指南：https://docs.claude.com/en/docs/claude-code/skills
- Financial Modeling Prep API：https://financialmodelingprep.com/developer/docs

有疑问或建议？欢迎提交 issue，或把使用说明附在相关技能文件夹旁，让未来的用户知道如何更好地使用这些交易助手。

## 许可证

本仓库中的所有技能与参考材料均以教育和研究为目的提供。采用 MIT 许可证。
