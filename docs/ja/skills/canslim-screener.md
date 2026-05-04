---
layout: default
title: CANSLIM Screener
grand_parent: 日本語
parent: スキルガイド
nav_order: 2
lang_peer: /en/skills/canslim-screener/
permalink: /ja/skills/canslim-screener/
---

# CANSLIM Screener
{: .no_toc }

William O'NeilのCANSLIM手法で米国成長株を7コンポーネントスコアリングするスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/canslim-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/canslim-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

CANSLIM Screenerは、William O'Neilが著書「How to Make Money in Stocks」で体系化した成長株選定手法を実装したスキルです。過去数十年の歴史的大化け銘柄に共通する7つの特徴を定量的にスコアリングし、次のマルチバガー候補を識別します。

**Phase 3（現行バージョン）** では7コンポーネント全てを実装しており、CANSLIM手法の**100%カバレッジ**を達成しています。

### 7つのCANSLIMコンポーネント

| コンポーネント | 説明 | ウェイト |
|---------------|------|---------|
| **C** - Current Earnings | 四半期EPS/売上成長（前年同期比） | 15% |
| **A** - Annual Growth | 3年間のEPS CAGR（複合年間成長率） | 20% |
| **N** - Newness | 52週高値からの距離、ブレイクアウト検出 | 15% |
| **S** - Supply/Demand | 出来高ベースの蓄積/分配分析 | 15% |
| **L** - Leadership | マルチ期間 RS（3m/6m/12m vs 設定可能 benchmark、デフォルト ^GSPC） | 20% |
| **I** - Institutional | 機関投資家保有率、スーパーインベスター検出 | 10% |
| **M** - Market Direction | S&P 500 vs 50日EMAのトレンド判定 | 5% |

**解決する問題:**
- O'NeilのCANSLIM条件を手動でチェックする手間を自動化
- 主観を排除した定量的スコアリングで成長株を客観的に評価
- ベアマーケット保護（Mコンポーネント）により不適切なタイミングでの買いを防止

---

## 2. 前提条件

> FMP APIキーが必須です。無料ティア（250回/日）で35銘柄のスクリーニングが可能です。40銘柄フルスクリーニングにはStarterティア（$29.99/月）が推奨されます。
{: .api_required }

| 項目 | 要否 | 説明 |
|------|------|------|
| FMP APIキー | 必須 | 決算データ、株価、機関投資家データの取得 |
| Python 3.7+ | 必須 | スクリプト実行用 |
| `requests` | 必須 | FMP API通信 |
| `beautifulsoup4` | 必須 | Finviz機関投資家データのフォールバック取得 |
| `lxml` | 必須 | HTML解析 |

**インストール:**

```bash
pip install requests beautifulsoup4 lxml
```

**APIキー設定:**

```bash
export FMP_API_KEY=your_key_here
```

### APIコール予算

| 対象銘柄数 | FMPコール数 | 無料ティア対応 |
|-----------|------------|---------------|
| 35銘柄 | 約248回 | 対応（250回/日制限内） |
| 40銘柄 | 約283回 | 超過（Starterティア推奨） |

1銘柄あたり7回のFMP APIコール（profile, quote, income x2, historical_90d, historical_365d, institutional）に加え、マーケットデータ3回（S&P 500 quote, VIX quote, S&P 500 52週履歴）が必要です。

---

## 3. クイックスタート

### 最小限の実行

```bash
# デフォルト設定（S&P 500 トップ40銘柄、上位20件をレポート）
python3 skills/canslim-screener/scripts/screen_canslim.py
```

### カスタム設定

```bash
# 無料ティア向け（35銘柄、上位10件）
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --top 10 --output-dir reports/
```

### Claudeへの自然言語

```
CANSLIM手法で成長株をスクリーニングして。S&P 500のトップ銘柄を分析してほしい。
```

---

## 4. 仕組み

### 3ステージパイプライン

```
Stage 1: データ取得（FMP API + Finviz）
  ↓
Stage 2: 7コンポーネント計算
  ↓
Stage 3: 複合スコアリング・ランキング・レポート生成
```

**Stage 1: データ取得**
- FMP APIから決算データ（四半期・年次）、株価履歴、機関投資家データを取得
- FMPで `sharesOutstanding` が未取得の場合、Finvizから機関投資家保有率をフォールバック取得

**Stage 2: 7コンポーネント計算**

各コンポーネントは0-100のスコアで評価されます：

- **C (Current Earnings):** EPS YoY成長率50%以上=100点、30-49%=80点、18-29%=60点
- **A (Annual Growth):** 3年EPS CAGR 40%以上=90点、30-39%=70点、25-29%=50点
- **N (Newness):** 52週高値から5%以内+ブレイクアウト=100点
- **S (Supply/Demand):** 上昇日出来高/下落日出来高比率 2.0以上=100点
- **L (Leadership):** マルチ期間重み付け RS（0.40 × rel_3m + 0.30 × rel_6m + 0.30 × rel_12m）。RS 90以上=100点。デフォルト benchmark `^GSPC`、`--rs-benchmark` で SPY/QQQ/IWM 等に変更可。データ欠損時の fallback 階層: ①benchmark 欠落 → 重み付き絶対リターン + 20% ペナルティ。②全期間欠損だが 50+ bars あり → 365 日全データの絶対リターンに fallback（benchmark 欠落時はさらに 20% ペナルティ）。③50 bars 未満 → score=0（error 設定）。
- **I (Institutional):** 50-100機関+30-60%保有率=100点
- **M (Market Direction):** 強い上昇トレンド=100点、ベアマーケット=0点

**Stage 3: 複合スコアリング**

```
複合スコア = C×15% + A×20% + N×15% + S×15% + L×20% + I×10% + M×5%
```

### Finvizフォールバック

FMP APIで機関投資家データが不完全な場合、自動的にFinviz.comから保有率を取得します。これにより Iコンポーネントの精度が大幅に向上します（35点→60-100点）。

---

## 5. 使用例

### 例1: デフォルトS&P 500スクリーニング

**プロンプト:**
```
CANSLIM手法でS&P 500銘柄をスクリーニングして
```

**Claudeの動作:**
- デフォルトユニバース（S&P 500トップ40銘柄）を使用
- 全7コンポーネントを計算し複合スコアでランキング
- Markdown + JSONレポートを `reports/` に保存

**期待される出力:** 上位20銘柄のスコアと各コンポーネント詳細の一覧

---

### 例2: 半導体セクター特化

**プロンプト:**
```
半導体セクターの銘柄でCANSLIMスクリーニングをして。
NVDA, AVGO, AMD, INTC, QCOM, MRVL, TXN, AMAT, LRCX, KLAC を分析して。
```

**Claudeの動作:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --universe NVDA AVGO AMD INTC QCOM MRVL TXN AMAT LRCX KLAC \
  --output-dir reports/
```

**なぜ有用か:** 特定セクター内でCANSLIM基準を満たすリーダー銘柄を識別できます。

---

### 例3: 無料枠の最適化

**プロンプト:**
```
FMPの無料枠（250コール/日）に収まるようにCANSLIMスクリーニングしたい
```

**Claudeの動作:**
```bash
python3 skills/canslim-screener/scripts/screen_canslim.py \
  --max-candidates 35 --top 10 --output-dir reports/
```

**なぜ有用か:** 35銘柄×7コール+マーケットデータ3コール=248コールで、無料ティアの250回制限内に収まります。

---

### 例4: コンポーネント詳細の解読

**プロンプト:**
```
NVDAのCANSLIMスコアの各コンポーネントを詳しく解説して
```

**Claudeの動作:**
- レポートからNVDAのエントリを抽出し、各コンポーネントの意味と評価基準を解説
- 例: 「C=100は四半期EPS成長率50%超を意味し、AI需要の爆発的な成長を反映しています」

**なぜ有用か:** スコアの背景にある投資判断の根拠を理解できます。

---

### 例5: ベアマーケットシナリオ

**プロンプト:**
```
Mコンポーネントが0（ベアマーケット）のとき、CANSLIMスクリーニングはどう解釈すべき？
```

**Claudeの動作:**
- M=0の場合の明確な警告を出力
- O'Neilの教え: 「4銘柄中3銘柄は市場トレンドに従う」を引用
- 推奨: 80-100%のキャッシュポジション、買い推奨なし

**なぜ有用か:** ベアマーケットでの過大なリスクテイクを防止できます。

---

### 例6: スコア解釈とポジションサイジング

**プロンプト:**
```
CANSLIMスコアが85の銘柄と72の銘柄、それぞれどれくらいのポジションで買うべき？
```

**Claudeの動作:**
- レーティングバンドに基づく推奨を提示：
  - **Exceptional (80-89):** 強い買い推奨、ポートフォリオの10-15%
  - **Strong (70-79):** 買い推奨、ポートフォリオの8-12%
- 最も弱いコンポーネントのリスク要因も解説

**なぜ有用か:** スコアに応じた適切なポジションサイズの指針を得られます。

---

## 6. 出力の読み方

### レーティングバンド

| レーティング | スコア範囲 | 意味 | 推奨アクション |
|-------------|----------|------|---------------|
| **Exceptional+** | 90-100 | 全コンポーネント近完璧 | 即時買い、積極的サイジング（15-20%） |
| **Exceptional** | 80-89 | 優れたファンダメンタル + モメンタム | 強い買い、標準サイジング（10-15%） |
| **Strong** | 70-79 | 全コンポーネント堅実 | 買い、標準サイジング（8-12%） |
| **Above Average** | 60-69 | 最低基準クリア、一部弱み | プルバック買い、保守的サイジング（5-8%） |

### レポート構造

```
# CANSLIM Stock Screening Results
├── Market Condition Summary（市場環境サマリー）
├── Top N CANSLIM Candidates（上位銘柄一覧）
│   ├── 各銘柄のComposite Score & Rating
│   ├── Component Breakdown（C, A, N, S, L, I, M）
│   ├── Interpretation（解釈・推奨）
│   └── Warnings（品質警告）
└── Summary Statistics（レーティング分布）
```

### 注意すべき品質警告

| 警告メッセージ | 意味 |
|--------------|------|
| `Revenue declining despite EPS growth` | EPS成長が自社株買いに依存している可能性 |
| `Using Finviz institutional ownership` | FMPデータ不足でFinvizフォールバック使用（精度は問題なし） |
| `Bear market detected (M=0)` | 全銘柄の買い推奨を停止すべき |

---

## 7. Tips & ベストプラクティス

### 効果的なユニバース選定

- **デフォルト（S&P 500トップ40）** は安定した結果を得られますが、大型株に偏ります
- **セクター特化** で半導体やバイオテク等のハイグロースセクターに集中すると、より高スコアの候補が見つかりやすいです
- **カスタムユニバース** で他のスクリーナー（FinViz等）の出力を入力として使えます

### API予算の管理

- 1日に複数回実行する場合は `--max-candidates` を小さく設定
- 最初に少数銘柄でテスト実行し、結果を確認してからフルスクリーニング
- FMP無料ティアのリセットはUTC午前0時

### ベアマーケットでの使い方

- M=0の場合、スコアが高い銘柄でも**買わない**のがO'Neilの鉄則
- ウォッチリストとして保存し、市場回復後にエントリーを検討
- 市場回復の確認には FTD Detector スキルが有用

---

## 8. 他スキルとの連携

### CANSLIM → VCP Screener

CANSLIMで高スコアの銘柄群をVCP Screenerに渡し、ブレイクアウトタイミングを評価：

```
1. CANSLIM: 上位10銘柄を取得
2. VCP: --universe で銘柄を指定、VCPパターンの有無とピボットポイントを分析
```

### CANSLIM → Technical Analyst

CANSLIMスコア80以上の銘柄について、週足チャートのテクニカル分析を実施：

```
1. CANSLIM: Exceptional以上の銘柄を特定
2. Technical Analyst: チャートパターン、サポート/レジスタンス、エントリータイミングを評価
```

### FinViz → CANSLIM（プレスクリーニング）

FinVizで粗い絞り込みを行い、CANSLIM用のカスタムユニバースを構築：

```
1. FinViz: fa_epsqoq_o25,ta_sma200_pa で候補リスト取得
2. CANSLIM: --universe で渡して7コンポーネント詳細分析
```

### 決算モメンタムパイプライン

```
1. Earnings Trade Analyzer: 直近決算の反応をスコアリング
2. CANSLIM: 高グレード銘柄のファンダメンタル検証
3. PEAD Screener: プルバック→ブレイクアウトパターンを監視
```

---

## 9. トラブルシューティング

### FMP APIレートリミット

```
ERROR: 429 Too Many Requests - Rate limit exceeded
```

**対処:**
1. スクリプトは自動で60秒後にリトライ
2. `--max-candidates 35` で無料ティア内に収める
3. 毎日のリセットはUTC午前0時

### 依存パッケージ不足

```
ERROR: required libraries not found. Install with: pip install beautifulsoup4 requests lxml
```

**対処:**
```bash
pip install requests beautifulsoup4 lxml
```

### Finviz 403 エラー

```
WARNING: Finviz request failed with status 403 for NVDA
```

**対処:**
- 一時的なレートリミット。数分後に再試行
- スクリプトはFMPデータのみで継続（Iスコアは上限70/100に制限）
- Finviz障害時も完全に失敗することはなく、品質警告付きで結果を出力

### スコアが全体的に低い

**原因:** ベアマーケット（M=0）か、ユニバースに成長株が少ない

**対処:**
1. Mコンポーネントを確認 → 0ならベアマーケットで正常動作
2. グロースセクター（Technology, Healthcare）の銘柄でリトライ
3. CANSLIM手法はブルマーケットで最も効果を発揮

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/canslim-screener/scripts/screen_canslim.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--api-key` | FMP APIキー | `$FMP_API_KEY` 環境変数 |
| `--max-candidates` | 分析する最大銘柄数 | 40 |
| `--top` | レポートに含める上位件数 | 20 |
| `--output-dir` | レポート出力ディレクトリ | カレントディレクトリ |
| `--universe` | カスタム銘柄リスト（スペース区切り） | S&P 500トップ40 |
| `--rs-benchmark` | L コンポーネント用 RS ベンチマーク（SPY, QQQ, IWM 等）。M コンポーネントは EMA スケール一貫性のため `^GSPC` を継続使用。 | `^GSPC` |
| `--disable-rs` | L コンポーネント計算をスキップ（銘柄ごとの 365 日 fetch とカスタムベンチマーク fetch を節約）。L は中立 50 で固定。 | `false` |

### Phase 3.1 出力スキーマ

L コンポーネントの新規フィールド（既存フィールドはすべて後方互換維持）:

| フィールド | 説明 |
|------------|------|
| `rs_3m_return` / `rs_6m_return` / `rs_12m_return` | 銘柄の 63 / 126 / 252 取引日リターン (%) |
| `benchmark_3m_return` / `benchmark_6m_return` / `benchmark_12m_return` | ベンチマークの同期間リターン (%) |
| `rel_3m` / `rel_6m` / `rel_12m` | 銘柄 − ベンチマーク（期間別）。ベンチマーク欠落時は null |
| `weighted_stock_performance` | 重み付き絶対リターン（ベンチマーク欠落時の scoring 入力） |
| `weighted_relative_performance` | 重み付き相対リターン（ベンチマークありの scoring 入力） |
| `benchmark_52w_performance` | symbol 中立な後継フィールド（`sp500_52w_performance` の代替） |
| `rs_benchmark` | 使用したベンチマーク symbol |
| `rs_benchmark_relative_return` | `rel_12m`（252 bars）と同値。**注意**: legacy `relative_performance`（365 日全データ）とは別値 |
| `rs_rating` | `Market Leader` / `Strong` / `Above Average` / `Average` / `Laggard` / `Weak` |
| `rs_component_score` | `score` の alias（0-100） |
| `rs_rank_percentile` | 相対パフォーマンスの閾値ベースで推定した percentile。**screening 内 cross-sectional percentile ではない**点に注意 |

非推奨注記:

- `sp500_52w_performance` は後方互換のため維持。`--rs-benchmark` で `^GSPC` 以外を指定した場合、フィールド名と内容が乖離する（中身は当該ベンチマークの 52w return）。新規利用は `benchmark_52w_performance` を推奨。
- `relative_performance` は 365 日全データの相対 return で、`rs_benchmark_relative_return`（252 bars）や `weighted_relative_performance`（重み付き）とは別値。

### コンポーネントスコア基準

| コンポーネント | 100点 | 80点 | 60点 | 40点 | 0点 |
|---------------|-------|------|------|------|------|
| **C** | EPS≥50%, Rev≥25% | EPS≥30%, Rev≥15% | EPS≥18%, Rev≥10% | EPS≥10% | EPS<10% |
| **A** | CAGR≥40%, 安定 | - | CAGR≥30% | CAGR≥25% | CAGR<25% |
| **N** | 高値5%以内+BO | 高値5%以内 | 高値10%以内+BO | 高値10%以内 | 高値25%超 |
| **S** | Vol比≥2.0 | Vol比≥1.5 | Vol比≥1.0 | Vol比≥0.8 | Vol比<0.8 |
| **L** | RS≥90+outperf | RS≥80 | RS≥70 | RS≥60 | RS<60 |
| **I** | 50-100機関+30-60%保有 | 条件一部 | 条件一部 | 少数 | データなし |
| **M** | 強い上昇トレンド | 上昇トレンド | 横ばい | 弱い | ベアマーケット |

### 出力ファイル

| ファイル | 形式 | 用途 |
|----------|------|------|
| `canslim_screener_YYYY-MM-DD_HHMMSS.json` | JSON | プログラマティック利用 |
| `canslim_screener_YYYY-MM-DD_HHMMSS.md` | Markdown | 人間向けレポート |

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/canslim-screener/SKILL.md` | スキル定義 |
| `skills/canslim-screener/references/canslim_methodology.md` | CANSLIM手法の完全解説（27KB） |
| `skills/canslim-screener/references/scoring_system.md` | スコアリング仕様（21KB） |
| `skills/canslim-screener/references/interpretation_guide.md` | 結果解釈ガイド（18KB） |
| `skills/canslim-screener/references/fmp_api_endpoints.md` | API統合ガイド（18KB） |
| `skills/canslim-screener/scripts/screen_canslim.py` | メインスクリプト |
| `skills/canslim-screener/scripts/calculators/` | 各コンポーネント計算モジュール |
