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
スクリーナー出力 → IDEA → ENTRY_READY → ACTIVE → PARTIALLY_CLOSED → CLOSED
IDEA / ENTRY_READY / ACTIVE / PARTIALLY_CLOSED → INVALIDATED
```

**解決する課題:**
- スクリーニングと執行追跡の間のギャップを解消
- 会話をまたいでトレードアイデアの単一情報源を提供
- 状態遷移を厳格に制御（ステップのスキップ不可）
- P&LとMAE/MFE付きの構造化ポストモーテムを生成
- 定期レビューのスケジューリングで放置ポジションを防止

**主要機能:**
- 7種の取り込みアダプター: kanchi-dividend-sop, earnings-trade-analyzer, vcp-screener, pead-screener, canslim-screener, edge-candidate-agent, manual
- 部分決済を含む6つのステータスによる前進限定ステートマシン
- フィンガープリントベースの重複排除（同じ入力で二重登録なし）
- Position Sizerからのポジションサイジング付与
- 利用者が結果を選ぶレビュースケジュール (OK, WARN, REVIEW)
- FMP API によるオプションの MAE/MFE 算出

**Phase 1 スコープ:** 株式または米ドル建て先物の単一商品。ペアトレードとオプション戦略は対象外です。

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

- **Python 3.11〜3.13**（このリポジトリの対応範囲）と `pyyaml`, `jsonschema`（プロジェクト依存に含まれます）
- **FMP API キー:** オプション — ポストモーテムの MAE/MFE 算出にのみ使用。コア機能（登録、遷移、決済、レビュー）は完全オフラインで動作
- **ステートディレクトリ:** `state/theses/` は初回使用時に自動作成

> FMP APIはポストモーテム時の日次価格データ取得（MAE/MFE算出）にのみ使用されます。APIキーがなくてもポストモーテムは他のすべてのフィールドで生成されます。
{: .tip }

---

## 4. クイックスタート

依存関係をインストールし、リポジトリのルートで実行します。Python例は既存thesisを使うため、`REPLACE_WITH_EXISTING_THESIS_ID` を実際のIDに置き換え、更新前にレポートのパスと日付を合わせてください。ランチャーはstore/ingest/reviewの引数を転送し、uvがあれば `uv run --project` を使用します。

過去日の例を順に記録する場合、最初のthesis履歴は2026年3月15日以前である必要があります。履歴の時刻は時系列を維持し、実際の記録日に合わせてください。

```bash
# ステップ 1: スクリーナー出力を thesis として登録
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# ステップ 2: thesis を検索
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ list --status IDEA

# ステップ 3: サマリー統計を表示
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ summary
```

---

## 5. ワークフロー

### ステップ 1: 登録 — スクリーナー出力の取り込み

ソーススクリーナー名とJSON出力ファイルを指定してインジェストスクリプトを実行します:

```bash
# kanchi-dividend-sop から
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source kanchi-dividend-sop \
  --input reports/kanchi_entry_signals_2026-03-14.json \
  --state-dir state/theses/

# earnings-trade-analyzer から
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source earnings-trade-analyzer \
  --input reports/earnings_trade_scored_2026-03-14.json \
  --state-dir state/theses/
```

JSONの各候補が `IDEA` ステータスの thesis になります。登録は**冪等**です — 同じ入力を2回実行しても重複は生じません（フィンガープリントによる重複排除）。

**対応ソース:** `kanchi-dividend-sop`, `earnings-trade-analyzer`, `vcp-screener`, `pead-screener`, `canslim-screener`, `edge-candidate-agent`, `manual`

株式の会計はロング限定です。parabolic-short計画の取り込みアダプターはなく、
`manual`経由で株式ショートを記録することもできません。明示的なSHORT指定は、
登録で消えてしまう前、手動取り込み、株式建玉開始、sharesレポート付与で拒否します。
先物のLONG/SHORTは従来どおり、検証済みの先物レポート付与または`--contracts`で記録します。

初期entry/stopの両方がある場合は有限の数値でなければならず、正のstopが正のentryを
上回る構成は拒否します。株式の開始時は実際の約定価格と比較します。任意項目の欠落と、
既存の有限なゼロ・負価格の互換性は維持します。稼働後のロングが利益保護ストップを
取得価格より上へ更新することは可能です。手動価格は出典情報のままで、約定は`open-position`
で記録します。利益保護ストップ付きで過去の取引を登録する場合は、初期stopで開始してから
現在のstopへ更新してください。

旧データの明示的なショート記録は、SHORTの語を含むものか、SELLだけのものを指します。例はSELL_SHORT、Short position、SELLで、Sell to closeなどはロングのままです。こうした記録は、新たな損益・MAE/MFE計算を拒否します。CLOSED/INVALIDATEDなら参考用のポストモーテムを生成できます。損益・MAE/MFE・評価額・リスクは「—」とし、未対応の旧ショート記録である理由を明記します。価格取得は行わず、thesis/index・既存の損益・出典情報も変更しません。過去の数値の妥当性を保証したり補正したりする機能ではありません。ACTIVE/PARTIALLY_CLOSEDでは引き続き生成を拒否します。
ただし終了価格を渡さないINVALIDATEDへの無効化とレビュー済み更新は可能で、既存の金額・出典情報は保持します。
集計・月次レポートは明示的なショートを除外し、除外件数を表示します。summary JSONでは非ゼロ時に
`excluded_unsupported_equity_shorts`を返します。過去の手動出典にあるBUY・Long positionなどの自由記述は
従来のロング会計として扱い、新規direction入力は引き続きLONG限定です。過去の損益を自動補正せず、
ストップ位置だけで旧記録の方向を推測しません。株式ショートの記録は外部に保管し、先物として偽って登録しないでください。

### ステップ 2: 分析レポートのリンク

深掘り分析（US Stock Analysis、Technical Analyst等）の結果を thesis に紐付けます:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import link_report

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

link_report(state_dir, thesis_id,
            skill="us-stock-analysis",
            file="reports/us_stock_AAPL_2026-03-15.md",
            date="2026-03-15")
```

### ステップ 3: IDEA から ENTRY_READY への遷移

分析で仮説を検証した後、昇格させます:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import transition

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

transition(state_dir, thesis_id, "ENTRY_READY",
           reason="テクニカル確認: 200日MA上・出来高増加",
           event_date="2026-03-15T00:00:00+00:00")
```

> `transition()` は IDEA → ENTRY_READY のみ許可します。他の遷移は専用関数を使用してください。
{: .warning }

### ステップ 4: ポジション開設 (ENTRY_READY → ACTIVE)

トレードを執行したら、実際のエントリーを記録します:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import open_position

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

open_position(state_dir, thesis_id,
              actual_price=155.50,
              actual_date="2026-03-16T10:30:00-04:00",
              event_date="2026-03-16T10:30:00-04:00")
```

これが **ACTIVE ステータスへの唯一の経路**です。`actual_price` と `actual_date`（RFC 3339形式、タイムゾーン必須）が必要です。

### ステップ 5: ポジションサイジングの付与

Position Sizer の出力をリンクして、株数とリスクパラメータを記録します:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import attach_position

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

attach_position(state_dir, thesis_id,
                position_report_path="reports/position_sizer_AAPL_2026-03-16.json")
```

レポートの `mode` は `"shares"` である必要があります（budget モードは拒否されます）。

### ステップ 6: 定期レビュー

注意が必要な thesis を確認します:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ review-due --as-of 2026-04-15
```

結果を明示的に選択してレビューを記録:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import mark_reviewed

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

mark_reviewed(state_dir, thesis_id,
              review_date="2026-04-15",
              outcome="OK")  # OK, WARN, REVIEW のいずれか
```

`next_review_date` はレビュー間隔に基づいて自動的に更新されます。

### ステップ 7: 決済とポストモーテム

ポジションをクローズしたとき:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path("skills/trader-memory-core/scripts").resolve()))
from thesis_store import close

state_dir = Path("state/theses/")
thesis_id = "REPLACE_WITH_EXISTING_THESIS_ID"

close(state_dir, thesis_id,
      exit_reason="target_hit",
      actual_price=172.00,
      actual_date="2026-05-01T15:45:00-04:00")
```

ポストモーテムを生成:

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/theses/ postmortem th_aapl_div_20260314_a3f1
```

P&L、保有日数、（FMP APIキーがあれば）MAE/MFEを含むレポートが `state/journal/pm_{thesis_id}.md` に保存されます。

---

### 株式の部分決済

約定済みの部分決済をACTIVEの株式thesisに記録します。`THESIS_ID` に残株数が十分ある既存IDを指定してください。一部の決済では `PARTIALLY_CLOSED` へ移り、残り全部の決済ではCLOSEDになります。最後の決済は、それまでの実現損益に加算されます。過去の記録では `--event-date` で履歴時刻を指定できます。

```bash
THESIS_ID="REPLACE_WITH_EXISTING_THESIS_ID"
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ trim "$THESIS_ID" \
  --shares-sold 0.5 --price 160.00 --date 2026-04-20
```

### 先物ポジション

商品ごとの別thesisを使います。IDEAまたはENTRY_READYの間に、確認済みのfutures-position-sizerの `SIZED` レポートを付与します。ACTIVEの先物に再付与はできません。レポートには正の整数枚数、倍率、LONG/SHORT、通貨USDが必要です。約定記録の前にENTRY_READYへ遷移してください。以下は、その状態と対応するレポートが準備済みであることを前提とします。

この例ではSHORTレポートと、例の建日以前に始まるthesis履歴が必要です。日付は実際の約定日に合わせ、過去の記録では `--event-date` で履歴の時系列を維持してください。

```bash
THESIS_ID="REPLACE_WITH_EXISTING_THESIS_ID"
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ attach-futures-position "$THESIS_ID" \
  --report reports/futures_position_es.json
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ open-position "$THESIS_ID" \
  --actual-price 5000 --actual-date 2026-05-10 --event-date 2026-05-10
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ trim "$THESIS_ID" \
  --contracts-sold 1 --price 4950 --date 2026-05-12
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ close "$THESIS_ID" \
  --exit-reason target_hit --actual-price 4900 --actual-date 2026-05-15
```

例では部分決済後に残りがあるよう、当初枚数が2枚以上必要です。closeは商品種別で自動分岐します。先物損益は価格差×倍率×枚数×売買方向で計算し、非USD契約は拒否します。レポートなしで直接openする場合は `--contracts`、`--multiplier`、`--direction`、`--contract-symbol`、`--contract-currency USD` を指定します。

### CLIフラグ参照

| フラグ | 用途 |
|---|---|
| `--source`, `--input` | 取込元と入力JSON |
| `--state-dir` | ローカルthesis保存先 |
| `--ticker`, `--status`, `--type` | 一覧の絞り込み |
| `--reason`, `--event-date` | 遷移理由と履歴時刻 |
| `--actual-price`, `--actual-date`, `--shares` | 株式の約定価格・日付・開始数量 |
| `--shares-sold`, `--contracts-sold`, `--price`, `--date` | 部分決済の数量・約定価格・日付 |
| `--report` | 付与するサイジングレポート |
| `--contracts`, `--multiplier`, `--direction` | 先物を直接開始する場合の仕様 |
| `--contract-symbol`, `--contract-currency` | 先物の識別と必須通貨USD |
| `--exit-reason`, `--terminal-status` | 決済理由または終了状態 |
| `--as-of` | レビュー基準日 |


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
- **削除より無効化。** YAMLファイルを手動削除するのではなく `terminate(state_dir, thesis_id, "INVALIDATED", exit_reason="thesis invalidated")` を使いましょう。監査証跡が保持されます。
- **レビュースケジュールを重視。** デフォルトのレビュー間隔は30日です。`review-due` で期限超過の thesis を確認し、放置ポジションを防ぎましょう。
- **レビュー結果。** OK、WARN、REVIEWを明示的に選択します。記録時にその結果を保存し、次回レビュー日を進めます。連続WARNによる自動エスカレーションはありません。
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
| **US Stock Analysis** | レポートリンク | `link_report(state_dir, thesis_id, skill="us-stock-analysis", file="reports/analysis.md", date="2026-03-15")` |
| **Technical Analyst** | レポートリンク | `link_report(state_dir, thesis_id, skill="technical-analyst", file="reports/technical.md", date="2026-03-15")` |
| **Position Sizer** | サイジング付与 | `attach_position(state_dir, thesis_id, report_path)` |
| **Portfolio Manager** | トレード執行 | ポジション開設/決済後に thesis を更新 |
| **kanchi-dividend-review-monitor** | レビュートリガー | T1-T5 異常検知が `mark_reviewed()` にフィード |

---

## 9. トラブルシューティング

| エラー | 原因 | 対処法 |
|--------|------|--------|
| `ValidationError: ... is not a 'date-time'` | 日時フィールドにタイムゾーンがない、またはスペース区切り | RFC 3339形式を使用: `2026-03-16T10:30:00-04:00` |
| `ValueError: Cannot transition from terminal status CLOSED` | 決済/無効化済みの thesis を変更しようとした | ターミナルステータスは永続的です。必要なら新しい thesis を作成してください。 |
| `ValueError: Use open_position() to transition to ACTIVE` | `transition()` で ACTIVE を指定した | `open_position(state_dir, thesis_id, actual_price, actual_date)` を使用 |
| `ValueError: Position report mode is 'budget', expected 'shares'. ...` | Position Sizer レポートが `mode: "budget"` | `--entry` と `--stop` を指定して shares モードで再実行 |
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

**実例:**
- `examples/workflows/trade-memory-loop/sample-run-full-path/` -- Plan -> Trade -> Record -> Postmortem -> Backtest -> Journal のエンドツーエンド実行例
