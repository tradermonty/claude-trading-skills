---
layout: default
title: "Downtrend Duration Analyzer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/downtrend-duration-analyzer/
permalink: /ja/skills/downtrend-duration-analyzer/
generated: false
---

# Downtrend Duration Analyzer
{: .no_toc }

過去の下落局面を peak-to-trough で抽出し、セクター別・時価総額別に「典型的な調整期間」を可視化するスキルです。押し目戦略や平均回帰戦略の保有期間設計に使います。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/downtrend-duration-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/downtrend-duration-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Downtrend Duration Analyzer は、銘柄の過去データから下落期間を抽出し、調整が何営業日続きやすいかを統計的に確認するための分析スキルです。

確認できること:

- 過去の下落期間の中央値、平均、パーセンタイル
- セクター別の調整期間の違い
- 大型株、中型株、小型株など時価総額別の違い
- 短期 pullback と長期 downtrend の分布
- HTML ヒストグラムによる視覚的な確認

---

## 2. 使う場面

- 「このセクターの調整は通常どれくらい続くか」を知りたい
- 押し目買い・平均回帰戦略の timeout を決めたい
- 下落中の銘柄を何日待つべきか、過去分布から確認したい
- セクターや時価総額ごとの correction behavior を比較したい
- 保有期間や損切りまでの猶予を現実的に設計したい

---

## 3. 前提条件

- Python 3.9+
- 過去 OHLC データ
- FMP API を使う場合は `FMP_API_KEY`
- ローカルデータがある場合は API なしでも分析可能

このスキルは将来の反発を予測するものではありません。過去の調整期間の分布を使って、期待値と時間軸を現実的にするための補助ツールです。

---

## 4. クイックスタート

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

HTML 可視化を作る場合:

```bash
python3 skills/downtrend-duration-analyzer/scripts/generate_histogram_html.py \
  --input reports/downtrend_analysis_*.json \
  --output-dir reports/
```

---

## 5. ワークフロー

1. 対象ユニバースと期間を決める
2. 過去 OHLC データから局所的な peak と trough を抽出する
3. 各 downtrend の期間と下落率を計算する
4. セクター、時価総額、深さなどで集計する
5. JSON、Markdown、HTML ヒストグラムを確認する

ワークフローでFMPから再取得する場合も、次のコマンドを使います。実行には `FMP_API_KEY` が必要です。

```bash
python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py \
  --sector "Technology" \
  --lookback-years 5 \
  --output-dir reports/
```

短い調整、標準的なセクターローテーション、長期のトレンド転換を混同しないよう、期間と下落率をセットで見ます。

---

## 6. 出力の読み方

| 指標 | 見るポイント |
|---|---|
| median duration | 一般的な調整期間の目安 |
| 75th / 90th percentile | 長引いた場合の上限感 |
| depth pct | 期間だけでなく下落幅も確認 |
| sector split | セクターごとの違い |
| market cap split | 小型株と大型株の調整速度の差 |

HTML のヒストグラムでは、分布の山が短期に偏っているのか、長期に裾が伸びているのかを確認します。

---

## 7. 注意点

- 過去の分布は将来の反発日を保証しません。
- bear market と通常の pullback は同じ分布で扱わないよう注意します。
- サンプル数が少ないセクターや時価総額帯の結論は弱く扱います。
- 売買判断には `market-regime-daily`、`technical-analyst`、`position-sizer` と組み合わせて使います。
