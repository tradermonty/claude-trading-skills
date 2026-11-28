---
layout: default
title: "Parabolic Short Trade Planner"
grand_parent: 日本語
parent: スキルガイド
nav_order: 11
lang_peer: /en/skills/parabolic-short-trade-planner/
permalink: /ja/skills/parabolic-short-trade-planner/
---

# Parabolic Short Trade Planner
{: .no_toc }

米国株式の Parabolic exhaustion パターンを日次でスクリーニングし、条件付きの寄り前ショートプランを生成、さらにライブ 5 分足から当日のトリガー発火を評価するスキル。Phase 1 は日次 5 因子スコア（MA 乖離 / 加速度 / Volume Climax / レンジ拡張 / 流動性）、Phase 2 は候補ごとに ORL ブレイク / First Red 5min / VWAP fail の 3 トリガープランを borrow / SSR / 手動確認ゲート付きで出力、Phase 3 はワンショット FSM がライブで発火を検出し、具体的な株数まで解決する。Phase 1 + Phase 2 + Phase 3 をカバー。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/parabolic-short-trade-planner.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/parabolic-short-trade-planner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Qullamaggie 流の Parabolic Short ウォッチリストと、米国株向けの条件付き寄り前プランを生成するスキル。**注文は一切送信しない** — JSON + Markdown を出力し、トレーダーが自分のブローカー画面と照合してから手動でエントリーする設計。

3 つのフェーズで構成:

- **Phase 1 (`screen_parabolic.py`)**: FMP から EOD バー + 企業プロフィールを取得し、モード別の hard invalidation rule を適用。生き残った候補を 5 因子（重み 30/25/20/15/10）で採点し A/B/C/D グレードを付与。
- **Phase 2 (`generate_pre_market_plan.py`)**: Phase 1 の JSON を読み、`--tradable-min-grade`（既定 `B`）でフィルタ。Alpaca のショート在庫を確認（または `ManualBrokerAdapter` にフォールバック）し、引き継いだ前日終値から SEC Rule 201 (SSR) ステートを評価。候補ごとに 3 つのトリガープランをレンダリング。
- **Phase 3 (`monitor_intraday_trigger.py`)**: Phase 2 のプランを読み、5 分足を取得（Alpaca ライブまたは fixture）。各プランの FSM を 1 ステップ進め、プランごとの状態を保存。`state` / `entry_actual` / `stop_actual` / `shares_actual`（triggered 時）を含む `intraday_monitor` JSON を出力。**ワンショット** — トレーダーが `watch` または cron で 1〜5 分ごとに実行。リプレイ決定論的（同じ入力で再実行すると byte-identical な出力）。

---

## 2. 利用シーン

このスキルを呼び出すべきケース:

- S&P 500（または独自 CSV）から日次 Parabolic Short ウォッチリストを構築したいとき。
- ウォッチリストを borrow / SSR / state cap の明示的ゲート付きの寄り前プランに変換したいとき。
- Alpaca で発注する前に、候補の blocking / advisory な手動確認理由を監査したいとき。

呼び出さないケース:

- ロングサイドのモメンタムスクリーニング → `vcp-screener` または `canslim-screener` を使う。
- 1 分以下のサブミニッツ・シグナル → Phase 3 は 5 分足のみ評価。
- ライブ発注 → このスキルは設計上 detection-only。Phase 3 は具体的な entry / stop / 株数を含む `triggered` ステートを出力するが、発注はトレーダーが手動で行う。

---

## 3. 前提条件

- **FMP API キー** が必須（環境変数 `FMP_API_KEY`）。無料の FMP プランでは一部の銘柄の気配値や履歴のリクエストが拒否されます（HTTP 402/403）。その場合はプラン制限のエラーで停止し、有料プランが必要になることがあります（[FMP プラン]({{ '/ja/getting-started/' | relative_url }}#fmp-plans) を参照）
- FMP が Phase 1 用、Alpaca はオプション（`requests` 直叩き、SDK 不要）。Alpaca が無い場合、全候補は `plan_status: watch_only` に固定される
- **Alpaca API キー**（`ALPACA_API_KEY` + `ALPACA_SECRET_KEY`）は Phase 3 のライブデータで必須。paper account でも `data.alpaca.markets` は同一エンドポイント
- Python 3.9+ 推奨

---

## 4. クイックスタート

```bash
python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
```

---

## 5. ワークフロー

### Phase 1 — 日次スクリーナー

1. `FMP_API_KEY` が設定済みであることを確認（環境変数または `--api-key`）。
2. デフォルトの安全寄りモードで実行:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/screen_parabolic.py \
     --mode safe_largecap --as-of 2026-04-30 --output-dir reports/
   ```
3. `reports/parabolic_short_<date>.md` を確認 — ウォッチリストはグレード（A→D）でグループ化されている。
4. 興味のある銘柄を Phase 2 に進める。

スモールキャップの blow-off を狙う場合は `--mode classic_qm` に切り替える（市場 cap / ADV のフロアを緩め、5 日 ROC 閾値を上げる）。

API 無しでテストする場合は、`--dry-run --fixture <path>` で JSON fixture を使う（`scripts/tests/fixtures/dry_run_minimal.json` に同梱）。

### Phase 2 — 寄り前プラン生成器

1. 任意: ライブ borrow チェックのため `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` を設定。未設定の場合プランナーは `ManualBrokerAdapter` にフォールバックし、全候補を `borrow_inventory_unavailable` / `plan_status: watch_only` でマーク。
2. 実行:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py \
     --candidates-json reports/parabolic_short_2026-04-30.json \
     --account-size 100000 --risk-bps 50 --output-dir reports/
   ```
3. 出力: `reports/parabolic_short_plan_<date>.json`。各プランは 3 つのエントリープラン（5min ORL break、First Red 5-min、VWAP fail）を含み、`entry_hint` / `stop_hint` は数式文字列（株数は固定値ではなく、トレーダーが trigger 発火時に `shares_formula` から算出）。

### Phase 3 — 当日トリガーモニター

1. `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` が設定済みであることを確認（Phase 3 は Alpaca のマーケットデータを使用。`data.alpaca.markets` は paper / live どちらの口座でも動作）。
2. 米国 regular session 中にワンショット実行 — 寄付後 30 分は 60 秒ごと、その後は 5 分ごとが典型:
   ```bash
   python3 skills/parabolic-short-trade-planner/scripts/monitor_intraday_trigger.py \
     --plans-json reports/parabolic_short_plan_2026-05-05.json \
     --bars-source alpaca \
     --state-dir state/parabolic_short/ \
     --output-dir reports/
   ```
   `watch -n 60 'python3 ...'` または cron でラップする。
3. 出力: `reports/parabolic_short_intraday_<date>.json`。モニタ対象の各プランについて `state`（`armed` / `triggered` / `invalidated` / FSM 固有のサブステート）、bar 由来のトランジションタイムスタンプ、triggered 時には `size_recipe_resolved`（具体的な `shares_actual`）が記録される。
4. API 無しでテストする場合は `--bars-source fixture --bars-fixture <path>` で JSON fixture を使う（`scripts/tests/fixtures/intraday_bars/`）。

Phase 3 は **idempotent**: 各実行が寄付から `now_et`（または `--now-et` オーバーライド）までの全 session bars を replay するため、同じ分内の再実行は同じステートを生成する。`prior_state` は diff / 通知の表示用にのみ使用され、FSM を進めることは無い。

### エントリー前のプラン確認

ティッカーごとに 3 つのトップレベルフィールドを読む:

- `plan_status`: `actionable`（手動ゲートをクリア可能）または `watch_only`（hard blocker — borrow 不可または SSR active）。
- `blocking_manual_reasons`: トリガーを引く前にすべて解消する必要がある。
- `advisory_manual_reasons`: 注意喚起のみ。例: `manual_locate_required`（常にセット）、`warning:too_early_to_short`。

---

## 6. リソース

**References（参照ドキュメント）:**

- `skills/parabolic-short-trade-planner/references/broker_capability_matrix.md` — ブローカーごとのショート在庫 API 機能マトリクス
- `skills/parabolic-short-trade-planner/references/intraday_trigger_playbook.md` — 各トリガータイプの FSM 詳細、Phase 3 が実装するトランジション、same-bar tie-break セマンティクス
- `skills/parabolic-short-trade-planner/references/parabolic_short_methodology.md` — Qullamaggie の 3 トリガーフレームワークと exhaustion シグナル
- `skills/parabolic-short-trade-planner/references/short_invalidation_rules.md` — モード別の除外ルール
- `skills/parabolic-short-trade-planner/references/short_risk_management.md` — Rule 201、ETB vs HTB、locate
- `skills/parabolic-short-trade-planner/references/smoke_test_runbook.md` — ライブ API スモーク手順書（Phase 1/2/3 全カバー）
- `skills/parabolic-short-trade-planner/references/smoke_universe_diverse.csv` — 棄却スモーク用 CSV（10〜15 mega-cap defensives）
- `skills/parabolic-short-trade-planner/references/smoke_universe_relaxed.csv` — エンドツーエンドスモーク用 CSV（8〜10 ETB 候補 mega-cap）

**Scripts（スクリプト）:**

- `skills/parabolic-short-trade-planner/scripts/bar_normalizer.py`
- `skills/parabolic-short-trade-planner/scripts/broker_short_inventory_adapter.py`
- `skills/parabolic-short-trade-planner/scripts/check_live_apis.py`
- `skills/parabolic-short-trade-planner/scripts/fmp_client.py`
- `skills/parabolic-short-trade-planner/scripts/generate_pre_market_plan.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_size_resolver.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_state_machine.py`
- `skills/parabolic-short-trade-planner/scripts/intraday_state_store.py`
- `skills/parabolic-short-trade-planner/scripts/invalidation_rules.py`
- `skills/parabolic-short-trade-planner/scripts/manual_reasons.py`
- `skills/parabolic-short-trade-planner/scripts/market_clock.py`
- `skills/parabolic-short-trade-planner/scripts/math_helpers.py`
- `skills/parabolic-short-trade-planner/scripts/monitor_intraday_trigger.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_report_generator.py`
- `skills/parabolic-short-trade-planner/scripts/parabolic_scorer.py`
- `skills/parabolic-short-trade-planner/scripts/screen_parabolic.py`
- `skills/parabolic-short-trade-planner/scripts/size_recipe_builder.py`
- `skills/parabolic-short-trade-planner/scripts/ssr_state_tracker.py`
- `skills/parabolic-short-trade-planner/scripts/state_caps.py`
- `skills/parabolic-short-trade-planner/scripts/vwap.py`
