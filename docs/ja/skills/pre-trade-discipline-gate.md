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

注文対象の候補には `planned_risk_dollars` と `actual_risk_dollars` の両方が必須です。各値には、ゼロを含む有限の非負数または数値文字列を指定します。値の欠落、真偽値、数値でない文字列、`NaN`、無限大、負数は `REVIEW_REQUIRED` となり、記録上は JSON の `null` に正規化されます。両方が有効で、実際のリスクが計画リスクを上回る場合は `NO_GO` になります。

---

## 4. 判定

| 判定 | 意味 |
|---|---|
| `GO` | 手動注文対象の候補がすべて通過 |
| `REVIEW_REQUIRED` | 入力不足、未知値、記録リンク失敗などで確認が必要。承認済みルールの確認記録の欠落、例外の記録、ルール台帳の読み込み失敗も含む |
| `NO_GO` | 規律ルールまたは上流ゲートにより注文不可 |
| `NO_ACTIONABLE_ORDERS` | ブローカーに入れる注文がない |

シェル自動化で非`GO`を終了コード`2`にしたい場合は `--fail-on-non-go` を使います。

---

## 5. Trader Memory 連携

候補に `thesis_id` があり、`--state-dir` を指定した場合、生成したJSON reportをthesisの `linked_reports` に追加します。`mark_reviewed` は呼ばないため、monitoringのレビュー日は進みません。

JSON reportとJSONL journalには、候補ごとの `checklist_answers` として、計画、ストップ、サイズ、リスク金額、メモの回答が残ります。無効なリスク値は JSON の `null` として保存されます。二進浮動小数点で正確に往復できない有効な JSON 小数は数値文字列として保持し、比較処理と監査記録まで正確な値を渡します。これにより、GO判定も後から監査できます。

---

## 6. 承認済み運用ルール（任意）

月次レビューで人が承認したルールは、ローカルの台帳を通じて次の注文前チェックに引き継げます。ルールは自由記述です。ゲートは該当するルールを一覧に出して確認記録を求めますが、遵守の検証はしません。

```bash
# 月次の rule-changes artifact から承認済みルールを有効化する（replay 形式と sample 形式の両方に対応）
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py activate \
  --rule-changes reports/06_rule_changes_for_next_month.yaml \
  --effective-date 2026-06-01 --review-after 2026-06-30 --confirm-activation

# 各ルールの計算済み状態を表示し、台帳を指定してゲートを実行する
python3 skills/pre-trade-discipline-gate/scripts/manage_approved_rules.py list --as-of 2026-06-15
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --approved-rules-ledger state/rules/approved_rules.json
```

注文対象の各候補に、適用中のルールごとに1件の確認記録を追加します。

```json
"approved_rule_checks": [{"rule_id": "rule_3f9a1c2b7d10", "status": "followed", "note": ""}]
```

| 回答 | 影響 |
|---|---|
| `followed`, `not_applicable` | なし |
| `note` が空でない `exception` | メモ付きの `REVIEW_REQUIRED` |
| 記録の欠落、メモのない `exception`、未知のstatus、不正な値 | `REVIEW_REQUIRED` |

`exception` は、その実行では `REVIEW_REQUIRED` のままです。ゲートは例外を承認できないためです。注文を出さないか、台帳を変更（`retire` または `supersede`）してから再実行してください。`NO_GO` はこれより優先されます。

台帳の操作は `activate`, `list`, `supersede`, `retire`, `extend`, `restore` です。ルールIDは正規化したテキストから決まるため、同じルールを再承認すると更新扱いになり、同じレビューのファイルを再実行しても何も変わりません。履歴は追記のみです。ゲートが適用するかどうかは、America/New_York の日付で計算した状態で決まります。

| 状態 | 適用 |
|---|---|
| `effective`（`review_after` 当日を含む） | 適用する |
| `review_due`（`review_after` の翌日以降） | 警告付きで適用する |
| `not_yet_effective`, `expired`（`expires_on` の翌日以降）, `superseded`, `retired` | 適用しない |

`supersede` はルールを即時に置き換えます。`--effective-date` は America/New_York の当日以前に限り、将来日付は台帳を変更せず拒否します。予定した適用日以降に再実行してください。過去日付を指定しても、過去の状態の再現や既存レポートの書き換えは行いません。

台帳は単一ユーザー向けのローカルファイルで、同時書き込みには対応しません。状態は現在の保存済みstatusから計算するため、過去の `--as-of` を指定しても以前の台帳は再現されません。台帳を読めない場合、注文対象の候補は `REVIEW_REQUIRED` になり、reportとjournalは書き出されます。`--approved-rules-ledger` を指定しない場合、出力は従来と変わりません。

## 7. 運用ルールの2週間実験

承認済みルールを1つ選び、`review_rule_experiment.py start` で適用条件と14暦日の実験期間を決めます。実際の判断（`enter`、`wait`、`pass`）、評価、参照先のローカルIDを非公開のJSONログに記録し、`review_rule_experiment.py review` で集計します。ルールに従った見送りも、適用機会の母数に含めます。取引前チェックは根拠として参照し、実際にどう判断したかは別に記録します。

レポートでは記録数と適用機会数を示し、時間帯別に例外を集計します。遵守率は期間終了後に、評価済みの適用機会が10件以上あり、未評価が0件の場合に表示します。台帳の該当ルールが変更されたら、新しい実験を開始します。月次レビューに自己申告の記録として集計結果を持ち込み、ルールの変更は既存の承認手順で行います。[コマンドと架空の記録例](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/pre-trade-discipline-gate/references/rule_experiment.md)を参照してください。

## 8. 月次の運用ルール遵守レビュー

月が終わったら `review_rule_adherence.py` が、journal に残ったゲートの確認記録を承認済みルールごとに集計し、月次レビュー用のローカルレポートを書き出します。対象は、そのルールが適用されていた月です。

```bash
python3 skills/pre-trade-discipline-gate/scripts/review_rule_adherence.py \
  --journal-dir state/journal/pre-trade-discipline \
  --ledger state/rules/approved_rules.json --month 2026-06 \
  --as-of 2026-07-05 --output-dir reports/pre-trade-discipline
```

ルールごとに、従った、例外、該当なし、未確認の件数、レビュー日時点の台帳の状態、見直しの理由を示します。見直しの理由には、`review_after` の見直し期日を過ぎていることや、該当する機会がなかったことがあります。遵守率は月の終了後に、確認済みの機会が10件以上あり、未確認が0件の場合だけ表示します。同じ候補を同じ日にゲートで再実行した場合は、後の行が前の行に置き換わります。集計は自己申告のゲート回答であり、行動の証明ではありません。レポートは台帳を変更しないので、判断の反映は `manage_approved_rules.py` で行います。JSON と Markdown のファイル名は `rule_adherence_<YYYY-MM>_as-of_<YYYY-MM-DD>` なので、月の途中で確認しても月末のレポートは上書きされません。ゲートの実行がない月には `no_gate_runs_in_window`、有効なルールがない月には `no_rules_in_window`、別の台帳パスの行があるときは `different_ledger_path` の警告が出ます。[コマンド、入力、出力項目](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/pre-trade-discipline-gate/references/rule_adherence.md)を参照してください。
