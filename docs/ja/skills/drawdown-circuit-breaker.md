---
layout: default
title: "Drawdown Circuit Breaker"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/drawdown-circuit-breaker/
permalink: /ja/skills/drawdown-circuit-breaker/
generated: false
---

# Drawdown Circuit Breaker
{: .no_toc }

trader-memory-core の状態から口座レベルのドローダウン・サーキットブレーカーを評価し、今日新規リスクを取ってよいかを判定します。実現損益、連敗クールダウン、週次/月次ドローダウン制限を使い、外部APIなしで動作します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/drawdown-circuit-breaker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Drawdown Circuit Breaker は、口座レベルの実現損益と直近の終端トレード結果から、今日の新規トレードリスクを許容できるかを評価します。読み取り対象は trader-memory-core の thesis YAML のみです。市場側ゲートである exposure-coach の `exposure_decision` と対になる、トレーダー側ゲート `circuit_breaker_decision` を生成します。

このサーキットブレーカーは推奨と記録のための道具です。人間の判断を置き換えるものではなく、ブローカー側で注文を自動停止するものでもありません。

---

## 2. 使うタイミング

- 新しいスイングトレード候補をスクリーニングまたはサイジングする前
- 損切りや部分利確/損切りの後、クールダウンが必要か確認したいとき
- trader-memory-core に直近のクローズ済みまたは部分クローズ済みポジションがある日次計画時
- swing-opportunity-daily の候補生成前ゲートとして使うとき
- 日次、週次、月次の損失制限に到達していないかレビューするとき

---

## 3. 前提条件

- Python 3.9+
- 通常は `state/theses/` にある trader-memory-core の thesis YAML
- 口座サイズ
- APIキーやネットワーク接続は不要

---

## 4. クイックスタート

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --output-dir reports/
```

---

## 5. ワークフロー

### Step 1: Trader Memory State を読む

thesis state directory を指定して実行します。

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --output-dir reports/
```

スクリプトはすべての `th_*.yaml` を走査し、各 thesis の `status_history[]` ledger から `realized_pnl` を読みます。`_index.json` は P&L 計算に使いません。インデックスは軽量な検索用ファイルであり、部分クローズや日次実現損益に必要な台帳を持たないためです。

state directory が存在しない、または空の場合は、`data_quality: EMPTY_STATE` とともに `TRADING_ALLOWED` を返します。履歴がまだない新規ユーザーをブロックしないためです。

### Step 2: サーキットブレーカールールを評価する

デフォルトルールは次の通りです。

| ルール | デフォルト | トリップ時の状態 | 解除 |
|--------|------------|------------------|------|
| 日次最大損失 | 口座の2.0% | HALTED | 次のET平日 |
| 連敗クールダウン | 終端 thesis 2連敗 | COOLDOWN | 最後の負け exit から24時間 |
| 週次ドローダウン停止 | 口座の5.0% | HALTED | 次の月曜ET |
| 月次ドローダウン停止 | 口座の8.0% | HALTED | 次月1日ET |

日、週、月の境界は `America/New_York` で判定します。`trader-memory-core`
が日付のみの入力から生成するtimestampは、指定されたET日付のイベントとして扱います。
テストやサンプル実行を決定論的にしたい場合は `--as-of` を指定します。日付のみの
`--as-of` はそのET日付の終日を対象にし、時刻付きの `--as-of` はその時刻より後の
未来イベントを除外します。

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --state-dir state/theses \
  --account-size 100000 \
  --as-of 2026-07-02T12:00:00-04:00 \
  --output-dir reports/
```

### Step 3: 閾値を上書きする

個別のCLI引数で閾値を変更できます。

```bash
python3 skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py \
  --account-size 100000 \
  --max-daily-loss-pct 1.5 \
  --losing-streak-n 3 \
  --cooldown-hours 48 \
  --weekly-drawdown-pct 4 \
  --monthly-drawdown-pct 6
```

JSON config でもまとめて指定できます。

```json
{
  "max_daily_loss_pct": 1.5,
  "losing_streak_n": 3,
  "cooldown_hours": 48,
  "weekly_drawdown_pct": 4.0,
  "monthly_drawdown_pct": 6.0
}
```

CLI引数は config ファイルの値より優先されます。

### Step 4: 判定を解釈する

生成された decision を新規トレードリスクのゲートとして使います。

| Recommendation | 意味 |
|----------------|------|
| TRADING_ALLOWED | 有効なサーキットブレーカールールはなく、次のワークフローに進める |
| COOLDOWN | 新規ポジションは取らず、既存ポジション管理と直近損失のレビューに集中する |
| HALTED | 有効期限まで新規エントリーを停止し、レビューに集中する |

既存ポジションの管理は人間が判断します。このスキルは、実現損失後に新規リスクを積み増すことを防ぐためのゲートです。

---

## 6. 出力形式

スクリプトは `circuit_breaker_decision_YYYY-MM-DD_HHMMSS.json` を出力し、`--json-only` がない場合は同名の Markdown レポートも出力します。

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-02T16:00:00+00:00",
  "as_of_date": "2026-07-02",
  "recommendation": "COOLDOWN",
  "triggered_rules": [
    {
      "rule": "losing_streak_cooldown",
      "threshold": 2,
      "observed": 2,
      "active_until": "2026-07-02T15:30:00-04:00",
      "detail": "2 consecutive losing closes; last loss exit 2026-07-01T15:30:00-04:00."
    }
  ],
  "metrics": {
    "realized_pnl_today": 0.0,
    "realized_pnl_wtd": -250.0,
    "realized_pnl_mtd": -250.0,
    "consecutive_losses": 2,
    "last_loss_exit_at": "2026-07-01T15:30:00-04:00",
    "theses_scanned": 12
  },
  "account_size": 100000.0,
  "config": {
    "max_daily_loss_pct": 2.0,
    "losing_streak_n": 2,
    "cooldown_hours": 24.0,
    "weekly_drawdown_pct": 5.0,
    "monthly_drawdown_pct": 8.0
  },
  "data_quality": "OK",
  "warnings": [],
  "rationale": "Recent losing closes triggered a cooldown. Avoid new entries until the cooldown expires."
}
```

---

## 7. リソース

- `scripts/check_circuit_breaker.py` - メインCLIとルールエンジン
- `references/circuit_breaker_framework.md` - ルール定義、デフォルト値、データソースの注意点
- `skills/trader-memory-core/schemas/thesis.schema.json` - thesis state のソーススキーマ

---

## 8. 重要原則

1. **実現損益のみを見る** - 日次計算には記録済みの `realized_pnl` を使い、未実現損益や thesis 単位の累計だけに依存しない。
2. **生存を優先する** - サーキットブレーカーは損失後のエスカレーションを止めるためにある。
3. **助言であり自動執行ではない** - 出力は workflow gate に使うが、注文の発注、取消、ブロックは行わない。
4. **段階的に劣化する** - 空 state は許可し、壊れたローカルファイルは `PARTIAL` として記録しつつクラッシュを避ける。
