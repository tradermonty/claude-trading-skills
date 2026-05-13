# Claude Trading Skills

Claude Trading Skills は、作者自身が AI を使って自分のトレードプロセスを改善したいと考えたことから始まりました。

Claude Trading Skills は、時間制約のある個人投資家が、Claude を使って投資・トレード判断を仕組み化するための Claude Skills 集です。

長期投資、ETF、配当株を Core としつつ、相場環境が整ったときには Satellite として規律あるスイングトレードで追加リターンを狙う投資家を主対象にしています。

目的は、AI に売買判断を丸投げすることではありません。市場確認、リスク管理、トレード計画、記録、振り返りを再現可能なプロセスにすることです。より良いトレード判断を支えるワークフロー、チェックリスト、振り返りの習慣は、共有された実践を通じて改善できると考えているため、オープンソースとして公開しています。

これは売買シグナル配信や利益保証のためのプロジェクトではありません。より良い判断プロセスを作りたいトレーダーのための道具箱です。

このプロジェクトの立ち位置は **first for self, open for others** です。まず作者自身が実際に使う実践的な workflow として作り、それを同じ制約を持つ人にも役立つ可能性があるものとして公開します。

📖 **ドキュメントサイト:** <https://tradermonty.github.io/claude-trading-skills/>

**プロジェクトビジョン:** [`PROJECT_VISION.ja.md`](PROJECT_VISION.ja.md)

English README is available at [`README.md`](README.md).

## 免責

このリポジトリは、教育、研究、プロセス改善を目的としたものです。金融助言、投資顧問、税務・法務助言、売買シグナル配信、ブローカー注文執行を提供するものではありません。投資・トレードには元本損失を含むリスクがあります。過去パフォーマンス、バックテスト、スクリーニング結果、レポート、AI が生成した分析は将来の成果を保証しません。最終的な売買判断、ポジションサイズ、税務・規制遵守、ブローカー利用判断は、すべてユーザー自身の責任です。

このプロジェクトは MIT License に基づき、**AS IS, WITHOUT WARRANTY**、つまり保証なしで提供されます。

## このリポジトリが向いている人

このリポジトリは、以下のような人に向いています。

- 投資に使える時間が限られている個人投資家
- 長期投資を土台にしつつ、相場が良いときだけスイングトレードも行いたい人
- 配当株、ETF、保有株を定期的に点検したい人
- 銘柄探しより先に、市場環境とリスクを確認したい人
- トレードを記録し、振り返りから改善したい人

完全自動売買、売買シグナルの丸投げ、短期スキャルピングを主目的にする人向けではありません。

## おすすめの始め方

初めて使う場合は、以下のいずれかの運用ワークフローから始めてください。各リンクは [`workflows/`](workflows/) 以下の機械可読 manifest を指していて、使うスキル・判断ゲート・artifact の流れを順番通りに記述しています。

| 目的 | ワークフロー | 主要スキル | API プロファイル |
| --- | --- | --- | --- |
| 毎朝15分で相場を確認したい | [`market-regime-daily`](workflows/market-regime-daily.yaml) | market-breadth-analyzer, uptrend-analyzer, exposure-coach | API なし可 |
| 長期ポートフォリオを週次で見直したい | [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core | Alpaca（または手動 CSV） |
| 相場環境が許すときだけスイング候補を探す | [`swing-opportunity-daily`](workflows/swing-opportunity-daily.yaml) | vcp-screener, technical-analyst, position-sizer | FMP 必須 |
| 約定後にトレードを記録して学ぶ | [`trade-memory-loop`](workflows/trade-memory-loop.yaml) | trader-memory-core, signal-postmortem | API なし可 |
| 月次でパフォーマンスとルールを見直す | [`monthly-performance-review`](workflows/monthly-performance-review.yaml) | trader-memory-core, signal-postmortem, backtest-expert | API なし可 |

manifest の読み方や手動実行手順は [`workflows/README.md`](workflows/README.md) を参照してください。

### API キー不要の入口

FMP / FINVIZ / Alpaca の有料サブスクをまだ持っていない場合は、まずこの5つのスキルを手動で回してください。

1. `market-breadth-analyzer` — 公開 CSV による breadth スコア、API キー不要
2. `uptrend-analyzer` — 公開 CSV の uptrend 比率、API キー不要
3. `position-sizer` — 純粋計算、I/O なし
4. `trader-memory-core` — ローカル YAML での journaling
5. `signal-postmortem` — レビューフレームワーク

この導線だけで「相場確認 → ポジションサイズ → トレード記録 → レビュー」の最小ループが**有料データ API なし**で回せます。ただし「API なし」は「外部データなし」ではなく、公開 CSV・チャート画像・ローカルファイルは依然として必要です。各スキルの正確な入力要件は [`skills-index.yaml`](skills-index.yaml) の `integrations:` 欄を参照してください。

> **正本（canonical source）:** [`skills-index.yaml`](skills-index.yaml) が全スキルメタデータの正本です。本 README・`CLAUDE.md`・docs 側との内容差があった場合は index 側が正です。マルチスキル導線についても同様で、[`workflows/*.yaml`](workflows/) が正本です。

## リポジトリ構成
- `skills/<skill-name>/` – 各スキルのソースフォルダ。`SKILL.md`、参照資料、補助スクリプトが含まれます。
- `skills-index.yaml` – 全スキルのメタデータ正本（id・カテゴリ・integrations・workflows 参照）。
- `workflows/` – Core + Satellite 運用ワークフローの manifest 群（正本、`--strict-workflows` で validator 検証済み）。
- `skill-packages/` – Claudeウェブアプリの**Skills**タブへそのままアップロードできる`.skill`パッケージ置き場。
- `docs/` – ドキュメントサイトのコンテンツ、生成済みスキルページ、`docs/dev/metadata-and-workflow-schema.md`（スキーマ仕様書）。
- `scripts/` – リポジトリ全体の自動化・保守スクリプト。validator や bootstrap helper を含む。
- `skillsets/` – 追加予定の目的別スキルセット manifest（vision Phase 2、未作成）。

## はじめに
### Claudeウェブアプリで使う場合
1. 利用したいスキルに対応する`.skill`ファイルを`skill-packages/`からダウンロードします。
2. ブラウザでClaudeを開き、**Settings → Skills**に進んでZIPをアップロードします（詳しくはAnthropicの[Skillsローンチ記事](https://www.anthropic.com/news/skills)を参照）。
3. 必要な会話内でスキルを有効化します。

### Claude Code（デスクトップ/CLI）で使う場合
1. このリポジトリをクローン、もしくはダウンロードします。
2. 使いたいスキルのフォルダ（例: `backtest-expert`）をClaude Codeの**Skills**ディレクトリにコピーします（Claude Code → **Settings → Skills → Open Skills Folder**。詳細は[Claude Code Skillsドキュメント](https://docs.claude.com/en/docs/claude-code/skills)を参照）。
3. Claude Codeを再起動、またはリロードすると新しいスキルが認識されます。

> ヒント: ソースフォルダとZIPの内容は同一です。スキルをカスタマイズする場合はソースフォルダを編集し、ウェブアプリ向けに配布するときは再度ZIP化してください。

## 主要スキル領域

このリポジトリには、以下の領域のスキルが含まれます。

| 領域 | 代表スキル |
| --- | --- |
| Market Regime | `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach` |
| Core Portfolio | `portfolio-manager`, `value-dividend-screener`, `kanchi-dividend-sop` |
| Swing Opportunities | `vcp-screener`, `canslim-screener`, `breakout-trade-planner` |
| Trade Planning | `position-sizer`, `technical-analyst` |
| Trade Memory | `trader-memory-core`, `signal-postmortem` |
| Strategy Research | `backtest-expert`, `edge-pipeline-orchestrator` |
| Advanced Satellite | `parabolic-short-trade-planner`, `earnings-trade-analyzer`, `options-strategy-advisor` |

以下の詳細カタログは `skills-index.yaml` から `scripts/generate_catalog_from_index.py` で**自動生成**されます。スキル説明を更新する場合は `skills-index.yaml` を編集してから generator を再実行（`python3 scripts/generate_catalog_from_index.py`）してください。より見やすい一覧はドキュメントサイトを参照してください。

## 詳細スキル一覧

<!-- skills-index:start name="catalog-ja" -->
<!-- 本セクションは skills-index.yaml から scripts/generate_catalog_from_index.py で自動生成されます。手動編集せず、index を更新して generator を再実行してください。 -->

### 相場環境（Market Regime）

| スキル | サマリ | 依存 | ステータス |
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

### コアポートフォリオ（Core Portfolio）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`) | Use this skill to find high-quality dividend growth stocks (12%+ annual dividend growth, 1.5%+ yield) that are experiencing temporary pullbacks, identified by RSI oversold conditions (RSI ≤40). | `fmp` **required**, `finviz` _recommended_ | production |
| **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`) | Monitor dividend portfolios with Kanchi-style forced-review triggers (T1-T5) and convert anomalies into OK/WARN/REVIEW states without auto-selling. | `fmp` _recommended_ | production |
| **Kanchi Dividend SOP** (`kanchi-dividend-sop`) | Convert Kanchi-style dividend investing into a repeatable US-stock operating procedure. | `fmp` _recommended_ | production |
| **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`) | Provide US dividend tax and account-location workflow for Kanchi-style income portfolios. | `local_calculation` — | production |
| **Portfolio Manager** (`portfolio-manager`) | Comprehensive portfolio analysis using Alpaca MCP Server integration to fetch holdings and positions, then analyze asset allocation, risk metrics, individual stock positions, diversification, and generate rebalancing recommendations. | `alpaca` **required** | production |
| **Value Dividend Screener** (`value-dividend-screener`) | Screen US stocks for high-quality dividend opportunities combining value characteristics (P/E ratio under 20, P/B ratio under 2), attractive yields (3% or higher), and consistent growth (dividend/revenue/EPS trending up over 3 years). | `fmp` **required**, `finviz` _recommended_ | production |

### スイング候補（Swing Opportunity）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Breakout Trade Planner** (`breakout-trade-planner`) | Generate Minervini-style breakout trade plans from VCP screener output with worst-case risk calculation, portfolio heat management, and Alpaca-compatible order templates (stop-limit bracket for pre-placement, limit bracket for post-confi... | `local_calculation` — | production |
| **CANSLIM Screener** (`canslim-screener`) | Screen US stocks using William O'Neil's CANSLIM growth stock methodology. | `fmp` **required** | production |
| **Finviz Screener** (`finviz-screener`) | Build and open FinViz screener URLs from natural language requests. | `finviz` optional | production |
| **Theme Detector** (`theme-detector`) | Detect and analyze trending market themes across sectors. | `fmp` optional, `finviz` _recommended_ | production |
| **VCP Screener** (`vcp-screener`) | Screen S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP). | `fmp` **required** | production |

### トレード計画（Trade Planning）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Position Sizer** (`position-sizer`) | Calculate risk-based position sizes for long stock trades. | `local_calculation` — | production |
| **Technical Analyst** (`technical-analyst`) | This skill should be used when analyzing weekly price charts for stocks, stock indices, cryptocurrencies, or forex pairs. | `chart_image` **required** | production |
| **US Stock Analysis** (`us-stock-analysis`) | Comprehensive US stock analysis including fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), stock comparisons, and investment report generation. | `user_input` **required** | production |

### トレード記録（Trade Memory）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Signal Postmortem** (`signal-postmortem`) | Record and analyze post-trade outcomes for signals generated by edge pipeline and other skills. | `local_calculation` — | production |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | >. | `local_calculation` — | production |
| **Trader Memory Core** (`trader-memory-core`) | Track investment theses across their lifecycle — from screening idea to closed position with postmortem. | `fmp` optional | production |

### 戦略リサーチ（Strategy Research）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Backtest Expert** (`backtest-expert`) | Expert guidance for systematic backtesting of trading strategies. | `user_input` **required** | production |
| **Edge Candidate Agent** (`edge-candidate-agent`) | Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. | `fmp` optional | production |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export. | `local_calculation` — | production |
| **Edge Hint Extractor** (`edge-hint-extractor`) | Extract edge hints from daily market observations and news reactions, with optional LLM ideation, and output canonical hints.yaml for downstream concept synthesis and auto detection. | `local_calculation` — | production |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and export. | `local_calculation` — | production |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradicti... | `local_calculation` — | production |
| **Edge Strategy Designer** (`edge-strategy-designer`) | Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation. | `local_calculation` — | production |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | >. | `local_calculation` — | production |
| **Scenario Analyzer** (`scenario-analyzer`) | |. | `websearch` **required** | production |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | Druckenmiller Strategy Synthesizer - Integrates 8 upstream skill outputs (Market Breadth, Uptrend Analysis, Market Top, Macro Regime, FTD Detector, VCP Screener, Theme Detector, CANSLIM Screener) into a unified conviction score (0-100),... | `local_calculation` — | production |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum. | `local_calculation` — | production |

### アドバンスト・サテライト（Advanced Satellite）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | Analyze recent post-earnings stocks using a 5-factor scoring system (Gap Size, Pre-Earnings Trend, Volume Trend, MA200 Position, MA50 Position). | `fmp` **required** | production |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | Use this skill to track institutional investor ownership changes and portfolio flows using 13F filings data. | `fmp` **required** | production |
| **Options Strategy Advisor** (`options-strategy-advisor`) | Options trading strategy analysis and simulation tool. | `fmp` optional | production |
| **Pair Trade Screener** (`pair-trade-screener`) | Statistical arbitrage tool for identifying and analyzing pair trading opportunities. | `fmp` **required** | production |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | Screen US equities for parabolic exhaustion patterns and generate conditional pre-market short plans, then evaluate intraday trigger fires from live 5-min bars. | `fmp` **required**, `alpaca` optional | production |
| **PEAD Screener** (`pead-screener`) | Screen post-earnings gap-up stocks for PEAD (Post-Earnings Announcement Drift) patterns. | `fmp` **required** | production |

### メタ / 開発ツール（Meta）

| スキル | サマリ | 依存 | ステータス |
|---|---|---|---|
| **Data Quality Checker** (`data-quality-checker`) | Validate data quality in market analysis documents and blog articles before publication. | `local_calculation` — | production |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | Review skills in any project using a dual-axis method: (1) deterministic code-based checks (structure, scripts, tests, execution safety) and (2) LLM deep review findings. | `local_calculation` — | production |
| **Earnings Calendar** (`earnings-calendar`) | This skill retrieves upcoming earnings announcements for US stocks using the Financial Modeling Prep (FMP) API. | `fmp` **required** | production |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | Fetch upcoming economic events and data releases using FMP API. | `fmp` **required** | production |
| **Skill Designer** (`skill-designer`) | Design new Claude skills from structured idea specifications. | `local_calculation` — | production |
| **Skill Idea Miner** (`skill-idea-miner`) | Mine Claude Code session logs for skill idea candidates. | `local_calculation` — | production |
| **Skill Integration Tester** (`skill-integration-tester`) | Validate multi-skill workflows defined in CLAUDE.md by checking skill existence, inter-skill data contracts (JSON schema compatibility), file naming conventions, and handoff integrity. | `local_calculation` — | production |
<!-- skills-index:end name="catalog-ja" -->

<details>
<summary>従来の手動カタログ（参考用、自動生成版レビュー後に削除予定）</summary>

### マーケット分析・リサーチ

- **セクターアナリスト** (`sector-analyst`)
  - セクターのアップトレンド比率データをCSVから取得（APIキー不要）し、マーケットサイクル理論に基づくセクターローテーションパターンを分析。
  - シクリカル vs ディフェンシブのリスクレジームスコア算出、オーバーボート/オーバーソールド判定、マーケットサイクルフェーズ推定（Early/Mid/Late CycleまたはRecession）。
  - チャート画像のオプション提供で業種レベルの補助分析が可能。
  - セクターローテーション戦略のためのシナリオベース確率評価を生成。

- **ブレッド（市場幅）チャートアナリスト** (`breadth-chart-analyst`)
  - S&P 500ブレッドインデックスと米国株上昇トレンド銘柄比率チャートを分析し、市場の健全性とポジショニングを評価。
  - 市場幅指標に基づく中期的戦略と短期的戦術の市場見通しを提供。
  - 強気相場フェーズ（健全な市場幅、市場幅縮小、分配）と弱気相場シグナルを識別。
  - 詳細な市場幅解釈フレームワークと歴史的パターン参照を含む。

- **テクニカルアナリスト** (`technical-analyst`)
  - 株式、指数、暗号通貨、為替ペアの週足チャートを純粋なテクニカル分析で評価。
  - ファンダメンタルバイアスなしで、トレンド、サポート/レジスタンスレベル、チャートパターン、モメンタム指標を識別。
  - トレンド変化の具体的なトリガーレベルを含むシナリオベース確率評価を生成。
  - エリオット波動、ダウ理論、日本のローソク足、テクニカル指標解釈を参照資料として収録。

- **マーケットニュースアナリスト** (`market-news-analyst`)
  - WebSearch/WebFetchを使った自動収集により、過去10日間の市場動向ニュースイベントを分析。
  - FOMCの決定、中央銀行の政策、メガキャップ決算、地政学イベント、コモディティ市場要因に焦点。
  - 定量的スコアリングフレームワーク（価格インパクト×広がり×将来重要性）を使用したインパクトランク付けレポートを生成。
  - 信頼できるニュースソースガイド、イベントパターン分析、地政学-コモディティ相関を参照資料として収録。

- **米国株分析** (`us-stock-analysis`)
  - ファンダメンタル、テクニカル、同業比較、投資メモ生成を網羅した包括的な米国株リサーチアシスタント。
  - 財務指標、バリュエーション比率、成長軌道、競争力ポジショニングを分析。
  - 強気/弱気ケースとリスク評価を含む構造化された投資メモを生成。
  - 分析フレームワーク（`fundamental-analysis.md`、`technical-analysis.md`、`financial-metrics.md`、`report-template.md`）を参照ライブラリに収録。

- **マーケット環境分析** (`market-environment-analysis`)
  - 株式指数、為替、コモディティ、金利、市場センチメントを含むグローバルマクロブリーフィングをガイド。
  - 指標ベース評価を含む日次/週次マーケットレビュー用の構造化レポートテンプレートを提供。
  - インジケータ解説（`references/indicators.md`）と分析パターンを含む。
  - レポート整形とデータ可視化を支援する補助スクリプト`scripts/market_utils.py`を同梱。

- **マーケットブレッド アナライザー** (`market-breadth-analyzer`)
  - TraderMontyの公開CSVデータを使用し、データ駆動型6コンポーネントスコアリングシステム（0-100）で市場幅の健全性を定量化。
  - コンポーネント: 全体ブレッド、セクター参加、セクターローテーション、モメンタム、平均回帰リスク、ヒストリカルコンテキスト。
  - APIキー不要 - GitHubの無料CSVデータを使用。

- **アップトレンドアナライザー** (`uptrend-analyzer`)
  - Monty's Uptrend Ratio Dashboardを使用して、約2,800の米国株を11セクターにわたり追跡し、市場幅の健全性を診断。
  - 5コンポーネント複合スコアリング（0-100）: マーケットブレッド、セクター参加、セクターローテーション、モメンタム、ヒストリカルコンテキスト。
  - 警告オーバーレイシステム: Late CycleとHigh Selectivityフラグがエクスポージャーガイダンスを引き締め、注意アクションを追加。
  - APIキー不要 - GitHubの無料CSVデータを使用。

- **マクロレジーム検出器** (`macro-regime-detector`)
  - クロスアセット比率分析を用いて構造的なマクロレジーム転換（1-2年ホライズン）を検出。
  - 6コンポーネント分析: RSP/SPY集中度、イールドカーブ、クレジット環境、サイズファクター、株式-債券関係、セクターローテーション。
  - レジーム識別: Concentration、Broadening、Contraction、Inflationary、Transitional。
  - FMP APIキーが必要。

- **テーマ検出器** (`theme-detector`)
  - FINVIZの業種・セクターパフォーマンスデータを複数タイムフレームで分析し、上昇・下落両方のトレンドテーマを検出。
  - 3次元スコアリング: Theme Heat (0-100: モメンタム/ボリューム/アップトレンド/ブレッド)、Lifecycle Maturity (0-100: 持続期間/RSI極端度/価格極端度/バリュエーション/ETF本数)、Confidence (Low/Medium/High)。
  - Direction-aware分析: ベアテーマもブルテーマと同等の感度でスコアリング（反転指標使用）。
  - クロスセクターテーマ検出（AI/半導体、クリーンエネルギー、ゴールド、サイバーセキュリティ等）とセクター内垂直集中検出。
  - ライフサイクルステージ: Emerging, Accelerating, Trending, Mature, Exhausting — テーマごとに代表銘柄とプロキシETFを表示。
  - Monty's Uptrend Ratio Dashboardを補助ブレッドシグナルとして統合（3点評価: ratio + MA10 + slope）。
  - コア機能にAPIキー不要（FINVIZパブリック + yfinance）。FMP/FINVIZ Eliteはオプションで銘柄選定を強化。

### 経済・決算カレンダー

- **経済カレンダー取得** (`economic-calendar-fetcher`)
  - Financial Modeling Prep (FMP) APIを使用して、今後7-90日間の経済イベントを取得。
  - 中央銀行の決定、雇用統計（NFP）、インフレデータ（CPI/PPI）、GDP発表、その他市場を動かす指標を取得。
  - インパクト評価（High/Medium/Low）と市場への影響分析を含む時系列マークダウンレポートを生成。
  - 包括的なエラー処理を備えた柔軟なAPIキー管理（環境変数またはユーザー入力）をサポート。

- **決算カレンダー** (`earnings-calendar`)
  - FMP APIを使用して、時価総額2B ドル以上の中型株以上の企業に焦点を当てた米国株の今後の決算発表を取得。
  - 日付とタイミング（市場前、市場後、市場中）別に決算を整理。
  - 週次決算レビューとポートフォリオ監視のためのクリーンなマークダウンテーブル形式を提供。
  - CLI、デスクトップ、Web環境をサポートする柔軟なAPIキー管理。

### 戦略・リスク管理

- **シナリオアナライザー** (`scenario-analyzer`)
  - ニュースヘッドラインを入力として18ヶ月シナリオを分析。1次・2次・3次影響、候補銘柄、レビューを含む包括的レポートを生成。
  - デュアルエージェント構成: scenario-analystで主分析、strategy-reviewerでセカンドオピニオンを取得。
  - APIキー不要 - WebSearchでニュース収集。

- **バックテストエキスパート** (`backtest-expert`)
  - 戦略仮説の定義、パラメータ堅牢性検証、ウォークフォワード検証を含むプロフェッショナルグレードの戦略検証フレームワーク。
  - 現実的な前提条件を重視：スリッページモデリング、取引コスト、生存バイアス除去、アウトオブサンプル検証。
  - 詳細な手法（`references/methodology.md`）と失敗事例集（`references/failed_tests.md`）を参照資料として収録。
  - アイデア生成から本番デプロイまでの品質ゲート付きシステマティックアプローチをガイド。

- **スタンレー・ドラッケンミラー投資アドバイザー** (`stanley-druckenmiller-investment`)
  - マクロポジショニング、流動性分析、非対称的リスク/リターン評価のためのドラッケンミラーの投資哲学をエンコード。
  - 「高い確信度の時は大きく賭ける」アプローチと厳格な損切り規律に焦点。
  - 投資哲学の詳細、市場分析ワークフロー、歴史的ケーススタディを含むリファレンスパック（日本語・英語）。
  - マクロテーマの識別、テクニカル確認、ポジションサイジング戦略を重視。

- **米国市場バブル検出器** (`us-market-bubble-detector`)
  - 定量的8指標「バブルメーター」スコアリングシステムを備えたミンスキー/キンドルバーガーバブルフレームワーク。
  - バブルステージを識別：転換 → ブーム → 熱狂 → 利益確定 → パニック。
  - 各ステージのレビュー用プレイブックを提供：利益確定検討、ヘッジ検討、現金展開タイミングの確認。
  - 歴史的ケースファイル（ドットコム2000、住宅2008、COVID 2020）、クイックリファレンスチェックリスト（日英）、対話型スコアラースクリプト`scripts/bubble_scorer.py`を補足。

- **オプション戦略アドバイザー** (`options-strategy-advisor`)
  - Black-Scholesモデルを使用した理論的価格算出、戦略分析、リスク管理ガイダンスを提供する教育的オプション取引ツール。
  - 全グリークス（Delta、Gamma、Theta、Vega、Rho）の計算と17以上のオプション戦略をサポート。
  - FMP APIは任意（株価データ取得用）。理論価格計算のみでもBlack-Scholesで動作。

- **ポートフォリオマネージャー** (`portfolio-manager`)
  - Alpaca MCP Server連携によるリアルタイム保有データを使った包括的ポートフォリオ分析・管理。
  - 多次元分析: 資産配分、セクター分散、リスク指標（ベータ、ボラティリティ、ドローダウン）、パフォーマンスレビュー。
  - HOLD/ADD/TRIM/SELL などの検討フラグを生成し、ユーザー自身のレビューを支援する。
  - リバランス案を生成し、実際にどのアクションを取るかはユーザーが手動で判断する。
  - Alpaca証券口座（ペーパーまたはライブ）とAlpaca MCP Serverの設定が必要。

- **ポジションサイザー** (`position-sizer`)
  - Fixed Fractional、ATRベース、Kelly Criterionの3手法でロング株式トレードのリスクベースポジションサイズを計算。
  - ポートフォリオ制約（最大ポジション%、最大セクター%）を適用し、最も厳しい制約（binding constraint）を特定。
  - 2つの出力モード: sharesモード（エントリー/ストップ指定）で株数候補、budgetモード（Kelly単独）でリスク予算候補を返却。
  - JSON + マークダウンレポートを生成。APIキー不要 — 純粋計算、オフラインで動作。

- **Parabolic Short トレードプランナー** (`parabolic-short-trade-planner`)
  - Qullamaggie 型 Parabolic Short 候補の日次スクリーナー（5因子加重スコア: MA Extension 30% / Acceleration 25% / Volume Climax 20% / Range Expansion 15% / Liquidity 10%）。`safe_largecap` / `classic_qm` の2モードで無効化閾値を切り替え。
  - 寄り前プラン生成器が候補ごとに3種類の条件付きトリガー（5min ORL ブレイク、First Red 5-min、VWAP fail）を出力。`entry_hint` / `stop_hint` は数式文字列で、shares は固定値ではなく `shares_formula` として Phase 3 で trigger 発火時に評価。
  - Phase 3 当日トリガーモニター（`monitor_intraday_trigger.py`）— Alpaca ライブまたは fixture から 5分足を取得し、トリガー別 FSM（ORL: 3 状態、First Red: 4 状態 + same-bar invalidation 優先、VWAP fail: 6 状態）を1ステップ進めて `intraday_monitor` JSON に `state` / `entry_actual` / `stop_actual` / `shares_actual`（triggered 時）を出力。リプレイ決定論（再実行で byte-identical）；`triggered` は terminal ではなく、post-trigger reclaim で `invalidated` へ遷移可能。`watch -n 60` または5分 cron でラップ。
  - 抽象化された broker short-inventory adapter。Alpaca 実装は `requests` 直叩き（SDK 非依存）で ETB-only ポリシーを表現し、HTB 銘柄は `borrow_inventory_unavailable` → `plan_status: watch_only` として明示。
  - SEC Rule 201 (SSR) 状態トラッカーは Phase 1 出力の `prior_close`（regular session close、aftermarket ではない）を引継ぎ、銘柄別の state file で翌日の carryover に反映。
  - Manual confirmation 理由は `blocking_manual_reasons`（HTB 借株、SSR 発動、premarket high/low 取得失敗）と `advisory_manual_reasons`（`manual_locate_required` は常に advisory）に分離。FMP API 必須、Alpaca は Phase 3 で必須（paper feed で OK）、Phase 2 ではオプション（未設定時は manual fallback）。

- **エッジ候補エージェント** (`edge-candidate-agent`)
  - 日次マーケット観察を再現可能なリサーチチケットに変換し、`trade-strategy-pipeline` Phase I互換の候補スペックをエクスポート。
  - 構造化リサーチチケットから`strategy.yaml` + `metadata.json`アーティファクトを生成。インターフェース契約（`edge-finder-candidate/v1`）のバリデーション付き。
  - 2つのエントリーファミリーをサポート: `pivot_breakout`（VCP検出付き）、`gap_up_continuation`（ギャップ検出付き）。
  - パイプラインスキーマに対する事前検証と`uv run`サブプロセスフォールバックによるクロス環境互換性を提供。
  - APIキー不要 — ローカルYAMLファイルで動作し、ローカルパイプラインリポジトリに対して検証。

- **トレード仮説アイデエータ** (`trade-hypothesis-ideator`)
  - 戦略コンテキスト・市場コンテキスト・トレードログ・ジャーナル証拠から、反証可能な仮説カードを1-5件生成。
  - 2パス構成: Pass 1で`evidence_summary.json`を生成、Pass 2で生仮説を検証してランキングし、JSON + Markdownレポートを出力。
  - ガードレールで必須フィールド欠落、禁止フレーズ、重複仮説、制約違反を検出。
  - `pursue`判定の仮説を`edge-finder-candidate/v1`互換の`strategy.yaml` + `metadata.json`へエクスポート可能（`pivot_breakout` / `gap_up_continuation`のみ）。
  - APIキー不要 — ローカルJSON/YAMLのみで実行可能。

- **戦略ピボットデザイナー** (`strategy-pivot-designer`)
  - バックテスト反復ループの停滞を検知し、パラメータ調整が局所最適に陥った際に構造的に異なる戦略ピボット案を生成。
  - 4つの決定論的トリガー: 改善停滞、過学習プロキシ、コスト敗北、テールリスク — `evaluate_backtest.py`出力からマッピング。
  - 3つのピボット手法: 前提反転、アーキタイプ置換、目的関数リフレーム。8つの正規戦略アーキタイプをカバー。
  - Jaccard距離によるノベルティスコアリングと決定論的タイブレークで再現可能な提案ランキングを保証。
  - `strategy_draft`互換YAMLと`pivot_metadata`拡張を出力。エクスポート可能なドラフトにはcandidate-agentチケットYAMLも同梱。
  - APIキー不要 — backtest-expertとedge-strategy-designerのローカルJSON/YAMLファイルで動作。

- **エッジ戦略レビュアー** (`edge-strategy-reviewer`)
  - `edge-strategy-designer`が出力する戦略ドラフトの決定論的品質ゲート。
  - 8基準（C1-C8）で評価: エッジの妥当性、過学習リスク、サンプル充足度、レジーム依存性、イグジット校正、リスク集中度、執行現実性、無効化シグナル品質。
  - 加重スコアリング（0-100）によるPASS/REVISE/REJECT判定とエクスポート適格性の判定。
  - 精密閾値検出がカーブフィッティングされた条件をペナルティ化。年間機会推定が制約過多な戦略をフラグ。
  - REVISE判定にはフィードバックループ用の具体的な修正指示を付与。
  - APIキー不要 — edge-strategy-designerのローカルYAMLファイルで動作。

- **エッジパイプラインオーケストレータ** (`edge-pipeline-orchestrator`)
  - エッジ研究パイプライン全体をエンドツーエンドでオーケストレーション: 自動検出、ヒント、コンセプト統合、戦略設計、クリティカルレビュー、エクスポート。
  - レビュー→修正フィードバックループ（最大2回）: PASS/REJECTはイテレーション間で蓄積、REVISEドラフトは修正後に再レビュー、残りのREVISEはresearch_probeにダウングレード。
  - エクスポート適格性ゲート: PASS + export_ready_v1 + エクスポート可能エントリーファミリーのドラフトのみ候補エクスポートに進行。
  - 全upstreamスキルをsubprocess経由で呼び出し（スキル間の直接importなし）。パイプラインマニフェストで実行トレース全体を記録。
  - resume-from-drafts、review-only、dry-runモードをサポート。
  - APIキー不要 — エッジスキル間のローカルYAML/JSONファイルをオーケストレーション。

- **エッジシグナルアグリゲータ** (`edge-signal-aggregator`)
  - edge-candidate-agent、edge-concept-synthesizer、theme-detector、sector-analyst、institutional-flow-tracker、edge-hint-extractor の出力を統合。
  - 重み付け、重複排除、鮮度調整、矛盾シグナル処理を適用して、確信度順のダッシュボードを生成。
  - `priority_score`、`support.avg_priority_score`、`themes.all`、`heat/theme_heat` など複数の上流スキーマ差分に対応。
  - provenance（`contributing_skills`）、矛盾ログ、重複統合ログを含む JSON + Markdown レポートを出力。
  - APIキー不要 — 上流エッジスキルのローカル JSON/YAML 出力を入力として動作。

- **Trader Memory Core** (`trader-memory-core`)
  - スクリーニングからポジション決済・振り返りまで、投資仮説のライフサイクルを永続的に追跡するステート層。
  - スクリーナー → 分析 → ポジションサイジング → ポートフォリオ管理の各出力を1つの thesis オブジェクトに統合。
  - ライフサイクル管理（IDEA → ENTRY_READY → ACTIVE → CLOSED）、ポジション付与、レビュースケジュール、MAE/MFE分析をサポート。
  - kanchi-dividend-sop、earnings-trade-analyzer、vcp-screener、pead-screener、canslim-screener、edge-candidate-agent と統合。

- **エクスポージャーコーチ** (`exposure-coach`)
  - market-breadth-analyzer、uptrend-analyzer、macro-regime-detector、market-top-detector、ftd-detector、theme-detector、sector-analyst、institutional-flow-tracker の出力を統合し、エクスポージャー決定を一元化。
  - 「今、株式にどれだけ資本を投入すべきか？」という核心的な問いに回答。
  - エクスポージャー上限（0-100%）、グロース/バリュー傾斜、参加幅評価、ポスチャー用レビューフラグ（NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY）を含む1ページのマーケットポスチャーサマリーを生成。
  - 部分的な入力にも対応 — upstreamファイルが欠落してもconfidenceレベルが低下するだけで実行はブロックされない。
  - FMP APIキーは任意（institutional-flow-trackerデータ利用時のみ必要）。

- **シグナルポストモーテム** (`signal-postmortem`)
  - エッジパイプライン、スクリーナー、他スキルが生成したシグナルの結果を記録・分析。
  - TRUE_POSITIVE、FALSE_POSITIVE、MISSED_OPPORTUNITY、REGIME_MISMATCHの4カテゴリに分類。
  - edge-signal-aggregator向けウェイト調整フィードバックとスキル改善バックログエントリを生成。
  - 成熟シグナルのバッチ処理（5日/20日保有期間）と手動結果記録をサポート。
  - スキル別・銘柄別・期間別の集計統計で定期的なシグナル品質監査に対応。
  - FMP APIキーは任意（実現リターン取得用。手動価格入力にも対応）。

### マーケットタイミング・底打ち検出

- **マーケットトップ検出器** (`market-top-detector`)
  - O'NeilのDistribution Days、MinerviniのLeading Stock Deterioration、MontyのDefensive Rotationを使用してマーケットトップの確率を検出。
  - 分配と天井形成パターンを識別する6コンポーネント戦術的タイミングシステム。

- **IBD Distribution Day Monitor** (`ibd-distribution-day-monitor`)
  - QQQ/SPYに対するIBD式Distribution Day（終値0.2%以上下落＋出来高増加）を日次検出。25取引セッション失効・5%上昇による無効化を追跡。
  - `age_sessions` で各レコードを管理し、`d5/d15/d25` クラスタから NORMAL/CAUTION/HIGH/SEVERE のリスク判定を生成。
  - TQQQ/QQQ向けエクスポージャーレビュー用フラグを出力（TQQQは3倍レバレッジ特性により早めに縮小）。トレーリングストップ参考水準も併せて提示。
  - Market Top Detectorとの違い: 単一コンポーネント／ETF直結／TQQQ特性考慮。Market Top Detectorは6コンポーネント複合スコア。
  - FMP APIキーが必要。

- **下落トレンド期間分析** (`downtrend-duration-analyzer`)
  - 過去の下落トレンド期間（ピーク→トラフ）を分析し、セクター・時価総額別のインタラクティブHTMLヒストグラムを生成。
  - ローリングウィンドウによるピーク/トラフ検出、深度・期間フィルター設定可能。
  - FMP APIキーが必要。

- **FTD検出器** (`ftd-detector`)
  - William O'Neilの手法を用いて、市場底打ち確認のためのFollow-Through Day (FTD) シグナルを検出。
  - デュアルインデックス追跡（S&P 500 + NASDAQ）と状態マシンによるラリー試行、FTD適格、FTD後の健全性監視。
  - Market Top Detectorの補完スキル: Market Top Detector = ディフェンシブ（分配検出）、FTD Detector = オフェンシブ（底打ち確認）。
  - 修正後の市場再参入のためのエクスポージャーガイダンス付きクオリティスコア（0-100）を生成。
  - FMP APIキーが必要。

### 決算モメンタムスクリーニング

- **決算トレードアナライザー** (`earnings-trade-analyzer`)
  - 直近決算銘柄を5要素加重スコアリング: ギャップサイズ (25%)、決算前トレンド (30%)、出来高トレンド (20%)、MA200ポジション (15%)、MA50ポジション (10%)。
  - A/B/C/Dグレード割当（A: 85+, B: 70-84, C: 55-69, D: <55）、複合スコア0-100。
  - BMO/AMCタイミング別ギャップ算出 — 決算発表タイミングに応じて異なる基準価格を使用。
  - オプションのエントリークオリティフィルタで低勝率パターンを除外。
  - APIコール予算管理（`--max-api-calls`、デフォルト: 200）。
  - PEADスクリーナー連携用に`schema_version: "1.0"`付きJSON出力。
  - FMP APIキーが必要（無料ティアで2日間ルックバックに十分）。

- **PEADスクリーナー** (`pead-screener`)
  - 決算ギャップアップ銘柄のPEAD（Post-Earnings Announcement Drift）パターンを週足分析でスクリーニング。
  - ステージベース監視: MONITORING → SIGNAL_READY（赤キャンドル検出）→ BREAKOUT（赤キャンドル高値ブレイク）→ EXPIRED（5週超過）。
  - 4コンポーネントスコアリング: セットアップ品質 (30%)、ブレイクアウト強度 (25%)、流動性 (25%)、リスク/リワード (20%)。
  - 2つの入力モード: モードA（FMP決算カレンダー、単体）、モードB（earnings-trade-analyzerのJSON出力、パイプライン）。
  - ISO週（月曜始まり）での週足集約、決算週分割、部分週対応。
  - 流動性フィルタ: ADV20 >= $25M、平均出来高 >= 100万株、株価 >= $10。
  - FMP APIキーが必要（無料ティアで14日間ルックバックに十分）。

### 株式スクリーニング・選定

- **VCPスクリーナー** (`vcp-screener`)
  - S&P 500銘柄からMark MinerviniのVolatility Contraction Pattern (VCP) をスクリーニング。
  - ブレイクアウトピボットポイント近辺でボラティリティが収縮しているStage 2上昇トレンド銘柄を識別。
  - 2軸スコアリング: パターン品質とエントリー可能性を分離（State Capsにより延長済み銘柄の追従を防止）。
  - 多段階フィルタリング: トレンドテンプレート → VCPベース検出 → 収縮分析 → ピボットポイント計算。
  - FMP APIキーが必要（無料ティアで上位100候補のデフォルトスクリーニングに十分）。

- **CANSLIM株式スクリーナー** (`canslim-screener`) - **Phase 3.1**
  - William O'NeilのCANSLIM成長株手法を用いて米国株をスクリーニング。マルチバガー候補の発見に特化。
  - **Phase 3.1** では全7コンポーネント（100%カバレッジ）を **マルチ期間 RS** で実装：C (四半期決算)、A (年次成長)、N (新高値)、S (需給)、**L (リーダーシップ / マルチ期間 RS)**、I (機関投資家)、M (市場方向)。
  - L コンポーネントは 3m / 6m / 12m 重み付け RS（`0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m`）を設定可能 benchmark（`--rs-benchmark`、デフォルト `^GSPC`）に対して計算。
  - 複合スコアリング（0-100）は O'Neil 原版重み：C 15%、A 20%、N 15%、S 15%、**L 20%**、I 10%、M 5%。
  - ベアマーケット保護：M=0 で「現金化」警告。`--disable-rs` で L を中立 50 に固定し API 予算を節約可能。
  - JSON 出力に RS 専用フィールドを追加：`rs_rating`、`rs_rank_percentile`、`rs_3m_return` / `rs_6m_return` / `rs_12m_return`、`rs_benchmark`、`rs_benchmark_relative_return`、`rs_component_score`、`benchmark_52w_performance`。Markdown には Summary Table を追加。スキーマバージョン `3.1`。

- **バリュー配当スクリーナー** (`value-dividend-screener`)
  - FMP APIを使用して高品質な配当投資機会をスクリーニング。
  - 多段階フィルタリング: バリュー特性（P/E≤20、P/B≤2）+ 配当利回り（≥3.5%）+ 成長性（3年配当/売上/EPS上昇トレンド）。
  - 配当持続性、財務健全性、クオリティスコアの高度な分析。FINVIZエリートは任意だが推奨（実行時間70-80%短縮）。

- **配当成長プルバックスクリーナー** (`dividend-growth-pullback-screener`)
  - 高品質な配当成長株（年間配当成長12%以上、利回り1.5%以上）で一時的なプルバック中の銘柄を検出。
  - ファンダメンタルの配当分析とテクニカルタイミング指標（RSI≤40のオーバーソールド）を組み合わせ。
  - FMP APIキーが必要。FINVIZエリートは任意（RSIプリスクリーニング用）。

- **かんち式配当SOP** (`kanchi-dividend-sop`)
  - かんち式5ステップを米国株向けの再現可能なワークフローに変換。
  - スクリーニング、安全性精査、バリュエーション判定、一過性要因除外、押し目買い条件を標準化。
  - 閾値表、評価基準、1ページ銘柄メモテンプレを含む運用基盤スキル。

- **かんち式配当レビュー監視** (`kanchi-dividend-review-monitor`)
  - T1-T5トリガーで異常検知を行い、`OK/WARN/REVIEW`に機械判定。
  - 自動売却は行わず、強制点検キューとレビュー票を生成。
  - `build_review_queue.py` と境界値テストを含む監視運用スキル。

- **かんち式配当 米国税務・口座配置** (`kanchi-dividend-us-tax-accounting`)
  - qualified/ordinaryの前提整理、保有期間チェック、口座配置の意思決定を支援。
  - 年次税務メモテンプレと未確定前提の管理を標準化。
  - スクリーニング後の実装・保守フェーズに使う税務運用スキル。

- **機関投資家フロートラッカー** (`institutional-flow-tracker`)
  - 13F SEC提出書類データを使用して機関投資家の所有変動を追跡し、「スマートマネー」の蓄積・分配パターンを識別。
  - ティアベース品質フレームワーク: スーパーインベスター（Berkshire、Baupost）を3.0-3.5倍、インデックスファンドを0.0-0.5倍で重み付け。
  - FMP API統合。無料ティアで四半期ポートフォリオレビューに十分。

- **ペアトレードスクリーナー** (`pair-trade-screener`)
  - 共和分検定を用いたペアトレード機会の統計的裁定ツール。
  - ヘッジ比率、平均回帰速度（半減期）、zスコアベースのエントリー/エグジットシグナルを算出。
  - セクターワイドスクリーニングとカスタムペア分析をサポート。FMP APIキーが必要。

- **FinVizスクリーナー** (`finviz-screener`)
  - 自然言語（日本語/英語）によるスクリーニング指示をFinVizフィルターコードに変換し、Chromeで結果を表示。
  - ファンダメンタル（P/E、配当、成長性、マージン）、テクニカル（RSI、SMA、パターン）、記述的フィルター（セクター、時価総額、国）等500以上のフィルターコードに対応。
  - **テーマ×サブテーマのクロス検索:** FinVizの30以上の投資テーマと268のサブテーマを任意のフィルターと組み合わせ可能。「AI × 物流」「データセンター × 電力インフラ」「サイバーセキュリティ × クラウド」のようなセクター横断的なテーマスクリーニングを実現。従来のセクター/業種フィルターでは不可能だったナラティブベースの銘柄発掘ができます。`--themes`と`--subthemes`で複数テーマを1クエリに指定可能（例: `--themes "artificialintelligence,cybersecurity" --filters "cap_midover"`）。
  - `$FINVIZ_API_KEY`環境変数からFINVIZ Eliteを自動検出。未設定時はパブリックスクリーナーにフォールバック。
  - 高配当バリュー、小型成長株、売られすぎ大型株、ブレイクアウト候補、AI/テーマ投資等、14のプリセットレシピを収録。
  - 基本利用にAPIキー不要（パブリックFinVizスクリーナー）。FINVIZ Eliteは任意で拡張機能利用可能。

</details>

## 追加ワークフロー例

Core + Satellite の主導線は上記の「おすすめの始め方」にまとめています。以下は、Advanced Satellite やコントリビューター向けを含む追加の組み合わせ例です。

### 日次マーケット監視
1. **経済カレンダー取得**を使用して、今日の高インパクトイベント（FOMC、NFP、CPI発表）をチェック
2. **決算カレンダー**を使用して、今日決算発表する主要企業を特定
3. **マーケットニュースアナリスト**を使用して、夜間の展開と市場への影響をレビュー
4. **ブレッドチャートアナリスト**を使用して、全体的な市場の健全性とポジショニングを評価

### 週次戦略レビュー
1. **セクターアナリスト**でCSVデータを取得しローテーションパターンを識別（オプションでチャート画像を提供可）
2. **テクニカルアナリスト**を主要指数とポジションに使用して、トレンド確認
3. **マーケット環境分析**を使用して、包括的なマクロブリーフィングを実施
4. **米国市場バブル検出器**を使用して、投機的過熱とリスクレベルを評価

### 個別銘柄リサーチ
1. **米国株分析**を使用して、包括的なファンダメンタルおよびテクニカルレビューを実施
2. **決算カレンダー**を使用して、今後の決算日をチェック
3. **マーケットニュースアナリスト**を使用して、最近の企業固有ニュースとセクター展開をレビュー
4. **バックテストエキスパート**を使用して、ポジションサイジング前にエントリー/エグジット戦略を検証

### 戦略的ポジショニング
1. **スタンレー・ドラッケンミラー投資アドバイザー**を使用して、マクロテーマを識別
2. **経済カレンダー取得**を使用して、主要データリリース周辺のエントリータイミングを計る
3. **ブレッドチャートアナリスト**と**テクニカルアナリスト**を使用して、確認シグナルを取得
4. **米国市場バブル検出器**を使用して、リスク管理と利益確定ガイダンスを取得

### 決算モメンタムトレード
1. **決算トレードアナライザー**を使用して、直近決算のリアクション（ギャップ、トレンド、出来高、MA位置）をスコアリング
2. **PEADスクリーナー**（モードB）でアナライザー出力を入力として、PEADセットアップ（赤キャンドルプルバック→ブレイクアウトシグナル）を検出
3. **テクニカルアナリスト**を使用して、週足チャートパターンとサポート/レジスタンスレベルを確認
4. PEADスクリーナーの流動性フィルタでポジションサイジングの実現可能性を確認
5. SIGNAL_READY銘柄を監視し、明確なストップロス（赤キャンドル安値）と2Rターゲットでブレイクアウトエントリー

### かんち式配当ワークフロー（米国株）
1. **かんち式配当SOP**で5ステップ選定と買い条件を作成
2. **かんち式配当レビュー監視**で日次/週次/四半期の異常検知キューを運用
3. **かんち式配当 米国税務・口座配置**で口座配置と税務前提を固定
4. `REVIEW`判定は再度**かんち式配当SOP**へ戻して前提再評価

### スキル品質・自動化

- **データ品質チェッカー** (`data-quality-checker`)
  - マーケット分析ドキュメントやブログ記事の公開前にデータ品質を検証。
  - 5つのチェックカテゴリ: 価格スケール不整合（ETF vs 先物の桁数ヒント）、商品表記一貫性、日付曜日ミスマッチ（英語+日本語対応）、配分合計エラー（セクション限定）、単位不整合。
  - アドバイザリーモード — 問題を警告として表示、検出ありでもexit 0。最終判断は人間。
  - 全角文字（％、〜）、レンジ表記（50-55%）、年なし日付の年推定をサポート。
  - APIキー不要 — ローカルマークダウンファイルでオフライン動作。

- **スキルデザイナー** (`skill-designer`)
  - 構造化されたアイデア仕様から新しいスキルを設計するためのClaude CLIプロンプトを生成。
  - リポジトリ規約（構造ガイド、品質チェックリスト、SKILL.mdテンプレート）をプロンプトに埋め込み。
  - 既存スキル一覧を含めて重複を防止。スキル自動生成パイプラインのdailyフローで使用。
  - APIキー不要。

- **デュアルアクシス・スキルレビュアー** (`dual-axis-skill-reviewer`)
  - デュアルアクシス方式でスキル品質をレビュー: 決定論的オートスコアリング（構造、ワークフロー、実行安全性、成果物、テスト健全性）とオプションのLLMディープレビュー。
  - 5カテゴリ・オートアクシス（0-100）: メタデータ＆ユースケース (20)、ワークフローカバレッジ (25)、実行安全性＆再現性 (25)、サポート成果物 (10)、テスト健全性 (20)。
  - `knowledge_only`スキル（スクリプトなし、リファレンスのみ）を検出し、不公平なペナルティを回避するためにスコアリング基準を調整。
  - オプションのLLMアクシスで定性的レビュー（正確性、リスク、欠落ロジック、保守性）を実施。重み付けブレンドが可能。
  - `--all`で全スキル一括レビュー、`--skip-tests`でクイックトリアージ、`--project-root`で他プロジェクトのレビューに対応。
  - APIキー不要。

- **スキルアイデアマイナー** (`skill-idea-miner`)
  - Claude Codeセッションログからスキルアイデア候補をマイニングし、新規性・実現可能性・トレーディング価値でスコアリングして優先順位付きバックログを管理。
  - 週次スキル自動生成パイプラインで使用。手動実行も可能。
  - APIキー不要。

## スキル自己改善ループ

このセクションはコントリビューター向けです。初めて使う人は読み飛ばして、上記の Core + Satellite 導線から始めてください。

スキル品質を継続的にレビュー・改善する自動パイプライン。毎日の`launchd`ジョブが1つのスキルを選択し、デュアルアクシスレビュアーでスコアリングし、スコアが90/100未満の場合は`claude -p`で改善を適用してPRを作成します。

### 仕組み

1. **ラウンドロビン選択** — レビュアー自身を除く全スキルを順番に巡回。状態は`logs/.skill_improvement_state.json`に永続化。
2. **オートスコアリング** — `run_dual_axis_review.py`を実行して決定論的スコア（0-100）を取得。
3. **改善ゲート** — `auto_review.score < 90`の場合、Claude CLIがSKILL.mdとリファレンスを修正。
4. **品質ゲート** — 改善後に再スコアリング（テスト有効）。スコアが改善されなかった場合はロールバック。
5. **PR作成** — 変更をフィーチャーブランチにコミットし、人間レビュー用にGitHub PRを作成。
6. **日次サマリー** — 結果を`reports/skill-improvement-log/YYYY-MM-DD_summary.md`に出力。

### 手動実行

```bash
# ドライラン: 改善やPR作成なしでスコアリングのみ
python3 scripts/run_skill_improvement_loop.py --dry-run

# 全スキルをドライランでレビュー
python3 scripts/run_skill_improvement_loop.py --dry-run --all

# フルラン: スコアリング、必要に応じて改善、PR作成
python3 scripts/run_skill_improvement_loop.py
```

### launchd設定 (macOS)

毎日05:00にmacOS `launchd`で自動実行:

```bash
# エージェントをインストール
cp launchd/com.trade-analysis.skill-improvement.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-improvement.plist

# 確認
launchctl list | grep skill-improvement

# 手動トリガー
launchctl start com.trade-analysis.skill-improvement
```

### 主要ファイル

| ファイル | 用途 |
|---------|------|
| `scripts/run_skill_improvement_loop.py` | オーケストレーションスクリプト（選択、スコアリング、改善、PR） |
| `scripts/run_skill_improvement.sh` | launchd用シェルラッパー |
| `launchd/com.trade-analysis.skill-improvement.plist` | macOS launchdエージェント設定 |
| `skills/dual-axis-skill-reviewer/` | レビュアースキル（スコアリングエンジン） |
| `logs/.skill_improvement_state.json` | ラウンドロビン状態と履歴 |
| `reports/skill-improvement-log/` | 日次サマリーレポート |

## スキル自動生成パイプライン

このセクションはコントリビューター向けです。トレード運用に必須の workflow ではなく、リポジトリ保守用の自動化です。

セッションログからスキルアイデアをマイニング（週次）し、設計・レビュー・PR作成（日次）を自動実行するパイプライン。自己改善ループと連携してスキルカタログを継続的に拡張します。

### 仕組み

1. **週次マイニング** — Claude Codeセッションログをスキャンし、スキル化できる繰り返しパターンを検出。各アイデアを新規性・実現可能性・トレーディング価値でスコアリング。
2. **バックログスコアリング** — ランク付けされたアイデアを`logs/.skill_generation_backlog.yaml`にステータス追跡付きで保存（`pending`、`in_progress`、`completed`、`design_failed`、`review_failed`、`pr_failed`）。
3. **日次選択** — 最高スコアの`pending`アイデアを選択。`design_failed`/`pr_failed`は1回リトライ（`review_failed`はコンテンツ品質の問題を示すため最終判定）。
4. **設計＆レビュー** — スキルデザイナーが完全なスキル（SKILL.md、リファレンス、スクリプト）を構築し、デュアルアクシスレビュアーがスコアリング。スコアが低い場合は`review_failed`。
5. **PR作成** — 新スキルをフィーチャーブランチにコミットし、人間レビュー用にGitHub PRを作成。

### 手動実行

```bash
# 週次: セッションログからアイデアをマイニング・スコアリング
python3 scripts/run_skill_generation_pipeline.py --mode weekly --dry-run

# 日次: バックログの最高スコアアイデアからスキルを設計
python3 scripts/run_skill_generation_pipeline.py --mode daily --dry-run

# フルラン（ブランチ作成、スキル設計、PR作成）
python3 scripts/run_skill_generation_pipeline.py --mode daily
```

### launchd設定 (macOS)

週次と日次の2つの`launchd`エージェントで自動実行:

```bash
# エージェントをインストール
cp launchd/com.trade-analysis.skill-generation-weekly.plist ~/Library/LaunchAgents/
cp launchd/com.trade-analysis.skill-generation-daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-weekly.plist
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-daily.plist

# 確認
launchctl list | grep skill-generation

# 手動トリガー
launchctl start com.trade-analysis.skill-generation-weekly
launchctl start com.trade-analysis.skill-generation-daily
```

### 主要ファイル

| ファイル | 用途 |
|---------|------|
| `scripts/run_skill_generation_pipeline.py` | オーケストレーションスクリプト（マイニング、選択、設計、レビュー、PR） |
| `scripts/run_skill_generation.sh` | launchd用シェルラッパー |
| `launchd/com.trade-analysis.skill-generation-weekly.plist` | 週次マイニングスケジュール（土曜06:00） |
| `launchd/com.trade-analysis.skill-generation-daily.plist` | 日次生成スケジュール（07:00） |
| `skills/skill-idea-miner/` | マイニング＆スコアリングスキル |
| `skills/skill-designer/` | スキル設計プロンプトビルダー |
| `logs/.skill_generation_backlog.yaml` | ステータス追跡付きスコア済みアイデアバックログ |
| `logs/.skill_generation_state.json` | 実行履歴と状態 |
| `reports/skill-generation-log/` | 日次生成サマリーレポート |

## カスタマイズと貢献
- トリガー説明や機能メモを調整する場合は、各フォルダ内の`SKILL.md`を更新してください。ZIP化する際はフロントマター`name`がフォルダ名と一致しているか確認してください。
- 参照資料の追記や新規スクリプト追加でワークフローを拡張できます。
- 変更を配布する場合は、最新の内容を反映した`.skill`ファイルを`skill-packages/`に再生成してください。

## API要件

いくつかのスキルはデータアクセスのためにAPIキーが必要です：

- **経済カレンダー取得**、**決算カレンダー**、**CANSLIM株式スクリーナー**、**VCPスクリーナー**、**FTD検出器**、**マクロレジーム検出器**、**IBD Distribution Day Monitor**: [Financial Modeling Prep (FMP) API](https://financialmodelingprep.com)キーが必要
  - 無料ティア: 250リクエスト/日（ほとんどのスキルに十分）
  - 環境変数を設定: `export FMP_API_KEY=your_key_here`
  - または、プロンプト時にコマンドライン引数でキーを提供
- **マーケットブレッドアナライザー**、**アップトレンドアナライザー**、**セクターアナリスト**: APIキー不要（GitHubの無料CSVデータを使用。セクターアナリストはオプションでチャート画像も利用可）
- **テーマ検出器**: コア機能にAPIキー不要（FINVIZパブリック + yfinance）。FMP APIは銘柄選定強化用（オプション）、FINVIZ Eliteは銘柄リスト取得用（オプション）
- **FinVizスクリーナー**: APIキー不要（パブリックFinVizスクリーナー）。FINVIZ Eliteは`$FINVIZ_API_KEY`環境変数から自動検出（オプション）
- **かんち式配当3スキル**（`kanchi-dividend-sop` / `kanchi-dividend-review-monitor` / `kanchi-dividend-us-tax-accounting`）: APIキー不要（上流データは他スキル出力または手動入力を利用）
- **エッジ候補エージェント** (`edge-candidate-agent`): APIキー不要（ローカルYAML生成、ローカルパイプラインリポジトリに対して検証）
- **トレード仮説アイデエータ** (`trade-hypothesis-ideator`): APIキー不要（ローカルJSON仮説パイプライン、任意で戦略エクスポート）
- **エッジ戦略レビュアー** (`edge-strategy-reviewer`): APIキー不要（ローカルYAMLドラフトの決定論的スコアリング）
- **エッジパイプラインオーケストレータ** (`edge-pipeline-orchestrator`): APIキー不要（ローカルエッジスキルをsubprocess経由でオーケストレーション）
- **エッジシグナルアグリゲータ** (`edge-signal-aggregator`): APIキー不要（ローカルJSON/YAML出力を統合し重み付けランキングを生成）
- **Trader Memory Core** (`trader-memory-core`): 🟡 オプション — FMPはポストモーテムのMAE/MFEのみ使用。コア機能はオフラインで動作
- **エクスポージャーコーチ** (`exposure-coach`): 🟡 オプション — FMPはinstitutional-flow-trackerデータ利用時のみ必要
- **シグナルポストモーテム** (`signal-postmortem`): 🟡 オプション — FMPは実現リターン取得用。手動価格入力にも対応

## 参考リンク
- Claude Skillsローンチ概要: https://www.anthropic.com/news/skills
- Claude Code Skillsガイド: https://docs.claude.com/en/docs/claude-code/skills
- Financial Modeling Prep API: https://financialmodelingprep.com/developer/docs

質問や改善案があればissueを作成するか、各スキルフォルダにメモを残しておくと、後から利用するユーザーにもわかりやすくなります。

## ライセンス

このリポジトリのすべてのスキルと参照資料は、教育および研究目的で提供されています。
