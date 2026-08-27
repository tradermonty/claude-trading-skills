---
layout: default
title: "Trading Skills Navigator"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/trading-skills-navigator/
permalink: /ja/skills/trading-skills-navigator/
---

# Trading Skills Navigator
{: .no_toc }

自然言語で書かれたトレードや投資の目的から、適切な workflow、skillset、API profile、セットアップ手順を案内する入口用スキルです。実行や発注はせず、どこから始めるべきかを説明します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trading-skills-navigator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Trading Skills Navigator は、ユーザーの目的を受け取り、このリポジトリ内のどの workflow / skillset / skill から始めるべきかを案内します。

例:

- 「どれを使えばいい」
- 「API キーなしで使えるものは」
- 「市場が良いときだけスイングしたい」
- 「配当投資をしたい」
- 「ショート候補を探したい」
- 「バックテストから始めたい」

このスキルは案内専用です。他のスキルを自動実行したり、売買注文を出したり、未実装の workflow をあるかのように説明したりしません。まだ出荷されていない領域は、未出荷であることを明確に伝えます。

---

## 2. 使う場面

- トレードや投資の目的はあるが、どのスキルから始めるべきか分からない
- 有料 API キーなしで使える workflow だけを知りたい
- 初心者向け、短時間運用向け、API あり / なしの道筋を分けたい
- 「part-time swing trader」「dividend investor」「short seller」などのペルソナから推奨ルートを出したい
- skillset と workflow の関係をユーザーに説明したい

使わない場面:

- 実際にスクリーニング、分析、バックテストを走らせる
- 注文やポジション変更を実行する
- 推奨された workflow が存在しないのに手順を作り上げる

---

## 3. 前提条件

- ローカルの `skills-index.yaml` と `workflows/*.yaml`、またはバンドル済み snapshot を読みます
- ネットワーク接続は不要です
- Python 3.9+ 推奨

---

## 4. クイックスタート

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<ユーザーの目的をそのまま入れる>" \
  --format json
```

任意オプション:

```bash
--no-api
--time-budget 15m|30m|60m|90m|any
--experience beginner|intermediate|advanced
```

---

## 5. ワークフロー

### Step 1: 目的と制約を取り出す

ユーザーのメッセージから、次を抽出します。

- 自然言語の goal
- API なし限定かどうか
- 1日の時間予算
- 経験レベル

目的が空、または意図がほとんど判別できない場合だけ、短い確認質問を 1 つまで行います。基本的には recommender が安全に劣化するため、すぐに進めます。

### Step 2: recommender を実行する

```bash
python3 skills/trading-skills-navigator/scripts/recommend.py \
  --query "<ユーザーの目的をそのまま入れる>" \
  --format json
```

Claude Code では repo root の `skills-index.yaml` と `workflows/*.yaml` を読みます。Claude Web App では repo root がないため、バンドル済みの `assets/metadata_snapshot.json` にフォールバックします。

### Step 3: 結果を会話として説明する

JSON を読み、ユーザーの言語で次を説明します。

- Primary workflow: 名前、cadence、推定時間、API profile、いつ使うか
- Secondary workflows: 先にレジーム確認を行うなど、補助 workflow との関係
- Skillset: `skillset.id` とカテゴリ
- API なし / API あり: `--no-api` で除外された workflow があれば、どの有料連携が理由か
- Honest gap: 出荷済み workflow がない場合は、その事実と `suggested_skills` を正直に伝える
- Operational roles: setup bundle または honest-gap 候補に含まれる各スキルの
  `operational_roles` を説明し、standalone の場合は理由も伝える
- Rationale: なぜその推奨になったのか

### Step 4: セットアップ手順を示す

`references/setup_paths.md` を参照し、推奨 workflow の `required_skills` / `optional_skills` に合わせて、Claude Web App での `.skill` アップロード、または Claude Code でのフォルダ配置を説明します。必要な有料 API キーも明示します。

### Step 5: 学習ループへつなげる

最後に、`trader-memory-core` と `trade-memory-loop` / `monthly-performance-review` を案内し、Plan -> Trade -> Record -> Review -> Improve の循環へ戻します。

---

## 6. リソース

参照資料:

- `skills/trading-skills-navigator/references/intent_routing.md`
- `skills/trading-skills-navigator/references/setup_paths.md`

スクリプト:

- `skills/trading-skills-navigator/scripts/build_snapshot.py`
- `skills/trading-skills-navigator/scripts/recommend.py`
