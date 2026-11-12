---
layout: default
title: "Exposure Coach"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/exposure-coach/
permalink: /ja/skills/exposure-coach/
generated: false
---

# Exposure Coach
{: .no_toc }

市場ブレッドス、上昇参加率、マクロレジーム、トップリスク、テーマ、セクター、機関投資家フローを統合し、株式への許容エクスポージャー上限と新規リスク可否をまとめるスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/exposure-coach.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/exposure-coach){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Exposure Coach は、個別銘柄を分析する前に「今、株式リスクをどれだけ取ってよいか」を決めるための制御盤です。複数の市場環境スキルの出力を統合し、次のような Market Posture を作ります。

- net exposure ceiling
- growth vs value bias
- breadth / participation assessment
- `NEW_ENTRY_ALLOWED`、`REDUCE_ONLY`、`CASH_PRIORITY`
- 入力の揃い具合に基づく confidence

---

## 2. 使う場面

- 新しいスイングトレード候補を検討する前
- 週初にポートフォリオのリスク上限を決めるとき
- ブレッドス、レジーム、テーマ、トップリスクのシグナルが食い違うとき
- 大きなマクロイベント後に株式比率を見直すとき
- cash priority か新規 entry allowed かを明文化したいとき

---

## 3. 前提条件

推奨される上流出力:

- `market-breadth-analyzer`
- `uptrend-analyzer`
- `macro-regime-detector`
- `market-top-detector`
- `ftd-detector`
- `theme-detector`
- `sector-analyst`
- `institutional-flow-tracker`

一部の入力が欠けていても実行できます。ただし、欠けた入力が多いほど confidence は下がります。FMP は一部の上流スキルで必要になる場合があります。

---

## 4. クイックスタート

```bash
python3 skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth reports/breadth_latest.json \
  --uptrend reports/uptrend_latest.json \
  --regime reports/regime_latest.json \
  --top-risk reports/top_risk_latest.json \
  --ftd reports/ftd_latest.json \
  --theme reports/theme_latest.json \
  --sector reports/sector_latest.json \
  --institutional reports/institutional_latest.json \
  --output-dir reports/
```

---

## 5. 確認する出力

| 出力 | 意味 |
|---|---|
| exposure ceiling | 株式に割り当てる上限の目安 |
| action recommendation | 新規リスク可否 |
| growth/value bias | グロース寄りかバリュー寄りか |
| participation breadth | 上昇が広いか狭いか |
| confidence | 入力の充足度（鮮度・品質検証・予測精度ではない） |

`inputs_provided`・`inputs_missing`・`inputs_unparseable`・`input_warnings`を確認します。
診断フィールドは内容がある場合のみ出力し、通常の既存JSON形式を維持します。
テーマ入力の未指定はmissing、指定済みでも読めない・不正な場合はunparseableとして除外し、stderrへ警告します。
上流の品質警告はJSON・Markdown・stderrに保持します。

正規theme-detectorレポートは`themes.all`を一度だけ使用します。方向はbullish/bearish、heatは有限な数値0〜100（真偽値は不可）、
`data_quality`はstatusがok/warningでflagsが文字列リストであることが必須です。行や品質情報が欠ける・不正なら全体を除外します。
変換規則は`round(50 + mean(signed_heat)/2)`で、bullishは正、bearishは負です（最近接整数、ちょうど中間なら偶数へ）。
heat 80ならbullishは90、bearishは10、同じ強さの対立テーマは50です。消費側の未較正の補助規則であり、鮮度や予測の正しさを保証しません。
旧theme_scoreと既知のtheme_strengthも引き続き利用できます。

---

## 6. 運用ルール

- `NEW_ENTRY_ALLOWED`: 通常の候補選別へ進めます。ただし position sizing は別途確認します。
- `REDUCE_ONLY`: 新規 entry より既存ポジションの管理を優先します。
- `CASH_PRIORITY`: 新規リスクを避け、watchlist と検証に留めます。

Exposure Coach は個別銘柄の買い推奨ではありません。市場環境に応じたリスク上限を定めるための補助です。

---

## 7. 注意点

- canonical macro-regimeレポートには、nested `regime.confidence` と、有効な整数component countを持つ `composite.data_quality` が必須です。availability metadataの欠落・不正、`very_low` confidence、または利用可能コンポーネント0件は重要入力の欠損として扱います。regime scoreやbiasへ手動で戻さず、missing-input haircutとconfidence capを維持してください。
- theme detector の JSON が認識されない場合、テーマ要因を手動で exposure ceiling に混ぜないでください。
- 入力が少ないときは、結論より confidence と missing input を重視してください。
- 実際の発注前には `technical-analyst` と `position-sizer` で個別確認します。

## market-regime-daily の出所検証

必須2生成処理に同じ一意の `--run-id daily-20261017-unique` を渡します。
省略時は各処理が個別IDを生成します。JSONの `data_provenance` は主時系列の
実データ日付、UTC取得日時、出所、実行IDを記録します。不明な品質フラグはfalseです。
補助サマリーの日付は未検証であり、合成スコア全体の鮮度保証にはなりません。
主時系列の日付が欠落・不正な場合はレポート生成を停止します。

今回表示された正確なJSONパスをExposure Coachに渡し、
`--require-provenance --run-id daily-20261017-unique --as-of 2026-10-17T13:00:00Z
--max-age-days 3` を指定します。`--as-of` はタイムゾーン付き評価日時です。
schema 1.0・実行ID・UTC取得日時・未来日付・鮮度を採点前に検証し、失敗時は出力しません。
既定3暦日は取引所休日を考慮しない保守的な方針です。成功時は受理した出所と保証範囲を記録します。
任意のtop-risk等は検証対象外です。実行IDは真正性やpoint-in-timeの証明ではありません。
厳格モードを使わない従来の入出力形式も引き続き利用できます。
