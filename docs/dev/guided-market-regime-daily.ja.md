# ガイド付き架空マーケットレジーム実行

[English](guided-market-regime-daily.md)

`scripts/run_market_regime_daily.py` は、`market-regime-daily` ワークフローを、準備確認、実行単位の成果物受け渡し、人間によるポスチャ判断、ローカルのジャーナル受け渡しまで案内します。コミット済みの架空コンポーネントフィクスチャだけを使うオフライン学習用の経路で、評価時刻は **2026-01-15T13:08:00+00:00** に固定されています。現在の市場を表すものではなく、売買シグナルでもありません。

このページは判断差分、現在の制限、計測計画を日本語で完全に記述します。起動方法、証跡の構成、中断からの復旧、ロックの扱い、終了コードの基本は[英語版](guided-market-regime-daily.md)を参照してください。

## 判断差分とは

判断差分は、朝の次の問いに答えます。前回の判断で書き残した見直し条件のうち、どれが変わり、どれが変わらず、どれが今日は判定できないか。

判断差分は読み取り専用の証跡で、ポスチャを決めることはありません。架空フィクスチャだけが対象で、指定しない限り動作しません。新しいオプションを使わない実行は従来と同じです。ただし、後述する入れ子ディレクトリの拒否だけは新しく加わっています。

2日目は、2つ目の架空フィクスチャ `examples/workflows/market-regime-daily/guided-day-2/` を使います。評価時刻は **2026-01-16T13:08:00+00:00** です。リプレイの派生ではなく、`replay-coverage.yaml` にも載せていません。1日目のリプレイ契約とゴールデンは変わりません。

## 2日間の流れ

```bash
# 1日目: top-risk を含めて作成し、判断と見直し条件を記録する
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d1 --include-top-risk
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d1 --resume --decision restrict \
  --revisit-conditions my-conditions.json

# 2日目: 1日目を指定して作成し、差分を読んで終了コード 3 で止まり、判断する
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d2 --fixture-set day-2 \
  --previous-run-dir reports/market-regime-daily/d1
uv run python scripts/run_market_regime_daily.py \
  --run-dir reports/market-regime-daily/d2 --resume --decision allow
```

`my-conditions.json` は自分で書くファイルです。

```json
{
  "schema_version": 1,
  "conditions": [
    {"id": "breadth-weakens", "label": "Breadth composite falls below 60",
     "metric": "breadth.composite_score", "comparator": "lt", "threshold": 60},
    {"id": "top-risk-rises", "label": "Top-risk composite reaches 50",
     "metric": "top_risk.composite_score", "comparator": "ge", "threshold": 50}
  ]
}
```

2日目に作成すると、`Decision diff (read-only; it never records a decision)` で始まるブロックが表示されます。前回の判断、条件ごとの `[changed|unchanged|not_evaluable]` の行と前回値と今日の値、確認すべき項目が並びます。同じ内容は `decision_diff.json` に保存され、停止中は `--status` でも表示されます。

連鎖が続くかどうかは、判断のたびに `--revisit-conditions` を渡すかどうかで決まります。上の2日目の判断は渡していないので、2日目は `revisit_conditions: null` で記録されます。2日目を前回として3日目を作成しても、分類する条件がなく、確認項目に「見直し条件なし」が出るだけです。連鎖を続けるには、毎回の判断で条件ファイルを渡してください。

## コマンドラインの規則

| オプション | 指定できる場面 | 備考 |
|---|---|---|
| `--fixture-set {day-1,day-2}` | 実行の作成時 | 既定は day-1。作成後は変更できません。 |
| `--previous-run-dir PATH` | 実行の作成時 | 前回の実行を明示します。 |
| `--previous-runs-root ROOT` | 実行の作成時 | ROOT 配下で最新の完了済み実行を選びます。`--previous-run-dir` とは同時に指定できません。 |
| `--revisit-conditions FILE` | ゲートでの `--resume --decision` | 判断と一緒に条件を記録します。 |

次の場合は終了コード 2 で終了します。

- `--fixture-set`、`--previous-run-dir`、`--previous-runs-root` を `--resume` または `--status` と一緒に指定した。
- 前回実行の2つのオプションを同時に指定した。
- `--decision` なしで `--revisit-conditions` を指定した。

それ以外の終了コードは変わりません。対話式のポスチャ入力も変わりません。条件を記録したいときは、空欄で一時停止してからフラグ付きで再開します。対話式で入力したポスチャは `revisit_conditions: null` として記録されます。

## 前回実行の選び方

- **明示指定** `--previous-run-dir`: 指定されたディレクトリをそのまま分類します。評価時刻が今日より後の場合だけ拒否し、同時刻は許可します。
- **ルート指定** `--previous-runs-root`: ルート直下の子ディレクトリだけを見ます。再帰はせず、ファイルの更新時刻は使いません。ルート自体がシンボリックリンクだと使えません。子は、マニフェストの `workflow_id` が `market-regime-daily`、状態が `COMPLETED`、`evaluation_at` がタイムゾーン付きで今日以前、ゲートの `decision_at` がタイムゾーン付き、の条件を満たすと候補になります。シンボリックリンクの子と通常ファイルは飛ばします。マニフェストが無い、大きすぎる、読めない子は `skipped_unreadable` に数えます。`(evaluation_at, decision_at)` が最大のものを選び、完全に同じ候補が複数あれば `ambiguous` です。ルートが存在しない場合と、条件を満たす実行が無い場合は、どちらも `not_found` で、メッセージが異なります。子ディレクトリが500を超えると `unavailable` です。ファイルは数えません。`reports/market-regime-daily/` のような専用ルートを使ってください。
- **代替はしない。** 選ばれた1件だけを完全に検証します。失敗した場合はその状態を報告し、初回実行として続行します。古い実行に切り替えることはないので、上書き済みの判断が「前回」として表示されることはありません。古い実行を使いたいときは `--previous-run-dir` で明示します。

結果は作成時に一度だけ `inputs/previous_run.json` に固定されます。選択の件数は入りますが、パスは入りません。再開と `--status` は前回のディレクトリを再び読まないので、後から移動や削除をしても構いません。分類は読み取り専用で、前回実行のロックを取得も削除もせず、そこへ何も書きません。

| 状態 | 意味 |
|---|---|
| `loaded` | 検証済みで完了済み、時刻が同じか前。条件を分類します。 |
| `not_found` | パスまたはルートが無い、または条件を満たす実行が無い。 |
| `unavailable` | パスにシンボリックリンクがある、ディレクトリでない、ロック中、読めない、読み取り中にロックや変更が現れた、またはルート直下が多すぎる。 |
| `invalid` | 読めるマニフェストが無い、未知のフィクスチャセット、または想定外の失敗。 |
| `other_workflow` | 別のワークフローのマニフェスト。 |
| `incomplete` | まだ判断が記録されていない。 |
| `source_changed` | その実行以降に、ランナー、ワークフロー、フィクスチャ、ネイティブのソースが変わった。 |
| `integrity_mismatch` | 前回の実行が検証を通らない。 |
| `not_earlier` | 前回の実行が今日の評価時刻より後。 |
| `ambiguous` | ルート配下で最新の候補が複数あり、同順位。 |

`loaded` 以外はすべて初回実行として扱います。`first_run: true`、条件は空、固定メッセージ、確認項目として「初回実行」が付きます。メッセージは固定文字列で、ファイルの内容は表示されません。

## 判断が記録するもの

`--previous-run-dir`、`--previous-runs-root`、`--revisit-conditions` のいずれかを使うと、判断ゲートに拡張記録が保存され、ジャーナルは `schema_version: 2` になります。version 1 の項目はすべて残り、次の4項目が加わります。

- `decision`: 従来どおりのポスチャ。
- `revisit_conditions`: 見直し条件。各条件に `value_at_decision` と `holds_at_decision` が付きます。`null` は条件を渡さなかったこと、`[]` は「何が起きても考えは変わらない」と明示的に記録したことを表します。
- `data_as_of`: 評価時刻と、実行された各入力の `as_of`。
- `unevaluated`: 評価されなかった入力。選ばなかった任意ステップは `optional_step_not_selected`、このワークフローが提供しないエクスポージャー入力は `not_provided_by_this_workflow` です。

ジャーナルには `decision_diff` も入ります。差分ファイルのマニフェスト記録、または `null` です。新しいオプションを使わない実行は、従来の version 1 ジャーナルのままです。

## 条件とメトリクス

各条件は `id`、`label`、`metric`、`comparator`、`threshold` をちょうど持ちます。`id` は全体が `[a-z0-9][a-z0-9-]{0,63}` に一致する必要があり、末尾の改行も不可で、重複できません。`label` は表示可能な1〜200文字です。条件は最大20件、ファイルは最大64 KiBです。NaN、Infinity、JSON の重複キーは拒否します。エラーはすべて固定メッセージで、ファイルの内容は表示しません。

| メトリクス | 比較子 | しきい値 |
|---|---|---|
| `breadth.composite_score`、`uptrend.composite_score`、`top_risk.composite_score` | `lt`、`le`、`gt`、`ge` | 有限の数値。真偽値は不可。 |
| `exposure.recommendation` | `eq`、`ne` | `CASH_PRIORITY`、`REDUCE_ONLY`、`NEW_ENTRY_ALLOWED` のいずれか。 |

値は常に、その実行自身の検証済み成果物から取ります。スキップされたステップは基準値なし、つまり `value_at_decision: null` で記録され、これは許可されます。コンポーネント単位のメトリクスと、数値のエクスポージャーのメトリクスは今後の課題です。すでに成立している条件を記録すると警告が出て、次の差分では `condition_already_met_at_decision` として確認項目に並びます。

## 条件の分類

`changed` は、前回の判断時と今日とで、条件の真偽が入れ替わったことを意味します。しきい値をどちらの向きに越えても `changed` です。値が動いても真偽が変わらなければ `unchanged` です。`unchanged` になるのは、次の確認をすべて通過した場合だけです。最初に引っかかった確認が、`not_evaluable` の理由になります。

1. `no_baseline_value`: 前回の判断時に値が記録されていない。
2. `input_missing_today`: 今日の値が無い。たとえば任意の top-risk ステップを選ばなかった場合で、詳細は `optional_step_not_selected` です。
3. `input_as_of_unknown`: どちらかの `as_of` が無い。
4. `input_not_refreshed`: 今日の `as_of` が前回より厳密に新しくない。これが古さの規則で、更新されていない入力が「変化なし」になることはありません。
5. `input_stale`: 今日の評価時刻で、入力が `max_age_days` より古い。
6. `input_set_changed`: `exposure.recommendation` で、合成値を作った入力の組み合わせが違う。
7. `invalid_value`: 有限でない値、または型の不一致。

欠けている入力や古い入力が `unchanged` になることはありません。テストでこの契約を強制しています。

## 現在の制限

- 架空フィクスチャのみ。プロバイダ、ブローカー、実際の trader-memory の状態には触れません。
- 前回の実行は `--previous-run-dir` で名指しするか、専用ルート1つから記録された時刻だけで選びます。それ以外は探索しません。
- 2つの日の間でランナー、補助コード、ワークフロー、フィクスチャのいずれかを編集すると `source_changed` になり、翌日は初回実行になります。ハッシュだけで古い記録を表示する方式は今後の課題です。
- 見直し条件の対話入力はありません。フラグを使います。
- 記録は trader-memory-core へ配信されません。Issue #513 が対象です。
- `as_of` は、Issue #297 の実データ向け規約ができるまで、フィクスチャの慣例に従います。
- スナップショットと差分のハッシュは編集や破損を検出しますが、改ざん防止ではありません。判断記録を消し、version 1 のジャーナルに書き直してハッシュを更新するダウングレードは、前回実行を使っていない実行では検出できません。
- `manifest.json` を持つディレクトリの下には、実行ディレクトリを作れなくなりました。新しいオプションの有無にかかわらず適用される新しい拒否です。実行の中に別の実行を書くと、証跡が壊れるためです。

## 計測計画 メンテナ向けの定例作業

判断差分が、変化を見落とさずに朝の判断を短くするかを確かめます。

- **指標 A 判断までの時間。** 各マニフェストの `steps[3].decision_at` から `created_at` を引きます。例は `jq -r '[.created_at, .steps[3].decision_at] | @tsv' reports/<run>/manifest.json` です。停止していた時間も含まれるため、実作業の分数も手で記録します。
- **指標 B 見直し漏れ。** 判断のたびに、差分が示さなかったのに自分で再確認する必要があった項目を数えます。B1 は `unchanged` と表示されたのに実際は変わっていた項目で、契約上の不具合です。目標は0件で、1件でも出たら Issue にします。B2 はどの条件にも含まれていなかった変化で、条件の書き方の不足です。
- **記録。** 日付、run_id、分数、changed と unchanged と not_evaluable の件数、B1、B2、メモを、gitignore 済みの `reports/` 配下の私的な CSV に残します。コミットはしません。
- **期間。** この段階では、手順を2日間の架空リプレイだけで試します。実測は、Issue #513 の実データ経路ができてから20回連続で行い、前回実行を使わない5回を基準にします。
