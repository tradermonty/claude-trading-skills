---
layout: default
title: "PEAD Screener"
grand_parent: 日本語
parent: スキルガイド
nav_order: 34
lang_peer: /en/skills/pead-screener/
permalink: /ja/skills/pead-screener/
---

# PEAD Screener
{: .no_toc }

## 価格バーの欠損

使用するOHLCV値が欠損・非有限・不正な候補は評価不能としてランキングから除外します。
JSONの `metadata.price_bar_gap_exclusions` とMarkdownに銘柄と該当バーの日付を記録します。
決算ギャップの端点、週足集計（取引水準に使う赤いローソク足の高値・安値を含む）、
直近20本の流動性データを検証します。バーの削除やゼロ補完は行いません。
出来高ゼロは有効です。正常な候補のスコアとレポート形式は変わりません。
決算週が存在する場合、決算前のOHLCは使用しません。決算前の出来高は、陰線の周辺週平均、
ブレイクアウトの過去4週平均、または直近20営業日の流動性計算で使用する場合のみ検証します。

決算後ギャップアップ銘柄をPEAD（Post-Earnings Announcement Drift：決算後アナウンスメントドリフト）パターンでスクリーニングします。週足チャートの形成を分析し、陰線プルバックとブレイクアウトシグナルを検出します。2つの入力モードをサポート — FMP決算カレンダー（モードA）またはearnings-trade-analyzerのJSON出力（モードB）。PEADスクリーニング、決算後ドリフト、決算ギャップのフォロースルー、陰線ブレイクアウトパターン、または週足決算モメンタムセットアップについて聞かれた際に使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/pead-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/pead-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

決算後アナウンスメントドリフト（PEAD）パターンを検出するスクリーナーです。

---

## 2. 使用タイミング

- PEADスクリーニングや決算後ドリフト分析を求められた場合
- 決算ギャップアップ銘柄でフォロースルーの可能性がある銘柄を見つけたい場合
- 決算後の陰線ブレイクアウトパターンを求められた場合
- 週足の決算モメンタムセットアップを求められた場合
- earnings-trade-analyzerのJSON出力をさらにスクリーニングしたい場合

---

## 3. 前提条件

- FMP APIキー（環境変数 `FMP_API_KEY` を設定するか `--api-key` を渡す）
- 無料枠（250コール/日）でデフォルトスクリーニングに十分
- モードBの場合: schema_version "1.0" のearnings-trade-analyzer JSON出力ファイル

---

## 4. クイックスタート

```bash
# モードA: FMP決算カレンダー（スタンドアロン）
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --min-gap 3.0 --max-api-calls 200 \
  --output-dir reports/

# モードB: earnings-trade-analyzerの出力からパイプライン
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_*.json \
  --min-grade B --output-dir reports/
```

---

## 5. ワークフロー

### ステップ1: スクリーニングの準備と実行

PEADスクリーナースクリプトを2つのモードのいずれかで実行:

**モードA（FMP決算カレンダー）:**
```bash
# デフォルト: 過去14日間の決算、5週間のモニタリングウィンドウ
python3 skills/pead-screener/scripts/screen_pead.py --output-dir reports/

# カスタムパラメータ
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 21 \
  --watch-weeks 6 \
  --min-gap 5.0 \
  --min-market-cap 1000000000 \
  --output-dir reports/
```

**モードB（earnings-trade-analyzer JSON入力）:**
```bash
# earnings-trade-analyzerの出力から
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B \
  --output-dir reports/
```

### ステップ2: 結果のレビュー

1. 生成されたJSONとMarkdownレポートを確認
2. PEADの理論とパターンのコンテキストとして `references/pead_strategy.md` を読み込む
3. トレード管理ルールとして `references/entry_exit_rules.md` を読み込む

### ステップ3: 分析の提示

各候補について以下を提示:
- ステージ分類（MONITORING, SIGNAL_READY, BREAKOUT, EXPIRED）
- 週足チャートパターンの詳細（陰線の位置、ブレイクアウト状況）
- コンポジットスコアとレーティング
- トレードセットアップ: エントリー、ストップロス、ターゲット、リスク/リワード比率
- 流動性指標（ADV20、平均出来高）

### ステップ4: アクショナブルなガイダンスの提供

ステージとレーティングに基づく:
- **BREAKOUT + 強いセットアップ (85+):** 高確信PEADトレード、フルポジションサイズ
- **BREAKOUT + 良いセットアップ (70-84):** 堅実なPEADセットアップ、標準ポジションサイズ
- **SIGNAL_READY:** 陰線形成済み、陰線高値超えのブレイクアウトにアラート設定
- **MONITORING:** 決算後、まだ陰線なし、ウォッチリストに追加
- **EXPIRED:** モニタリングウィンドウ超過、ウォッチリストから削除

---

## 6. リソース

**リファレンス:**

- `skills/pead-screener/references/entry_exit_rules.md`
- `skills/pead-screener/references/pead_strategy.md`

**スクリプト:**

- `skills/pead-screener/scripts/fmp_client.py`
- `skills/pead-screener/scripts/report_generator.py`
- `skills/pead-screener/scripts/scorer.py`
- `skills/pead-screener/scripts/screen_pead.py`
