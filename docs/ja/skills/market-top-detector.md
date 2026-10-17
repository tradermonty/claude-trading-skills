---
layout: default
title: "Market Top Detector"
grand_parent: 日本語
parent: スキルガイド
nav_order: 31
lang_peer: /en/skills/market-top-detector/
permalink: /ja/skills/market-top-detector/
---

# Market Top Detector
{: .no_toc }

オニールのディストリビューションデー、ミネルヴィニの先導株劣化、モンティのディフェンシブセクターローテーションを使用して市場天井のヒューリスティックなリスクを評価します。リスクゾーン分類付きの0-100コンポジットスコアを生成します。市場天井リスク、ディストリビューションデー、ディフェンシブローテーション、リーダーシップ崩壊、またはエクイティエクスポージャーを縮小すべきかについて聞かれた際に使用します。10-20%の調整に対する2〜8週間の戦術的タイミングシグナルに焦点を当てます。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/market-top-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/market-top-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

0〜100の値はヒューリスティックなリスクスコアであり、推定イベント確率ではありません。リスク予算は運用方針上の目安です。過去パターンは事後的な参考例です。データ欠損または加重RMS距離が15を超える場合は「比較可能な事例なし」とします。時点整合性を保った実測較正結果は未提供です。

[Point-in-time evaluation protocol](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/market-top-detector/references/point_in_time_evaluation.md)

市場天井のヒューリスティックなリスクを評価するスキルです。

---

## 2. 使用タイミング

- ユーザーが「天井が近い？」「今は利確すべき？」と質問した場合
- ディストリビューションデーの蓄積を懸念している場合
- ディフェンシブセクターがグロースをアウトパフォームしていることを観測した場合
- 先導株が崩れ始めているが指数はまだ持ちこたえている場合
- エクスポージャー縮小のタイミング判断を求められた場合
- 今後2〜8週間の調整リスクを評価したい場合

---

## 3. 前提条件

- **APIキー:** 不要
- **Python 3.9+** 推奨

---

## 4. クイックスタート

```bash
1. S&P 500 ブレッドス (200DMA超え %)
   TraderMonty CSVから自動取得（WebSearch不要）
   スクリプトがGitHub PagesのCSVデータから自動取得します。
   オーバーライド: --breadth-200dma [VALUE] で手動値を使用。
   無効化: --no-auto-breadth で自動取得をスキップ。

2. [必須] S&P 500 ブレッドス (50DMA超え %)
   有効範囲: 20-100
   検索例: "S&P 500 percent stocks above 50 day moving average"
   フォールバック: "market breadth 50dma site:barchart.com"
   データ日付を記録

3. [必須] CBOE エクイティ プット/コール比率
   有効範囲: 0.30-1.50
   検索例: "CBOE equity put call ratio today"
   フォールバック: "CBOE total put call ratio current"
   フォールバック: "put call ratio site:cboe.com"
   データ日付を記録

4. [任意] VIX期間構造
   値: steep_contango / contango / flat / backwardation
   検索例: "VIX VIX3M ratio term structure today"
   フォールバック: "VIX futures term structure contango backwardation"
   注: VIX3Mクオートが利用可能な場合、FMP APIから自動検出。
   CLI --vix-term で自動検出をオーバーライド。

5. [任意] 信用取引残高 前年比 %
   検索例: "FINRA margin debt latest year over year percent"
   フォールバック: "NYSE margin debt monthly"
   注: 通常1-2ヶ月のラグあり。報告月を記録。
```

---

## 5. ワークフロー

### フェーズ1: WebSearchによるデータ収集

Pythonスクリプトを実行する前に、WebSearchを使用して以下のデータを収集します。
**データ鮮度要件:** すべてのデータは直近3営業日以内のものである必要があります。古いデータは分析品質を低下させます。

```
1. S&P 500 ブレッドス (200DMA超え %)
   TraderMonty CSVから自動取得（WebSearch不要）
   スクリプトがGitHub PagesのCSVデータから自動取得します。
   オーバーライド: --breadth-200dma [VALUE] で手動値を使用。
   無効化: --no-auto-breadth で自動取得をスキップ。

2. [必須] S&P 500 ブレッドス (50DMA超え %)
   有効範囲: 20-100
   検索例: "S&P 500 percent stocks above 50 day moving average"
   フォールバック: "market breadth 50dma site:barchart.com"
   データ日付を記録

3. [必須] CBOE エクイティ プット/コール比率
   有効範囲: 0.30-1.50
   検索例: "CBOE equity put call ratio today"
   フォールバック: "CBOE total put call ratio current"
   フォールバック: "put call ratio site:cboe.com"
   データ日付を記録

4. [任意] VIX期間構造
   値: steep_contango / contango / flat / backwardation
   検索例: "VIX VIX3M ratio term structure today"
   フォールバック: "VIX futures term structure contango backwardation"
   注: VIX3Mクオートが利用可能な場合、FMP APIから自動検出。
   CLI --vix-term で自動検出をオーバーライド。

5. [任意] 信用取引残高 前年比 %
   検索例: "FINRA margin debt latest year over year percent"
   フォールバック: "NYSE margin debt monthly"
   注: 通常1-2ヶ月のラグあり。報告月を記録。
```

### フェーズ2: Pythonスクリプトの実行

収集したデータをCLI引数としてスクリプトを実行:

```bash
python3 skills/market-top-detector/scripts/market_top_detector.py \
  --api-key $FMP_API_KEY \
  --breadth-50dma [VALUE] --breadth-50dma-date [YYYY-MM-DD] \
  --put-call [VALUE] --put-call-date [YYYY-MM-DD] \
  --vix-term [steep_contango|contango|flat|backwardation] \
  --margin-debt-yoy [VALUE] --margin-debt-date [YYYY-MM-DD] \
  --output-dir reports/ \
  --context "Consumer Confidence=[VALUE]" "Gold Price=[VALUE]"
# 200DMAブレッドスはTraderMonty CSVから自動取得。
# 必要に応じて --breadth-200dma [VALUE] でオーバーライド。
# --no-auto-breadth で自動取得を無効化。
```

スクリプトは以下を実行します:
1. FMP APIからS&P 500、QQQ、VIXのクオートと履歴を取得
2. 先導ETF（ARKK, WCLD, IGV, XBI, SOXX, SMH, KWEB, TAN）データを取得
3. セクターETF（XLU, XLP, XLV, VNQ, XLK, XLC, XLY）データを取得
4. 全6コンポーネントを計算
5. コンポジットスコアとレポートを生成

### フェーズ3: 結果の提示

生成されたMarkdownレポートをユーザーに提示し、以下をハイライト:
- コンポジットスコアとリスクゾーン
- データ鮮度の警告（3日以上前のデータがある場合）
- 最も強い警告シグナル（最高コンポーネントスコア）
- 歴史的比較（最も類似した過去の天井パターン）
- What-ifシナリオ（主要変数への感応度）
- リスクゾーンに基づく推奨アクション
- フォロースルーデーのステータス（該当する場合）
- 前回実行との差分（前回レポートが存在する場合）

---

---

## 6. リソース

**リファレンス:**

- `skills/market-top-detector/references/distribution_day_guide.md`
- `skills/market-top-detector/references/historical_tops.md`
- `skills/market-top-detector/references/market_top_methodology.md`

**スクリプト:**

- `skills/market-top-detector/scripts/breadth_csv_client.py`
- `skills/market-top-detector/scripts/fmp_client.py`
- `skills/market-top-detector/scripts/historical_comparator.py`
- `skills/market-top-detector/scripts/market_top_detector.py`
- `skills/market-top-detector/scripts/report_generator.py`
- `skills/market-top-detector/scripts/scenario_engine.py`
- `skills/market-top-detector/scripts/scorer.py`
- `skills/market-top-detector/scripts/utils.py`
