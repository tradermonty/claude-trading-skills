---
layout: default
title: "Mt5 Robot Tester"
grand_parent: 日本語
parent: スキルガイド
nav_order: 44
lang_peer: /en/skills/mt5-robot-tester/
permalink: /ja/skills/mt5-robot-tester/
generated: false
---

# Mt5 Robot Tester
{: .no_toc }

3ラウンドのパイプラインでMT5ストラテジーテスターをコマンドラインから駆動し、未バックテストのMetaTrader 5トレーディングロボット（Expert Advisor）から最良のものを選びます。MT5ボット／EAの一括テスト、全シンボル横断のスクリーニング、EAパラメータの最適化、利益・ドローダウン・月次／年次のプラス率・資産曲線基準での候補からファイナリストへの選別に使用します。terminal64.exeをヘッドレス実行します。実行時はWindows + MetaTrader 5が必要です。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/mt5-robot-tester.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/mt5-robot-tester){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

*candidates* フォルダ内のMetaTrader 5ロボット（Expert Advisor）から最良のものを選びます。ストラテジーテスターをコマンドラインから**3ラウンドパイプライン**で駆動し、各ボットを前進に応じてフォルダ間で移動させ、**実行をまたいだ学習**で選別ループごとに精度を上げます。全実行はチェックポイント化され再開可能です。

- **ラウンド1 — スクリーニング（全ペア）:** 設定 `common.symbols` リストの各シンボルでEAをバックテスト（シンボルごとに `Optimization=0` バックテスト1件。MT5 build 6061では `Optimization=3` のXMLが空になるためシンボル別バックテストを使用）。ゲート: **5シンボル以上で利益 AND 最良シンボルが証拠金の3倍以上**。
- **ラウンド2 — 最良ペアのバックテスト:** 最良シンボルで単一バックテスト。純利益%、最大ドローダウン%、プラス月率、全年プラス、LR相関、新高値までの月数を分析します。
- **ラウンド3 — 逐次パラメータ最適化:** `MagicNumber` 以降の5〜6入力を1つずつ最適化（範囲±50%、刻み5%）。その後最終バックテスト。
- **ファイナリスト:** 最適化結果がラウンド2を**上回り** AND 利益が証拠金の**4倍以上** AND 最大ドローダウン**12%以下**。

テスト済みボットは *in-testing* に移動します。ファイナリストは最適化済み `.set` とともに *finalists* にもコピーされます。

---

## 2. 使用タイミング

- "Prueba robots / bots / EAs en MetaTrader 5."
- MT5 Expert Advisorのフォルダをスクリーニングし、全ペア横断で最良を選ぶ場合。
- EAパラメータを最適化し、利益／ドローダウン／ consistency でファイナリストを決める場合。
- 中断したテスト実行を再開する場合。

---

## 3. 前提条件

- **Windows + MetaTrader 5** インストール済み（テスターは `terminal64.exe` を実行）。
- ブローカーの**ティックデータ**をダウンロード済み（デフォルトのモデリングはリアルティック、`Model=4`）。
- `MQL5\Experts` 配下の3フォルダ: *candidates*、*in-testing*、*finalists*。
- コンフィグに **`common.symbols`** を設定（ラウンド1がバックテストするペア。Market Watchのシンボル）。
- ボットごとの任意 `.set` ファイル（コンフィグ `sets_dir`）。ラウンド2のベースラインとラウンド3のパラメータ最適化用。最適化中は探索中の1パラメータ以外すべての入力が固定されます。`.set` がない場合ラウンド3はスキップされ、判定はラウンド2に基づきます。
- **実行前にMetaTrader 5を終了する** — テスターはデータフォルダの排他使用を必要とします。
- Python 3.9以降（標準ライブラリのみ）。有料API不要。

---

## 4. クイックスタート

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --dry-run
```

---

## 5. 仕組み

### ステップ1 — 設定

`assets/pipeline_config.template.json` をコピーし、3つのフォルダパスと（任意で）`terminal_path` を記入します。実際の個人パスはコミットせず、実行時に渡します。デフォルトには合意済み設定がエンコードされています（2020.01.01→2026.06.30、H1、Model=4、10000 USD、1:100、ゲートと閾値）。

### ステップ2 — ドライラン（任意）

MT5を起動せずに生成ラウンド1のINIを検証します。

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --dry-run
```

### ステップ3 — パイプラインを実行

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline
```

各ボットは R1 → R2 → R3 → ファイナリスト判定と流れます。進捗は毎ステップ `state.json` と `run.log` に書き込まれます。

### ステップ4 — 中断時は再開

```bash
python3 skills/mt5-robot-tester/scripts/mt5_batch_tester.py \
  --config my_config.json --output-dir reports/mt5_pipeline --resume
```

`--resume` は完了ボットをスキップし、完了ラウンドは実行コンフィグ・EAバイナリ・入力 `.set` のフィンガープリントが一致する間のみ再利用します。期間、シンボルリスト、バイナリ、`.set` の変更があったボットは安全に再スタートします。

### 任意 — HTMLコントロールパネル

ローカルダッシュボードを起動し、各フォルダのボット、各ボットのフェーズと判定、**Launch** ボタンを確認できます。起動後のCLI操作は不要です。

```bash
python3 skills/mt5-robot-tester/scripts/dashboard.py \
  --config my_config.json --output-dir reports/mt5_pipeline
```

`http://127.0.0.1:8765/` をサーブします（自動で開く、localhostのみ）。ページは3秒ごとに自動更新されます。フォルダ内容、ボットごとのフェーズ（R1/R2/R3/done）、合否判定、集計数、ライブの `run.log` です。開始／停止リクエストは正確なローカルオリジンに限定され、サーバーごとのCSRFトークンが必要です。

### ステップ5 — 結果を読む

- `leaderboard_<ts>.md` / `.json` — 判定と主要指標付きランキング。
- `learnings.json` / `learnings.md` — このループでスキルが学んだこと（パラメータ影響とシンボル事前分布）。設定済み出力ディレクトリ配下。
- `mt5_reports/` と `mt5_ini/` — ボット／ラウンドごとの生MT5レポートとコンフィグ。

---

## 6. リファレンス

**リファレンス:**

- `skills/mt5-robot-tester/references/mt5-cli-reference.md`

**スクリプト:**

- `skills/mt5-robot-tester/scripts/dashboard.py`
- `skills/mt5-robot-tester/scripts/mt5_batch_tester.py`
- `skills/mt5-robot-tester/scripts/mt5_common.py`
- `skills/mt5-robot-tester/scripts/mt5_learnings.py`
- `skills/mt5-robot-tester/scripts/parse_mt5_optimization.py`
- `skills/mt5-robot-tester/scripts/parse_mt5_report.py`
