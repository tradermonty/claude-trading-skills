---
layout: default
title: "Dividend Growth Pullback Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 13
lang_peer: /en/skills/dividend-growth-pullback-screener/
permalink: /ja/skills/dividend-growth-pullback-screener/
---

# Dividend Growth Pullback Screener
{: .no_toc }

年間配当成長率12%以上、利回り1.5%以上の高品質な配当成長株のうち、RSIオーバーソールド（RSI≤40）による一時的な押し目を経験している銘柄を検索するスキルです。ファンダメンタルの配当分析とテクニカルのタイミング指標を組み合わせ、短期的な弱さの中にある強い配当成長銘柄の買い機会を特定します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">FINVIZ任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/dividend-growth-pullback-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/dividend-growth-pullback-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

強いファンダメンタル特性を持ちながらも一時的なテクニカルの弱さを示している配当成長株をスクリーニングするスキルです。卓越した配当成長率（CAGR 12%以上）を持ち、RSIオーバーソールドレベル（≤40）まで押し目をつけた銘柄をターゲットにし、長期配当成長投資家のエントリー機会を創出します。

**投資テーシス:** 高品質な配当成長株（利回りは通常1〜2.5%）は、高い現在利回りではなく配当の増加を通じて資産を複利的に成長させます。これらの銘柄を一時的な押し目（RSI≤40）で購入することにより、強いファンダメンタル成長と有利なテクニカルエントリータイミングを組み合わせてトータルリターンを向上させることができます。

---

## 2. 使用タイミング

以下の場合に使用します：
- 卓越した複利ポテンシャル（配当CAGR 12%以上）を持つ配当成長株を探している場合
- 一時的な市場の弱さの中で質の高い銘柄のエントリー機会を求めている場合
- より高い配当成長のために低い現在利回り（1.5〜3%）を受け入れられる場合
- 現在のインカムよりも5〜10年のトータルリターンに注目している場合
- 市場環境がセクターローテーションや広範な押し目で質の高い銘柄に影響している場合

**以下の場合には使用しないでください:**
- 高い現在インカムを求める場合（代わりに value-dividend-screener を使用）
- 3%超の即時配当利回りが必要な場合
- 厳格なP/EやP/B要件を持つディープバリュー銘柄を探す場合
- 6ヶ月未満の短期トレードにフォーカスする場合

---

## 3. 前提条件

- **FMP APIキー**が必要（`FMP_API_KEY` 環境変数）
- **FINVIZ Elite** は任意（パフォーマンス向上に有効）
- FMPは分析用、FINVIZはRSIプレスクリーニング用
- Python 3.9+ 推奨

---

## 4. クイックスタート

```bash
# RSIフィルター付き2段階スクリーニング（推奨）
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --use-finviz

# FMPのみのスクリーニング（APIリミットにより最大約40銘柄）
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --max-candidates 40

# カスタムRSI閾値と配当成長要件
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py \
  --use-finviz \
  --rsi-max 35 \
  --min-div-growth 15
```

---

## 5. ワークフロー

### ステップ1: APIキーの設定

#### 2段階アプローチ（推奨）

最適なパフォーマンスのために、FINVIZ Elite APIでプレスクリーニング + FMP APIで詳細分析を行います：

```bash
# 両方のAPIキーを環境変数として設定
export FMP_API_KEY=your_fmp_key_here
export FINVIZ_API_KEY=your_finviz_key_here
```

**なぜ2段階なのか？**
- **FINVIZ**: RSIフィルター付きの高速プレスクリーニング（1回のAPIコール→候補約10〜50銘柄）
- **FMP**: プレスクリーニング済み候補のみの詳細ファンダメンタル分析
- **結果**: より少ないFMP APIコールでより多くの銘柄を分析（無料枠内に収まる）

#### FMPのみのアプローチ（従来の方法）

FINVIZ Eliteのアクセスがない場合：

```bash
export FMP_API_KEY=your_key_here
```

**制限**: FMP無料枠（250リクエスト/日）では分析が約40銘柄に限定されます。`--max-candidates 40` を使用してリミット内に収めてください。

### ステップ2: スクリーニングの実行

**2段階スクリーニング（推奨）:**

```bash
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --use-finviz
```

以下を実行します：
1. FINVIZプレスクリーン: 配当利回り0.5〜3%、配当成長10%+、EPS成長5%+、売上成長5%+、RSI<40
2. FMP詳細分析: 12%+配当CAGRの検証、正確なRSI計算、ファンダメンタル分析

**FMPのみのスクリーニング:**

```bash
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --max-candidates 40
```

**カスタマイズ:**

```bash
# 2段階スクリーニングの条件を変更
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35

# FMPのみで取得件数と条件を変更
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --min-yield 2.0 --min-div-growth 10.0 --max-candidates 30

# 環境変数の代わりにAPIキーを引数で指定
python3 skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY
```

### ステップ3: 結果のレビュー

スクリプトは2つの出力を生成します：

1. **JSONファイル:** `dividend_growth_pullback_results_YYYY-MM-DD.json`
   - さらなる分析のためのすべてのメトリクスを含む構造化データ
   - 配当成長率、RSI値、財務健全性メトリクスを含む

2. **マークダウンレポート:** `dividend_growth_pullback_screening_YYYY-MM-DD.md`
   - 銘柄プロファイルを含む人間可読な分析
   - シナリオベースの確率評価
   - エントリータイミングの推奨

### ステップ4: 適格銘柄の分析

各適格銘柄について、レポートには以下が含まれます：

**配当成長プロファイル:**
- 現在の利回りと年間配当
- 3年配当CAGRと一貫性
- 配当性向と持続性評価：FCF状態・カバー状況・判定基準・銘柄ごとの説明を出力します。
- 非REITは利益ベースの配当性向80%未満、かつ報告されたFCFが支払配当を上回る場合のみ持続性を確認します。負・ゼロ・不足・欠損・無効FCFでは確認しません。metricsの代替配当性向は表示専用です。
- 明示的なREITフラグまたはREIT業種のみ、簡易FFO配当性向80%未満を使用します。不動産セクターだけではREITと判定しません。簡易FFOは純利益と減価償却の両方が必要で、不動産売却損益の調整を含みません。REITのFCF状態は参考情報です。
- 判定には丸め前の値を使用します。カバー不足は将来の減配を断定するものではありません。

**テクニカルタイミング:**
- 現在のRSI値（≤40 = オーバーソールド）
- RSIコンテキスト（極端なオーバーソールド<30 vs 初期押し目 30-40）
- 直近トレンドに対する価格アクション

**クオリティメトリクス:**
- 売上・EPS成長（事業のモメンタム確認）
- 財務健全性（債務水準、流動性比率）
- 収益性（ROE、利益率）

**投資推奨:**
- エントリータイミング評価（即時 vs 確認待ち）
- 銘柄固有のリスク要因
- 配当成長の複利効果に基づくアップサイドシナリオ

---

## 6. リソース

**リファレンス:**

- `skills/dividend-growth-pullback-screener/references/dividend_growth_compounding.md`
- `skills/dividend-growth-pullback-screener/references/fmp_api_guide.md`
- `skills/dividend-growth-pullback-screener/references/rsi_oversold_strategy.md`

**スクリプト:**

- `skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py`
