---
layout: default
title: Market Breadth Analyzer
grand_parent: 日本語
parent: スキルガイド
nav_order: 5
lang_peer: /en/skills/market-breadth-analyzer/
permalink: /ja/skills/market-breadth-analyzer/
---

# Market Breadth Analyzer
{: .no_toc }

6コンポーネントの自動重み付けスコアリングで市場のブレッドスを定量化するスキルです（0-100、100=健全）。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-breadth-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-breadth-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Market Breadth Analyzerは、TraderMontyの公開CSVデータを使って市場の参加率（ブレッドス）を6つの次元で定量評価し、0-100のコンポジットスコアを算出するスキルです。

**主な特徴:**
- 6コンポーネント自動重み付けスコアリング（合計100点満点）
- TraderMontyのGitHub Pages公開CSVを使用（APIキー不要）
- データ欠損時の自動重み再分配メカニズム
- スコア履歴の自動追跡（最大20エントリ）と改善/悪化トレンド検出
- JSON + Markdownレポートの同時出力

**解決する問題:**
- 「ラリーは広がっているか？」「一部の銘柄だけが上昇しているのか？」という問いをデータで回答
- ブレッドスの健全度をもとに、エクスポージャー水準の目安を提示
- S&P 500の価格とブレッドスの乖離（ダイバージェンス）を定量検出

**Breadth Chart Analystとの違い:**

| 項目 | Market Breadth Analyzer | Breadth Chart Analyst |
|------|-------------------------|----------------------|
| データソース | CSV（自動取得） | チャート画像（手動） |
| 出力 | 定量スコア（0-100） | 定性的チャート分析 |
| 再現性 | 完全に再現可能 | アナリスト依存 |

---

## 2. 前提条件

| 項目 | 要否 | 説明 |
|------|------|------|
| Python 3.9+ | 必須 | スクリプト実行用 |
| APIキー | 不要 | 公開CSVデータを使用 |
| インターネット接続 | 必須 | GitHub PagesからCSVを取得 |

追加のPythonパッケージのインストールは不要です（標準ライブラリのみ使用）。

> CSVデータはGitHub Actionsにより1日2回自動更新されます。スクリプトはデータの鮮度を自動チェックし、5日以上古い場合は警告を表示します。
{: .tip }

---

## 3. クイックスタート

Claudeに自然言語で質問するだけで使えます：

```
マーケットブレッドスはどうですか？
```

Claudeが以下の流れで処理します：
1. CSVデータの取得（~2,500行の詳細データ + 8指標のサマリー）
2. 6コンポーネントのスコア計算（重み再分配を自動適用）
3. コンポジットスコアとヘルスゾーンの判定
4. スコア履歴への追記とトレンド判定
5. Markdown + JSONレポートの生成

CLIで直接実行する場合：

```bash
python3 skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --output-dir reports/
```

---

## 4. 仕組み

### ワークフロー

```
CSV取得 → データ検証 → 6コンポーネント計算 → 重み再分配 → コンポジットスコア → ゾーン判定 → 履歴追跡 → レポート出力
```

### 6コンポーネントスコアリング

| # | コンポーネント | 重み | 主なシグナル |
|---|--------------|------|------------|
| 1 | ブレッドスレベル&トレンド | **25%** | 8MA水準 + 200MAトレンド方向 + 8MA方向修正子 |
| 2 | 8MA vs 200MAクロスオーバー | **20%** | MAギャップと方向によるモメンタム |
| 3 | ピーク/トラフサイクル | **20%** | ブレッドスサイクルにおける現在位置 |
| 4 | 弱気シグナル | **15%** | バックテスト済み弱気シグナルフラグ |
| 5 | ヒストリカルパーセンタイル | **10%** | 全期間の分布における現在の位置 |
| 6 | S&P 500ダイバージェンス | **10%** | マルチウィンドウ（20日+60日）の価格vsブレッドス乖離 |

### ヘルスゾーン

| スコア | ゾーン | エクスポージャー | アクション |
|--------|--------|------------------|-----------|
| 80-100 | **Strong** | 90-100% | フルポジション、グロース/モメンタム重視 |
| 60-79 | **Healthy** | 75-90% | 通常運用 |
| 40-59 | **Neutral** | 60-75% | 選択的、ストップを厳格化 |
| 20-39 | **Weakening** | 40-60% | 利益確定、キャッシュ比率引き上げ |
| 0-19 | **Critical** | 25-40% | 資本保全、トラフの監視 |

### 重み再分配メカニズム

データ不足で計算できないコンポーネントがある場合、そのコンポーネントを除外し、残りのコンポーネントに比例配分で重みを再分配します。

**例:** C6（10%）が利用不可の場合：
- C1: 25/90 = 27.8%, C2: 20/90 = 22.2%, C3: 20/90 = 22.2%, C4: 15/90 = 16.7%, C5: 10/90 = 11.1%

レポートにはオリジナル重みと実効重みの両方が表示されます。

---

## 5. 使用例

### 例1: 朝の市場ヘルスチェック（デフォルト実行）

**プロンプト:**
```
今日のマーケットブレッドスのスコアを確認して
```

**Claudeの動作:**
- CSVデータ取得、6コンポーネント計算を実行
- コンポジットスコアとヘルスゾーンを提示
- 推奨エクスポージャー水準と注目すべきブレッドス水準を提示

**なぜ有用か:** 毎朝の市場チェックルーティンに組み込むことで、客観的なデータに基づくリスク管理が可能になります。

---

### 例2: ラリーの広がり評価

**プロンプト:**
```
最近の上昇は広がっている？ブレッドスのスコアと各コンポーネントを詳しく教えて
```

**Claudeの動作:**
- 全6コンポーネントの個別スコアと重みを詳細表示
- 最も強いコンポーネントと最も弱いコンポーネントを特定
- ラリーの持続可能性についての評価を提示

**なぜ有用か:** 指数だけが上がっている「ナロー・ラリー」なのか、多くの銘柄が参加している「ブロードベース・ラリー」なのかを判別できます。

---

### 例3: ナロー・リーダーシップ警告の検出

**プロンプト:**
```
S&Pは高値更新しているのにブレッドスが悪化していないか確認して
```

**Claudeの動作:**
- C6（S&P 500ダイバージェンス）の20日/60日ウィンドウを重点的に分析
- 「価格上昇 + ブレッドス低下」のベアリッシュ・ダイバージェンスを検出した場合はEarly Warningフラグを報告
- 過去の類似パターン（2000年、2007年、2021年の天井前パターン）との比較

**なぜ有用か:** 市場の天井を予測する最も信頼性の高い先行指標の一つであるダイバージェンスを自動検出できます。

---

### 例4: S&P 500との乖離分析

**プロンプト:**
```
ブレッドスとS&P 500のダイバージェンスはどうなっている？
```

**Claudeの動作:**
- 20日ウィンドウ（短期）と60日ウィンドウ（中期）の両方で乖離を数値化
- コンポジットスコア = 60日スコア x 0.6 + 20日スコア x 0.4 として算出
- パターン分類: Healthy Rally / Narrow Market / Bullish Divergence / Consistent Decline

**なぜ有用か:** 短期と中期の2つの時間軸で乖離を分析するため、「短期は悪化しているが構造的にはまだ健全」といった段階的な判断が可能です。

---

### 例5: ヒストリカル・パーセンタイルとの比較

**プロンプト:**
```
現在のブレッドスは過去の分布と比べてどの水準にある？
```

**Claudeの動作:**
- C5（ヒストリカルパーセンタイル）を中心に分析
- 2016年以降の全データにおけるパーセンタイル位置を表示
- 平均ピーク（~0.729）や平均トラフ（~0.232）との比較

**なぜ有用か:** 「現在のブレッドスが歴史的に見て高いのか低いのか」を客観的に把握し、過熱感や売られすぎの判断材料にできます。

---

### 例6: ゾーン遷移によるエクスポージャー判断

**プロンプト:**
```
ブレッドスのスコア推移を見せて。最近改善している？悪化している？
```

**Claudeの動作:**
- スコア履歴（最大20エントリ）からトレンドを判定（Improving / Deteriorating / Stable）
- 直近5回のスコア推移のデルタを計算
- ゾーンの遷移パターン（例: Weakening → Neutral → Healthy）を時系列で表示

**なぜ有用か:** 単発のスコアだけでなく、トレンド方向に基づいてエクスポージャーの増減判断ができます。例えば「Neutralだが改善中」ならやや積極的、「Healthyだが悪化中」ならやや防御的に動けます。

---

## 6. 出力の読み方

### JSON出力の主要フィールド

| フィールド | 説明 |
|-----------|------|
| `composite_score` | 0-100のコンポジットスコア |
| `zone` | ヘルスゾーン（Strong/Healthy/Neutral/Weakening/Critical） |
| `component_scores` | 各コンポーネントの個別スコアと重み |
| `data_quality` | データ品質ラベル（Complete/Partial/Limited） |
| `trend` | 直近スコアの方向（Improving/Deteriorating/Stable） |

### データ品質ラベル

| 利用可能コンポーネント数 | ラベル | 解釈 |
|------------------------|--------|------|
| 6/6 | Complete | 完全な信頼度 |
| 4-5/6 | Partial | 注意して解釈 |
| 0-3/6 | Limited | 低信頼度 |

### Markdownレポートの構成

1. **ヘッダー** - 分析日時、データ最新日、データ品質ラベル
2. **コンポジットスコア** - スコア値、ゾーン、推奨エクスポージャー
3. **コンポーネント詳細** - 各コンポーネントの個別スコアとシグナル説明
4. **スコア履歴** - 直近の推移とトレンド方向
5. **推奨アクション** - ゾーンに基づく具体的な行動指針

### 注意点

- 8MA方向修正子がマイナスの場合、レポートに「Caution」警告が自動追加されます
- これはゾーンベースのガイダンスが楽観的すぎる可能性を示唆するシグナルです
- Caution発動時は「新規ポジションサイズの縮小」「既存ポジションのストップ引き締め」が追記されます

---

## 7. Tips & ベストプラクティス

### スコアの活用方法

- **単体利用**: 毎朝のルーティンで市場の健全度を確認し、その日のトレード積極度を調整
- **トレンド重視**: 単発のスコアよりも、数回分の推移（Improving/Deteriorating）のほうが重要
- **ゾーン境界に注意**: 60点と59点の間に大きな違いはないため、厳密なゾーン切り替えよりも方向性を重視

### エクスポージャー管理の目安

| 状況 | 対応 |
|------|------|
| Strong + Improving | 攻めのポジション拡大（グロース、モメンタム） |
| Healthy + Stable | 通常運用を維持 |
| Neutral + Deteriorating | 新規ポジションを抑制、ストップを引き締め |
| Weakening | 利益確定を進め、キャッシュ比率を上げる |
| Critical | 資本保全モード、トラフ形成の兆候を監視 |

### データ鮮度の確認

- データが5日以上古い場合はスクリプトが自動で警告を出します
- 週末を挟む場合は正常なので無視して構いません
- CSVが更新されない場合は、元データソース（TraderMontyのGitHub Pages）の状態を確認してください

---

## 8. 他スキルとの連携

### Breadth Analyzer → Sector Analyst

ブレッドスの定量スコアで全体像を把握し、セクターチャートでローテーションの詳細を確認：

```
1. Market Breadth Analyzer: コンポジットスコアで市場全体の参加率を確認
2. Sector Analyst: Weakening時はディフェンシブセクターへのローテーションを分析
```

### Breadth Analyzer → CANSLIM / VCP Screener

ブレッドスのゾーンに応じてスクリーニングの積極度を調整：

```
1. Market Breadth Analyzer: Strong/Healthyゾーンを確認
2. CANSLIM / VCP Screener: Strong時はグロースモメンタム条件を積極的に適用
   Weakening時はスクリーニングを一時停止またはフィルターを厳格化
```

### Breadth Analyzer → Position Sizer

ブレッドスのスコアに基づいてポジションサイズを動的に調整：

```
1. Market Breadth Analyzer: スコアが40-59（Neutral）の場合
2. Position Sizer: リスク%を通常の1.0%から0.5%に引き下げてサイジング
```

---

## 9. トラブルシューティング

### CSVデータが取得できない

**原因:** インターネット接続の問題、またはGitHub Pagesの一時的なダウン

**対処:**
- インターネット接続を確認
- `https://sydcurie.github.io/market-breadth-analysis/market_breadth_data.csv` にブラウザから直接アクセスして確認
- 一時的な問題であれば数分後に再実行

### データ鮮度の警告が表示される

**原因:** CSVの最新行の日付が5日以上前

**対処:**
- 週末・祝日を挟んでいる場合は正常（市場営業日ベースで確認）
- 平日なのに更新されていない場合は、元リポジトリのGitHub Actionsの状態を確認
- `--detail-url` で代替データソースを指定可能

### コンポーネントが「data_available: False」と表示される

**原因:** データ行数が不足しており、特定のコンポーネント（例: ダイバージェンス分析に必要な60日分のデータ）を計算できない

**対処:**
- 重み再分配が自動的に適用されるため、スコア自体は算出されます
- データ品質ラベル（Partial/Limited）を確認し、信頼度を考慮して判断してください

### スコア履歴が表示されない

**原因:** 初回実行のため履歴がまだない

**対処:**
- 2回目以降の実行で履歴が蓄積されます
- 履歴ファイル（`market_breadth_history.json`）は出力ディレクトリに保存されます
- トレンド判定は最低2エントリ以上必要です

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--detail-url` | 詳細CSVのURL | TraderMontyのGitHub Pages URL |
| `--summary-url` | サマリーCSVのURL | TraderMontyのGitHub Pages URL |
| `--output-dir` | レポート出力先ディレクトリ | カレントディレクトリ |

### 主要な閾値

| 指標 | 値 | 意味 |
|------|-----|------|
| 8MA > 0.70 | 非常に強い | 幅広い銘柄が上昇に参加 |
| 8MA > 0.50 | 中立 | 約半数の銘柄が参加 |
| 8MA < 0.40 | 極端な弱さ | トラフ形成の可能性 |
| 8MA < 0.20 | 危機水準 | 大底に先行する稀なレベル |
| 平均ピーク（200MA） | ~0.729 | ブレッドスサイクルの典型的な天井 |
| 平均トラフ（8MA < 0.4時） | ~0.232 | 極端なトラフの平均水準 |

### 出力ファイル

| ファイル | 説明 |
|----------|------|
| `market_breadth_YYYY-MM-DD_HHMMSS.json` | 構造化されたJSON結果 |
| `market_breadth_YYYY-MM-DD_HHMMSS.md` | 人間が読みやすいMarkdownレポート |
| `market_breadth_history.json` | スコア履歴（最大20エントリ、実行間で永続化） |

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/market-breadth-analyzer/SKILL.md` | スキル定義（ワークフロー） |
| `skills/market-breadth-analyzer/references/breadth_analysis_methodology.md` | スコアリング方法論の全詳細 |
| `skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py` | メイン分析スクリプト |
| `skills/market-breadth-analyzer/scripts/scorer.py` | コンポーネントスコア計算ロジック |
| `skills/market-breadth-analyzer/scripts/csv_client.py` | CSVデータ取得クライアント |
| `skills/market-breadth-analyzer/scripts/history_tracker.py` | スコア履歴管理 |
| `skills/market-breadth-analyzer/scripts/report_generator.py` | レポート生成 |

### 外部リソース

| リソース | URL |
|---------|-----|
| インタラクティブダッシュボード | [sydcurie.github.io/market-breadth-analysis](https://sydcurie.github.io/market-breadth-analysis/) |
| 詳細CSV | [market_breadth_data.csv](https://sydcurie.github.io/market-breadth-analysis/market_breadth_data.csv) |
| サマリーCSV | [market_breadth_summary.csv](https://sydcurie.github.io/market-breadth-analysis/market_breadth_summary.csv) |
| ソースリポジトリ | [github.com/sydcurie/market-breadth-analysis](https://github.com/sydcurie/market-breadth-analysis) |
