---
layout: default
title: "Futures Position Sizer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 32
lang_peer: /en/skills/futures-position-sizer/
permalink: /ja/skills/futures-position-sizer/
generated: false
---

# Futures Position Sizer
{: .no_toc }

方向・エントリー価格・ストップロスから、先物のコントラクト数を計算するスキルです。銘柄ごとに検証済みの契約仕様（乗数・ティックサイズ・ティック価値）を使用します。何枚の先物コントラクトを取引すべきか尋ねられたとき、先物ポジションのサイジングをしたいとき（ES、NQ、ZB、GC、CL、6E/E6、VX、BTなど）、あるいはcontrarian-setup-gateのREADY_FOR_PLAN判定からdirectionとinvalidation_levelを引き継いでサイジングするときに使用します。APIキーもネットワークも使わない、純粋でオフラインな計算スキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/futures-position-sizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/futures-position-sizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

ジェイソン・シャピロの逆張りパイプラインにおけるステップ4です。方向・エントリー価格・ストップロスと、口座のリスク予算、検証済みの契約仕様（乗数・ティックサイズ・ティック価値）から、コントラクト数を計算します。既存の`position-sizer`とは別の新規スキルです。先物はレバレッジの効いたマルチプライヤーベースの商品で、1ポイントあたりのドル価値が銘柄ごとに大きく異なります。0.25ポイントの値動きはESでは12.50ドルですが、NQでは5.00ドル、ZBでは31.25ドルになります。株式の株数計算用サイザーを先物に転用すると、この違いを反映できずサイズを誤って計算してしまいます。

サイジングには2つの方法があります。

- **モードA（明示指定）**: `--symbol --direction --entry --stop`を直接指定します
- **モードB（ゲート引き継ぎ）**: `--gate-json <contrarian-setup-gateのレポート> --entry`を指定します。directionとstop（ゲートの`invalidation_level`）はゲートの`READY_FOR_PLAN`レポートから取得します。ゲートがREADYと確認していないセットアップはサイジングしません。また`--gate-json`と一緒に明示的な`--direction`や`--stop`を指定することはできません。ゲートが指定されている場合、ゲートの値が優先されます

`--entry`はどちらのモードでも常に必須です。このスキルもゲートもエントリー価格を算出することはなく、オペレーターが指定します。

---

## 2. 使用タイミング

- contrarian-setup-gateがREADY_FOR_PLANに到達し、確認済みのdirectionとstopに対するコントラクト数が必要なとき
- 「ES/NQ/GC/CLは何枚トレードすべきか」と尋ねられたとき
- エントリーとストップが既知の先物トレードアイデアがあり、リスクベースでサイジングしたいとき
- サイジング前に、銘柄の検証済み契約仕様（乗数・ティックサイズ・ティック価値）を確認したいとき（`--list-specs`）

---

## 3. 前提条件

- **Python 3.9以上、標準ライブラリのみ**
- **APIキーは不要です。** このスキルは完全にオフラインで動作します
- direction・entry・stop（モードA）、または`setup_status: READY_FOR_PLAN`のcontrarian-setup-gate JSONレポート（モードB）
- 検証済み23銘柄のコアテーブルに含まれない銘柄を扱う場合は、その乗数・ティックサイズ・建値通貨（3つすべて）

---

## 4. クイックスタート

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ES --direction LONG --entry 5000.25 --stop 4980.00 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

---

## 5. ワークフロー

### Phase 1: ポジションのサイジング

**モードA - 明示指定:**

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ES --direction LONG --entry 5000.25 --stop 4980.00 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

**モードB - ゲート引き継ぎ:**

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --gate-json reports/contrarian_setup_gate_B6_2026-07-15.json \
  --entry 1.3400 \
  --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/ --format both
```

モードBでは`--symbol`を省略できます。省略した場合はゲートレポートから取得します。両方を指定した場合は一致している必要があり、一致しなければ`gate_symbol_mismatch`になります。`--direction`と`--stop`を`--gate-json`と一緒に指定すると使用方法エラーとなり、終了コード2で終了します。どちらか一方のモードのみを使用してください。

### Phase 2: 結果の読み取り

| `sizing_status` | 意味 |
|---|---|
| `SIZED` | `contracts`が1以上です。`total_risk_usd`と`risk_pct_of_account`が実際に取ったリスクを示します |
| `NO_TRADE` | 決してクラッシュしません。常に`no_trade_reason`が付与されます。理由の一覧は下記を参照してください |

`risk_below_one_contract`によるNO_TRADEでも、リスク計算そのもの（コントラクトあたりリスク・リスク予算・ストップ距離）はレポートに含まれます。指定したリスク率とストップ距離では1枚分の予算を確保できないだけなので、ストップを広げる、リスク率を上げる、あるいは見送るという判断につながります。

### Phase 3: 警告の確認

`warnings`（トップレベルのリスト）はサイジングをブロックしません。監査上注意すべき条件のみを示します。`risk_pct_above_2`はリスクが2%のガイドラインを超えたことを示し、`off_tick_grid_entry`と`off_tick_grid_stop`は非ボンド銘柄の価格がティックグリッドちょうどに乗っていないことを示します。これは気配値の途中値として正当なケースもありますが、確認する価値はあります。

### Phase 4: 検証済み契約仕様テーブルの確認

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py --list-specs
```

23銘柄のコアテーブル全体（乗数・ティックサイズ・ティック価値・通貨・取引所）を表示します。出典は各取引所の公式契約仕様ページです。銘柄ごとの出典URLと検証日は`references/futures-contract-specs.md`を参照してください。

## ボンド系銘柄のオフグリッドガード（32分の1表記から小数表記への変換）

ボンド・ノート系の先物（ZT、ZF、ZN、ZB）は、ポイントの分数表記（32分の1、または32分の1のさらに分数）で気配され、アポストロフィで区切って表記されます。`110'16`は`110 + 16/32 = 110.50`を意味します。アポストロフィの後ろの数字をそのまま小数のセントとして読み違え、`110.16`と入力してしまうミスは、静かに誤った金額計算を生む典型的な事故です。`110.16`はZBの1/32グリッド（`0.03125`）に一切乗りません。

```bash
# 誤り - 110.16はZBの1/32グリッドに乗っていません。おそらく "110'16"（110.50を意味します）の
# 打ち間違いです。終了コード2で終了し、レポートは書き出されません
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ZB --direction LONG --entry 110.16 --stop 108.00 \
  --account-size 100000 --risk-pct 1.0

# 正しい入力 - 32分の1の数字ではなく、小数表記のポイントを入力します
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --symbol ZB --direction LONG --entry 110.50 --stop 108.00 \
  --account-size 100000 --risk-pct 1.0
```

テーブル内の他の銘柄はすべて通常の小数表記で気配されます。気配値の途中値などでティックグリッドから外れていても、`off_tick_grid_*`の警告のみで、拒否はされません。

---

## 6. リソース

**リファレンス:**

- `skills/futures-position-sizer/references/futures-contract-specs.md`
- `skills/futures-position-sizer/references/sizing-methodology.md`

**スクリプト:**

- `skills/futures-position-sizer/scripts/futures_position_sizer.py`
- `skills/futures-position-sizer/scripts/futures_sizing.py`
