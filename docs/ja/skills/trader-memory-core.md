---
layout: default
title: "Trader Memory Core"
grand_parent: 日本語
parent: スキルガイド
nav_order: 45
lang_peer: /en/skills/trader-memory-core/
permalink: /ja/skills/trader-memory-core/
---

# Trader Memory Core
{: .no_toc }

投資仮説のライフサイクルを永続的に追跡するステート層。スクリーニングから決済・振り返りまで、各スキルの出力を1つの thesis オブジェクトに統合します。
{: .fs-6 .fw-300 }

<span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trader-memory-core.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trader-memory-core){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Trader Memory Coreは「何を考え、何が起き、何を学んだか」を記録するスキルです。各投資仮説のライフサイクル全体をファイルベースで永続管理します。

```
スクリーナー出力 → IDEA → ENTRY_READY → ACTIVE → CLOSED
                    │          │            │
                    └──────────┴────────────┴──→ INVALIDATED
```

**解決する課題:**
- スクリーニングと執行追跡の間のギャップを解消
- 会話をまたいでトレードアイデアの単一情報源を提供
- 状態遷移を厳格に制御（ステップのスキップ不可）
- P&LとMAE/MFE付きの構造化ポストモーテムを生成
- 定期レビューのスケジューリングで放置ポジションを防止

**主要機能:**
- 7種のスクリーナーアダプター: kanchi-dividend-sop, earnings-trade-analyzer, vcp-screener, pead-screener, canslim-screener, edge-candidate-agent, edge-concept-synthesizer
- 5つのステータスによる前進限定ステートマシン
- フィンガープリントベースの重複排除（同じ入力で二重登録なし）
- Position Sizerからのポジションサイジング付与
- エスカレーション付きレビュースケジュール (OK → WARN → REVIEW)
- FMP API によるオプションの MAE/MFE 算出

**Phase 1 スコープ:** 単一銘柄のみ。ペアトレードとオプション戦略は Phase 2 で対応予定。

---

## 2. 使用タイミング

- スクリーナーが候補を出力した後、**永続的に追跡したい**とき
- 仮説をアイデアから**エントリー準備→アクティブポジションへ遷移**させたいとき
- **ポジションサイジングの結果を紐付け**たいとき
- **レビュー期限が来た仮説**を確認したいとき
- **ポジションを決済**してポストモーテム（振り返り）を生成したいとき
- **トレーディングジャーナル**としてP&L統計を確認したいとき

**トリガーフレーズ:** 「仮説を登録」「このアイデアを追跡」「仮説のステータス」「レビュー期限」「ポジションを決済」「ポストモーテム」「トレーディングジャーナル」

---

## 3. 前提条件

- **Python 3.9+** と `pyyaml`, `jsonschema`（プロジェクト依存に含まれます）
- **FMP API キー:** オプション — ポストモーテムの MAE/MFE 算出にのみ使用。コア機能（登録、遷移、決済、レビュー）は完全オフラインで動作
- **ステートディレクトリ:** `state/theses/` は初回使用時に自動作成

> FMP APIはポストモーテム時の日次価格データ取得（MAE/MFE算出）にのみ使用されます。APIキーがなくてもポストモーテムは他のすべてのフィールドで生成されます。
{: .tip }

---

## 4. クイックスタート

```bash
# ステップ 1: スクリーナー出力を thesis として登録
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# ステップ 2: thesis を検索
python3 skills/trader-memory-core/scripts/thesis_store.py \
  --state-dir state/theses/ list --status IDEA

# ステップ 3: サマリー統計を表示
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ summary
```

---

## 5. ワークフロー

### ステップ 1: 登録 — スクリーナー出力の取り込み

ソーススクリーナー名とJSON出力ファイルを指定してインジェストスクリプトを実行します:

```bash
# kanchi-dividend-sop から
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# earnings-trade-analyzer から
python3 skills/trader-memory-core/scripts/thesis_ingest.py \
  --source earnings-trade-analyzer \
  --input reports/earnings_trade_scored_2026-03-14.json \
  --state-dir state/theses/
```

JSONの各候補が `IDEA` ステータスの thesis になります。登録は**冪等**です — 同じ入力を2回実行しても重複は生じません（フィンガープリントによる重複排除）。

**対応ソース:** `kanchi-dividend-sop`, `earnings-trade-analyzer`, `vcp-screener`, `pead-screener`, `canslim-screener`, `edge-candidate-agent`

### ステップ 2: 分析レポートのリンク

深掘り分析（US Stock Analysis、Technical Analyst等）の結果を thesis に紐付けます:

```python
from skills.trader_memory_core.scripts.thesis_store import link_report

link_report(state_dir, thesis_id,
            skill="us-stock-analysis",
            file="reports/us_stock_AAPL_2026-03-15.md",
            date="2026-03-15")
```

### ステップ 3: IDEA から ENTRY_READY への遷移

分析で仮説を検証した後、昇格させます:

```python
from skills.trader_memory_core.scripts.thesis_store import transition

transition(state_dir, thesis_id, "ENTRY_READY",
           reason="テクニカル確認: 200日MA上・出来高増加")
```

> `transition()` は IDEA → ENTRY_READY のみ許可します。他の遷移は専用関数を使用してください。
{: .warning }

### ステップ 4: ポジション開設 (ENTRY_READY → ACTIVE)

トレードを執行したら、実際のエントリーを記録します:

```python
from skills.trader_memory_core.scripts.thesis_store import open_position

open_position(state_dir, thesis_id,
              actual_price=155.50,
              actual_date="2026-03-16T10:30:00-04:00")
```

これが **ACTIVE ステータスへの唯一の経路**です。`actual_price` と `actual_date`（RFC 3339形式、タイムゾーン必須）が必要です。

### ステップ 5: ポジションサイジングの付与

Position Sizer の出力をリンクして、株数とリスクパラメータを記録します:

```python
from skills.trader_memory_core.scripts.thesis_store import attach_position

attach_position(state_dir, thesis_id,
                report_path="reports/position_sizer_AAPL_2026-03-16.json")
```

レポートの `mode` は `"shares"` である必要があります（budget モードは拒否されます）。

### ステップ 6: 定期レビュー

注意が必要な thesis を確認します:

```bash
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ review-due --as-of 2026-04-15
```

レビューを記録（エスカレーション対応）:

```python
from skills.trader_memory_core.scripts.thesis_store import mark_reviewed

mark_reviewed(state_dir, thesis_id,
              review_date="2026-04-15",
              outcome="OK")  # OK, WARN, REVIEW のいずれか
```

`next_review_date` はレビュー間隔に基づいて自動的に更新されます。

### ステップ 7: 決済とポストモーテム

ポジションをクローズしたとき:

```python
from skills.trader_memory_core.scripts.thesis_store import close

close(state_dir, thesis_id,
      exit_reason="target_reached",
      exit_price=172.00,
      exit_date="2026-05-01T15:45:00-04:00")
```

ポストモーテムを生成:

```bash
python3 skills/trader-memory-core/scripts/thesis_review.py \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1
```

P&L、保有日数、（FMP APIキーがあれば）MAE/MFEを含むレポートが `state/journal/pm_{thesis_id}.md` に保存されます。

---

## 6. 出力の理解

### Thesis YAML ファイル

各 thesis は `state/theses/` にYAMLファイルとして保存されます:

| セクション | 主要フィールド | 説明 |
|-----------|--------------|------|
| Identity | `thesis_id`, `ticker`, `created_at` | ティッカーとハッシュを含む一意ID |
| Classification | `thesis_type`, `setup_type`, `catalyst` | 例: `dividend_income`, `earnings_drift` |
| Status | `status`, `status_history` | 現在のステータス + タイムスタンプ付き遷移ログ |
| Entry | `entry.target_price`, `entry.actual_price` | 計画 vs 実際のエントリー |
| Exit | `exit.stop_loss`, `exit.target_price`, `exit.actual_price` | 計画 vs 実際のイグジット |
| Position | `position.shares`, `position.risk_dollars` | Position Sizer から付与 |
| Monitoring | `next_review_date`, `review_history` | レビュースケジュールと履歴 |
| Origin | `origin.source_skill`, `origin.screening_grade` | ソーススクリーナーとスコア |
| Outcome | `outcome.pnl_pct`, `outcome.holding_days` | 決済時に自動計算 |

### インデックスファイル

`state/theses/_index.json` は個別YAMLを読み込まずに高速検索するための軽量インデックスです。`rebuild_index()` で再生成可能です。

### ポストモーテムジャーナル

`state/journal/pm_{thesis_id}.md` にエントリー/イグジットサマリー、P&L分析、MAE/MFE（利用可能な場合）、振り返りを含む構造化レポートが保存されます。

---

## 7. ヒントとベストプラクティス

- **早めに登録、判断は後で。** スクリーナー出力はすべて IDEA として取り込みましょう。追わないものは後で invalidate できます。
- **冪等性を活用。** 同じインジェストコマンドの再実行は安全です — フィンガープリントが重複を防ぎます。
- **RFC 3339 日付形式を使用。** すべての日時フィールドにタイムゾーンが必要です（例: `2026-03-16T10:30:00-04:00`）。ナイーブな日時やスペース区切りは拒否されます。
- **削除より無効化。** YAMLファイルを手動削除するのではなく `terminate(thesis_id, "INVALIDATED", ...)` を使いましょう。監査証跡が保持されます。
- **レビュースケジュールを重視。** デフォルトのレビュー間隔は7日です。`review-due` で期限超過の thesis を確認し、放置ポジションを防ぎましょう。
- **エスカレーションラダー。** レビュー結果は OK → WARN → REVIEW とエスカレートします。連続 WARN は自動的にエスカレーションされます。
- **レポートリンクは積極的に。** 紐付ける分析が多いほど、ポストモーテムが充実します。
- **state/ を Git 追跡。** `state/` ディレクトリはコミットする設計です。`git log` と `git blame` で完全な監査証跡が得られます。
- **FMP なしでもポストモーテム可能。** MAE/MFEはあると便利ですが、P&L、保有日数、振り返りは API なしで動作します。

---

## 8. 他スキルとの連携

| スキル | 連携ポイント | 方法 |
|--------|-------------|------|
| **kanchi-dividend-sop** | 登録 | `thesis_ingest.py --source kanchi-dividend-sop` |
| **earnings-trade-analyzer** | 登録 | `thesis_ingest.py --source earnings-trade-analyzer` |
| **vcp-screener** | 登録 | `thesis_ingest.py --source vcp-screener` |
| **pead-screener** | 登録 | `thesis_ingest.py --source pead-screener` |
| **canslim-screener** | 登録 | `thesis_ingest.py --source canslim-screener` |
| **edge-candidate-agent** | 登録 | `thesis_ingest.py --source edge-candidate-agent` |
| **US Stock Analysis** | レポートリンク | `link_report(thesis_id, skill="us-stock-analysis", ...)` |
| **Technical Analyst** | レポートリンク | `link_report(thesis_id, skill="technical-analyst", ...)` |
| **Position Sizer** | サイジング付与 | `attach_position(thesis_id, report_path)` |
| **Portfolio Manager** | トレード執行 | ポジション開設/決済後に thesis を更新 |
| **kanchi-dividend-review-monitor** | レビュートリガー | T1-T5 異常検知が `mark_reviewed()` にフィード |

---

## 9. トラブルシューティング

| エラー | 原因 | 対処法 |
|--------|------|--------|
| `ValidationError: ... is not a 'date-time'` | 日時フィールドにタイムゾーンがない、またはスペース区切り | RFC 3339形式を使用: `2026-03-16T10:30:00-04:00` |
| `ValueError: Cannot transition from terminal status CLOSED` | 決済/無効化済みの thesis を変更しようとした | ターミナルステータスは永続的です。必要なら新しい thesis を作成してください。 |
| `ValueError: Use open_position() to transition to ACTIVE` | `transition()` で ACTIVE を指定した | `open_position(thesis_id, actual_price, actual_date)` を使用 |
| `ValueError: Budget mode not supported` | Position Sizer レポートが `mode: "budget"` | `--entry` と `--stop` を指定して shares モードで再実行 |
| `ValueError: Missing required field: ticker` | スクリーナーJSONに必要なフィールドがない | 入力がソースアダプターの期待するフォーマットに合っているか確認 |
| 重複 thesis が作成されない | フィンガープリントが既存 thesis と一致 | 意図的な動作（冪等性）です。既存の thesis_id が返されます。 |

---

## 10. リソース

**リファレンス:**
- `skills/trader-memory-core/references/thesis_lifecycle.md` -- ステータスステートと有効な遷移
- `skills/trader-memory-core/references/field_mapping.md` -- ソーススキルからカノニカルフィールドへのマッピング

**スクリプト:**
- `skills/trader-memory-core/scripts/thesis_ingest.py` -- スクリーナーアダプターレジストリとCLI
- `skills/trader-memory-core/scripts/thesis_store.py` -- CRUD、遷移、ステート管理
- `skills/trader-memory-core/scripts/thesis_review.py` -- ポストモーテム生成とサマリー統計
- `skills/trader-memory-core/scripts/fmp_price_adapter.py` -- MAE/MFE用FMP APIインテグレーション

**スキーマ:**
- `skills/trader-memory-core/schemas/thesis.schema.json` -- thesis バリデーション用 JSON Schema
