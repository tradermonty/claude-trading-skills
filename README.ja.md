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
| 長期ポートフォリオを週次で見直したい | [`core-portfolio-weekly`](workflows/core-portfolio-weekly.yaml) | portfolio-manager, kanchi-dividend-review-monitor, trader-memory-core | Alpaca 必須。手動 CSV は劣後フォールバック |
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
- `skillsets/` – 目的別のインストール単位。主要 goal ごとに required / recommended / optional skills を定義します（コア 4 skillset 実装済み: market-regime, core-portfolio, swing-opportunity, trade-memory。Navigator が参照）。

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

> **翻訳方針:** 本カタログはカテゴリ見出しと表ラベルのみ日本語化しています。サマリ・依存・ステータスの本文は `skills-index.yaml` の英語正本をそのまま表示します。本文の日本語化は将来対応予定です（index 側に `summary_ja` 等のフィールドを追加するか、別のローカライズ層を設ける方向で検討中）。

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
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | Generate falsifiable trade strategy hypotheses from market data, trade logs, and journal snippets with ranked hypothesis cards and optional strategy.yaml export. | `local_calculation` — | production |
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
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | Critically review strategy drafts from edge-strategy-designer for edge plausibility, overfitting risk, sample size adequacy, and execution realism. | `local_calculation` — | production |
| **Scenario Analyzer** (`scenario-analyzer`) | Analyze 18-month scenarios from news headlines via scenario-analyst agent with strategy-reviewer second opinion; outputs primary/secondary/tertiary impact analysis and stock picks. | `websearch` **required** | production |
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
| **Trading Skills Navigator** (`trading-skills-navigator`) | Recommend the right workflow, skillset, API profile, and setup path from a natural-language trading goal. | `local_calculation` — | production |
<!-- skills-index:end name="catalog-ja" -->

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
