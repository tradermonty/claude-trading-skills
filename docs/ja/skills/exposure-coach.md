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

入力に `evaluation_coverage` がある場合、schema 1.0の整合する件数と
`verdict: complete` が必要です。部分評価・評価不能・不正な件数はstderrへ警告し、
採点対象から除外します。そのスコアや元の文脈を信頼度・方向性へ戻さないでください。
このブロックがない従来の入力も引き続き利用できます。

| 出力 | 意味 |
|---|---|
| exposure ceiling | 株式に割り当てる上限の目安 |
| action recommendation | 新規リスク可否 |
| growth/value bias | グロース寄りかバリュー寄りか |
| participation breadth | 上昇が広いか狭いか |
| confidence | 入力の充足度（鮮度・品質検証・予測精度ではない） |

`inputs_provided`・`inputs_missing`・`inputs_unparseable`・`input_warnings`を確認します。
診断フィールドは内容がある場合のみ出力し、通常の既存JSON形式を維持します。
テーマ・セクター入力の未指定はmissing、指定済みでも読めない・不正な場合はunparseableとして除外し、stderrへ警告します。
上流の品質警告はJSON・Markdown・stderrに保持します。

正規theme-detectorレポートは`themes.all`を一度だけ使用します。方向はbullish/bearish、heatは有限な数値0〜100（真偽値は不可）、
`data_quality`はstatusがok/warningでflagsが文字列リストであることが必須です。行や品質情報が欠ける・不正なら全体を除外します。
変換規則は`round(50 + mean(signed_heat)/2)`で、bullishは正、bearishは負です（最近接整数、ちょうど中間なら偶数へ）。
heat 80ならbullishは90、bearishは10、同じ強さの対立テーマは50です。消費側の未較正の補助規則であり、鮮度や予測の正しさを保証しません。
旧theme_scoreと既知のtheme_strengthも引き続き利用できます。

### Sector Analyst の正規JSON

`python3 skills/sector-analyst/scripts/analyze_sector_rotation.py --json --save`
で生成し、表示された `sector_rotation_*.json` の正確なパスをそのまま `--sector` に渡します。

`ranking` には既知の11セクターが重複・欠落なく必要です。各行の `ratio` は有限な数値0〜1、
`slope` はnullまたは有限な数値−1〜1で、真偽値は認めません。trendは文字列が必要です。slopeがnull（生成側はCSVの空欄をnullにします）の場合や、trendとslopeの向きが合わない場合は、警告を付けて受理し、傾きによる加減点は行いません。
`trends` の上向き・下向き件数とセクター一覧も各行に一致する必要があります。
`meta` はオブジェクト必須です。鮮度情報の省略・nullは警告付きで受理しますが、不正な形式は拒否します。
必要データが部分的・不正・矛盾する場合は全体を除外し、旧形式のスコアを追加しても検証を迂回できません。

変換規則 `sector_uptrend_health_v1` は、Uptrend Analyzerの絶対比率の区分
（境界0.097・0.25・0.37・0.50）を各セクターに適用し、trendがUpでslopeが正なら+5、Downで負なら−5、それ以外は0を加算します。
各値を0〜100に収め、**個別には丸めず**11セクターを等しく平均し、最後に一度だけ最近接整数へ丸めます
（ちょうど中間なら偶数へ）。相対的なローテーション指標 `groups.score` の転用や、比率のばらつきが小さいことへの加点は行いません。
未較正の補助規則であり、銘柄数で重み付けした市場全体の比率や予測精度を表すものではありません。
厳密な計算式は[Sector Scoreの説明](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/exposure-coach/references/exposure_framework.md#sector-score)を参照してください。

正規セクター入力は合成スコアだけに使い、bias・participationは他の受理済み入力から判定します。
正規JSONの比率spreadを従来のdispersionに読み替えることはしません。
対応する旧 `sector_score` または `dispersion`/`leadership` 入力は、従来の採点と検証済み文脈による判定を維持します。

`sector_integration` に変換version・各セクターの計算・`source_freshness` が記録されます。
鮮度不明・上流が古いと申告したデータ・上流の警告は、JSON・Markdown・stderrへ保持し、他の要件を満たす入力は受理します。
`is_fresh: true` も生成側の申告であり、`--as-of` を指定しない場合は利用時点の経過日数を再検証せず、`freshness_verified` はfalseのままです。
`--as-of` を指定すると、セクターの元データの日付 `meta.freshness.date` を、America/New_York での評価日と比べます。評価日より後の日付、または `--max-age-days` より古い日付なら、セクター入力を使えない入力として除外します。
`--require-provenance` では、鮮度が不明なレポートと、日付のない旧形式の入力も除外します。除外しても実行は止まらず、`inputs_unparseable`・`input_warnings`・Markdown・stderrに理由が出ます。検証に通ると `freshness_verified` がtrueになり、`freshness_check` に結果が記録されます。
厳格モード以外では、タイムゾーンのない `--as-of` や負の `--max-age-days` を渡しても実行は止まらず、セクターの年齢チェックだけを警告付きで省略します。
Sector AnalystとUptrend Analyzerは上流データを共有するため、入力が増えても独立した証拠が増えたとは限りません。
confidenceは受理した入力の充足度であり、独立性・鮮度・検証済み品質・予測精度の保証ではありません。

### 市場ステータスによる上限オーバーレイ

ftd-detectorのJSONに統合された`market_state.market_status`がある場合、重み付き平均には加えず、結果の上限として適用します。
複合スコアは変わらず、`exposure_ceiling_pct`は`min(複合スコアの上限, cap)`です。

- `market_in_correction`（CORRECTION、RALLY_ATTEMPT、FTD_WINDOW、RALLY_FAILED、FTD_INVALIDATED）: 上限20%。NEW_ENTRY_ALLOWEDはREDUCE_ONLYに下がり、CASH_PRIORITYはそのままです。
- `confirmed_uptrend`でFTD_CONFIRMED: `ftd_invalidation.days_since_ftd`で決まります。5セッション未満は40%、5〜14は60%、15以上は80%、経過日数が不明なら60%です。推奨は変わりません。
- `confirmed_uptrend`でUPTREND_RESUMED: 上限80%。FTDではなく、新高値による再開として表示します。
- `uptrend_under_pressure`: 確認済みの上限より1段階（20ポイント）低く、下限は20%です。rationaleに「be selective」と`cycle.pressure_reasons`を載せます。
- ステータスがnullまたは無い場合（旧ftd-detector出力、NO_SIGNAL、データ欠損）や`--ftd`が無い場合: オーバーレイも新しいキーもありません。

結果の`market_status_overlay`ブロックを確認します。項目は`status`、`legacy_state`、`cap_pct`、`applied`、`reason`、`days_since_ftd`、`per_index`、`pressure_reasons`です。Markdownレポートにも表示します。

これらのcapは、IBDに着想を得た未較正のモデル上の選択です。IBD自身の指針は二次報道からの引用にとどまります。
[リスク管理ルール](https://inkl.com/news/trump-tariff-sell-off-how-ibd-s-risk-management-rules-avoided-big-losses)、
[FTD後の投資](https://www.inkl.com/news/how-to-invest-after-a-follow-through-day-3-breakout-stocks-to-watch)を参照してください。
メンテナーの検証では、これらのシグナルでエクスポージャーを変えても、同じ平均エクスポージャーを保つ場合と比べて、指数レベルのリターン（S&P 500、Nasdaq、RSP、SPY、QQQ）はほとんど変わりませんでした。
この上限は、個別株を買い増せる環境かどうかを判断するためのもので、指数売買のシグナルではありません。

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
