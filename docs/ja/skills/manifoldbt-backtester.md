---
layout: default
title: "Manifoldbt Backtester"
grand_parent: 日本語
parent: スキルガイド
nav_order: 41
lang_peer: /en/skills/manifoldbt-backtester/
permalink: /ja/skills/manifoldbt-backtester/
generated: false
---

# Manifoldbt Backtester
{: .no_toc }

宣言型の戦略スペックをmanifoldbt RustエンジンでOHLCVバーに対して実行し、約定ログをラウンドトリップに束ね、backtest-expertスキルが採点する8つの入力値を出力します。バックテストを実行したいとき、記述したルールを計測したいとき、実バーから勝率・平均勝ち・平均負け・最大ドローダウンを得たいとき、推定値ではなく実測値でbacktest-expertに渡したいときに使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/manifoldbt-backtester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/manifoldbt-backtester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

# manifoldbt Backtesterスキル

---

## 2. 使用タイミング

- ユーザーがルールを記述し、それを計測したい場合
- `backtest-expert` を実行予定だが数値がまだ存在しない場合
- 勝率、平均勝ち、平均負け、ドローダウンをバーから得る必要がある場合
- 採点のために戦略のパラメータ数を確定させる必要がある場合

判定は `backtest-expert` に委ねます。閾値とレッドフラグはあちらが持ち、このスキルは重複しません。

---

## 3. 前提条件

- Python 3.9以降
- `pip install manifoldbt` (Apache 2.0 with Commons Clause。このスキルが行うことはすべて無料枠でまかなえます)
- カラム `timestamp, open, high, low, close, volume` を持つCSVまたはParquet形式のOHLCVバー
- APIキー不要

---

## 4. クイックスタート

```bash
Field reference: `references/strategy_spec.md`.

Set `fees_bps` and `slippage_bps` to realistic values before you read any
result. A frictionless run scores 0 on execution realism, and over short holding
periods costs decide whether an edge survives.

### 2. Run it
```

---

## 5. 仕組み

### 1. 戦略スペックを書く

スペックはインジケーターと1つのエントリー条件を命名します。仮説を述べる最小のルールに留めます。ノブを1つ足すごとに、偶然のインサンプル適合が容易になり、評価者はその数を減点します。

```json
{
  "name": "sma_cross_costed",
  "indicators": {
    "fast": { "type": "sma", "period": 20 },
    "slow": { "type": "sma", "period": 60 }
  },
  "entry": { "left": "fast", "op": ">", "right": "slow" },
  "size": 1.0,
  "stop_loss_pct": 1.5,
  "fees_bps": 5.0,
  "slippage_bps": 2.0
}
```

フィールドリファレンス: `references/strategy_spec.md`。

結果を読む前に `fees_bps` と `slippage_bps` を現実的な値に設定します。フリクションレスの実行は執行リアリズムで0点となり、短期保有ではコストがエッジの生死を分けます。

### 2. 実行する

```bash
python3 scripts/run_backtest.py \
  --spec strategy.json \
  --data bars.csv \
  --symbol BTCUSDT \
  --json-out result.json
```

スクリプトはデータに触れる前にスペックを検証するため、スペックの誤りは長時間ロードの後ではなく1秒で分かります。

### 3. 数値の前に警告を読む

実行は結果の読み方を変える警告を出力します。取引30件未満のサンプル、1年未満の期間、フリクション未モデル化、エンジンの勝率とペアリング後の勝率の乖離などです。いずれも設定を直して再実行する理由になります。

以下3条件ではスコアを出さず引き継ぎを停止します。完了ラウンドトリップなし、最大ドローダウンの欠測または非有限、スクラッチ取引です。評価者にスクラッチ入力はないため、それらを含む母集団を渡すと導出期待値が完了取引と不一致になります。

### 4. backtest-expertに引き継ぐ

実行の最後に貼り付け可能なコマンドが出ます。それを実行するか、同じ数値で `backtest-expert` スキルを呼び出します。

```bash
python3 skills/backtest-expert/scripts/evaluate_backtest.py \
  --total-trades 3854 --win-rate 20.24 \
  --avg-win-pct 0.2917 --avg-loss-pct 0.2342 \
  --max-drawdown-pct 99.2893 --years-tested 0 \
  --num-parameters 3 --slippage-tested
```

---

## 6. リファレンス

**リファレンス:**

- `skills/manifoldbt-backtester/references/metric_bridge.md`
- `skills/manifoldbt-backtester/references/strategy_spec.md`

**スクリプト:**

- `skills/manifoldbt-backtester/scripts/bridge.py`
- `skills/manifoldbt-backtester/scripts/round_trips.py`
- `skills/manifoldbt-backtester/scripts/run_backtest.py`
- `skills/manifoldbt-backtester/scripts/spec.py`
