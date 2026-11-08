---
layout: default
title: "Stockbee Momentum Burst Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 50
lang_peer: /en/skills/stockbee-momentum-burst-screener/
permalink: /ja/skills/stockbee-momentum-burst-screener/
generated: false
---

# Stockbee Momentum Burst Screener
{: .no_toc }

Stockbee / Pradeep Bonde スタイルの短期 Momentum Burst 候補をスクリーニングするスキルです。4% ブレイクアウト、ドル幅ブレイクアウト、レンジ拡大、出来高拡大、直前レンジ収縮、終値位置、失敗フィルター、ストップまでの距離をまとめて評価します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-momentum-burst-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-momentum-burst-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Stockbee Momentum Burst Screener は、短期の 3-5 日スイングを想定したモメンタム候補を探すためのスクリーナーです。

主な判定軸:

- 4% ブレイクアウト: 前日終値比で 4% 以上上昇し、出来高条件を満たす
- ドル幅ブレイクアウト: 始値から終値までの値幅が十分に大きい
- レンジ拡大: 直近よりも当日の値幅が明確に拡大している
- 出来高拡大、終値の高値引け度合い、直前ベースの収縮
- 直近で伸び切った銘柄や 4% 下落などの失敗フィルター
- エントリー基準からストップ基準までのリスク距離

出力は「候補の優先順位付け」です。自動売買シグナルではなく、チャート確認、ポジションサイズ計算、学習用モデルブックへ渡す前段のフィルターとして使います。

---

## 2. 使う場面

- Stockbee / Pradeep Bonde 風の Momentum Burst 候補を探したい
- 4% breakout、dollar breakout、range expansion の候補を見たい
- 短期スイング向けに A / B / C のセットアップ品質を比較したい
- 銘柄リスト、ユニバースファイル、または OHLCV JSON を使ってスクリーニングしたい
- 候補を `technical-analyst`、`position-sizer`、`trader-memory-core`、`stockbee-setup-fluency-trainer` に渡したい

使わない場面:

- 市場レジームが新規リスクを許可していないのに、そのまま発注判断へ進む
- 長期投資、配当投資、ファンダメンタルズ評価だけで候補を選びたい
- 人間のチャート確認なしに売買を実行したい

---

## 3. 前提条件

ライブのユニバース取得と過去 OHLCV 取得には Financial Modeling Prep の API キーが必要です。

```bash
export FMP_API_KEY=your_api_key_here
```

API を使わない検証では、銘柄ごとの日足 OHLCV を含む `--prices-json` を渡します。ただし通常の FMP ユニバーススキャンを行う場合は FMP API が必須です。

実運用では、先に market-regime 系ワークフローで新規スイングリスクが許容されているか確認してください。レジームが不利な場合、出力は `manual-review-only` として扱います。

---

## 4. クイックスタート

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

---

## 5. ワークフロー

### Step 1: 入力モードを選ぶ

FMP ユニバースを使う場合:

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe \
  --max-symbols 300 \
  --output-dir reports/
```

明示的な銘柄リストを使う場合:

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols NVDA SMCI PLTR TSLA \
  --output-dir reports/
```

ローカル OHLCV JSON を使う場合:

```bash
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --as-of 2026-11-06 \
  --output-dir reports/
```

### Step 2: スクリーニング結果を読む

生成される JSON / Markdown レポートでは、候補ごとに次を確認します。

- トリガー種別と一致したタグ
- 当日上昇率、ドル幅、出来高倍率、終値位置
- 直前ベースの日数と幅
- エントリー基準、ストップ基準、ストップまでのリスク率
- セットアップスコア、格付け、状態、除外理由
- 次に取るべきレビューアクション

### Step 3: 候補を下流の確認へ渡す

スコアは保守的に扱います。

- A / A- 候補: `technical-analyst` でチャートを手動確認し、問題なければ `position-sizer` へ渡す
- B 候補: ウォッチリスト、または小さなリスクでの検討に留める
- Watch-only 候補: モデルブックに残し、チャート確認で格上げされない限り売買計画にしない
- Rejected 候補: 実行用ではなく、後日の失敗例分析に使う

---

## 6. リソース

参照資料:

- `skills/stockbee-momentum-burst-screener/references/entry_exit_rules.md`
- `skills/stockbee-momentum-burst-screener/references/momentum_burst_methodology.md`
- `skills/stockbee-momentum-burst-screener/references/scoring_system.md`

スクリプト:

- `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py`

## 確定セッションとデータ鮮度

全入力モードで採点前に鮮度を検証します。既定の基準は、取得開始前に固定した
NYSEの直近確定セッションです。取引時間中の未確定バーは除外し、週末・祝日・
夏時間・短縮取引日は共通カレンダーに従います。

- `--as-of YYYY-MM-DD` は指定日以前の最終セッションを選びます。実際の直近確定
  セッションを超える指定は、当日の引け前も含めてエラーです。過去日付は取得済み
  データの範囲を制限するだけで、ライブFMPの過去取得やPITデータを保証しません。
- `--max-bar-age-sessions N` は許容する経過セッション数です。非負整数、既定値0。
  大きい値を指定しても古い観測が現在のデータになるわけではありません。
- 日付は正規の`YYYY-MM-DD`が必要です。日付欠落・不正、最新対象バーが休場日なら
  `invalid_price_date`、基準日以前にバーがなければ`no_completed_price_data`、
  古すぎれば`stale_price_data`として`REJECTED`になり、売買計画へ送りません。
- カレンダー障害・未来または未確定の日付指定は終了1、引数構文エラーは終了2。
  これらの失敗では既存レポートを変更しません。FMPのuniverse取得ではactive銘柄を
  要求し、明示的にinactiveとされた行も除外します。

JSONには銘柄別の`latest_bar_date`、`expected_session`、`bar_age_sessions`、
`max_bar_age_sessions`を追加します。判定不能な値はnullです。metadataには
`latest_bar_dates`と`stale_price_data_count`もあり、Markdownの集計にも基準日・
許容日数・古いデータによる除外数を表示します。過去の架空データの検証には、
例えば`--as-of 2026-11-06`を明示してください。鮮度の検証は売買承認ではありません。
