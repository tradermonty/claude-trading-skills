---
layout: default
title: 最初の1週間
parent: 日本語
nav_order: 8
lang_peer: /en/your-first-week/
permalink: /ja/your-first-week/
---

# 最初の1週間
{: .no_toc }

インストールから、再現可能な相場確認、最初のジャーナル登録、最初の週次レビューまでを
7日間で進めるガイドです。
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 始める前に

必要なものは、Skills機能に対応したClaudeプラン、Python 3.9以上、`git`、`uv`、
公開CSVへ接続できるインターネット環境です。FMP、FINVIZ Elite、ブローカー認証情報などの
**有料マーケットデータAPIは不要**です。

> 「有料API不要」は「オフライン」という意味ではありません。2つの相場分析スキルは
> 公開CSVをダウンロードします。ジャーナルと週次レビューはローカルで完結します。
> このガイドは発注せず、レポートを売買シグナルとして扱いません。
{: .note }

以下のコピー可能なコマンドは、Claude Codeまたはリポジトリルートのターミナル向けです。
Web Appでは
[`skill-packages/`](https://github.com/tradermonty/claude-trading-skills/tree/main/skill-packages)
から `trading-skills-navigator`、`market-breadth-analyzer`、`uptrend-analyzer`、
`exposure-coach`、`trader-memory-core`、`weekly-performance-digest` の
`.skill` ファイルをアップロードできます。

## 1日目 — 再現可能な環境を準備する

まだ取得していない場合はリポジトリをクローンし、lock済みのruntime依存を導入します。

```bash
git clone https://github.com/tradermonty/claude-trading-skills.git
cd claude-trading-skills
uv sync --locked
mkdir -p reports/first-week state/first-week-theses first-week-inputs
```

以降はすべてリポジトリルートで実行します。`requests`、`PyYAML`、`jsonschema` を
lock済み環境から使うため、Pythonコマンドを `uv run python` に統一します。

## 2日目 — Navigatorに入口を選ばせる

初心者向けの15分ルーチンを決定論的Navigatorに問い合わせます。

<!-- first-week-navigator-command:start -->
```bash
uv run python skills/trading-skills-navigator/scripts/recommend.py \
  --query "I want a 15-minute daily market check without paid API keys" \
  --no-api \
  --time-budget 15m \
  --experience beginner \
  --format json
```
<!-- first-week-navigator-command:end -->

JSON内の次のフィールドを確認します。

```text
primary_workflow.id = market-regime-daily
primary_workflow.api_profile = no-api-basic
no_api_path = true
```

Navigatorは推奨だけを行い、他のスキルを自動実行しません。手順と必須artifactの正本は
[`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml)
manifestです。

## 3日目 — 有料APIなしの相場確認を実行する

公開データを使う必須の2分析を実行します。

```bash
uv run python skills/market-breadth-analyzer/scripts/market_breadth_analyzer.py \
  --output-dir reports/first-week

uv run python skills/uptrend-analyzer/scripts/uptrend_analyzer.py \
  --output-dir reports/first-week
```

各分析からタイムスタンプ付きJSONを1ファイルだけ選びます。breadthのpatternは
`market_breadth_history.json` を意図的に除外します。

```bash
breadth_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'market_breadth_????-??-??_??????.json' -print | sort | tail -n 1)"
uptrend_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'uptrend_analysis_????-??-??_??????.json' -print | sort | tail -n 1)"

test -n "$breadth_json" && test -f "$breadth_json"
test -n "$uptrend_json" && test -f "$uptrend_json"
```

workflowのmarket-top手順は任意なので、この最小導線では省略します。取得できた2つの
artifactだけをExposure Coachへ渡します。

```bash
uv run python skills/exposure-coach/scripts/calculate_exposure.py \
  --breadth "$breadth_json" \
  --uptrend "$uptrend_json" \
  --output-dir reports/first-week
```

最新の `exposure_posture_*.json` を確認します。

```bash
exposure_json="$(find reports/first-week -maxdepth 1 -type f \
  -name 'exposure_posture_????-??-??_??????.json' -print | sort | tail -n 1)"
test -n "$exposure_json" && test -f "$exposure_json"

uv run python - "$exposure_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as report_file:
    report = json.load(report_file)

for key in (
    "inputs_provided",
    "inputs_missing",
    "confidence",
    "recommendation",
    "exposure_ceiling_pct",
):
    print(f"{key}: {report[key]}")
PY
```

`inputs_provided` に `breadth` と `uptrend`、`inputs_missing` に省略した系統が入り、
`confidence: LOW` になることを確認します。重要入力のregimeとtop-riskがないため、
fail-safeの推奨は `REDUCE_ONLY` または `CASH_PRIORITY` であり、
`NEW_ENTRY_ALLOWED` にはなりません。これは**入力不足時の縮退ポスチャー**で、
相場全体が弱気であるという完全な判定ではありません。任意の拡張を使う場合は、
その時点の各スキルガイドで追加データ要件を確認してください。

## 4日目 — 最初のジャーナル項目を作る

手入力で `IDEA` を1件作成します。実在tickerと反証可能な文を使い、チュートリアルを
埋めるためだけの架空エントリーやpositionは作らないでください。

<!-- first-week-manual-json:start -->
```json
{
  "ticker": "AMD",
  "thesis_statement": "Observe whether AMD holds above the prior breakout area for five sessions.",
  "thesis_type": "growth_momentum"
}
```
<!-- first-week-manual-json:end -->

このJSONを保存し、ingestします。

```bash
cat > first-week-inputs/manual-idea.json <<'JSON'
{
  "ticker": "AMD",
  "thesis_statement": "Observe whether AMD holds above the prior breakout area for five sessions.",
  "thesis_type": "growth_momentum"
}
JSON
```

<!-- first-week-ingest-command:start -->
```bash
uv run python skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source manual \
  --input first-week-inputs/manual-idea.json \
  --state-dir state/first-week-theses
```
<!-- first-week-ingest-command:end -->

コマンドは生成したthesis IDを表示し、`IDEA` を作成します。取引をACTIVEにせず、
注文も出しません。

## 5日目 — 変更する前にジャーナルを読む

実際に記録されたstateを一覧します。

```bash
uv run python skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/first-week-theses \
  list

uv run python skills/trader-memory-core/scripts/trader_memory_cli.py review \
  --state-dir state/first-week-theses \
  review-due
```

ticker、thesis type、statusが入力どおりか確認します。別途setupを検証するまでは
`IDEA` のままにします。schemaとlifecycle検証を維持するため、YAML stateを手編集せず、
必ずCLIを使ってください。

## 6日目 — 手順をルーチンにする

新しいスイングリスクを検討する前に3日目を繰り返します。短いchecklistを守ります。

1. 両analyzerの鮮度警告を読む。
2. Exposure Coachが実際に受理した入力を確認する。
3. 不足入力を不足のまま扱い、推測で埋めない。
4. 予想ではなく、ポスチャーと判断理由を記録する。
5. 発注とリスク判断はこのworkflowの外で、自分のルールに従って行う。

日次出力は、制限的なポスチャーなら調査を減らし、完全なレビューで許可された場合だけ
別の個別銘柄分析へ進む、といったプロセス改善に使います。単独の売買シグナルではありません。

## 7日目 — 最初の週次レビューを行う

ローカルジャーナルから直近7日間のdigestを生成します。

```bash
uv run python skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/first-week-theses \
  --output-dir reports/first-week \
  --verbose
```

クローズした取引がなければ、0件レポートが正しい結果です。指標を埋めるための架空取引を
作らないでください。生成された `weekly_digest_*.md` を読み、次に答えます。

1. リスクを検討する前に相場確認を行ったか。
2. 不足入力とneutral signalを区別したか。
3. 物語ではなく、反証可能なthesisを書いたか。
4. 来週も維持または変更するprocess ruleは何か。

これで、有料データAPIを使わずに最小の Plan → Record → Review → Improve ループを
完了しました。このルーチンが再現可能になってから
[ワークフローの選び方]({{ '/ja/find-your-workflow/' | relative_url }})へ進んでください。
