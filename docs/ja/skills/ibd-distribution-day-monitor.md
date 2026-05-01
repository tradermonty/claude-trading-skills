---
layout: default
title: IBD Distribution Day Monitor
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/ibd-distribution-day-monitor/
permalink: /ja/skills/ibd-distribution-day-monitor/
---

# IBD Distribution Day Monitor
{: .no_toc }

QQQ/SPY のIBD式 Distribution Day を検出し、25セッションでの失効・5%上昇による無効化を追跡。リスク区分（NORMAL / CAUTION / HIGH / SEVERE）と TQQQ/QQQ 向けエクスポージャ推奨を生成。日次のクロージング後レビュー用。
{: .fs-6 .fw-300 }

[Skillパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/ibd-distribution-day-monitor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/ibd-distribution-day-monitor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

IBD Distribution Day Monitor は、William O'Neil の CAN SLIM フレームワークの中で最も実践的なシグナル—機関投資家が静かに売り抜けている日の検出—を、再現可能な日次ワークフローとして自動化します。Distribution Day のクラスターは過去の主要な調整局面のほとんどに先行しており、本スキルはこのルールを厳密な手順に落とし込みます。

**解決する課題:**
- 「25セッションは inclusive か？」「DD 当日の高値は5%判定に含めるか？」など、トレーダーごとに解釈が分かれるルールから曖昧さを排除
- 決定論的なリスクレベル（NORMAL / CAUTION / HIGH / SEVERE）と TQQQ 特化のエクスポージャ推奨を1コマンドで生成
- 目視判断を、有効カウントに寄与した日付まで含む監査可能な JSON 出力に置き換え
- QQQ + SPY を同時処理し、TQQQ 戦略を意識した重み付けで全体リスクへ統合

**主な機能:**
- Distribution Day 検出: 終値 0.2% 以上の下落 + 出来高増加。境界には float の epsilon を明示的に適用
- 25セッション失効と 5% 無効化を別軸で追跡し、`removal_reason` に `expired_25_sessions` または `invalidated_5pct_gain` を記録
- 表示用と無効化判定用で `high_since` の範囲を分離: DD 当日の intraday high は表示には含むが同じ DD の無効化には使用しない
- `invalidation_price_source` を選択可能: `high`（保守的、デフォルト）または `close`（終値ベース）
- 設定可能な `RiskThresholds` によるリスク分類、21EMA / 50SMA フィルタで両 MA を下回り `d25 >= 5` の場合に SEVERE へエスカレート
- TQQQ 重視の複数指数統合: QQQ 単独の HIGH、または QQQ NORMAL + SPY HIGH のいずれも全体リスクを引き上げ
- TQQQ エクスポージャポリシー（100 / 75 / 50 / 25%）とリスク上昇に応じた段階的トレーリングストップ。QQQ には控えめなバリアント
- UTF-8 出力（`ensure_ascii=False`）。監査スナップショット内の API キーは自動でリダクション

<span class="badge badge-api">FMP必須</span>

---

## 2. 前提条件

- **API キー:** [Financial Modeling Prep (FMP)](https://site.financialmodelingprep.com/developer/docs) — 無料ティア（250 calls/day）で日次の QQQ + SPY 実行に十分
- **Python 3.9+:** 標準ライブラリ + `requests`（既インストール）+ `pyyaml`（`pyproject.toml` に依存追加済み）
- **pandas 不要:** OHLCV はすべて `list[dict]` で処理（移植性と速度のため）

> API キーは環境変数で1度だけ設定: `export FMP_API_KEY=your_key_here`。解決順は `--api-key` フラグ > config の `data.api_key` > `FMP_API_KEY` 環境変数 で、CLI override が常に優先されます。
{: .tip }

> Distribution Day ルール自体は市場構造の前提に依存しないため、FMP がサポートする任意の流動性のある US ETF/指数で動作します。デフォルトは QQQ + SPY 向けに調整されています。
{: .note }

---

## 3. クイックスタート

デフォルト設定で実行:

```bash
export FMP_API_KEY=your_key_here

python3 skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py \
  --symbols QQQ,SPY \
  --lookback-days 80 \
  --instrument TQQQ \
  --current-exposure 100 \
  --base-trailing-stop 10 \
  --output-dir reports/
```

スクリプトは各シンボルの 80 セッション分の OHLCV を取得し、有効な Distribution Day を検出、リスクを分類、`reports/` に `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.{json,md}` ペアを書き出します。

Claude Code 内では会話形式でも呼び出せます: 「今日の IBD Distribution Day モニターを実行して、TQQQ のポジションを 100% のままで良いか教えて」。

---

## 4. 仕組み

```
+-----------------+   +-----------------------+   +-----------------------+
| 1. OHLCV 取得   |-->| 2. as_of 正規化       |-->| 3. DD 検出            |
|   (FMP/シンボル)|   |   prepare_effective_  |   |  pct_change <= -0.002 |
+-----------------+   |   history             |   |  かつ出来高増加       |
                      +-----------------------+   +-----------+-----------+
                                                              |
+-----------------+   +-----------------------+   +-----------v-----------+
| 7. リスク統合   |<--| 6. 指数別分類         |<--| 4. レコード拡充       |
|   QQQ 重み付け  |   |   d5/d15/d25 + MA     |   |  high_since (表示)    |
+--------+--------+   +-----------------------+   |  無効化イベント       |
         |                                         |  失効 / ステータス    |
         v                                         +-----------+-----------+
+-----------------+   +-----------------------+               |
| 8. エクスポー   |-->| 9. JSON + MD 書き出し |<--------------+
|   ジャ推奨      |   |  リダクション付き     |
+-----------------+   +-----------------------+
```

1. **OHLCV 取得** — 各シンボルに対して `lookback_days + 5` の余裕を持たせて取得。50SMA フィルタが計算可能になるよう確保。`fmp_client.py` は Issue #64 修正版で正しく truncate。
2. **`as_of` 正規化** — 当日（デフォルト）または `--as-of YYYY-MM-DD` 指定日を、`effective_history[0]` が常に評価セッションになるよう slice。`as_of_index` を後段モジュールに引き回さないため、トラッカーの実装がシンプルに保たれる。
3. **DD 検出** — 連続するペアごとに `pct_change <= -0.002 + EPSILON` かつ出来高増加を判定。close/volume が欠損または非正値のセッションはスキップし、`audit.skipped_sessions` に記録。
4. **拡充** — 各 raw DD を完全なレコードに変換:
    - 表示用 `high_since` = `max(history[0:k+1] の high)`（DD 当日 high を含む）
    - 無効化スキャン = `history[0:k]` ∩ 失効ウィンドウ、`invalidation_price_source` の設定に従う
    - ステータス優先順位: `invalidated` > `expired` > `active`
    - 25 セッション**経過後**の 5% 上昇は `expired_25_sessions` 扱いで、無効化扱いにはならない
5. **カウント** — `count_active_in_window(records, N)` は `active` かつ `age_sessions <= N` のレコード数を返す。つまり `d25_count` は age 0..25（26 セッション）を含む。`expiration_sessions = 25` と境界が揃っており、age=25 の DD は active で d25 にもカウント、age=26 で expired となり d25 から外れる。
6. **指数別分類** — しきい値（SEVERE は `d25 >= 6` または `d15 >= 4` 等）は config（`RiskThresholds`）から読み込み。21EMA / 50SMA フィルタは終値が**両方の**MA を下回り、かつ `d25 >= 5` の場合のみ SEVERE へエスカレート。データ不足で MA が計算できない場合、フィルタは `None` となり SEVERE エスカレートはスキップ。
7. **統合** — 統合リスクは TQQQ 重視: いずれかの指数で SEVERE、または QQQ で HIGH の場合は即座にエスカレート。`QQQ NORMAL + SPY HIGH` も HIGH に引き上げ（広範な市場劣化が TQQQ に波及するため）。それ以外は最大リスクを採用。
8. **エクスポージャポリシー** — TQQQ はリスクに応じて {100, 75, 50, 25}% を目標とし、トレーリングストップも段階的に絞る。QQQ は控えめなバリアント {100, 100, 75, 50}%。推奨はユーザー既存のトレーリングストップを**広げない**—絞ることのみ。
9. **出力** — JSON は `ensure_ascii=False` で書き出し、日本語の説明文がそのまま round-trip 可能。機微キー（`api_key`, `fmp_api_key`, `token` 等）は両ファイル書き出し前に lowercase 比較でリダクション。

---

## 5. 使用例

### 例1: 日次クロージング後のチェック

**プロンプト:**
```
今日の IBD Distribution Day モニターを実行して、TQQQ ポジションを調整すべきか
レポートして。
```

**動作:** スキルは QQQ + SPY の 80 セッション分を読み込み、有効な Distribution Day を検出し、統合リスクレベルと TQQQ 特化の推奨（目標エクスポージャ %、トレーリングストップ %）を出力。

**有用性:** 指数チャートの目視判断を、数秒で得られる決定論的な答えに置き換え。同じ入力は常に同じ出力を返すため、リスク管理ルールに必要な性質を担保。

---

### 例2: 過去の天井をバックテスト

**プロンプト:**
```
2025-04-04（関税ショックによる下落の翌日）時点の IBD Distribution Day の状況は
どうだった？
```

**動作:** `--as-of 2025-04-04 --lookback-days 80` で履歴を当日基準に再正規化し、その日が今日であるかのようにフルパイプラインを実行。MA フィルタも 5% 無効化トラッカーも歴史的文脈を尊重。

**有用性:** 実際のドローダウンに先立ってルールが警告を出していたかを検証。`insufficient_lookback` フラグが立った場合は `lookback-days` を増やして再実行。

---

### 例3: リスクしきい値の調整

**プロンプト:**
```
もう少し保守的なトリガーが欲しい。HIGH を d25 >= 4 に変更して、今日の分析を
再実行して。
```

**動作:** `skills/ibd-distribution-day-monitor/config/default.yaml`（または独自 `--config` パス）で `risk_thresholds.high.d25_count: 4` に編集して再実行。スキルは新しいしきい値を読み込んで再分類。変更は必ず先に `--as-of` で過去日に対して検証を。

**有用性:** 感度はトレーダーごとに好みが異なる。スキルはしきい値をハードコードせず、すべて YAML に置き、ポートフォリオごとにチューニング可能。

---

### 例4: クローズベースの無効化に切り替え

**プロンプト:**
```
無効化判定を、終値が DD 終値を 5% 以上上回った時のみ発火させたい。intraday
high は使わない。
```

**動作:** config の `distribution_day_rule.invalidation_price_source: close` に変更。`_find_invalidation_event` スキャナーは `row["high"]` ではなく `row["close"]` を `dd_close * 1.05` と比較するようになる。

**有用性:** 厳密な終値ベース解釈を好む実務家もいる。スキルはコード変更なしに両方をサポート。選択は `audit.rule_evaluation.distribution_day_rule.invalidation_price_source` に記録される。

---

### 例5: TQQQ 買い増し前のサニティチェック

**プロンプト:**
```
TQQQ ポジションを 25% 追加しようと思う。市場環境はゴーサイン？
```

**動作:** スキルが現在のリスクレベルをレポート。NORMAL なら推奨は `HOLD_OR_FOLLOW_BASE_STRATEGY`、CAUTION なら `AVOID_NEW_ADDS`、HIGH/SEVERE なら明示的にエクスポージャ縮小を提案。

**有用性:** レバレッジの追加買い前の 5 秒のサニティチェック。HIGH 状態の市場で繰り返し買い増しすることは、アマチュアの TQQQ トレーダーが指数下落以上に資金を失う最も典型的なパターン。

---

### 例6: Position Sizer との連携

**プロンプト:**
```
リスクレベルが HIGH。推奨に基づいて、トレーリングストップを絞った状態で
TQQQ のポジションサイズを再計算して。
```

**動作:** IBD Monitor は HIGH 状態で `trailing_stop_pct: 5` を返す。これを Position Sizer スキル（`--atr-multiplier` またはストップベースサイジング）に渡してより小さい株数を計算。

**有用性:** リスク管理は連鎖する。Distribution Day シグナルがトレーリングストップを決め、トレーリングストップが株数を決める。両方とも決定論的かつ監査可能。

---

## 6. 出力の読み方

スキルは 2 つのファイルとコンソールサマリを出力します:

1. **JSON レポート** — `market_distribution_state` / `portfolio_action` / `rule_evaluation` / `audit` の完全スキーマ。UTF-8 + `ensure_ascii=False`
2. **Markdown レポート** — 指数別の active DD テーブル、推奨アクション、audit flag を含む人可読サマリ

### リスクレベル早見表

| Risk | トリガー（いずれか） | TQQQ アクション | TQQQ 目標 | トレース上限 |
|------|------|------|------|------|
| NORMAL | `d25 <= 2` | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base |
| CAUTION | `d25 >= 3` | AVOID_NEW_ADDS | 75% | 7% |
| HIGH | `d25 >= 5` または `d15 >= 3` または `d5 >= 2` | REDUCE_EXPOSURE | 50% | 5% |
| SEVERE | `d25 >= 6` または `d15 >= 4` または（21EMA かつ 50SMA を下回り `d25 >= 5`）| CLOSE_TQQQ_OR_HEDGE | 25% | 3% |

### 各 DD レコードのフィールド

| フィールド | 意味 |
|-------|---------|
| `date` | Distribution Day 日付 |
| `age_sessions` | DD からの経過セッション数（0 = 今日） |
| `expires_in_sessions` | `25 - age_sessions`（0 で下限） |
| `pct_change` | DD 当日の下落率（負値） |
| `volume_change_pct` | DD 当日の出来高変化率 |
| `high_since` | DD 当日**含む** intraday high の表示用最大値 |
| `invalidation_price` | `dd_close * 1.05` |
| `invalidation_date` | DD 後に最初に 5%+ をトリガーした日付（未トリガーは null） |
| `invalidation_trigger_price` | 実際にトリガーした価格（config に応じて high または close） |
| `invalidation_trigger_source` | config 設定値 `"high"` または `"close"` |
| `status` | `active` / `expired` / `invalidated` |
| `removal_reason` | `expired_25_sessions` / `invalidated_5pct_gain`（active 時は null） |

### Audit flag

| フラグ | 意味 |
|------|---------|
| `insufficient_lookback` | ロード済み履歴が必要ウィンドウ（50SMA + 1 等）に満たない |
| `insufficient_data_for_moving_average` | 21EMA または 50SMA が計算不能。SEVERE エスカレートはスキップ |
| `data_quality_warnings` | OHLCV の欠損・無効値で 1 セッション以上スキップ |
| `no_data_returned` | FMP がいずれかのシンボルで空応答 |

---

## 7. Tips & ベストプラクティス

- **クロージング後に実行、intraday では実行しない。** Distribution Day ルールは end-of-day データを前提に設計されている。intraday の出来高推定は不確実で、引けまでに値が回復すれば intraday の "DD" は消失する。
- **カウントだけでなくクラスターパターンを見る。** 5 セッション内で 2 つの DD（`d5 >= 2`）は、25 セッションに均等分布する 5 つの DD よりも危険。同じ HIGH でも質が違う。スキルは d5/d15/d25 の 3 バケットでこれを表現。
- **`--as-of` でルールを過去検証。** しきい値変更を信頼する前に、2008、2018、2020、2022、2025-04 に対して修正後 config を当て、適切なタイミングで発火していたかを確認。
- **トレーリングストップは広げない。** スキルの推奨は常に `min(your_base, policy_cap)`。既存のトレースが既に絞られていればスキルはそれを尊重。手動で広げるとルールの意義が損なわれる。
- **`market_below_21ema_or_50ma=None` は実在するケース。** IPO 直後や薄商いの指数では 50SMA フィルタが利用不能。スキルは適切に `None` を返し、推測に基づく SEVERE エスカレートを行わない。
- **FTD Detector と組み合わせて完全な状態管理。** Distribution Days は守りに入る警告、Follow-Through Days は攻めに転じる確認。両方を回すのが主要指数タイミングの最もシンプルな 2 極フレームワーク。

---

## 8. 他スキルとの連携

| ワークフロー | 連携方法 |
|----------|---------------|
| **日次エクスポージャレビュー** | IBD Distribution Day Monitor でリスクレベルを取得 → Market Breadth Analyzer で確認。不一致（DD が HIGH なのに breadth が Strong 等）は追加調査 |
| **底打ち確認ペア** | SEVERE → ドローダウン → 回復後、最安値から FTD Detector を起動。FTD シグナルが distribution の警告と相殺 |
| **Position Sizing** | トレーリングストップ推奨を Position Sizer に渡してレバレッジ ETF の株数を計算。絞ったストップは小さい株数に直結 |
| **天井確率の合成** | `risk_level` を Market Top Detector の入力の 1 つに。Distribution クラスターは O'Neil の天井 6 コンポーネントの 1 つ |
| **バックテスト検証** | `--as-of` を過去日でループし、JSON 出力を Backtest Expert に渡してしきい値+エクスポージャポリシーが buy-and-hold より drawdown を改善するか検証 |
| **かんち式配当ポートフォリオ** | リスクレベルをオーバーレイとして使用: HIGH/SEVERE では TQQQ への買い増しを停止。ただし個別仮説の T1-T5 がクリーンならかんち式の配当買いは継続 |

---

## 9. トラブルシューティング

### `FMP API key required` エラー

**原因:** `--api-key`、`config.data.api_key`、`FMP_API_KEY` 環境変数のいずれも設定されていない。

**対処:** シェルで `export FMP_API_KEY=your_key_here` を設定するか、CLI に `--api-key your_key_here` を渡す。スキルは明示的な config パス経由以外でディスクから API キーを読まない。

### `as_of YYYY-MM-DD not found in loaded history`

**原因:** 指定した日付が FMP のデータ上の取引日ではない、または `lookback_days` の範囲外。

**対処:** 指定日が US 市場の取引日（週末・祝日でない）であることを確認したうえで、`--lookback-days` を増やして対象日を取得範囲に含める。80 セッション以上前の日付には `--lookback-days 200` 以上を設定。

### `insufficient_lookback` audit flag

**原因:** `as_of` slice 後の履歴行数が `required_min_sessions = max(lookback, 50, expiration_sessions + 2)` を下回った。

**対処:** `--lookback-days` を増やし、slice 後も十分なセッション数を確保。分析は続行されるが、50SMA が `None` となり SEVERE エスカレートはスキップされる。

### `insufficient_data_for_moving_average` audit flag

**原因:** ロードした履歴の close が 21 行（21EMA 用）または 50 行（50SMA 用）未満。

**対処:** `--lookback-days` を最低 80 に増やす。意図的に短い履歴で運用する場合、SEVERE は `d25 >= 6` または `d15 >= 4` でしか発火せず、MA 条件では発火しない点を理解しておく。

### リスクレベルが HIGH なのにヘッドラインは静か

**原因:** Distribution クラスターは、ニュースになるような売り崩しに数日〜数週間先行することが多い。2007 年中頃、2021 年末、2022 年初頭はいずれも、実際の崩壊がヘッドラインを飾る前から HIGH 状態にあった。

**対処:** これは想定動作—先行指標は明白になるまでは "早すぎる" と感じる。ルールを信じてストップを絞り、新規買いを止める。HIGH の理由を見たければ Markdown レポートの active DD テーブルを確認。

### 推奨トレーリングストップが現在のストップより広い

**原因:** スキルは `min(your_base, policy_cap)` を返す。`--base-trailing-stop 4` を渡し、HIGH のポリシー上限が 5% なら、推奨は正しく 4% を維持。

**対処:** 対処不要—これは想定動作。スキルは既存の絞られたストップを広げない。

---

## 10. リファレンス

### CLI 引数

| 引数 | 必須 | デフォルト | 説明 |
|----------|----------|---------|-------------|
| `--symbols` | No | `QQQ,SPY`（config 由来） | カンマ区切りシンボル |
| `--lookback-days` | No | `80` | 取得する取引セッション数 |
| `--instrument` | No | `TQQQ`（config 由来） | `TQQQ` または `QQQ`（エクスポージャポリシーを切り替え） |
| `--current-exposure` | No | `100`（config 由来） | 現在のエクスポージャ（整数 %） |
| `--base-trailing-stop` | No | `10`（config 由来） | ベーストレーリングストップ %（スキルは広げない） |
| `--as-of` | No | 最新セッション | バックテスト用の `YYYY-MM-DD` |
| `--config` | No | `config/default.yaml` | 独自 YAML override パス |
| `--api-key` | No | `FMP_API_KEY` 環境変数 | FMP API キー |
| `--output-dir` | No | `reports/` | JSON + MD ペアの出力先 |

### デフォルト設定（`config/default.yaml`）

| セクション | キー | デフォルト |
|---------|-----|---------|
| `distribution_day_rule` | `min_decline_pct` | `-0.002` |
| `distribution_day_rule` | `expiration_sessions` | `25` |
| `distribution_day_rule` | `invalidation_gain_pct` | `0.05` |
| `distribution_day_rule` | `invalidation_price_source` | `high` |
| `risk_thresholds.caution` | `d25_count` | `3` |
| `risk_thresholds.high` | `d25_count` / `d15_count` / `d5_count` | `5 / 3 / 2` |
| `risk_thresholds.severe` | `d25_count` / `d15_count` / `severe_ma_d25` | `6 / 4 / 5` |
| `moving_average_filters` | `ema_periods` | `[21]` |
| `moving_average_filters` | `sma_periods` | `[50]` |
| `strategy_context` | `instrument` | `TQQQ` |
| `strategy_context` | `current_exposure_pct` | `100` |
| `strategy_context` | `base_trailing_stop_pct` | `10` |

### TQQQ vs QQQ エクスポージャポリシー

| Risk | TQQQ アクション | TQQQ 目標 | TQQQ 上限 | QQQ アクション | QQQ 目標 | QQQ 上限 |
|------|------|------|------|------|------|------|
| NORMAL | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base | HOLD_OR_FOLLOW_BASE_STRATEGY | 100% | base |
| CAUTION | AVOID_NEW_ADDS | 75% | 7% | AVOID_NEW_ADDS | 100% | 8% |
| HIGH | REDUCE_EXPOSURE | 50% | 5% | REDUCE_EXPOSURE | 75% | 6% |
| SEVERE | CLOSE_TQQQ_OR_HEDGE | 25% | 3% | REDUCE_EXPOSURE_OR_HEDGE | 50% | 5% |

### 出力ファイル

| ファイル | 説明 |
|------|-------------|
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json` | 完全な構造化レポート（UTF-8、`ensure_ascii=False`、機微情報リダクション済み） |
| `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.md` | active DD テーブル付きの人可読サマリ |
