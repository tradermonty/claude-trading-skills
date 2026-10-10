---
layout: default
title: "Value Dividend Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 44
lang_peer: /en/skills/value-dividend-screener/
permalink: /ja/skills/value-dividend-screener/
---

# Value Dividend Screener
{: .no_toc }

バリュー特性（PER 20倍以下、PBR 2倍以下）、魅力的な利回り（3%以上）、安定した成長（配当/売上/EPSが3年間上昇トレンド）を組み合わせて、高品質な配当銘柄をスクリーニングするスキルです。FINVIZ Elite APIによる効率的なプレフィルタリングとFMP APIによる詳細分析の2段階スクリーニングに対応。配当株スクリーニング、インカムポートフォリオのアイデア、ファンダメンタルズの優れたバリュー銘柄の検索時に使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/value-dividend-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/value-dividend-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

**2段階スクリーニングアプローチ** で、バリュー特性、魅力的なインカム、安定した成長を兼ね備えた高品質配当銘柄を特定するスキルです：

1. **FINVIZ Elite API（任意だが推奨）**: 基本条件でのプレスクリーニング（高速・低コスト）
2. **Financial Modeling Prep (FMP) API**: 候補銘柄の詳細ファンダメンタル分析

バリュエーション比率、配当指標、財務健全性、収益性などの定量基準に基づいて米国株をスクリーニングし、複合品質スコアによるランキングと詳細なファンダメンタル分析を含む包括的なレポートを生成します。

**効率面のメリット**: FINVIZプレスクリーニングによりFMP API呼び出しを90%削減でき、無料ティアのAPIユーザーに最適です。

---

## 2. 使用タイミング

以下のリクエストがあった場合にこのスキルを使用してください：
- 「高品質な配当銘柄を探して」
- 「バリュー配当銘柄のスクリーニングを実行」
- 「配当成長率の高い銘柄を見せて」
- 「適正なバリュエーションのインカム銘柄を探して」
- 「持続可能な高利回り銘柄をスクリーニング」
- 配当利回り、バリュエーション指標、ファンダメンタル分析を組み合わせたリクエスト全般

---

## 3. 前提条件

- **FMP APIキー** 必須（`FMP_API_KEY` 環境変数）
- **FINVIZ Elite** 任意（パフォーマンス向上）
- FMPは分析用、FINVIZにより実行時間を70-80%短縮
- Python 3.9+ 推奨

---

## 4. クイックスタート

```bash
# 2段階スクリーニング（推奨 - 70-80%高速）
python3 value-dividend-screener/scripts/screen_dividend_stocks.py --use-finviz

# FMPのみスクリーニング（FINVIZ不要）
python3 value-dividend-screener/scripts/screen_dividend_stocks.py

# カスタムパラメータ
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --top 50 \
  --output custom_results.json
```

---

## 5. ワークフロー

### ステップ1: APIキーの確認

**2段階スクリーニング（推奨）の場合：**

両方のAPIキーが利用可能か確認：

```python
import os
fmp_api_key = os.environ.get('FMP_API_KEY')
finviz_api_key = os.environ.get('FINVIZ_API_KEY')
```

利用できない場合は、APIキーの提供または環境変数の設定を案内：
```bash
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**FMPのみスクリーニングの場合：**

FMP APIキーが利用可能か確認：

```python
import os
api_key = os.environ.get('FMP_API_KEY')
```

利用できない場合は、APIキーの提供または環境変数の設定を案内：
```bash
export FMP_API_KEY=your_key_here
```

**FINVIZ Elite APIキー：**
- FINVIZ Eliteサブスクリプションが必要（月額約$40または年額約$330）
- プレスクリーニング結果のCSVエクスポートへのアクセスを提供
- FMP API使用量の削減に強く推奨

必要に応じて `references/fmp_api_guide.md` の手順を案内。

### ステップ2: スクリーニングスクリプトの実行

適切なパラメータでスクリーニングスクリプトを実行：

#### **2段階スクリーニング（推奨）**

FINVIZでプレスクリーニング、FMPで詳細分析：

**デフォルト実行（上位20銘柄）：**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz
```

**明示的なAPIキー指定：**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz \
  --fmp-api-key $FMP_API_KEY \
  --finviz-api-key $FINVIZ_API_KEY
```

**カスタム上位N件：**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --top 50
```

**カスタム出力先：**
```bash
python3 scripts/screen_dividend_stocks.py --use-finviz --output /path/to/results.json
```

**スクリプトの動作（2段階）：**
1. FINVIZ Eliteプレスクリーニング：
   - 時価総額: ミッドキャップ以上
   - 配当利回り: 3%以上
   - 配当成長率（3年）: 5%以上
   - EPS成長率（3年）: プラス
   - PBR: 2倍以下
   - PER: 20倍以下
   - 売上成長率（3年）: プラス
   - 地域: 米国
2. FINVIZ結果のFMP詳細分析（通常20-50銘柄）：
   - 配当成長率の計算（3年CAGR）
   - 売上・EPSトレンド分析
   - 配当持続可能性評価（配当性向、FCFカバレッジ）
   - 財務健全性指標（負債比率、流動比率）
   - 品質スコアリング（ROE、利益率）
3. 複合スコアリングとランキング
4. 上位N銘柄をJSONファイルに出力

**想定実行時間（2段階）：** 30-50のFINVIZ候補に対して2-3分（FMPのみより大幅に高速）

#### **FMPのみスクリーニング（従来方式）**

FMP Stock Screener APIのみを使用（API使用量が多い）：

**デフォルト実行：**
```bash
python3 scripts/screen_dividend_stocks.py
```

**明示的なAPIキー指定：**
```bash
python3 scripts/screen_dividend_stocks.py --fmp-api-key $FMP_API_KEY
```

**スクリプトの動作（FMPのみ）：**
1. FMP Stock Screener APIで初期スクリーニング（配当利回り>=3.0%、PER<=20、PBR<=2）
2. 候補の詳細分析（通常100-300銘柄）：
   - 2段階アプローチと同じ詳細分析
3. 複合スコアリングとランキング
4. 上位N銘柄をJSONファイルに出力

**想定実行時間（FMPのみ）：** 100-300候補に対して5-15分（レート制限あり）

**API使用量比較：**
- 2段階: FMP API呼び出し約50-100回（FINVIZが約30銘柄にプレフィルタ）
- FMPのみ: FMP API呼び出し約500-1500回（全スクリーナー結果を分析）

### ステップ3: 結果のパースと分析

生成されたJSONファイルを読み込み：

```python
import json

with open('dividend_screener_results.json', 'r') as f:
    data = json.load(f)

metadata = data['metadata']
stocks = data['stocks']
```

**銘柄ごとの主要データ：**
- 基本情報: `symbol`, `company_name`, `sector`, `market_cap`, `price`
- バリュエーション: `dividend_yield`, `pe_ratio`, `pb_ratio`
- 成長指標: `dividend_cagr_3y`, `revenue_cagr_3y`, `eps_cagr_3y`
- 持続可能性: `payout_ratio`, `fcf_payout_ratio`, `fcf_amount`, `fcf_status`, `fcf_coverage_status`, `sustainability_basis`, `dividend_sustainable`, `sustainability_bonus`, `sustainability_note`
- 財務健全性: `debt_to_equity`, `current_ratio`, `financially_healthy`
- 品質: `roe`, `profit_margin`, `quality_score`
- 総合ランキング: `composite_score`

非REITの持続可能性10点は、利益に対する配当性向が80%未満で、観測されたFCFが配当額を厳密に上回る場合だけ付与します。`fcf_status` はFCFの正・ゼロ・負・欠損を区別し、`fcf_coverage_status` は正のFCFの不足、余裕のない同額カバー（`AT_LIMIT`）、配当データ欠損、配当ゼロも区別します。FCFの赤字やゼロは観測された不足を示しますが、将来の減配を断定するものではありません。確認できたREITでは `sustainability_basis: FFO` を判定基準とし、FCFの状態は参考情報として残します。人向けレポートにも両状態と `sustainability_note` を記載してください。

### ステップ4: Markdownレポートの生成

以下のセクションを含む構造化されたMarkdownレポートを作成：

#### レポート構成

```markdown
# Value Dividend Stock Screening Report

**Generated:** [タイムスタンプ]
**Screening Criteria:**
- Dividend Yield: >= 3.5%
- P/E Ratio: <= 20
- P/B Ratio: <= 2
- Dividend Growth (3Y CAGR): >= 5%
- Revenue Trend: Positive over 3 years
- EPS Trend: Positive over 3 years

**Total Results:** [N] stocks
```

---

## 6. リソース

**リファレンス：**

- `skills/value-dividend-screener/references/fmp_api_guide.md`
- `skills/value-dividend-screener/references/screening_methodology.md`

**スクリプト：**

- `skills/value-dividend-screener/scripts/screen_dividend_stocks.py`
