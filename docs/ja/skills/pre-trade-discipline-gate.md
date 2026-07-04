---
layout: default
title: "Pre-Trade Discipline Gate"
grand_parent: 日本語
parent: スキルガイド
nav_order: 61
lang_peer: /en/skills/pre-trade-discipline-gate/
permalink: /ja/skills/pre-trade-discipline-gate/
generated: false
---

# Pre-Trade Discipline Gate
{: .no_toc }

手動注文をブローカーに入れる直前に、計画外エントリー、過大サイズ、リベンジトレード、市場レジームやサーキットブレーカーによる停止をチェックし、結果を記録します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pre-trade-discipline-gate){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Pre-Trade Discipline Gate は、候補の検証、ポジションサイズ計算、thesis登録が終わった後、実際の手動注文を入れる直前に使うゲートです。候補ごとのチェック結果を `pre_trade_discipline_decision` artifactとして出力します。

このスキルはオフラインの判断補助です。注文を自動発注するものではありません。

---

## 2. クイックスタート

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline \
  --journal-dir state/journal/pre-trade-discipline
```

---

## 3. チェックリスト入力

```json
{
  "candidates": [
    {
      "symbol": "AAPL",
      "thesis_id": "th_aapl_gm_20260703_0001",
      "order_intent": "ENTRY_READY",
      "entry_in_written_plan": true,
      "stop_predefined": true,
      "size_within_plan": true,
      "planned_risk_dollars": 500,
      "actual_risk_dollars": 500
    }
  ]
}
```

注文ゲート対象は `ENTRY_READY`, `ACTIONABLE`, `ACTIONABLE_DAY1`, `MANUAL_ORDER` です。watchlistやignoreの候補は `NO_ACTIONABLE_ORDERS` として記録されます。

---

## 4. 判定

| 判定 | 意味 |
|---|---|
| `GO` | 手動注文対象の候補がすべて通過 |
| `REVIEW_REQUIRED` | 入力不足、未知値、記録リンク失敗などで確認が必要 |
| `NO_GO` | 規律ルールまたは上流ゲートにより注文不可 |
| `NO_ACTIONABLE_ORDERS` | ブローカーに入れる注文がない |

シェル自動化で非`GO`を終了コード`2`にしたい場合は `--fail-on-non-go` を使います。

---

## 5. Trader Memory 連携

候補に `thesis_id` があり、`--state-dir` を指定した場合、生成したJSON reportをthesisの `linked_reports` に追加します。`mark_reviewed` は呼ばないため、monitoringのレビュー日は進みません。

JSON reportとJSONL journalには、候補ごとの `checklist_answers` として、計画、ストップ、サイズ、リスク金額、メモの回答が残ります。これにより、GO判定も後から監査できます。
