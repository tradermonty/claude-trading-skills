---
layout: default
title: ワークフロー
parent: 日本語
nav_order: 4
lang_peer: /en/workflows/
permalink: /ja/workflows/
---

# ワークフロー
{: .no_toc }

> _このページは `scripts/generate_workflow_docs.py` によって自動生成されます。手動編集しないでください。_

個人トレーダー OS の運用ワークフロー定義です。各ワークフローは使用するスキル・判断ゲート・成果物の流れを順番通りに記述しています。[`workflows/`](https://github.com/tradermonty/claude-trading-skills/tree/main/workflows) 以下の定義ファイルが正本で、本ページはそこから自動生成されます。

---

## ワークフロー一覧

| ワークフロー | 頻度 | 目安（分） | API プロファイル | 難易度 |
|---|---|---|---|---|
| [`core-portfolio-weekly`](#core-portfolio-weekly) — コア・ポートフォリオ週次レビュー | 毎週 | 60 | mixed | 初級 |
| [`kanchi-dividend-weekly`](#kanchi-dividend-weekly) — Kanchi式配当銘柄の週次選定 | 毎週 | 60 | mixed | 中級 |
| [`market-regime-daily`](#market-regime-daily) — 市場レジーム日次確認 | 毎日 | 15 | no-api-basic | 初級 |
| [`monthly-performance-review`](#monthly-performance-review) — 月次パフォーマンスレビュー | 毎月 | 90 | no-api-basic | 中級 |
| [`multi-asset-opportunity-daily`](#multi-asset-opportunity-daily) — マルチアセット投資機会の日次確認 | 毎日 | 45 | mixed | 中級 |
| [`shapiro-contrarian`](#shapiro-contrarian) — Shapiro式COT逆張り | 毎週 | 60 | fmp-required | 上級 |
| [`stockbee-20pct-study-daily`](#stockbee-20pct-study-daily) — Stockbee 20%値動き日次研究 | 毎日 | 30 | mixed | 上級 |
| [`stockbee-ep-daily`](#stockbee-ep-daily) — Stockbee EP日次確認 | 毎日 | 40 | mixed | 上級 |
| [`stockbee-fluency-loop`](#stockbee-fluency-loop) — Stockbeeセットアップ習熟ループ | 毎日 | 20 | no-api-basic | 中級 |
| [`swing-opportunity-daily`](#swing-opportunity-daily) — スイング取引機会の日次確認 | 毎日 | 40 | fmp-required | 中級 |
| [`trade-memory-loop`](#trade-memory-loop) — 取引記憶ループ | 随時 | 30 | no-api-basic | 初級 |

---

## コア・ポートフォリオ週次レビュー {#core-portfolio-weekly}

**`core-portfolio-weekly`** · 毎週 · 約60分 · mixed · 初級

**実行タイミング:** 毎週1回、通常は土曜日または日曜日の翌週市場開始前に実行する。 長期保有銘柄、配当ポジション、ポートフォリオ全体の配分を確認する。

**実行してはいけないとき:** 日次ルーティンとして実行しない。毎日の売買でポートフォリオを頻繁に 入れ替えると、このワークフローの長期投資という前提が崩れる。

**必須スキル:** `portfolio-manager`, `trader-memory-core`

**任意スキル:** `kanchi-dividend-review-monitor`, `value-dividend-screener`, `kanchi-dividend-us-tax-accounting`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `holdings_snapshot` | 1 | あり | `monthly-performance-review` |
| `allocation_report` | 2 | あり | — |
| `dividend_review_findings` | 3 | なし | — |
| `rebalance_actions` | 4 | あり | — |
| `weekly_journal_entry` | 5 | あり | — |

**ステップ:**

**ステップ 1: 保有銘柄のスナップショットを取得する** → `portfolio-manager`

- 出力: `holdings_snapshot`

**ステップ 2: 資産配分と集中度を確認する** （判断ゲート） → `portfolio-manager`

- 入力: `holdings_snapshot`
- 出力: `allocation_report`
- **判断:** セクター別および個別銘柄の集中度は目標範囲内か。範囲外の場合、 トレーダーはどのような具体的な再配分を提案するか。

**ステップ 3: 配当の健全性を確認する（T1-T5異常チェック）** （任意） → `kanchi-dividend-review-monitor`

- 入力: `holdings_snapshot`
- 出力: `dividend_review_findings`

**ステップ 4: リバランス対応を決定する** （判断ゲート） → `portfolio-manager`

- 入力: `allocation_report`, `dividend_review_findings`
- 出力: `rebalance_actions`
- **判断:** 来週実行するリバランス対応はあるか。ポジションサイズを含む具体的な 買い・売り・保有継続の一覧を確認する。

**ステップ 5: 週次レビューを記録する** → `trader-memory-core`

- 入力: `rebalance_actions`
- 出力: `weekly_journal_entry`

**手動レビュー:**

- 保有銘柄のスナップショットが実際の証券口座（AlpacaまたはCSV）の状態を反映していることを確認する。
- リバランス注文はブローカーで手動入力し、自動執行されないことを確認する。
- dividend_review_findings がT1-T5の問題を示した場合、解決するまで買い増しを見送る。

**記録先:** `trader-memory-core`

---

## Kanchi式配当銘柄の週次選定 {#kanchi-dividend-weekly}

**`kanchi-dividend-weekly`** · 毎週 · 約60分 · mixed · 中級

**実行タイミング:** Kanchiの5ステップ手法で米国上場の新規配当候補を抽出・精査するため、週次で実行する。 利回りと品質でスクリーニングし、有力銘柄を詳細分析して、エントリー前に根拠を 完全に記録した候補の投資仮説を登録する。v1は米国上場の配当株のみを対象とする。

**実行してはいけないとき:** 日本株や米国以外の市場に上場する配当株には使用しない。v1では対応せず、対応を示唆もしない。 Kanchi式スクリーニングが収益性のある戦略だと主張するものではない。これは買いシグナルではなく、 規律ある候補抽出手順である。既存保有銘柄の管理には使用しない。それは core-portfolio-weekly の役割であり、このワークフローは新規候補の発見と精査を目的とする。 注文は自動発注せず、すべての買い注文をブローカーで手動入力する。

**必須スキル:** `kanchi-dividend-sop`, `trader-memory-core`

**任意スキル:** `value-dividend-screener`, `dividend-growth-pullback-screener`, `kanchi-dividend-us-tax-accounting`, `kanchi-dividend-review-monitor`

**前提ワークフロー（参考情報）:**

- `core-portfolio-weekly` が期待する成果物 `holdings_snapshot` — 任意の税務またはレビュー監視チェックを行う場合、そのライブ保有情報を入力元として使う。 各スキル固有の手動入力スキーマへ正規化し、該当する入力がなければステップ4と5を省略する。

**手動入力契約:**

| 入力 | 必須 | 使用ステップ | スキーマ参照 | 説明 |
|---|---|---|---|---|
| `tax_holdings_input` | なし | 4 | `skills/kanchi-dividend-us-tax-accounting/references/input-schema.md` | holdings[] を含むオペレーター提供のJSON。新規候補では予定口座を仮定値として指定し、 hold_days_in_window は省略する。これにより、結果を誤って確認済みにせず assumption-required のまま保持する。 |
| `review_monitor_input` | なし | 5 | `skills/kanchi-dividend-review-monitor/references/input-schema.md` | 配当とリスクの証拠を含む、正規化済みの既存保有銘柄JSON。候補ティッカーだけからは 導出できないため、まだ保有しておらず監視証拠がない新規銘柄ではステップ5を省略する。 |

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `high_yield_candidates` | 1 | なし | — |
| `pullback_candidates` | 2 | なし | — |
| `kanchi_candidates` | 3 | あり | — |
| `stock_memo` | 3 | あり | — |
| `account_location_advice` | 4 | なし | — |
| `review_queue` | 5 | なし | — |
| `thesis_record` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: 高配当候補をスクリーニングする** （任意） → `value-dividend-screener`

- 出力: `high_yield_candidates`

**ステップ 2: 増配株の押し目候補をスクリーニングする** （任意） → `dividend-growth-pullback-screener`

- 出力: `pullback_candidates`

**ステップ 3: Kanchiの5ステップ精査を実行する** （判断ゲート） → `kanchi-dividend-sop`

- 入力: `high_yield_candidates`, `pullback_candidates`
- 出力: `kanchi_candidates`, `stock_memo`
- **判断:** 各候補のKanchi判定は実行可能な段階（CLEAN-PASS / PASS-CAUTION / CONDITIONAL-PASS）に達しているか。HOLD-REVIEW、STEP1-RECHECK、FAIL は fail-closed とし、サイズ計算や登録へ進めずここで停止する。候補はステップ1・2の スクリーナー出力を利用可能なら使うか、手動提供のティッカー一覧から取得できる。 このステップの実行にどちらのスクリーナーも必須ではない。

**ステップ 4: 米国税務と口座配置の扱いを確認する** （任意） → `kanchi-dividend-us-tax-accounting`

- 出力: `account_location_advice`

**ステップ 5: 既存保有銘柄のレビュー条件を確認する** （任意） → `kanchi-dividend-review-monitor`

- 出力: `review_queue`

**ステップ 6: 候補の投資仮説を登録する** （判断ゲート） → `trader-memory-core`

- 入力: `kanchi_candidates`, `stock_memo`, `account_location_advice`, `review_queue`
- 出力: `thesis_record`
- **判断:** 実行可能な各候補について、kanchi_candidates の判定を IDEA の投資仮説として 取り込み、保存した stock_memo ファイルを thesis_store.link_report() で関連付ける。 利用可能な場合は、税務・口座配置の助言とレビュー監視フラグも関連付け、根拠が完全に 記録されたKanchiメモを、文章で参照するだけでなく監査可能な記録の一部にする。 注文前に未解決の阻害要因、ポジションサイズ、セクター集中、分割買い計画を確認する。 ブローカーで実際に約定するまで投資仮説を ACTIVE に移行しない。このステップは IDEA / ENTRY_READY までとする。

**手動レビュー:**

- Kanchi判定が HOLD-REVIEW、STEP1-RECHECK、FAIL の場合は fail-closed とし、サイズ計算や投資仮説登録へ進めない。
- ステップ3の株式メモ（kanchi-dividend-sop の `references/stock-note-template.md` に基づく手書き1ページ）は kanchi_candidates JSON に埋め込まれない。ファイルへ保存し、IDEA の投資仮説登録後に `thesis_store.link_report(state_dir, thesis_id, "kanchi-dividend-sop", <memo_path>, date)` を呼び出して添付する。この呼び出しがなければ、メモを作成していても投資仮説の `linked_reports` に記録されない。
- 注文を自動発注せず、投資仮説を自動で ACTIVE へ移行しない。すべての約定をブローカーで手動入力し、その後 open-position で記録する。
- ステップ1・2のスクリーナーは任意であり、手動提供のティッカー一覧もステップ3への有効な入力とする。
- ステップ4の税務・口座配置の助言は参考情報であり、権威ある判断ではない。行動前に税務専門家または実際のブローカー・カストディアン資料で確認する。
- ステップ4にはリンク先スキーマに合う `tax_holdings_input` が必要であり、スクリーナーの未加工行を税務上の保有情報として直接渡さない。
- ステップ5のレビュー監視が既存保有銘柄を WARN または REVIEW と判定した場合、その銘柄の買い増しだけを一時停止する。自動売却は行わない。
- ステップ5には、より詳細なリンク先スキーマに合う `review_monitor_input` が必要である。ティッカーだけでは不十分なため、不足証拠を作り出さず任意ステップを省略する。
- スクリーナー出力は共有 `reports/` ではなく各スキル固有の `logs/` 配下に保存される。ステップを連携するとき、成果物IDは実ファイル名ではなく論理参照として扱う。
- dividend-growth-pullback-screener のコマンド例には `screen_dividend_growth_rsi.py` を使用する。`screen_dividend_growth.py` はこのリポジトリに存在しない。

**記録先:** `trader-memory-core`

---

## 市場レジーム日次確認 {#market-regime-daily}

**`market-regime-daily`** · 毎日 · 約15分 · no-api-basic · 初級

**実行タイミング:** その日の新規スイング取引リスクを検討する前に実行する。市場開始前、 または開始後30分以内に実行する。

**実行してはいけないとき:** この出力を単独の売買シグナルとして使用しない。exposure_decision は 方針（allow / restrict / cash-priority）であり、売買指示ではない。

**必須スキル:** `market-breadth-analyzer`, `uptrend-analyzer`, `exposure-coach`

**任意スキル:** `market-top-detector`, `macro-regime-detector`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `market_breadth_report` | 1 | あり | `swing-opportunity-daily`, `monthly-performance-review` |
| `uptrend_report` | 2 | あり | — |
| `top_risk_report` | 3 | なし | — |
| `exposure_decision` | 4 | あり | `swing-opportunity-daily` |

**ステップ:**

**ステップ 1: 市場の騰落状況を分析する** → `market-breadth-analyzer`

- 出力: `market_breadth_report`

**ステップ 2: 上昇トレンドへの参加状況を分析する** → `uptrend-analyzer`

- 出力: `uptrend_report`

**ステップ 3: 市場天井のリスクを確認する** （任意） → `market-top-detector`

- 出力: `top_risk_report`

**ステップ 4: エクスポージャー方針を決定する** （判断ゲート） → `exposure-coach`

- 入力: `market_breadth_report`, `uptrend_report`, `top_risk_report`
- 出力: `exposure_decision`
- **判断:** 本日の騰落状況、上昇トレンドへの参加状況、市場天井リスクを踏まえ、 新規スイング取引のリスクを allow、restrict、cash-priority の どれにするか。

**手動レビュー:**

- 出力を売買シグナルとして使用していないことを確認する。
- エクスポージャーを減らすか、維持するか、増やすかを確認する。
- exposure_decision が restrictive の場合、swing-opportunity-daily の実行を見送る。

**記録先:** `trader-memory-core`

---

## 月次パフォーマンスレビュー {#monthly-performance-review}

**`monthly-performance-review`** · 毎月 · 約90分 · no-api-basic · 中級

**実行タイミング:** 毎月最初の週末に、前月の決済済みポジション、未決済の投資仮説の健全性、 プロセス改善を確認する。計画 -> 取引 -> 記録 -> 振り返り -> 改善 の ループを完結させる。

**実行してはいけないとき:** 損失月であっても省略しない。そのような月にこそレビューが重要である。 ノイズを除くため月次としているので、週次では実行しない。

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**任意スキル:** `trade-performance-coach`, `backtest-expert`, `dual-axis-skill-reviewer`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `monthly_aggregate` | 1 | あり | — |
| `aggregate_postmortem` | 2 | あり | — |
| `monthly_performance_coach_report` | 3 | なし | — |
| `monthly_behavior_patterns` | 3 | なし | — |
| `next_month_operating_rules` | 3 | なし | — |
| `hypothesis_revalidation` | 4 | なし | — |
| `skill_review_findings` | 5 | なし | — |
| `monthly_decision_log` | 6 | あり | — |
| `rule_changes_for_next_month` | 6 | あり | — |
| `skill_improvement_backlog` | 6 | なし | — |

**ステップ:**

**ステップ 1: 当月の取引と投資仮説を集計する** → `trader-memory-core`

- 出力: `monthly_aggregate`

**ステップ 2: 月間のパターン単位で事後分析する** （判断ゲート） → `signal-postmortem`

- 入力: `monthly_aggregate`
- 出力: `aggregate_postmortem`
- **判断:** 当月の結果にどのような反復パターンがあるか。投資仮説の質、執行、 市場環境、偶然性に分類する。

**ステップ 3: 月次のプロセス、リスク、行動パターンを振り返る** （任意） （判断ゲート） → `trade-performance-coach`

- 入力: `monthly_aggregate`, `aggregate_postmortem`
- 出力: `monthly_performance_coach_report`, `monthly_behavior_patterns`, `next_month_operating_rules`
- **判断:** 翌月の運用ルールのうち、採用、修正、保留、記録のみとするものはどれか。

**ステップ 4: バックテストで仮説を再検証する** （任意） → `backtest-expert`

- 入力: `aggregate_postmortem`
- 出力: `hypothesis_revalidation`

**ステップ 5: 有効だったスキルと逆効果だったスキルを確認する** （任意） → `dual-axis-skill-reviewer`

- 入力: `aggregate_postmortem`
- 出力: `skill_review_findings`

**ステップ 6: 判断記録とルール変更を作成する** （判断ゲート） → `trader-memory-core`

- 入力: `aggregate_postmortem`, `hypothesis_revalidation`, `skill_review_findings`
- 出力: `monthly_decision_log`, `rule_changes_for_next_month`, `skill_improvement_backlog`
- **判断:** 当月の証拠に基づき、翌月に変更する具体的なルールは何か。取引側のルールと リポジトリ側の改善は分けて扱う。

**手動レビュー:**

- プロセス改善（ルール変更）と、偶然による結果を区別する。
- 取引側のルール変更は、翌月のトレーダーの行動に適用する。
- スキル側の改善はリポジトリ改善候補であり、必ず実施するとは限らない。
- 新しいルールを追加するだけでなく、機能していないルールの削除や格下げも検討する。

**最終出力:**

- `monthly_decision_log` — カテゴリ別に整理した、機能した取引と機能しなかった取引
- `rule_changes_for_next_month` — ポジションサイズ、エントリールール、レジームゲートの調整
- `skill_improvement_backlog` — リポジトリ改善ループへの任意のフィードバック（スキル / ワークフロー）

**記録先:** `trader-memory-core`

---

## マルチアセット投資機会の日次確認 {#multi-asset-opportunity-daily}

**`multi-asset-opportunity-daily`** · 毎日 · 約45分 · mixed · 中級

**実行タイミング:** market-regime-daily が非制限的な exposure_decision を出した後にのみ実行する。 マクロ、テーマ、ニュースを横断して、株式、株式プロキシ経由の商品、 オプション表現の投資アイデアを抽出し、優先順位付きの仮説カードにまとめる。

**実行してはいけないとき:** 最新の market-regime-daily の exposure_decision が cash-priority の場合は 実行しない。仮説カードを売買シグナルとして扱わない。カードには manual_review_required があり、資金を動かす前に人間の承認が必要である。 外国為替の出力は調査専用とし、ブローカーには決して連携しない。

**必須スキル:** `macro-regime-detector`, `theme-detector`, `trade-hypothesis-ideator`, `position-sizer`, `trader-memory-core`

**任意スキル:** `market-news-analyst`, `market-environment-analysis`, `sector-analyst`, `scenario-analyzer`, `stanley-druckenmiller-investment`

**前提ワークフロー（参考情報）:**

- `market-regime-daily` が期待する成果物 `exposure_decision` — マルチアセットの投資機会を探索するには、非制限的なエクスポージャー方針が 必要である。cash-priority の日は見送り、restrict の日は対象範囲を縮小する。

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `macro_regime_brief` | 1 | あり | `swing-opportunity-daily`, `monthly-performance-review` |
| `hot_themes` | 2 | あり | `swing-opportunity-daily` |
| `catalyst_news_brief` | 3 | なし | — |
| `hypothesis_cards` | 4 | あり | `swing-opportunity-daily`, `trade-memory-loop` |
| `sized_hypotheses` | 5 | あり | — |
| `opportunity_journal_entries` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: マクロレジームの状況を更新する** → `macro-regime-detector`

- 出力: `macro_regime_brief`

**ステップ 2: 注目テーマとセクターローテーションを検出する** → `theme-detector`

- 入力: `macro_regime_brief`
- 出力: `hot_themes`

**ステップ 3: ニュースとカタリストの状況を調査する** （任意） → `market-news-analyst`

- 入力: `hot_themes`
- 出力: `catalyst_news_brief`

**ステップ 4: 優先順位付きの仮説カードを作成する** （判断ゲート） → `trade-hypothesis-ideator`

- 入力: `macro_regime_brief`, `hot_themes`, `catalyst_news_brief`
- 出力: `hypothesis_cards`
- **判断:** 各仮説で、第1層（マクロ）は第2層（テーマ）と整合し、市場への織り込み状況は まだ有利か。コンセンサスとの差が不明確、またはすでに解消済みのカードは却下する。

**ステップ 5: 仮説カードにリスク基準のポジションサイズを適用する** → `position-sizer`

- 入力: `hypothesis_cards`
- 出力: `sized_hypotheses`

**ステップ 6: IDEA / ENTRY_READY の記録として保存する** （判断ゲート） → `trader-memory-core`

- 入力: `hypothesis_cards`, `sized_hypotheses`
- 出力: `opportunity_journal_entries`
- **判断:** どの仮説を IDEA から ENTRY_READY に進め、どれを追加確認待ちの IDEA に とどめ、どれを却下するか。

**手動レビュー:**

- マクロレジーム概要が market-regime-daily の exposure_decision と矛盾しないことを確認する。
- 各仮説に文章化された投資根拠と撤退条件の両方があることを確認する。
- ポジションサイズが銘柄別・セクター別のポートフォリオリスク上限を守っていることを確認する。
- 外国為替関連の出力は research_only=true であることを確認し、ブローカーには決して連携しない。
- IDEA から ENTRY_READY への移行が明示され、レビュー済みであることを確認する。

**記録先:** `trader-memory-core`

---

## Shapiro式COT逆張り {#shapiro-contrarian}

**`shapiro-contrarian`** · 毎週 · 約60分 · fmp-required · 上級

**実行タイミング:** CFTCのCommitment of Tradersレポート公開後（毎週金曜日の米東部時間午後3時30分頃、 火曜日時点の建玉）に週次で実行する。約65の先物市場から投機筋の極端な混雑を探し、 ニュース反応の失敗と週足の価格反転の両方が確認できた場合にのみ、 契約数を算出した逆張り計画を作成する。

**実行してはいけないとき:** 日中または週1回を超えて実行しない。COTデータは週次更新であり、エッジは日中値動きではなく 建玉状況に由来する。混雑の極端値だけで取引しない。ポジションサイズ計算前に、混雑、 ニュース反応の失敗、価格動向がすべて CONFIRMED となり、ゲートが READY_FOR_PLAN に 到達する必要がある。COTはCFTC先物市場のみを対象とするため、株式には使用しない。

**必須スキル:** `cot-contrarian-detector`, `news-reaction-failure-analyzer`, `technical-analyst`, `contrarian-setup-gate`, `futures-position-sizer`, `trader-memory-core`

**任意スキル:** （なし）

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `cot_crowding_report` | 1 | あり | — |
| `news_failure_verdict` | 2 | あり | — |
| `price_action_confirmation_report` | 3 | あり | — |
| `contrarian_setup_gate_report` | 4 | あり | — |
| `futures_position_size` | 5 | あり | — |
| `contrarian_thesis_entry` | 6 | あり | `trade-memory-loop`, `monthly-performance-review` |

**ステップ:**

**ステップ 1: COTの混雑度をスクリーニングする** （判断ゲート） → `cot-contrarian-detector`

- 出力: `cot_crowding_report`
- **判断:** 今週、3年間のCOT指数で混雑の極端値（CROWDED_LONG / CROWDED_SHORT）にある 先物市場はどれか。混雑だけではシグナルにならないため、極端値のみ次へ進める。

**ステップ 2: ニュース反応の失敗を確認する** （判断ゲート） → `news-reaction-failure-analyzer`

- 入力: `cot_crowding_report`
- 出力: `news_failure_verdict`
- **判断:** 各混雑市場で、群衆の方向に有利なニュースに価格が反応しなかったことを CONFIRMED と判定できるか。WebSearchで作成した一次情報・通信社情報の イベントファイルを使用し、NOT_CONFIRMED / INSUFFICIENT_EVIDENCE の市場は除外する。

**ステップ 3: 週足の価格反転を確認する** （判断ゲート） → `technical-analyst`

- 入力: `cot_crowding_report`
- 出力: `price_action_confirmation_report`
- **判断:** 週足チャートで群衆と逆方向の反転（キーリバーサル、ブレイクアウト失敗、極端値失敗）が CONFIRMED となり、スイングのストップが明確か。NOT_CONFIRMED / INSUFFICIENT_DATA は却下する。

**ステップ 4: 逆張りセットアップのゲート判定を統合する** （判断ゲート） → `contrarian-setup-gate`

- 入力: `cot_crowding_report`, `news_failure_verdict`, `price_action_confirmation_report`
- 出力: `contrarian_setup_gate_report`
- **判断:** ゲートは、混雑、ニュース反応の失敗、価格動向がすべて CONFIRMED となる fail-closed の READY_FOR_PLAN に到達したか。READY_FOR_PLAN の市場だけを ポジションサイズ計算へ進め、CROWDED / WATCHING_PRICE / REJECTED / INSUFFICIENT_EVIDENCE はここで停止する。

**ステップ 5: 先物ポジションのサイズを計算する** → `futures-position-sizer`

- 入力: `contrarian_setup_gate_report`
- 出力: `futures_position_size`

**ステップ 6: 逆張りの投資仮説を登録する** （判断ゲート） → `trader-memory-core`

- 入力: `futures_position_size`, `contrarian_setup_gate_report`
- 出力: `contrarian_thesis_entry`
- **判断:** sizer出力の sizing_status が SIZED の逆張りだけを、NO_TRADE の結果を除外して 次の順序で登録する。(1) 最初に IDEA の投資仮説を作成する（手動取り込みまたは register()。attach-futures-position は既存の投資仮説に付加するだけで新規作成しない）。 (2) attach-futures-position で SIZED レポートを付加し、契約数、方向、乗数、USD通貨、 リスクをポジションへ保存する。(3) cot_crowding_report、news_failure_verdict、 price_action_confirmation_report、contrarian_setup_gate_report を thesis_store.link_report() で投資仮説に関連付け、証拠の連鎖を監査可能にする。 (4) ブローカーで注文が実際に約定した後にのみ open-position で ACTIVE へ移行する。 取引ごとのリスクがsizer出力と一致し、ポートフォリオ全体のリスク量が上限内であることを確認する。

**手動レビュー:**

- COTデータには3日間の遅延がある（火曜日時点、金曜日公開）。混雑判定はライブではなく火曜日終了時点として扱う。
- 混雑は前提条件であり、取引シグナルではない。サイズ計算前にニュース反応の失敗と価格動向の両方を確認する。
- ニュース反応失敗のイベントは実在URL付きの一次情報・通信社情報から選び、捏造しない。INSUFFICIENT_EVIDENCE は次へ進めない。
- サイズ計算前にゲートの setup_status が READY_FOR_PLAN であることを確認する。sizerはREADYでないゲートを拒否するが、その場合は理由を確認する。
- ステップ5には contrarian_setup_gate_report 以外に、常にオペレーター指定の --entry、--account-size、--risk-pct が必要である。ゲートもsizerも導出しないため、futures-position-sizer 実行前に用意する。
- 注文前にsizerの契約数と1契約当たりリスクを検証し、ポートフォリオ全体のリスク量が上限内であることを確認する。
- 先物証拠金はブローカーと時点に依存し、計算されない。取引前に必要証拠金と維持証拠金をブローカーで確認する。
- すべての注文はブローカーで手動入力し、自動執行しない。contrarian-position-monitor 提供まではCOT正規化、ストップ、投資仮説無効化の監視も手動で行う。
- ゲートの entry_trigger とsizerの予定エントリーは実際の約定ではない。予定エントリーを含む SIZED レポート自体を保存する。手動取り込み元でも entry_price は origin.raw_provenance.entry_price に保持する。実際の約定前に entry.actual_price へ書き込まない。
- ブローカーで注文が実際に約定するまで、投資仮説を ACTIVE（open-position）へ移行しない。ステップ6は先物ポジションを付加した IDEA / ENTRY_READY までで、注文を自動発注しない。

**記録先:** `trader-memory-core`

---

## Stockbee 20%値動き日次研究 {#stockbee-20pct-study-daily}

**`stockbee-20pct-study-daily`** · 毎日 · 約30分 · mixed · 上級

**実行タイミング:** 米国市場の取引終了後、または過去データの補完調査時に実行する。+20% / -20% の 値動きを検出し、イベントの背景を分類し、観測期間を終えた結果を更新して、 急激な市場変動のモデルブックを蓄積する。

**実行してはいけないとき:** 売買シグナルや自動執行のワークフローとして使用しない。少数サンプル、 現在の銘柄集合だけを使った分析、または生存者バイアスとデータ品質の注記がない イベントから新しいルールを採用しない。

**必須スキル:** `stockbee-20pct-study`

**任意スキル:** `trader-memory-core`, `edge-candidate-agent`, `edge-hint-extractor`, `stockbee-episodic-pivot-analyzer`, `theme-detector`, `backtest-expert`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `twenty_pct_mover_events` | 1 | あり | — |
| `classified_event_study` | 2 | あり | — |
| `matured_event_outcomes` | 3 | あり | — |
| `twenty_pct_cohort_summary` | 4 | あり | `monthly-performance-review` |
| `edge_hints_yaml` | 4 | なし | `monthly-performance-review` |
| `accepted_lessons_log` | 5 | なし | `monthly-performance-review` |

**ステップ:**

**ステップ 1: 日次で+20% / -20%変動銘柄を抽出する** → `stockbee-20pct-study`

- 出力: `twenty_pct_mover_events`

**ステップ 2: カタリスト、チャート状況、テーマ群、リスクフラグを分類する** → `stockbee-20pct-study`

- 入力: `twenty_pct_mover_events`
- 出力: `classified_event_study`

**ステップ 3: 過去の20%研究記録について観測期間後の結果を更新する** → `stockbee-20pct-study`

- 入力: `classified_event_study`
- 出力: `matured_event_outcomes`

**ステップ 4: コホートを要約してエッジ候補を出力する** （判断ゲート） → `stockbee-20pct-study`

- 入力: `matured_event_outcomes`
- 出力: `twenty_pct_cohort_summary`, `edge_hints_yaml`
- **判断:** 20%変動パターンのうち、記録だけの観察ではなくエッジ研究へ進めるのに十分な サンプル数、安定した結果傾向、現実的な執行可能性を備えるものはどれか。

**ステップ 5: 採用した学びを記録する** （任意） （判断ゲート） → `trader-memory-core`

- 入力: `twenty_pct_cohort_summary`, `edge_hints_yaml`
- 出力: `accepted_lessons_log`
- **判断:** どの知見を運用ルール候補として採用し、どれを却下し、どれを追加事例待ちにするか。

**手動レビュー:**

- パターンを採用する前に、代表的な成功例と失敗例のチャートを確認する。
- 観察、研究仮説、実行可能な売買計画を区別する。
- 上場廃止銘柄を含まない現在の銘柄集合による過去分析は、生存者バイアスありと明記する。
- コホートのルールを採用する前に、明示したサンプル数の基準を満たすことを求める。
- ルールを場当たり的に変更せず、採用した学びを monthly-performance-review に引き渡す。

**記録先:** `trader-memory-core`

---

## Stockbee EP日次確認 {#stockbee-ep-daily}

**`stockbee-ep-daily`** · 毎日 · 約40分 · mixed · 上級

**実行タイミング:** 決算・ニュースが多い日に市場レジームのワークフローが新規リスクを許可した後、 または状況を変える重大なカタリストが現れたときに随時実行する。Day 1の Episodic Pivot候補を分類し、本日実行可能か、遅延EPの監視銘柄か、 PEADへ引き渡す候補かを判断する。

**実行してはいけないとき:** カタリスト入力なしの機械的な銘柄スクリーナーとして実行しない。市場レジームの ゲート、チャート検証、ポジションサイズ計算、カタリストの手動確認を迂回するために 使用しない。

**必須スキル:** `drawdown-circuit-breaker`, `stockbee-episodic-pivot-analyzer`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`

**任意スキル:** `earnings-trade-analyzer`, `stockbee-momentum-burst-screener`, `pead-screener`, `theme-detector`, `breakout-trade-planner`

**前提ワークフロー（参考情報）:**

- `market-regime-daily` が期待する成果物 `exposure_decision` — 新規EP取引でも市場レジームのエクスポージャーゲートに従う必要がある。

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `circuit_breaker_decision` | 1 | あり | — |
| `earnings_candidates` | 2 | なし | — |
| `momentum_burst_candidates` | 3 | なし | — |
| `episodic_pivot_candidates` | 4 | あり | — |
| `pead_handoff_candidates` | 4 | なし | `swing-opportunity-daily` |
| `delayed_ep_watchlist` | 4 | なし | — |
| `validated_ep_setups` | 5 | あり | — |
| `ep_position_sizing` | 6 | あり | — |
| `ep_trade_plan` | 7 | なし | — |
| `ep_journal_entry` | 8 | あり | `trade-memory-loop` |
| `pre_trade_discipline_decision` | 9 | あり | — |

**ステップ:**

**ステップ 1: 口座のサーキットブレーカーを確認する** （判断ゲート） → `drawdown-circuit-breaker`

- 出力: `circuit_breaker_decision`
- **判断:** 本日の新規EP取引リスクについて、口座のサーキットブレーカーは TRADING_ALLOWED になっているか。

**ステップ 2: 任意で決算候補を抽出する** （任意） → `earnings-trade-analyzer`

- 出力: `earnings_candidates`

**ステップ 3: 任意でモメンタム確認スキャンを実行する** （任意） → `stockbee-momentum-burst-screener`

- 出力: `momentum_burst_candidates`

**ステップ 4: Day 1 Episodic Pivot候補を分析する** （判断ゲート） → `stockbee-episodic-pivot-analyzer`

- 入力: `earnings_candidates`, `momentum_burst_candidates`
- 出力: `episodic_pivot_candidates`, `pead_handoff_candidates`, `delayed_ep_watchlist`
- **判断:** 状況を変える真のカタリストに加え、価格と出来高の確認がある候補はどれか。 ACTIONABLE_DAY1 と DELAYED_EP_WATCH を分け、見出しだけに反応した 低品質な値動きは却下する。

**ステップ 5: EPチャートの品質を検証する** （判断ゲート） → `technical-analyst`

- 入力: `episodic_pivot_candidates`
- 出力: `validated_ep_setups`
- **判断:** チャートは、終値の質、流動性、EP当日の安値までのリスクが許容できる 明確なEP反応を示しているか。

**ステップ 6: EPのポジションサイズを計算する** → `position-sizer`

- 入力: `validated_ep_setups`
- 出力: `ep_position_sizing`

**ステップ 7: 任意でEP取引計画を作成する** （任意） → `breakout-trade-planner`

- 入力: `validated_ep_setups`, `ep_position_sizing`
- 出力: `ep_trade_plan`

**ステップ 8: EPの投資仮説または監視リスト項目を登録する** （判断ゲート） → `trader-memory-core`

- 入力: `validated_ep_setups`, `ep_position_sizing`, `ep_trade_plan`
- 出力: `ep_journal_entry`
- **判断:** どの候補を有効な投資仮説とし、どれを遅延EP / PEADの監視対象とし、 初期スコアが高くてもどれを無視するか。

**ステップ 9: EPの手動執行規律ゲートを実行する** （判断ゲート） → `pre-trade-discipline-gate`

- 入力: `circuit_breaker_decision`, `ep_journal_entry`, `ep_position_sizing`, `ep_trade_plan`
- 出力: `pre_trade_discipline_decision`
- **判断:** ブローカーへ手動注文を出す前に、ACTIONABLE_DAY1 または ENTRY_READY の EP候補は、文章化された計画、事前設定したストップ、ポジションサイズ、直近損失、 市場レジーム、サーキットブレーカーの規律チェックを通過しているか。 遅延EP、PEAD引き渡し、無視、却下の候補は注文承認ではなく、取引なしの記録として扱う。

**手動レビュー:**

- 実行前に market-regime-daily が新規リスクを許可していることを確認する。
- 新規EP取引リスクを分析する前に circuit_breaker_decision が TRADING_ALLOWED であることを確認する。
- カタリストを手動で検証する。このワークフロー単独ではニュースの真偽を発見・検証しない。
- アナリスト評価や物語だけのEPは、価格と出来高の確認が例外的に強くない限り低品質として扱う。
- EP当日の安値を標準ストップ基準にするのは、その距離で現実的なサイズを設定できる場合だけとする。
- 過度に伸びた決算・業績見通しEPはDay 1で追わず、PEAD監視へ送る。
- ブローカーへ手動注文を出す前に pre_trade_discipline_decision が GO であることを確認し、監視リストとPEAD引き渡し候補を注文承認として扱わない。
- すべての注文はブローカーで手動入力し、自動執行しない。

**記録先:** `trader-memory-core`

---

## Stockbeeセットアップ習熟ループ {#stockbee-fluency-loop}

**`stockbee-fluency-loop`** · 毎日 · 約20分 · no-api-basic · 中級

**実行タイミング:** stockbee-momentum-burst-screener が候補レポートを生成した後と、3取引日・5取引日の 観測期間が経過した後に実行する。Stockbee Momentum Burstのモデルブックを作り、 トレーダーのセットアップ認識力を高める。

**実行してはいけないとき:** 執行ワークフローやシグナルサービスとして使用しない。少数サンプルから取引ルールを 変更しない。セットアップタグを採用・除外する前に、十分な観測済み事例と チャートの手動レビューを求める。

**必須スキル:** `stockbee-setup-fluency-trainer`

**任意スキル:** `trader-memory-core`, `signal-postmortem`, `backtest-expert`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `model_book_ingest` | 1 | あり | — |
| `matured_setup_outcomes` | 2 | あり | — |
| `setup_fluency_summary` | 3 | あり | `monthly-performance-review` |
| `rule_candidates` | 3 | なし | `monthly-performance-review` |
| `accepted_lessons_log` | 4 | なし | `monthly-performance-review` |

**ステップ:**

**ステップ 1: 最新のStockbeeモメンタムバースト候補を取り込む** → `stockbee-setup-fluency-trainer`

- 出力: `model_book_ingest`

**ステップ 2: 観測期間を終えた3日・5日後の結果を更新する** → `stockbee-setup-fluency-trainer`

- 入力: `model_book_ingest`
- 出力: `matured_setup_outcomes`

**ステップ 3: セットアップのコホートとルール候補を要約する** （判断ゲート） → `stockbee-setup-fluency-trainer`

- 入力: `matured_setup_outcomes`
- 出力: `setup_fluency_summary`, `rule_candidates`
- **判断:** 採用、格下げ、監視継続を判断できるだけの観測済み事例があるセットアップタグは どれか。取引ルールを変更する前に代表的なチャートを確認する。

**ステップ 4: 採用した学びを記録する** （任意） （判断ゲート） → `trader-memory-core`

- 入力: `setup_fluency_summary`, `rule_candidates`
- 出力: `accepted_lessons_log`
- **判断:** どの知見を運用ルールの変更として採用し、どれを追加事例待ちの記録だけの観察とするか。

**手動レビュー:**

- ルール変更を採用する前に、代表的な成功例と失敗例のチャートを確認する。
- 証拠と執行判断を区別する。このワークフローはセットアップの傾向を記録し、実際の損益を扱わない。
- 特に市場レジームが変化したときは、サンプル数の基準を明示する。
- 日々場当たり的なルールを加えず、採用した学びを monthly-performance-review に引き渡す。

**記録先:** `trader-memory-core`

---

## スイング取引機会の日次確認 {#swing-opportunity-daily}

**`swing-opportunity-daily`** · 毎日 · 約40分 · fmp-required · 中級

**実行タイミング:** market-regime-daily が非制限的なエクスポージャー判断を出した後にのみ実行する。 スイング取引候補を抽出し、エントリー計画を作成する。

**実行してはいけないとき:** 最新の market-regime-daily の exposure_decision が cash-priority または restrictive の場合は実行しない。レジームゲートを通さず、単独のスクリーナーとして使用しない。

**必須スキル:** `vcp-screener`, `drawdown-circuit-breaker`, `technical-analyst`, `position-sizer`, `trader-memory-core`, `pre-trade-discipline-gate`

**任意スキル:** `stockbee-momentum-burst-screener`, `stockbee-exhaustion-hammer-screener`, `canslim-screener`, `breakout-trade-planner`, `theme-detector`

**前提ワークフロー（参考情報）:**

- `market-regime-daily` が期待する成果物 `exposure_decision` — 新規スイング取引のリスクを取るには、非制限的なエクスポージャー判断が必要である。 cash-priority または restrictive の日はこのワークフローを見送る。

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `circuit_breaker_decision` | 1 | あり | — |
| `vcp_candidates` | 2 | あり | — |
| `momentum_burst_candidates` | 3 | なし | — |
| `exhaustion_hammer_candidates` | 4 | なし | — |
| `canslim_candidates` | 5 | なし | — |
| `theme_candidates` | 6 | なし | — |
| `validated_setups` | 7 | あり | — |
| `position_sizing` | 8 | あり | — |
| `trade_plans` | 9 | なし | `trade-memory-loop` |
| `candidate_journal_entry` | 10 | あり | `trade-memory-loop` |
| `pre_trade_discipline_decision` | 11 | あり | — |

**ステップ:**

**ステップ 1: 口座のサーキットブレーカーを確認する** （判断ゲート） → `drawdown-circuit-breaker`

- 出力: `circuit_breaker_decision`
- **判断:** 本日の新規取引リスクについて、口座のサーキットブレーカーは TRADING_ALLOWED になっているか。

**ステップ 2: VCPスクリーナーを実行する** → `vcp-screener`

- 出力: `vcp_candidates`

**ステップ 3: Stockbeeモメンタムバースト・スクリーナーを実行する** （任意） → `stockbee-momentum-burst-screener`

- 出力: `momentum_burst_candidates`

**ステップ 4: Stockbeeエグゾースションハンマー・スクリーナーを実行する** （任意） → `stockbee-exhaustion-hammer-screener`

- 出力: `exhaustion_hammer_candidates`

**ステップ 5: CANSLIMスクリーナーを実行する** （任意） → `canslim-screener`

- 出力: `canslim_candidates`

**ステップ 6: テーマ検出でクロスチェックする** （任意） → `theme-detector`

- 出力: `theme_candidates`

**ステップ 7: 週足チャートでセットアップを検証する** （判断ゲート） → `technical-analyst`

- 入力: `vcp_candidates`, `momentum_burst_candidates`, `exhaustion_hammer_candidates`, `canslim_candidates`, `theme_candidates`
- 出力: `validated_setups`
- **判断:** 明確な週足セットアップ（Stage 2の上昇トレンド、引き締まったベース、または 制御されたベースからのStockbee式レンジ拡大）があり、チャートの手動レビューを 通過する候補はどれか。エグゾースションハンマーでは、押しが投資仮説を崩すものではなく、 当日安値までのリスクが許容範囲かを確認する。通過しない候補は却下する。

**ステップ 8: ポジションサイズを計算する** → `position-sizer`

- 入力: `validated_setups`
- 出力: `position_sizing`

**ステップ 9: エントリー計画を作成する** （任意） → `breakout-trade-planner`

- 入力: `validated_setups`, `position_sizing`
- 出力: `trade_plans`

**ステップ 10: 投資仮説を記録する** （判断ゲート） → `trader-memory-core`

- 入力: `position_sizing`, `trade_plans`
- 出力: `candidate_journal_entry`
- **判断:** 検証を通過した各候補について、エントリー、ストップ、目標を含む投資仮説を登録する。 取引ごとのリスクが position-sizer の出力と一致し、ポートフォリオ全体の リスク量が上限内であることを確認する。

**ステップ 11: 手動執行規律ゲートを実行する** （判断ゲート） → `pre-trade-discipline-gate`

- 入力: `candidate_journal_entry`, `position_sizing`, `trade_plans`, `circuit_breaker_decision`
- 出力: `pre_trade_discipline_decision`
- **判断:** ブローカーへ手動注文を出す前に、実行可能な各候補は、文章化された計画、事前設定した ストップ、ポジションサイズ、直近損失、市場レジーム、サーキットブレーカーの 規律チェックを通過しているか。

**手動レビュー:**

- 実行前に market-regime-daily の exposure_decision が新規リスクを許可していることを確認する。
- 新規候補の抽出やサイズ計算前に circuit_breaker_decision が TRADING_ALLOWED であることを確認する。
- スクリーナーを通過していても、週足セットアップが不明確な候補は却下する。
- Stockbeeモメンタムバーストの出力は候補生成だけに使い、チャート検証とリスク距離の確認を必須とする。
- Stockbeeエグゾースションハンマーの出力は候補生成だけに使い、押しが投資仮説を崩すニュースによるものではないことと、当日安値までのリスクを確認する。
- 注文前にポートフォリオ全体のリスク量が上限内であることを確認する。
- ブローカーへ手動注文を出す前に pre_trade_discipline_decision が GO であることを確認する。
- すべての注文はブローカーで手動入力し、自動執行しない。

**記録先:** `trader-memory-core`

---

## 取引記憶ループ {#trade-memory-loop}

**`trade-memory-loop`** · 随時 · 約30分 · no-api-basic · 初級

**実行タイミング:** ポジションを全決済または一部決済するたびに実行する。結果を記録して事後分析を作成し、 任意でプロセス、リスク、執行、行動パターンを振り返り、元の仮説をバックテストで再検証する。

**実行してはいけないとき:** ポジション決済前には実行しない。未決済の投資仮説を更新する場合は trader-memory-core を直接使用する。利益取引であっても、決済後にこのループを省略しない。

**必須スキル:** `trader-memory-core`, `signal-postmortem`

**任意スキル:** `trade-performance-coach`, `backtest-expert`

**成果物一覧:**

| 成果物 | 生成ステップ | 必須 | 下流ヒント |
|---|---|---|---|
| `closed_thesis_record` | 1 | あり | — |
| `postmortem_findings` | 2 | あり | `monthly-performance-review` |
| `performance_coach_report` | 3 | なし | `monthly-performance-review` |
| `next_session_operating_rules` | 3 | なし | `monthly-performance-review` |
| `backtest_validation` | 4 | なし | — |
| `lessons_log_entry` | 5 | あり | `monthly-performance-review` |

**ステップ:**

**ステップ 1: 決済済み取引の結果を記録する** → `trader-memory-core`

- 出力: `closed_thesis_record`

**ステップ 2: 事後分析を作成する** （判断ゲート） → `signal-postmortem`

- 入力: `closed_thesis_record`
- 出力: `postmortem_findings`
- **判断:** 結果の根本原因は、投資仮説の質、執行、市場環境、偶然性のどれか。 分類して記録する。

**ステップ 3: プロセス、リスク、行動パターンを振り返る** （任意） （判断ゲート） → `trade-performance-coach`

- 入力: `closed_thesis_record`, `postmortem_findings`
- 出力: `performance_coach_report`, `next_session_operating_rules`
- **判断:** 次の取引セッションの運用ルールのうち、採用、修正、保留、記録のみとするものはどれか。

**ステップ 4: バックテストで仮説を再検証する** （任意） → `backtest-expert`

- 入力: `postmortem_findings`
- 出力: `backtest_validation`

**ステップ 5: 学びを記録に追記する** → `trader-memory-core`

- 入力: `postmortem_findings`, `backtest_validation`
- 出力: `lessons_log_entry`

**手動レビュー:**

- 利益が投資仮説によるものか、単なる幸運かを正直に評価する。
- 損失が投資仮説の欠陥によるものか、執行不良によるものかを正直に評価する。
- 偶然を技量や失敗として都合よく解釈しない。

**記録先:** `trader-memory-core`

---
