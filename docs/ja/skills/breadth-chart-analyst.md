---
layout: default
title: "Breadth Chart Analyst"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/breadth-chart-analyst/
permalink: /ja/skills/breadth-chart-analyst/
---

# Breadth Chart Analyst
{: .no_toc }

S&P 500ブレッドスインデックス（200日MAベース）およびUS株式市場上昇トレンド銘柄比率を分析するスキルです。2つのモードで動作します：**CSVデータモード**（チャート画像不要 -- 公開ソースからライブデータを取得）と**チャート画像モード**（2段階の右端抽出による視覚分析）。バックテスト済みポジショニングシグナルによる中期戦略・短期戦術的な市場見通しを提供します。すべてのアウトプットは英語です。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/breadth-chart-analyst.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/breadth-chart-analyst){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

2つの補完的な市場ブレッドス指標の専門分析を可能にするスキルです。戦略的（中長期）および戦術的（短期）の市場視点を提供します。

**2つの動作モード：**

| モード | 入力 | データソース | 最適な用途 |
|--------|------|-------------|-----------|
| **CSVデータ**（プライマリ） | 画像不要 | GitHub Pagesの公開CSV | 迅速な数値分析、自動化 |
| **チャート画像**（補助） | ユーザー提供のスクリーンショット | 視覚分析 + CSVクロスチェック | 過去パターンの文脈、視覚的確認 |

CSVデータが常に数値の**プライマリソース**です。チャート画像は補助的な視覚的文脈と過去パターンの認識を提供します。

---

## 2. 使用タイミング

以下の場合に使用します：
- 市場のブレッドス評価や市場健全性の評価を求めた場合
- ブレッドス指標に基づく中期戦略的ポジショニングについて質問した場合
- スイングトレーディングの短期戦術的タイミングシグナルが必要な場合
- 戦略・戦術を組み合わせた市場見通しを求めた場合
- **チャート画像なしでブレッドス分析を依頼した場合**（CSVデータモード）
- ブレッドスチャート画像を提供して視覚的分析を依頼した場合

以下の場合には使用しないでください：
- 個別銘柄分析（代わりに `us-stock-analysis`）
- ブレッドスチャートなしのセクターローテーション分析（代わりに `sector-analyst`）
- ニュースベースの市場分析（代わりに `market-news-analyst`）

---

## 3. 前提条件

- **チャート画像はオプション**: 公開ソースからのCSVデータがプライマリデータソース。チャート画像は補助的な視覚的文脈を提供
- **APIキー不要**: CSVデータは公開GitHub Pagesから取得。サブスクリプション不要
- **Python 3.9+**: CSVフェッチスクリプトの実行用（標準ライブラリのみ -- pipインストール不要）
- **言語**: すべての分析とアウトプットは英語で実施

---

## 4. クイックスタート

```bash
# 最新ブレッドスデータの取得（チャート画像不要）
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py

# プログラム処理用のJSON出力
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py --json
```

**出力例：**
```
============================================================
Breadth Data (CSV) - 2026-03-13
============================================================
--- Market Breadth (S&P 500) ---
200-Day MA: 62.13% (healthy (>=60%))
8-Day MA:   55.05% (neutral (40-60%))
8MA vs 200MA: -7.08pt (8MA BELOW -- DEAD CROSS)
Trend: -1
--- Uptrend Ratio (All Markets) ---
Current: 12.55% RED (bearish)
10MA: 15.67%, Slope: -0.0157, Trend: DOWN
--- Sector Summary ---
Overbought: Energy (50.3%)
Oversold: Industrials (8.4%), Communication Services (5.8%), ...
============================================================
```

---

## 5. ワークフロー

### ステップ0: CSVデータの取得（プライマリソース -- 必須）

CSVデータはすべてのブレッドス値のプライマリソースです。画像分析の前に必ず実行してください。

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py
```

**データソース：**

| ソース | URL | 提供データ |
|--------|-----|----------|
| マーケットブレッドス | `sydcurie.github.io/.../market_breadth_data.csv` | 200日MA、8日MA、トレンド、デッドクロス |
| アップトレンド比率 | `github.com/sydcurie/uptrend-dashboard/.../uptrend_ratio_timeseries.csv` | 比率、10MA、傾き、トレンド、色 |
| セクターサマリー | `github.com/sydcurie/uptrend-dashboard/.../sector_summary.csv` | セクター別比率、トレンド、ステータス |

**データソース優先順位：**

| 優先度 | ソース | 信頼性 |
|--------|--------|--------|
| 1（プライマリ） | **CSVデータ** | 高 |
| 2（補助） | チャート画像 | 中 |
| 3（非推奨） | ~~OpenCVスクリプト~~ | 低（非推奨） |

チャート画像が提供されない場合、ステップ1と1.5をスキップし、CSVデータを使用して直接分析に進みます。

### ステップ1: チャート画像の受領（提供された場合）

チャート画像が提供された場合：

1. チャート画像の受領を確認
2. 提供されたチャートを特定（チャート1: 200MAブレッドス、チャート2: アップトレンド比率、または両方）
3. ステップ1.5の2段階チャート分析に進む

### ステップ1.5: 2段階チャート分析（チャート提供時）

過去データを現在値と誤読することを防ぐ**2段階アプローチ**を使用：

**ステージ1: フルチャート** -- 過去の文脈、トラフ/ピーク、サイクルを分析

**ステージ2: 右端** -- 右端25%を抽出して現在値を分析：

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

ステージ1と2の値が異なる場合、**ステージ2が優先**されます。常にステップ0のCSVデータとクロスチェックしてください。

### ステップ2: 手法の読み込み

```
Read: references/breadth_chart_methodology.md
```

### ステップ3: チャート1の分析（200MAベースブレッドスインデックス）

#### 読み取る主要データ：
- **8MAレベル**（オレンジ線）と**200MAレベル**（緑線）
- 傾き、73%閾値と23%閾値からの距離
- シグナルマーカー: 8MAトラフ（紫▼）、200MAピーク（赤▲）

#### 重要: ラインカラーの確認
- **8MA = オレンジ**（動きが速い、変動が大きい）
- **200MA = 緑**（動きが遅い、滑らか）

#### 買いシグナル（すべての基準を満たす必要あり）：
1. 8MAが明確なトラフ（紫▼）を形成
2. 8MAがトラフから上昇開始
3. 8MAが2〜3回連続で上昇
4. 8MAが現在上昇中（下落していない）
5. 8MAが上昇軌道を維持

**シグナルステータス**: 確認済 / 発展中 / 失敗 / シグナルなし

#### 売りシグナル：
- 200MAが73%付近以上でピーク（赤▲）を形成

#### デッドクロス/ゴールデンクロスの検出：
- 8MAが200MAを下回り収束 = **デッドクロス**（弱気）
- 8MAが200MAを下回り上方乖離 = **ゴールデンクロス**（強気）

### ステップ4: チャート2の分析（アップトレンド銘柄比率）

#### 主要データ：
- 現在の比率、色（GREEN/RED）、傾き
- 10%（売られ過ぎ）と40%（買われ過ぎ）閾値からの距離
- 直近の色遷移（赤→緑 = 買い、緑→赤 = 売り）

### ステップ5: 統合分析

両データセットが利用可能な場合、4つのシナリオに分類：

| シナリオ | 戦略（チャート1） | 戦術（チャート2） | 含意 |
|---------|-----------------|-----------------|------|
| 両方強気 | 8MA上昇 | GREEN、上昇 | 最大強気 |
| 戦略強気/戦術弱気 | 8MA上昇 | RED、下落 | コア保持、エントリー待ち |
| 戦略弱気/戦術強気 | 200MAピーク | GREEN、上昇 | 戦術トレードのみ |
| 両方弱気 | 両MA下落 | RED、下落 | ディフェンシブ |

### ステップ6: レポート生成

`reports/`ディレクトリに保存：
- `breadth_200ma_analysis_[YYYY-MM-DD].md`
- `uptrend_ratio_analysis_[YYYY-MM-DD].md`
- `breadth_combined_analysis_[YYYY-MM-DD].md`

### ステップ7: 品質保証

主要な検証ポイント：
1. すべてのアウトプットが英語であること
2. ラインカラーの確認（8MA=オレンジ、200MA=緑）
3. トレンド方向が過去ではなく最右端のデータポイントを反映
4. デッドクロス/ゴールデンクロスのステータスを明記
5. シグナルステータスを明確に特定
6. シナリオ確率の合計が100%
7. 各トレーダータイプへの実行可能なポジショニング

---

## 6. リソース

**リファレンス：**

- `skills/breadth-chart-analyst/references/breadth_chart_methodology.md`

**スクリプト：**

- `skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py` -- プライマリデータソース（標準ライブラリのみ）
- `skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py` -- チャート右端抽出（PIL）
- `skills/breadth-chart-analyst/scripts/detect_uptrend_ratio.py` -- OpenCVアップトレンド検出（非推奨）
- `skills/breadth-chart-analyst/scripts/detect_breadth_values.py` -- OpenCVブレッドス検出（非推奨）
