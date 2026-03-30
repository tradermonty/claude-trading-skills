---
layout: default
title: スキル一覧
parent: 日本語
nav_order: 2
lang_peer: /en/skill-catalog/
permalink: /ja/skill-catalog/
---

# スキル一覧
{: .no_toc }

Claude Trading Skillsの全スキルをカテゴリ別に紹介します。各スキルのAPI要件バッジで、利用に必要な外部サービスをすぐに確認できます。
{: .fs-6 .fw-300 }

> 検索は英語スキル名（"CANSLIM", "VCP", "FinViz"等）での検索を推奨します。日本語の部分一致検索は制限があります。
{: .note }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## バッジの凡例

| バッジ | 意味 |
|--------|------|
| <span class="badge badge-free">API不要</span> | 外部APIキーなしで動作 |
| <span class="badge badge-api">FMP必須</span> | FMP APIキーが必要 |
| <span class="badge badge-optional">FMP任意</span> | FMP APIキーがあると機能強化 |
| <span class="badge badge-optional">FINVIZ任意</span> | FINVIZ Eliteがあると高速化・精度向上 |
| <span class="badge badge-api">Alpaca必須</span> | Alpaca証券口座が必要 |
| <span class="badge badge-workflow">ワークフロー</span> | 他スキルと連携するワークフロースキル |

---

## 1. 銘柄スクリーニング

| スキル | 説明 | API要件 |
|--------|------|---------|
| **CANSLIM Screener** | William O'NeilのCANSLIM手法で成長株を7コンポーネントスコアリング。四半期決算、年次成長、新高値、需給、リーダーシップ、機関投資家、市場方向を分析 | <span class="badge badge-api">FMP必須</span> |
| **VCP Screener** | Mark MinerviniのVolatility Contraction Pattern を検出。Stage 2上昇トレンド銘柄のボラティリティ収縮とブレイクアウトポイントを識別 | <span class="badge badge-api">FMP必須</span> |
| **FinViz Screener** | 自然言語（日本語/英語）でFinVizスクリーニング条件を構築。500以上のフィルターコードに対応し、Chromeで結果を表示。**テーマクロス検索**（30以上のテーマ × 268サブテーマ）で「AI × 物流」「データセンター × 電力」等のナラティブベース検索が可能 | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FINVIZ任意</span> |
| **Value Dividend Screener** | 高配当バリュー株をスクリーニング。P/E、P/B、配当利回り、3年成長トレンドで多段階フィルタリング | <span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span> |
| **Dividend Growth Pullback Screener** | 年間配当成長12%以上の高品質配当成長株で、RSI 40以下のプルバック中の銘柄を検出 | <span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span> |
| **Earnings Trade Analyzer** | 直近決算銘柄を5要素加重スコアリング（ギャップ、トレンド、出来高、MA200、MA50）でA-Dグレード評価 | <span class="badge badge-api">FMP必須</span> |
| **PEAD Screener** | 決算ギャップアップ銘柄のPost-Earnings Announcement Drift パターンを週足分析。MONITORING→SIGNAL_READY→BREAKOUTのステージ管理 | <span class="badge badge-api">FMP必須</span> |
| **FTD Detector** | William O'Neilの手法でFollow-Through Day シグナルを検出。市場底打ち確認のためのデュアルインデックス追跡 | <span class="badge badge-api">FMP必須</span> |
| **Institutional Flow Tracker** | 13F SEC提出書類で機関投資家の蓄積・分配パターンを追跡。スーパーインベスター重み付き品質フレームワーク | <span class="badge badge-api">FMP必須</span> |

---

## 2. マーケット分析

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Sector Analyst** | セクター・業種パフォーマンスチャートを分析し、マーケットサイクル理論に基づくローテーションパターンを評価 | <span class="badge badge-free">API不要</span> |
| **Breadth Chart Analyst** | S&P 500ブレッドインデックスと上昇トレンド比率チャートで市場の健全性を診断 | <span class="badge badge-free">API不要</span> |
| **Technical Analyst** | 週足チャートの純粋テクニカル分析。トレンド、サポート/レジスタンス、チャートパターン、モメンタム指標を識別 | <span class="badge badge-free">API不要</span> |
| **[Market News Analyst]({{ '/ja/skills/market-news-analyst/' | relative_url }})** | WebSearch/WebFetchで過去10日間のニュースを収集。定量的インパクトスコアリングでランキング | <span class="badge badge-free">API不要</span> |
| **Market Environment Analysis** | グローバルマクロブリーフィング。株式指数、為替、コモディティ、金利、センチメントを網羅 | <span class="badge badge-free">API不要</span> |
| **[Market Breadth Analyzer]({{ '/ja/skills/market-breadth-analyzer/' | relative_url }})** | TraderMontyの公開CSVデータで6コンポーネントスコアリング（0-100）の市場幅評価 | <span class="badge badge-free">API不要</span> |
| **Uptrend Analyzer** | 約2,800銘柄・11セクターの上昇トレンド比率を5コンポーネント複合スコアで診断 | <span class="badge badge-free">API不要</span> |
| **Macro Regime Detector** | クロスアセット比率分析で構造的マクロレジーム転換（1-2年ホライズン）を検出 | <span class="badge badge-api">FMP必須</span> |
| **[US Market Bubble Detector]({{ '/ja/skills/us-market-bubble-detector/' | relative_url }})** | ミンスキー/キンドルバーガーフレームワークの8指標バブルメーター。ステージ別プレイブック付き | <span class="badge badge-free">API不要</span> |
| **Market Top Detector** | O'NeilのDistribution Days、MinerviniのLeading Stock劣化、Defensive Rotationで天井確率を検出 | <span class="badge badge-free">API不要</span> |
| **[Downtrend Duration Analyzer]({{ '/ja/skills/downtrend-duration-analyzer/' | relative_url }})** | 過去の下落トレンド期間（ピーク→トラフ）を分析し、セクター・時価総額別のインタラクティブヒストグラムを生成 | <span class="badge badge-api">FMP必須</span> |

---

## 3. テーマ・戦略

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Theme Detector** | FINVIZの業種データで上昇・下落テーマを3次元スコアリング（Heat、Lifecycle、Confidence）で検出 | <span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span> <span class="badge badge-optional">FINVIZ任意</span> |
| **[Scenario Analyzer]({{ '/ja/skills/scenario-analyzer/' | relative_url }})** | ニュースヘッドラインから18ヶ月シナリオ分析。1次・2次・3次影響と推奨銘柄を生成 | <span class="badge badge-free">API不要</span> |
| **[Backtest Expert]({{ '/ja/skills/backtest-expert/' | relative_url }})** | 戦略仮説のパラメータ堅牢性検証、ウォークフォワード検証を含むプロフェッショナルグレード検証フレームワーク | <span class="badge badge-free">API不要</span> |
| **Options Strategy Advisor** | Black-Scholesモデルで理論価格・グリークス算出。17以上のオプション戦略を教育的に解説 | <span class="badge badge-optional">FMP任意</span> |
| **Pair Trade Screener** | 共和分検定でペアトレード機会を検出。ヘッジ比率、半減期、z-scoreシグナルを算出 | <span class="badge badge-api">FMP必須</span> |
| **Stanley Druckenmiller Investment** | ドラッケンミラーの投資哲学をエンコード。マクロポジショニング、非対称リスク/リターン評価 | <span class="badge badge-free">API不要</span> |
| **Strategy Pivot Designer** | バックテスト停滞時に構造的に異なる戦略ピボット案を生成。4つの決定論的トリガーで局所最適を脱出 | <span class="badge badge-free">API不要</span> |

---

## 4. ポートフォリオ・執行

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Portfolio Manager** | Alpaca MCP Serverでリアルタイム保有データを取得。資産配分、リスク指標、HOLD/ADD/TRIM/SELL推奨を生成 | <span class="badge badge-api">Alpaca必須</span> |
| **[Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }})** | 投資仮説のライフサイクルを永続追跡。スクリーナー出力をIDEAとして登録し、ENTRY_READY→ACTIVE→CLOSEDのステート遷移、ポジションサイジング付与、レビュースケジュール、MAE/MFE付きポストモーテム生成をサポート | <span class="badge badge-optional">FMP任意</span> |
| **[Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }})** | Fixed Fractional、ATRベース、Kelly Criterionの3手法でリスクベースポジションサイズを計算 | <span class="badge badge-free">API不要</span> |
| **[Exposure Coach]({{ '/ja/skills/exposure-coach/' | relative_url }})** | ブレッド、レジーム、トップリスク、フローの各スキル出力を統合し、エクスポージャー上限（0-100%）、グロース/バリュー傾斜、NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY推奨を含むマーケットポスチャーサマリーを生成 | <span class="badge badge-optional">FMP任意</span> |
| **[US Stock Analysis]({{ '/ja/skills/us-stock-analysis/' | relative_url }})** | ファンダメンタル、テクニカル、同業比較を網羅した包括的米国株リサーチアシスタント | <span class="badge badge-free">API不要</span> |
| **Earnings Calendar** | FMP APIで今後の決算発表を取得。時価総額$2B以上の中大型株に焦点 | <span class="badge badge-api">FMP必須</span> |
| **Economic Calendar Fetcher** | FMP APIで7-90日間の経済イベントを取得。インパクト評価付き時系列レポート | <span class="badge badge-api">FMP必須</span> |

---

## 5. 配当投資

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Kanchi Dividend SOP** | かんち式5ステップを米国株向け再現可能ワークフローに変換。閾値表、評価基準、銘柄メモテンプレを収録 | <span class="badge badge-free">API不要</span> |
| **Kanchi Dividend Review Monitor** | T1-T5トリガーで異常検知。OK/WARN/REVIEWの機械判定で強制点検キューを生成 | <span class="badge badge-free">API不要</span> |
| **Kanchi Dividend US Tax Accounting** | qualified/ordinaryの前提整理、保有期間チェック、口座配置の意思決定を支援 | <span class="badge badge-free">API不要</span> |

---

## 6. エッジリサーチパイプライン

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Edge Candidate Agent** | 日次マーケット観察をリサーチチケットに変換。`strategy.yaml` + `metadata.json`をエクスポート | <span class="badge badge-free">API不要</span> |
| **Edge Hint Extractor** | マーケットサマリーとアノマリーからヒントを抽出し `hints.yaml` を生成 | <span class="badge badge-free">API不要</span> |
| **Edge Concept Synthesizer** | リサーチチケットとヒントからエッジコンセプトを統合し `edge_concepts.yaml` を生成 | <span class="badge badge-free">API不要</span> |
| **Edge Strategy Designer** | エッジコンセプトから戦略ドラフト（`strategy_drafts/*.yaml`）を設計 | <span class="badge badge-free">API不要</span> |
| **Edge Strategy Reviewer** | 戦略ドラフトを8基準（C1-C8）で評価。PASS/REVISE/REJECT判定とエクスポート適格性を決定 | <span class="badge badge-free">API不要</span> |
| **Edge Pipeline Orchestrator** | エッジ研究パイプライン全体をエンドツーエンドでオーケストレーション。レビュー→修正フィードバックループ付き | <span class="badge badge-free">API不要</span> |
| **Edge Signal Aggregator** | edge-candidate-agent、theme-detector、sector-analyst、institutional-flow-trackerの出力を重み付け・重複排除・矛盾処理して確信度順ダッシュボードを生成 | <span class="badge badge-free">API不要</span> |
| **[Signal Postmortem]({{ '/ja/skills/signal-postmortem/' | relative_url }})** | エッジパイプラインやスクリーナーのシグナル結果を記録・分析。TRUE_POSITIVE/FALSE_POSITIVE/REGIME_MISMATCH分類、edge-signal-aggregatorへのウェイトフィードバック、スキル改善バックログ生成 | <span class="badge badge-optional">FMP任意</span> |

---

## 7. 品質・ワークフロー

| スキル | 説明 | API要件 |
|--------|------|---------|
| **Data Quality Checker** | マーケット分析ドキュメントの価格スケール、日付曜日、配分合計、単位の不整合を検証 | <span class="badge badge-free">API不要</span> |
| **Dual-Axis Skill Reviewer** | デュアルアクシス方式でスキル品質をレビュー。決定論的オートスコアリング + オプションLLMレビュー | <span class="badge badge-free">API不要</span> |
| **Skill Designer** | 構造化されたアイデア仕様からClaudeスキルを設計。SKILL.md、references、scripts、testsを含む完全なスキルディレクトリを生成 | <span class="badge badge-free">API不要</span> |
| **Skill Idea Miner** | Claude Codeセッションログからスキルアイデア候補を抽出・スコアリング・バックログ化 | <span class="badge badge-free">API不要</span> |
| **Skill Integration Tester** | CLAUDE.mdで定義されたマルチスキルワークフローをスキル存在、データ契約互換性、ハンドオフ整合性の観点で検証 | <span class="badge badge-free">API不要</span> |
| **Trade Hypothesis Ideator** | マーケットデータ、トレードログ、ジャーナルから反証可能なトレード仮説を生成しランキング。strategy.yamlエクスポート対応 | <span class="badge badge-free">API不要</span> |
| **Weekly Trade Strategy** | 週次トレード戦略の構造化テンプレートとワークフロー | <span class="badge badge-workflow">ワークフロー</span> |

---

## どのスキルを使うべき？

目的に応じた推奨スキルを紹介します。

### グロース株を見つけたい

- **CANSLIM Screener** - O'Neilの手法で成長株をスコアリング
- **VCP Screener** - Minerviniのボラティリティ収縮パターンを検出
- **FinViz Screener** - 自然言語で自由にグロース条件を指定

### 配当収入がほしい

- **Value Dividend Screener** - 高配当バリュー株をスクリーニング
- **Dividend Growth Pullback Screener** - 増配株のプルバック買い機会を検出
- **Kanchi Dividend SOP** - かんち式5ステップで体系的に配当株を選定

### 市場環境を把握したい

- **Breadth Chart Analyst** - 市場幅の健全性を診断
- **Sector Analyst** - セクターローテーションのパターンを評価
- **Market Environment Analysis** - グローバルマクロの包括的ブリーフィング
- **Uptrend Analyzer** - 上昇トレンド比率で市場幅の健全性を定量化

### テーマ投資をしたい

- **Theme Detector** - 上昇・下落テーマを3次元スコアリングで検出
- **FinViz Screener** - AIテーマ、サイバーセキュリティ等のテーマフィルターが利用可能

### 決算モメンタムを狙いたい

- **Earnings Trade Analyzer** - 決算リアクションを5要素でスコアリング
- **PEAD Screener** - 決算後のプルバック→ブレイクアウトパターンを検出
- **Earnings Calendar** - 今後の決算日を時系列で把握

### 戦略を検証したい

- **[Backtest Expert]({{ '/ja/skills/backtest-expert/' | relative_url }})** - 戦略仮説のプロフェッショナルグレード検証
- **Strategy Pivot Designer** - 停滞した戦略から新しいアプローチを生成

### ポートフォリオを管理したい

- **Portfolio Manager** - リアルタイム保有分析とリバランス推奨
- **[Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }})** - リスクベースのポジションサイズ計算
- **[Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }})** - 仮説登録からポストモーテムまで永続的にトラッキング

---

## API要件マトリクス

| スキル | FMP | FINVIZ Elite | Alpaca |
|--------|-----|-------------|--------|
| CANSLIM Screener | 必須 | - | - |
| VCP Screener | 必須 | - | - |
| FinViz Screener | - | 任意 | - |
| Value Dividend Screener | 必須 | 推奨 | - |
| Dividend Growth Pullback Screener | 必須 | 推奨 | - |
| Earnings Trade Analyzer | 必須 | - | - |
| PEAD Screener | 必須 | - | - |
| FTD Detector | 必須 | - | - |
| Institutional Flow Tracker | 必須 | - | - |
| Theme Detector | 任意 | 推奨 | - |
| Pair Trade Screener | 必須 | - | - |
| Macro Regime Detector | 必須 | - | - |
| Options Strategy Advisor | 任意 | - | - |
| Portfolio Manager | - | - | 必須 |
| Trader Memory Core | 任意 | - | - |
| Earnings Calendar | 必須 | - | - |
| Economic Calendar Fetcher | 必須 | - | - |
| Downtrend Duration Analyzer | 必須 | - | - |
| その他すべてのスキル | - | - | - |

「-」は不要を意味します。「任意」はあれば機能強化、なくても基本機能は動作します。
