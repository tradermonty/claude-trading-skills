---
layout: default
title: "Kanchi Dividend Review Monitor"
grand_parent: 日本語
parent: スキルガイド
nav_order: 26
lang_peer: /en/skills/kanchi-dividend-review-monitor/
permalink: /ja/skills/kanchi-dividend-review-monitor/
---

# Kanchi Dividend Review Monitor
{: .no_toc }

かんち式の強制レビュートリガー（T1-T5）で配当ポートフォリオを監視し、異常値をOK/WARN/REVIEWステートに変換します。自動売却は行いません。減配検知、8-Kガバナンス監視、配当安全性モニタリング、REVIEWキュー自動化、または定期的な配当リスクチェックを求められた際に使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-review-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-review-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

異常な配当リスクシグナルを検出し、人間のレビューキューにルーティングします。
自動化を自動トレード執行ではなく、異常検知として扱います。

---

## 2. 使用タイミング

以下が必要な場合にこのスキルを使用します:
- 配当保有銘柄の日次/週次/四半期の異常検知。
- T1-T5リスクトリガーによる強制レビューキューイング。
- ポートフォリオのティッカーに紐づいた8-K/ガバナンスキーワードスキャン。
- 手動の意思決定前に確定的な `OK/WARN/REVIEW` 出力。

---

## 3. 前提条件

以下に従った正規化済み入力JSONを用意:
- `references/input-schema.md`

上流データが利用できない場合、最低限以下を提供:
- `ticker`
- `instrument_type`
- `dividend.latest_regular`
- `dividend.prior_regular`

---

## 4. クイックスタート

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

---

## 5. ワークフロー

### 1) 入力データセットの正規化

ティッカーごとのフィールドを1つのJSONドキュメントに収集:
- 配当ポイント（最新の定期配当、前回の定期配当、欠損/ゼロフラグ）。
- カバレッジフィールド（FCFまたはFFOまたはNII、配当支払額、比率履歴）。
- バランスシートトレンドフィールド（純有利子負債、インタレストカバレッジ、自社株買い/配当）。
- ファイリングテキストスニペット（特に最近の8-Kまたは同等のアラートテキスト）。
- 事業トレンドフィールド（売上CAGR、マージントレンド、ガイダンストレンド）。

フィールド定義とサンプルペイロードは `references/input-schema.md` を使用。

### 2) ルールエンジンの実行

以下を実行:

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output-dir reports/
```

スクリプトは各ティッカーをT1-T5に基づいて `OK/WARN/REVIEW` にマッピングします。
出力ファイルは日付付きファイル名で指定ディレクトリに保存されます（例: `review_queue_20260227.json` と `.md`）。

### 3) 優先順位付けと重複排除

複数のトリガーが発火した場合:
- 監査証跡のため全ての検出結果を保持。
- 最終ステートは最高重要度のみにエスカレート。
- トリガー理由を1行のエビデンスとして保存。

### 4) 人間レビューチケットの生成

各 `REVIEW` ティッカーに対して以下を含める:
- トリガーIDとエビデンス。
- 推定される障害モード。
- 次の判断に必要な手動チェック項目。

出力フォーマットは `references/review-ticket-template.md` を使用。

---

## 6. リソース

**リファレンス:**

- `skills/kanchi-dividend-review-monitor/references/input-schema.md`
- `skills/kanchi-dividend-review-monitor/references/review-ticket-template.md`
- `skills/kanchi-dividend-review-monitor/references/trigger-matrix.md`

**スクリプト:**

- `skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py`
