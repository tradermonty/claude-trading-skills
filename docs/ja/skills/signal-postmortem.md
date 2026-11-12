---
layout: default
title: "Signal Postmortem"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/signal-postmortem/
permalink: /ja/skills/signal-postmortem/
generated: false
---

# Signal Postmortem
{: .no_toc }

スクリーナーや edge pipeline が出したシグナルの事後成績を記録し、false positive、missed opportunity、regime mismatch を分類するスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/signal-postmortem.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/signal-postmortem){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Signal Postmortem は、発生したシグナルがその後どうなったかを記録し、シグナル品質を改善するためのフィードバックを作ります。実際にエントリーしたトレードだけでなく、見送ったシグナルや候補も後から検証できます。

主な分類:

- true positive
- false positive
- missed opportunity
- regime mismatch
- invalid signal
- insufficient follow-through

---

## 2. 使う場面

- トレードを閉じたあと、元シグナルが有効だったか確認したい
- 5日後、20日後などの holding period が満了したシグナルをまとめて検証したい
- 特定スキルの false positive が多いかを確認したい
- `edge-signal-aggregator` の重み調整材料を作りたい
- 週次または月次でシグナル品質を監査したい

---

## 3. 前提条件

- Python 3.9+
- シグナル記録 JSON
- FMP API キーは任意。価格データを自動取得する場合のみ使います。
- 元シグナルJSONに有効な entry_price があり、exit price / exit date が分かる場合は API なしで手動記録できます。

---

## 4. クイックスタート

成熟したシグナルを一覧します。

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --list-ready \
  --signals-dir state/signals/ \
  --min-days 5
```

結果を記録します。

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signals-file state/signals/aggregated_signals_2026-03-10.json \
  --holding-periods 5,20 \
  --output-dir reports/
```

---

## 5. ワークフロー

1. 対象シグナルを集める
2. entry price、signal date、predicted direction、source skill を確認する
3. 5日後、20日後などの実現リターンを計算する
4. 結果を true/false positive などに分類する
5. source skill、market regime、setup type ごとに失敗パターンをまとめる
6. 改善 backlog や aggregator weight の見直し材料にする

---

## 6. 出力の読み方

| 項目 | 意味 |
|---|---|
| realized return | シグナル後の実現リターン |
| outcome class | シグナルの成功・失敗分類 |
| source skill | どのスキル由来か |
| regime context | 市場環境との相性 |
| feedback | 改善すべき重み、フィルター、レビュー観点 |

---

## 7. 注意点

- 実際に取引しなかったシグナルも、検証対象として価値があります。
- 個別トレードの心理・実行レビューは `trade-performance-coach` を使います。
- シグナル品質の評価であり、次の売買を自動決定するものではありません。


## バッチ記録の価格データ要件

バッチ記録には、有限かつ正のエントリー価格と5日後の実測価格が必要です。
5日目から9日目までの最初の有効な価格とその日付を終了記録に使います。
APIキーや実測価格がない場合はNEUTRALを生成せず、対象シグナルをスキップします。
実測リターンが横ばいの場合のNEUTRALは維持します。20日などの補助リターンが
欠損・非有限ならその項目だけ省略し、5日リターンが欠損・非有限なら記録しません。
バッチの `--holding-periods` には `5` を含めてください。順序は終了価格に影響しません。

バッチ概要の `processed` と `skipped` を確認してください。全件スキップ時は
診断用のバッチ概要のみを書き、終了コード1になります。一部成功時は有効な記録を
保存して終了コード0になります。スキップした対象の既存記録は上書きしません。
過去に保存された不正な記録は自動修復・自動除外されないため、分析前に確認が必要です。



## 元シグナルに基づく手動記録

手動記録では `--signals-file` と `--signal-id` を併せて指定します。ファイル中の
一致するシグナルがちょうど1件であることが必要です。IDから銘柄・日付を推測せず、
元の銘柄、日付、スキル、方向、エントリー価格を保持します。API通信はしません。

```bash
python3 skills/signal-postmortem/scripts/postmortem_recorder.py \
  --signals-file state/signals/aggregated_signals_2026-03-10.json \
  --signal-id sig_aapl_20260310_abc \
  --exit-price 178.50 --exit-date 2026-03-15 --output-dir reports/
```

エントリー・決済価格は有限の正数、日付は `YYYY-MM-DD` が必要です。決済日が
シグナル日より前の場合、一致がない・重複している場合、計算結果が非有限の場合も
記録せずエラーになります。入力と出力が同一ファイルの場合も、symlink・hardlinkを
含めて拒否します。検証失敗時に既存の実績ファイルは上書きしません。

実際の価格変化率 `(exit - entry) / entry` を `realized_returns.actual` として保存し、
`return_basis: actual_exit` と保有した暦日数を記録します。元のLONG/SHORT方向で
分類し、数量・レバレッジ・手数料を含む損益とは区別します。5日・20日の比較用
リターンは捏造しません。分析時は元のスキル・月の成績に加えますが、5日平均は
観測値だけで計算します。観測数は `return_samples_5d`、未観測はnull/N/Aです。
過去に保存済みの不正な実績は自動修復されないため、別途確認してください。
