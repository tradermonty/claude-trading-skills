---
layout: default
title: "Stockbee Setup Fluency Trainer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 51
lang_peer: /en/skills/stockbee-setup-fluency-trainer/
permalink: /ja/skills/stockbee-setup-fluency-trainer/
generated: false
---

# Stockbee Setup Fluency Trainer
{: .no_toc }

Momentum Burst スクリーナーの候補から Stockbee スタイルのモデルブックを作り、3日後・5日後の MFE / MAE、ストップ到達、結果タグ、コホート統計を更新する学習用スキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-setup-fluency-trainer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-setup-fluency-trainer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Stockbee Setup Fluency Trainer は、Momentum Burst 候補を「売買するかどうか」ではなく「セットアップ認識を上達させる教材」として蓄積するためのスキルです。

主な役割:

- `stockbee-momentum-burst-screener` の JSON からモデルブックを作成
- 候補ごとに 3日後・5日後のリターン、MFE、MAE、ストップ到達を記録
- `STRONG_WINNER`、`WORKED`、`FAILED_STOP`、`FAILED_FADE`、`CHOPPY_FAILURE`、`NEUTRAL` などの結果タグを付与
- rating、primary_trigger、setup_tags などでコホート集計
- どのタグを昇格、降格、除外候補にするかを検討する材料を作る

これは即時の売買シグナルを作るスキルではありません。サンプル数が増えるまで、出力は学習とルール改善の証拠として扱います。

---

## 2. 使う場面

- Stockbee Momentum Burst の成功例・失敗例を体系的に学びたい
- スクリーナー出力をモデルブックに変換したい
- 見逃した候補、失敗候補、A / B セットアップの違いを復習したい
- 3日後・5日後の成績、MFE、MAE、ストップ到達率を確認したい
- ポジションサイズを上げる前にセットアップ認識の精度を上げたい
- どのタグを重視し、どのタグをフィルターすべきかを検討したい
- 自分の VCP 判断（enter / wait / pass）を、結果を見ずに週末に再判断して振り返りたい。ルール遵守と値動きの結果を分けて採点する

---

## 3. 前提条件

- Python 3.10+
- `stockbee-momentum-burst-screener` の JSON レポート、または互換形式の候補 JSON
- 任意: FMP API キー。ローカル OHLCV JSON を使わずに outcome update を行う場合に必要
- 推奨 state パス: `state/stockbee/model_book.jsonl`
- ブラインドリプレイを使う場合: 引け後に生成した `vcp-screener` の JSON レポートと、reveal 時に渡すローカル OHLCV JSON。標準ライブラリのみで動作し、API キーは不要

API なしでも、ローカルの OHLCV JSON を渡せば outcome update まで実行できます。

---

## 4. クイックスタート

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py ingest \
  --screener-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --model-book state/stockbee/model_book.jsonl \
  --output-dir reports/
```

---

## 5. ワークフロー

### Step 1: Momentum Burst 候補を取り込む

Momentum Burst screener の JSON レポートを使ってモデルブックへ追加します。

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py ingest \
  --screener-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json \
  --model-book state/stockbee/model_book.jsonl \
  --output-dir reports/
```

通常は rejected 候補を除外します。失敗例セットを意図的に作る場合だけ `--include-rejects` を使います。`date` など学習に必要な最低限の情報がない skeleton reject はモデルブック記録ではなく skip 件数として扱います。

### Step 2: 3日後・5日後の outcome を更新する

FMP を使う場合:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --horizons 3,5 \
  --output-dir reports/
```

ローカル OHLCV JSON を使う場合:

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py update \
  --model-book state/stockbee/model_book.jsonl \
  --prices-json data/daily_ohlcv.json \
  --horizons 3,5 \
  --output-dir reports/
```

更新ステップでは、各 horizon について forward close return、MFE、MAE、stop-hit status、最初の stop-hit date、outcome tag を記録します。

### Step 3: コホートを集計する

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py summarize \
  --model-book state/stockbee/model_book.jsonl \
  --group-by rating,primary_trigger,setup_tags \
  --min-sample 5 \
  --output-dir reports/
```

生成される Markdown / JSON を確認します。`rule_candidates` は自動ルール変更ではなく、手動レビューのための証拠候補として扱います。

### Step 4: 学習内容を運用へ戻す

十分なサンプルがあるコホートでは、次を確認します。

- 勝率、5日期待値、平均 MAE が良いタグを昇格候補にする
- 期待値が弱い、stop hit が多い、fade failure が多いタグを降格・除外候補にする
- 代表チャートを手動確認してからルールを変更する
- 採用した学びを `trader-memory-core` や月次レビューに記録する

### Step 5: 自分の VCP 判断をブラインドで再判断する

`decision_replay.py` を使うと、過去の自分の VCP 判断を後知恵なしで練習できます。対応するのは「引け後にスクリーニングし、同じ夜に capture する」運用だけです。結果は練習のためのフィードバックであり、売買推奨ではありません。

スクリーニングのたびに capture します。decisions ファイルは、候補セットの全銘柄を網羅した `{symbol, decision, reason}` の JSON リストです。`decision` は `enter`、`wait`、`pass` のいずれかで、理由は1行にします。`--market-gate` には自分で判断した `open` か `closed` を渡します。

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py capture \
  --screener-json reports/vcp_screener_YYYY-MM-DD_HHMMSS.json \
  --decisions decisions_YYYY-MM-DD.json \
  --market-gate open \
  --store-dir state/decision_replay/
```

週末にブラインドのサンプルを抽出します。5日間の窓が確定するよう、`--decided-on-or-before` は1週間以上前の日付にします。

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py replay \
  --sample-size 10 \
  --decided-on-or-before YYYY-MM-DD \
  --store-dir state/decision_replay/ \
  --output-dir reports/
```

ブラインドビューを見て、全ケースについて enter、wait、pass と1行の理由を `answers.json` に記録します。形式は `[{case_id, decision, reason}]` です。全ケースの回答が揃うまで、該当銘柄のチャート、ニュース、価格を調べず、セットアップへのコメントも求めません。

```bash
python3 skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py reveal \
  --session-id replay-0123456789ab \
  --answers answers.json \
  --prices-json data/daily_ohlcv.json \
  --store-dir state/decision_replay/ \
  --output-dir reports/
```

reveal では、元の判断と再判断を、記録済みのルール結果および後日の値動きと並べて表示します。判断はルールに従ったか逸脱したか、結果は有利か不利かの4象限で、元の判断と再判断を別々に集計します。ルールに従った判断で不利な結果になった場合も、そのまま報告します。遵守と結果は合算しません。最初の後続バーより後に capture したケース、as-of 価格を確認できないケース、バーが足りないケースは除外し、件数を別に示します。pending のセッションは `replay --abandon SESSION_ID --reason TEXT` で破棄し、reveal 済みのケースを再び出すには `--include-seen`、台帳の欠落を直すには `reconcile-ledger` を使います。スキーマ、保証と限界は `skills/stockbee-setup-fluency-trainer/references/decision_replay.md` を参照してください。

---

## 6. リソース

参照資料:

- `skills/stockbee-setup-fluency-trainer/references/decision_replay.md`
- `skills/stockbee-setup-fluency-trainer/references/model_book_schema.md`
- `skills/stockbee-setup-fluency-trainer/references/outcome_tags.md`
- `skills/stockbee-setup-fluency-trainer/references/review_workflow.md`

スクリプト:

- `skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py`
- `skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py`
