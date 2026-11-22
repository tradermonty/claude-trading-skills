---
layout: default
title: "Kanchi Dividend SOP"
grand_parent: 日本語
parent: スキルガイド
nav_order: 27
lang_peer: /en/skills/kanchi-dividend-sop/
permalink: /ja/skills/kanchi-dividend-sop/
---

# Kanchi Dividend SOP
{: .no_toc }

かんち式配当投資を米国株向けの再現可能なオペレーティングプロシージャに変換します。かんち式配当投資、配当スクリーニング、配当成長の品質チェック、米国セクター向けPER×PBR適応、押し目指値注文プランニング、または1ページ銘柄メモの作成を求められた際に使用します。スクリーニング、深掘り、エントリープランニング、購入後のモニタリング頻度をカバーします。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/kanchi-dividend-sop.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/kanchi-dividend-sop){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

かんちの5ステップメソッドを米国配当投資の確定的ワークフローとして実装します。
アグレッシブな利回り追求よりも安全性と再現性を優先します。

---

## 2. 使用タイミング

以下が必要な場合にこのスキルを使用します:
- 米国株に適応したかんち式の配当銘柄選定。
- アドホックな銘柄選びの代わりに、再現可能なスクリーニングと押し目エントリープロセス。
- 明示的な無効化条件付きの1ページ引受メモ。
- モニタリングおよび税務/口座配置ワークフロー向けの引き渡しパッケージ。

---

## 3. 前提条件

### APIキー設定

エントリーシグナルスクリプトにはFMP APIアクセスが必要です:

```bash
export FMP_API_KEY=your_api_key_here
```

### 入力ソース

ワークフロー実行前に以下のいずれかの入力を準備:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` の出力。
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` の出力。
3. ユーザー提供のティッカーリスト（ブローカーエクスポートまたは手動リスト）。

確定的なアーティファクト生成には、以下にティッカーを渡します:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_sop_plan.py \
  --tickers "JNJ,PG,KO" \
  --output-dir reports/
```

ステップ5のエントリータイミングアーティファクト:

```bash
python3 skills/kanchi-dividend-sop/scripts/build_entry_signals.py \
  --tickers "JNJ,PG,KO" \
  --alpha-pp 0.5 \
  --output-dir reports/
```

---

### エントリーCLIのオプションと入力の境界

以下は `skills/kanchi-dividend-sop/scripts/build_entry_signals.py` のオプションです。
現在のプロバイダーデータを取得するため、評価日の指定だけで、すべての入力が過去時点の
スナップショットになるわけではありません。

| オプション | 意味 |
| --- | --- |
| `--tickers` | カンマ区切りの銘柄。空でない指定は `--input` より優先されます。 |
| `--input` | candidates/stocks/tickersを持つJSON。銘柄のみを読み、入力の価格や財務値でプロバイダー取得値を置き換えません。 |
| `--alpha-pp` | 利回りへの加算幅。単位はパーセントポイント、既定値は `0.5`。 |
| `--yield-floor` | Step 1の利回り下限をパーセントで明示（例 `3.0`）。既定は未指定で、指定時にStep 1とData Freshnessの評価を有効にします。 |
| `--financials-json` | 単位・出所・評価日・文書参照を伴う銘柄別財務値。採用値はMANUALとして記録し、文書の取得・真偽確認は行いません。 |
| `--yield-history-json` | 出所（`source`）付きで検証済みの銘柄別配当行・日次終値・株式分割。該当銘柄では取得データの代わりに使い、通常配当のみの5年平均利回りを再構築します。各銘柄に `price_basis: split_adjusted` と `splits` リストが必要です。配当行には `kind`（`special`、`exclude`、または `regular_amount` を伴う `combined`）と空でない `kind_source` を付けられ、Specialの行で `kind` がなければ拒否します。指定した行は、その銘柄の現在の分子を含め、取得した配当履歴の代わりに使われます。不正な入力は終了コード2で終了し、平均値の数字だけの入力は受け付けません。 |
| `--events-json` | 手動整理した企業イベント根拠。オプション未指定はSKIPPED、銘柄がなければNO_EVENT_FOUNDで、調査済み・問題なしの証明にはなりません。 |
| `--as-of` | 評価日 `YYYY-MM-DD`。既定値はローカルの当日です。 |
| `--profile` | income-now/balanced/growth-firstなどのプロファイルを実行記録に残します。`--yield-floor` や他の閾値は自動設定しません。 |
| `--safety-bias` | tight/mediumのラベルを実行記録に残します。指定だけでは配当安全性のルールは変わりません。 |
| `--universe-source` | 候補集合の出所を記録するラベル。候補の選択・取得を実行するオプションではありません。 |
| `--output-dir` | 出力先。既定値は `reports`。 |
| `--filename-prefix` | 出力名の接頭辞。既定値は `kanchi_entry_signals`。 |
| `--sleep-seconds` | プロバイダー呼出しの待ち時間。既定値は `0.15` 秒。 |

閾値を明示し、記録された根拠を確認してください。イベント根拠は手動整理した入力であり、
このCLIが自動でWebSearchするわけではありません。買い目標を保留する既存の制約は維持され、
フラグやラベルを加えても、検証できない目標価格でのエントリーが可能にはなりません。
財務値の補充は `--financials-json` の出典付き財務入力の契約を使い、`--input` に埋め込まないでください。

### 通常配当のみの5年平均利回り（issue #834）

買い目標は、特別配当を含むプロバイダーの年次利回りではなく、配当行と日次終値から再構築した平均で決まります。銘柄ごとに日次終値と株式分割を取得し、直近の完了月までの60か月について、各月の最終取引日の分割調整済み終値で`latest_declared_annualized` を割って平均します（方式 `month_end_60_regular_only_v1`）。配当周期が不規則、変動配当方針、直近2回の通常配当の間隔が異常（頻度の切替や日割りのスタブ配当）、FMPの `frequency` が推定周期と食い違う月は除外します。

価格または配当の履歴が5年に満たない場合、有効な月が90%未満の場合、窓内に株式分割がありながら `adjDividend` のない配当行がある場合は、平均を保留します。保留時は従来の `regular_only_average_unavailable` の動作を維持し、理由を `yield_history:` の接頭辞付きで `notes` に記録します。FMPで `frequency: Special` の行は特別配当として扱い、特別配当の判定は評価日時点の全履歴で一度だけ行います。株式分割の履歴が不明な場合や、窓の開始日以降に分割がありながら `adjDividend` のない配当行がある場合も平均を保留します。配当停止の疑いがある月は除外します。減配後は、その時点で宣言済みの配当率を維持し、`cut_in_window` を理由として記録しますが、これだけでは平均を保留しません。通常配当が、同額の連続した支払いより前の通常配当の中央値を25%超上回り、同額の支払いが2回続いていない場合は、次の支払いで同額が繰り返されるまで未確認とします。本物の増配は2回目の支払いで確認され、25%以下の増配は保留しません。直近に使った支払いが未確認の月は除外します。直近の通常配当が `Irregular` または未確認の場合は、`latest_dividend_unconfirmed` で目標を保留します。既知の制約として、履歴内の通常配当を25%未満しか上回らない通常配当と特別配当の合算行はデータだけでは検出できないため、`kind: combined` で補正してください。JSONの各行に `yield_history` の要約が付き、CSVには `yield_history_status`、`yield_window_start`、`yield_window_end`、`yield_coverage_ratio`、`yield_method` の列が加わります。ほかの発注ゲートは変わらず、`order_ready` には `--events-json` の `CLEAN_CONFIRMED` と、`--financials-json` の出典付き調整後EPSまたはセクター指標が引き続き必要です。


## 4. クイックスタート

### 1) スクリーニング前にマンデートを定義

まずパラメータを収集し確定:
- 目的: 現金収入重視 vs 配当成長重視。
- 最大ポジション数とポジションサイズ上限。
- 許可する商品: 株式のみ、またはREIT/BDC/ETFを含む。
- 推奨する口座タイプのコンテキスト: 課税口座 vs IRA類似口座。

---

## 5. ワークフロー

### 1) スクリーニング前にマンデートを定義

まずパラメータを収集し確定:
- 目的: 現金収入重視 vs 配当成長重視。
- 最大ポジション数とポジションサイズ上限。
- 許可する商品: 株式のみ、またはREIT/BDC/ETFを含む。
- 推奨する口座タイプのコンテキスト: 課税口座 vs IRA類似口座。

`references/default-thresholds.md` を読み込み、ユーザーがオーバーライドしない限り
ベースライン設定を適用。

### 2) 投資対象ユニバースの構築

品質バイアスのかかったユニバースから開始:
- コアバケット: 配当成長の長い銘柄（例: Dividend Aristocrats スタイルの品質セット）。
- サテライトバケット: 高利回りセクター（公益、通信、REIT）を別のリスクバケットとして。

ティッカー収集の明示的なソース優先順位:
1. `skills/value-dividend-screener/scripts/screen_dividend_stocks.py` の出力（FMP/FINVIZ）。
2. `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py` の出力。
3. APIが利用できない場合のユーザー提供ブローカーエクスポートまたは手動ティッカーリスト。

先に進む前にバケット別のティッカーリストを返す。

### 3) かんちステップ1を適用（利回りフィルターとトラップフラグ）

主要ルール:
- `forward_dividend_yield >= 3.5%`

トラップ制御:
- 極端な利回り（`>= 8%`）を `deep-dive-required` としてフラグ。
- ペイアウトの急激な増加を特別配当のアーティファクトの可能性としてフラグ。

出力:
- ティッカーごとに `PASS` または `FAIL`。
- 潜在的な利回りトラップの `deep-dive-required` フラグ。

### 4) かんちステップ2を適用（成長と安全性）

必須条件:
- 売上とEPSのトレンドが複数年の期間でプラス。
- 配当トレンドがレビュー期間中に非減少。

安全性チェックの追加:
- 配当性向とFCF配当性向が合理的な範囲内。
- 債務負担とインタレストカバレッジが悪化していない。

トレンドが混在しているが崩壊していない場合、ハードリジェクトではなく `HOLD-FOR-REVIEW` として分類。

### 5) かんちステップ3を適用（バリュエーション） — 米国セクターマッピング付き

`references/valuation-and-one-off-checks.md` を使用し、
セクター固有のバリュエーションロジックを適用:
- 金融: `PER × PBR` を引き続き主要指標として使用可。
- REIT: 通常の `P/E` の代わりに `P/FFO` または `P/AFFO` を使用。
- アセットライトセクター: フォワード `P/E`、`P/FCF`、ヒストリカルレンジを組み合わせ。

各ティッカーでどのバリュエーション手法を使用したか必ず記載。

### 6) かんちステップ4を適用（一時的イベントフィルター）

最近の利益が一時的効果に依存している銘柄をリジェクトまたは格下げ:
- 資産売却益、訴訟和解金、税効果スパイク。
- 売上トレンドに裏付けのないマージンスパイク。
- 繰り返される「一時的/非経常」調整。

各 `FAIL` に対して監査可能性を保つため1行のエビデンスを記録。

### 7) かんちステップ5を適用（ルールに基づく押し目買い）

エントリートリガーを機械的に設定:
- 利回りトリガー: 現在の利回りが5年平均利回り + アルファ（デフォルト `+0.5pp`）を上回る。
- バリュエーショントリガー: 目標マルチプルに到達（`P/E`、`P/FFO`、または `P/FCF`）。

執行パターン:
- 注文分割: `40% -> 30% -> 30%`。
- 各追加購入前に1文のサニティチェックを必須: 「テーゼ継続 vs 構造的破綻」。

### 8) 標準化された出力の作成

常に3つのアーティファクトを作成:
1. スクリーニングテーブル（`PASS`、`HOLD-FOR-REVIEW`、`FAIL` とエビデンス）。
2. 1ページ銘柄メモ（`references/stock-note-template.md` を使用）。
3. 分割サイジングと無効化条件付きの指値注文プラン。

---

## 6. リソース

**リファレンス:**

- `skills/kanchi-dividend-sop/references/default-thresholds.md`
- `skills/kanchi-dividend-sop/references/stock-note-template.md`
- `skills/kanchi-dividend-sop/references/valuation-and-one-off-checks.md`

**スクリプト:**

- `skills/kanchi-dividend-sop/scripts/build_entry_signals.py`
- `skills/kanchi-dividend-sop/scripts/build_sop_plan.py`

## 出典付き財務指標

`--financials-json financials.json` で、銘柄ごとの調整後EPS、FFO/負債、銀行・保険・REIT指標を補って再実行できます。
各値には単位・出典・基準日 `as_of`・文書参照が必要です。受理した値は MANUAL として記録します。
出典はユーザーの申告で、文書の実在・内容・公開日・鮮度は自動検証しません。
不正値は理由付き HOLD-REVIEW となり、既存の FAIL は維持します。
[完全な入力仕様・架空例・指標一覧](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/kanchi-dividend-sop/references/sourced-financials.md)を参照してください。
EPS/AFFO は配当と同じ米ドル基準の年額/株、比率は 0.12 = 12% の小数です。通貨変換には対応しません。

JSON・CSV・Markdown の `order_ready` が総合的なスクリーニング準備状態です。
TRIGGERED、CLEAN-PASS または CONDITIONAL-PASS、最終T1制限なし、注文前ブロッカーなしのすべてが必要で、PASS-CAUTION は false です。
`event_t1_blocked` はイベント由来のみ、従来の `t1_blocked` は判定統合後のT1制限です。
後者が false でも未解決ブロッカーは残り得ます。準備完了は取引の承認ではなく、人による確認と注文ゲートが必要です。

## Dividend availability and split amount basis

Distinguish a failed or malformed dividend request (`None`) from a confirmed empty list (`[]`). Unknown, unusable or entirely future-only evidence requires `STEP1-RECHECK`; only confirmed empty history establishes `FAIL no_dividend`. Never substitute profile TTM `lastDiv` for missing regular dividends: withhold yields/entry targets and keep order readiness false. Unrelated established safety failures retain their priority.

Use finite positive `adjDividend` consistently when any eligible row supplies that field. Do not mix adjusted and raw rows or fall back from missing/invalid adjusted amounts. Record `dividend_amount_basis` and the history status in JSON/CSV/Markdown. Raw-only CLI inputs require confirmed split history: unknown splits or a relevant split without adjusted dividends require review. Original-currency amounts whose split basis cannot be established also require review; never infer or apply a split ratio from a dividend-rate change. Future-only rows are excluded before basis selection.

Direct library callers retain raw-only compatibility unless `require_split_evidence=True`; the result marks that basis `raw_unverified`. The CLI always requires split evidence. A confirmed empty split list yields `raw_no_splits_confirmed`. Adjusted provider rows yield `split_adjusted`, which describes the supplied amount convention and does not certify live FMP adjustment semantics or point-in-time historical availability. Re-fetch failed data or supply sourced consistent history before retrying; do not act on incomplete reports.
