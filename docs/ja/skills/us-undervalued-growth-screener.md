---
layout: default
title: "US Undervalued Growth Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 72
lang_peer: /en/skills/us-undervalued-growth-screener/
permalink: /ja/skills/us-undervalued-growth-screener/
generated: false
---

# US Undervalued Growth Screener
{: .no_toc }

フォワード同一基準バリュエーション、ドライバー起点のEPS／FCF予測、一次情報による財務検証、SBCと希薄化の管理、セクター・景気循環の正規化、監査可能な候補プールカバレッジ、fail-closed最終報告を用い、NYSE・Nasdaq・NYSE Americanの事業会社株から割安成長／GARP機会を自律スクリーニングします。ティッカーリストやパラメータのない最小限の依頼を含め、米割安成長株の発掘・スクリーニング・ランク付け・更新を求められたときに使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/us-undervalued-growth-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/us-undervalued-growth-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

最小限の依頼から米割安成長／GARPスクリーンをエンドツーエンドで実行します。マルチプル拡張を仮定**せず**に、1株あたりEPSまたはFCFの複利成長だけで2〜3年の魅力的なリターンを支えられる企業を探します。会計基準、予測構築、SBC、希薄化、レバレッジ、景気循環性、コーポレートアクション、ピア比較、ソース鮮度、エビデンス品質を管理します。

**Claude Codeが推奨実行環境です。** Claude Codeではローカルdirect-FMPパイプラインを1回実行します。Pythonプロセスが一括取得、永続キャッシュ、FY1正規化、流動性計算、4レーン発掘、確定的ブロードスクリーンを実行し、生FMPペイロードはディスク上に保持してモデルコンテキストから外します。Claudeはコンパクトな実行サマリーと選定候補パケットのみ読み、SEC／IR引受と既存の厳格評価シーケンスを完了させます。

**「このスキルで割安成長株をスクリーニングして」といった依頼は完結形として扱います。** デフォルト解決、最新データ収集、実行可能な取得パス選択、チェックポイント、取得可能なブロッカーの修復を行い、同一タスク内で完成結果を返します。ユーザーが明示的に範囲を狭めない限り、ティッカーリスト、APIプラン詳細、出力パス、別途「続けて」の指示を求めません。

---

## 2. 使用タイミング

このスキルを使用するのは以下の場合です。

- 米上場の割安成長株またはGARP株の発掘・ランク付け。
- NYSE・Nasdaq・NYSE Americanの事業会社普通株のスクリーニング。
- EPSまたは1株あたりFCF成長だけで2〜3年に約30%〜50%の上昇余地を支えられるかの検証。
- 決算、ガイダンス、開示、コーポレートアクション、予想改訂後の prior スクリーンの更新。
- フォワードバリュエーション、成長持続性、ROIC、標準FCF、SBC、希薄化、ピア、景気循環リスク、セクター固有KPIでの候補比較。

以下には使用しません。

- 銘柄選定後の汎用単一ティッカーレポート。`us-stock-analysis` を使用します。
- 純粋な配当、モメンタム、テクニカルパターン、プレレベニュー・バイオ、M&Aアービトラージのスクリーニング。
- 自動発注。

---

## 3. 前提条件

- Python 3.9以降。
- 生成direct-FMPクライアント用の `requests`。確定的評価・監査スクリプトはそれ以外標準ライブラリのみ。
- Claude Codeダイレクトモード用の環境変数 `FMP_API_KEY`。キーをコミット・出力しません。
- 選定企業の underwriting 用に最新SEC・企業IR・マクロソースへアクセス可能。
- 書き込み可能な `reports/` と `.cache/` ディレクトリ。
- 特定の有料FMPプランを仮定しません。一括エンドポイント失敗は範囲限定の銘柄別エンリッチにフォールバックし、診断情報に開示します。

---

## 4. クイックスタート

```bash
Never copy values, URLs, dates, source IDs, or tickers from synthetic example assets into a live run.

### Step 2 — Build, normalize, and audit the candidate pool

Keep the original user-requested scope in the run contract. If bulk economics are unavailable, build a bounded discovery pool from the fully audited listing universe without narrowing the requested market-cap range. Every listing row used for pool generation must carry validated provider-average or 20+ trading-day liquidity evidence.

When provider screening is available, save one JSONL per lane and combine them deterministically:
```

---

## 5. 仕組み

### ステップ1 — Claude Codeでダイレクト発掘を実行

Claude Codeでは上記のダイレクトランナーから開始します。実行ディレクトリ、上場・候補プール監査、コンパクト候補パケット、`run-summary.json`、`NEXT_ACTION.json` を作成します。ユーザー確認を求めず `NEXT_ACTION.json` に従います。以下の手動コマンドはダイレクトHTTPコードを実行できないホスト用のフォールバックです。

### ステップ1B — 手動ホストのフォールバック: 実行ディレクトリとライブコンテキストを作成

```text
reports/us-undervalued-growth-screener/<run-id>/
├── market-context.json
├── global-sources.json
├── universe.jsonl
├── discovery/
├── broad-screen/
├── run/
└── final/
```

合成サンプル資産の値、URL、日付、ソースID、ティッカーをライブ実行にコピーしません。

### ステップ2 — 候補プールを構築・正規化・監査

実行コントラクトに元のユーザー要求スコープを保持します。一括ファンダメンタルズが利用不可の場合、要求時価総額レンジを狭めず、完全監査済み上場ユニバースから範囲限定の発掘プールを構築します。プール生成に使う上場行はすべて、検証済みプロバイダー平均または20営業日以上の流動性エビデンスを持つ必要があります。

プロバイダースクリーニングが利用可能な場合、レーンごとにJSONLを1件保存し確定的に結合します。

```bash
python3 skills/us-undervalued-growth-screener/scripts/build_provider_prefilter_pool.py \
  --universe reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --lane core_garp=reports/us-undervalued-growth-screener/<run-id>/provider/core.jsonl \
  --lane high_growth_exception=reports/us-undervalued-growth-screener/<run-id>/provider/high-growth.jsonl \
  --lane quality_near_miss=reports/us-undervalued-growth-screener/<run-id>/provider/near-miss.jsonl \
  --lane cyclical_normalization=reports/us-undervalued-growth-screener/<run-id>/provider/cyclical.jsonl \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/provider \
  --analysis-as-of <ISO-8601> \
  --source-id <provider-source-id> \
  --per-lane 15 --max-pool 60 --minimum-pool 30
```

出力 `provider-prefilter-audit.json` を `--discovery-audit` に、`provider-prefilter-pool.jsonl` を候補プールに使用します。

```bash
python3 skills/us-undervalued-growth-screener/scripts/build_discovery_pool.py \
  --input reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/discovery \
  --source-id <listing-source-id> \
  --min-market-cap 500000000 \
  --max-market-cap 20000000000 \
  --user-requested-min-market-cap 500000000 \
  --user-requested-max-market-cap 20000000000 \
  --max-pool 120 \
  --per-cell 3
```

ブロードスクリーン前に日付付き年次コンセンサス行を正規化します。`--estimate-as-of` は必須です。解決するNTM／FY1行を持たない企業は、生の外年データを診断専用に保持し `unavailable` になるかエンリッチに残ります。最新のフォワードP/Eは付与できません。

```bash
python3 skills/us-undervalued-growth-screener/scripts/normalize_estimates.py \
  --estimates reports/us-undervalued-growth-screener/<run-id>/discovery/raw-annual-estimates.jsonl \
  --listing-input reports/us-undervalued-growth-screener/<run-id>/discovery/discovery-pool.jsonl \
  --analysis-as-of <ISO-8601> \
  --estimate-as-of <ISO-8601> \
  --source-id <estimate-source-id> \
  --output reports/us-undervalued-growth-screener/<run-id>/discovery/enriched-candidate-pool.jsonl
```

正規化済み予想行を範囲限定プールにマージし `screen_universe.py` を実行します。明示的な取得範囲と上場列挙証跡を指定し、生成監査を `--discovery-audit` で通します。

```bash
python3 skills/us-undervalued-growth-screener/scripts/screen_universe.py \
  --input reports/us-undervalued-growth-screener/<run-id>/universe.jsonl \
  --candidate-pool reports/us-undervalued-growth-screener/<run-id>/discovery/enriched-candidate-pool.jsonl \
  --discovery-audit reports/us-undervalued-growth-screener/<run-id>/discovery/discovery-audit.json \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/broad-screen \
  --analysis-as-of <ISO-8601> \
  --source-id <listing-source-id> \
  --candidate-source-id <estimate-source-id> \
  --candidate-generation-mode liquidity_stratified_estimates \
  --retrieval-min-market-cap 500000000 \
  --retrieval-max-market-cap 20000000000 \
  --user-requested-min-market-cap 500000000 \
  --user-requested-max-market-cap 20000000000 \
  --provider-reported-total <count> \
  --pages-fetched <count> \
  --pagination-exhausted \
  --config skills/us-undervalued-growth-screener/assets/screening-config.example.json \
  --max-deep-dives 5
```

コマンドが終了コード `2` で終わった場合 `enrichment-queue.json` と `broad-screen-audit.json` を調べ、同一タスク内でエンリッチを継続して再実行します。すべての行が解決し、生成監査が範囲限定スコープを証明した後にのみ `--candidate-pool-exhausted` を渡します。

### ステップ3 — 実行をチェックポイント

スクリーニング監査を初期化して紐付けます。

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py init \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --analysis-as-of <ISO-8601> \
  --price-as-of <ISO-8601> \
  --session regular_close \
  --price-source-id <source-id> \
  --market-context reports/us-undervalued-growth-screener/<run-id>/market-context.json \
  --global-sources reports/us-undervalued-growth-screener/<run-id>/global-sources.json \
  --base-commit <git-sha>

python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py set-screening-audit \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --audit reports/us-undervalued-growth-screener/<run-id>/broad-screen/broad-screen-audit.json \
  --universe-artifact reports/us-undervalued-growth-screener/<run-id>/broad-screen/universe-audit-results.jsonl \
  --candidate-artifact reports/us-undervalued-growth-screener/<run-id>/broad-screen/broad-screen-results.jsonl
```

### ステップ4 — 選定ディープダイブを完了

選定シンボルごとに以下を行います。

1. 先にコーポレートアクションのプレフライトを実施。
2. 最新四半期と通年を別々に検証。
3. 標準FCFとTTMエビデンスを構築。
4. キャッシュ分類を正規化。
5. 同一基準の現行／2年前／3年前バリュエーション期間を構築。
6. 独立した予測ブリッジを構築。
7. 調整後指標をGAAPに照合。
8. ROIC、EBITDA、SBC、希薄化、ピア、セクター／景気循環エビデンスを収集。
9. 最終候補ステータスが `review_required`、`screened_out`、`excluded` になる場合でも候補を `verified` として保存。

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py save-candidate \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --candidate reports/us-undervalued-growth-screener/<run-id>/candidates/<SYMBOL>.json \
  --stage verified
```

### ステップ5 — 完了と組み立て

```bash
python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py set-status \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  complete

python3 skills/us-undervalued-growth-screener/scripts/manage_run_state.py assemble \
  --run-dir reports/us-undervalued-growth-screener/<run-id>/run \
  --output reports/us-undervalued-growth-screener/<run-id>/final/final-snapshot.json
```

### ステップ6 — 厳格評価と修復ループ

```bash
python3 skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py \
  --input reports/us-undervalued-growth-screener/<run-id>/final/final-snapshot.json \
  --artifact-root reports/us-undervalued-growth-screener/<run-id> \
  --output-dir reports/us-undervalued-growth-screener/<run-id>/final \
  --language ja \
  --strict \
  --require-final
```

終了コード `0` かつ出力に以下を含む場合のみ正式結果として提示します。

```text
contract.valid = true
ranking_status = final
unprocessed_candidates = []
runtime.contract_revision = 3.5
```

### ステップ7 — 公開前監査と自己完結バンドル

生成された最終JSONとMarkdownを特定し、以下を実行します。

```bash
python3 skills/us-undervalued-growth-screener/scripts/prepublish_audit.py \
  --report-json reports/us-undervalued-growth-screener/<run-id>/final/<report>.json \
  --report-md reports/us-undervalued-growth-screener/<run-id>/final/<report>.md \
  --artifact-root reports/us-undervalued-growth-screener/<run-id> \
  --output reports/us-undervalued-growth-screener/<run-id>/final/prepublish-audit.json

python3 skills/us-undervalued-growth-screener/scripts/bundle_run_artifacts.py \
  --run-dir reports/us-undervalued-growth-screener/<run-id> \
  --report-json reports/us-undervalued-growth-screener/<run-id>/final/<report>.json \
  --report-md reports/us-undervalued-growth-screener/<run-id>/final/<report>.md \
  --output reports/us-undervalued-growth-screener/<run-id>/final/us-undervalued-growth-screen-<date>.zip
```

両コマンドとも終了コード `0` が必須です。自己完結ZIPをレポートとともに提示します。

---

## 6. リファレンス

**リファレンス:**

- `skills/us-undervalued-growth-screener/references/autonomous-execution.md`
- `skills/us-undervalued-growth-screener/references/checkpointing.md`
- `skills/us-undervalued-growth-screener/references/claude-code-execution.md`
- `skills/us-undervalued-growth-screener/references/data-contract.md`
- `skills/us-undervalued-growth-screener/references/full-universe-snapshot.md`
- `skills/us-undervalued-growth-screener/references/methodology-ja.md`
- `skills/us-undervalued-growth-screener/references/methodology.md`
- `skills/us-undervalued-growth-screener/references/migration-v1-to-v2.md`
- `skills/us-undervalued-growth-screener/references/migration-v2-to-v3.md`
- `skills/us-undervalued-growth-screener/references/migration-v3-to-v3.1.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.1-to-v3.2.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.2-to-v3.3.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.3-to-v3.4.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.4-to-v3.5.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.5-to-v3.6.md`
- `skills/us-undervalued-growth-screener/references/migration-v3.6-to-v3.6.1.md`
- `skills/us-undervalued-growth-screener/references/original-prompt-mapping.md`
- `skills/us-undervalued-growth-screener/references/output-template.md`
- `skills/us-undervalued-growth-screener/references/research-checklist.md`
- `skills/us-undervalued-growth-screener/references/review-regression-matrix.md`
- `skills/us-undervalued-growth-screener/references/scoring-rubric.md`
- `skills/us-undervalued-growth-screener/references/sector-kpis.md`

**スクリプト:**

- `skills/us-undervalued-growth-screener/scripts/build_discovery_pool.py`
- `skills/us-undervalued-growth-screener/scripts/build_provider_prefilter_pool.py`
- `skills/us-undervalued-growth-screener/scripts/bundle_run_artifacts.py`
- `skills/us-undervalued-growth-screener/scripts/coverage_semantics.py`
- `skills/us-undervalued-growth-screener/scripts/estimate_snapshot.py`
- `skills/us-undervalued-growth-screener/scripts/evaluate_candidates.py`
- `skills/us-undervalued-growth-screener/scripts/fmp_client.py`
- `skills/us-undervalued-growth-screener/scripts/manage_run_state.py`
- `skills/us-undervalued-growth-screener/scripts/normalize_estimates.py`
- `skills/us-undervalued-growth-screener/scripts/prepublish_audit.py`
- `skills/us-undervalued-growth-screener/scripts/research_contract.py`
- `skills/us-undervalued-growth-screener/scripts/run_pipeline.py`
- `skills/us-undervalued-growth-screener/scripts/screen_universe.py`
- `skills/us-undervalued-growth-screener/scripts/screening_semantics.py`
- `skills/us-undervalued-growth-screener/scripts/skill_version.py`
