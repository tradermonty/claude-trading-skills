---
layout: default
title: "Weekly Performance Digest"
grand_parent: 日本語
parent: スキルガイド
nav_order: 60
lang_peer: /en/skills/weekly-performance-digest/
permalink: /ja/skills/weekly-performance-digest/
generated: false
---

# Weekly Performance Digest
{: .no_toc }

`trader-memory-core` の CLOSED thesis から、週次の成績サマリーを生成するスキルです。勝率、期待値、profit factor、R multiple、MAE / MFE、勝ち負けのパターンをローカル計算だけで集計します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/weekly-performance-digest.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/weekly-performance-digest){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Weekly Performance Digest は、1週間にクローズしたトレードを 1 つの成績レポートへ集約します。

読み取る主な入力は、`trader-memory-core` が管理する CLOSED thesis ファイルです。デフォルトでは `state/theses/th_*.yaml` を対象にします。

集計する内容:

- 勝率
- 期待値
- profit factor
- R multiple（分母が正の場合のみ。約定価格がstop以下のgap fillや、stopを約定価格以上に引き上げた取引は算出不可としてR平均から除外し、損益・勝敗・最大勝ち負けには残します）
- MAE / MFE
- source skill、exit reason、thesis type、sector、mechanism tag、screening grade 別の内訳
- 週の最大勝ち、最大負け、主な学び

出力は JSON レコードと人間が読む Markdown レポートです。有料 API は不要で、純粋なローカル計算として動きます。

---

## 2. 使う場面

- 週末に、実現損益ベースの成績をまとめて振り返りたい
- クローズ済みポジション全体の勝率と期待値を測りたい
- どの source skill、exit reason、sector、mechanism が勝ち負けに寄与したか確認したい
- 4週分をまとめて月次レビューへ渡したい
- 実際に閉じたトレードに基づく「何が効いたか / 効かなかったか」を素早く見たい

---

## 3. 前提条件

- Python 3.9+
- `PyYAML`
- `trader-memory-core` の thesis YAML state directory。通常は `state/theses/`
- API キーは不要

---

## 4. クイックスタート

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

---

## 5. ワークフロー

### Step 1: 対象週の digest を生成する

```bash
python3 skills/weekly-performance-digest/scripts/generate_weekly_digest.py \
  --state-dir state/theses \
  --from-date 2026-06-13 --to-date 2026-06-20 \
  --output-dir reports/ -v
```

デフォルト:

- `--state-dir state/theses`
- `--from-date`: `--to-date` の 7日前
- `--to-date`: 今日
- `--output-dir reports/`

日付フラグを省略すると、直近 7 日分を集計します。

### Step 2: レポートを読む

実行後、次のファイルが生成されます。

- `reports/weekly_digest_<to-date>.json`
- `reports/weekly_digest_<to-date>.md`

Markdown では executive summary、metrics table、pattern breakdowns、top winners / losers を確認します。JSON は後続の月次レビューや postmortem に渡せます。

### Step 3: 下流レビューへ渡す

複数週の JSON digest をまとめて月次レビューへ渡したり、postmortem / coach ステップで参照したりします。このスキルは記述的な集計を行うだけなので、実際のルール変更は通常のレビュー手順で判断します。

---

## 6. リソース

参照資料:

- `skills/weekly-performance-digest/references/weekly-digest-metrics.md`

スクリプト:

- `skills/weekly-performance-digest/scripts/generate_weekly_digest.py`
