---
layout: default
title: "Stockbee Exhaustion Hammer Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 51
lang_peer: /en/skills/stockbee-exhaustion-hammer-screener/
permalink: /ja/skills/stockbee-exhaustion-hammer-screener/
generated: false
---

# Stockbee Exhaustion Hammer Screener
{: .no_toc }

Stockbee / Pradeep Bonde スタイルの selling exhaustion hammer 候補を探すスキルです。流動性・品質、直前モメンタム、押し目の深さ、undercut/reclaim、長い下ヒゲ、終値位置、出来高、ストップまでのリスクをまとめて評価します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-exhaustion-hammer-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-exhaustion-hammer-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

このスキルは、引け前に出る売り枯れ型のハンマー候補を探すためのスクリーナーです。単なるローソク足のハンマーではなく、文脈を重視します。

主な判定軸:

- 品質・流動性: 価格、出来高、20日平均ドル出来高、任意の時価総額・保有者メタデータ
- 直前モメンタム: 近い高値、20日 / 60日の強さ
- 押し目: 直近高値からの適度な下落
- 売り枯れ: 短期安値の undercut/reclaim、数日間の売り、出来高確認
- ハンマー形状: 長い下ヒゲ、小さい実体、強い終値位置、安値からの回復
- リスク: エントリー基準から当日安値ストップまでの距離

出力は候補の優先順位付けです。自動売買シグナルではありません。

---

## 2. 使う場面

次のようなときに使います。

- Stockbee / Pradeep Bonde 風の exhaustion setup を探したい
- 引け前にハンマー反転候補を見つけたい
- 強い銘柄の押し目で、最後の投げ売りが尽きた可能性を探したい
- undercut/reclaim 候補を手動チャート確認に回したい
- `stockbee-setup-fluency-trainer` に学習用サンプルを渡したい

市場レジームが restrictive のときや、チャート確認なしに発注判断へ進む用途には使いません。

---

## 3. 前提条件

ライブのユニバース取得と FMP データ取得には Financial Modeling Prep の API キーが必要です。

```bash
export FMP_API_KEY=your_api_key_here
```

API を使わない場合は、銘柄ごとの OHLCV JSON を渡します。引け前運用では、最新バーが引け前時点の暫定日足になっていることが重要です。

---

## 4. クイックスタート

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --max-symbols 300 \
  --market-gate allowed \
  --output-dir reports/
```

引け前の quote override を使う場合:

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --fmp-universe \
  --use-quote-latest \
  --max-api-calls 700 \
  --market-gate allowed \
  --output-dir reports/
```

ローカルの暫定 OHLCV を使う場合:

```bash
python3 skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py \
  --prices-json data/near_close_daily_ohlcv.json \
  --profiles-json data/quality_profiles.json \
  --market-gate allowed \
  --output-dir reports/
```

---

## 5. 出力の読み方

候補ごとに次を確認します。

- 状態と格付け
- 直近高値からの押し目率
- undercut/reclaim の有無
- ハンマー形状の各指標
- 出来高倍率と平均ドル出来高
- エントリー / ストップ基準とリスク率
- スコア内訳と除外理由

Actionable 候補でも、必ずチャート確認、決算・ニュースリスク確認、ポジションサイズ計算を行います。

両レポートには `evaluation_coverage` ブロックが含まれます（`docs/dev/evaluation-coverage-contract.md`）。
候補0件の結果は、必ず `verdict` と合わせて読みます。全対象銘柄がスクリーニング判定に
到達したのは `complete` のときだけです。価格履歴の不足や取得失敗は拒否ではなく、
`not_evaluated_reasons` に未評価として計上されます。何も評価できなかった実行でも、
両レポートは `not_evaluable` の判定で出力され、終了コードは0です。

---

## 6. リソース

参照資料:

- `skills/stockbee-exhaustion-hammer-screener/references/exhaustion_hammer_methodology.md`
- `skills/stockbee-exhaustion-hammer-screener/references/scoring_system.md`
- `skills/stockbee-exhaustion-hammer-screener/references/near_close_operations.md`

スクリプト:

- `skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py`
