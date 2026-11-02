---
layout: default
title: "Institutional Flow Tracker"
grand_parent: 日本語
parent: スキルガイド
nav_order: 25
lang_peer: /en/skills/institutional-flow-tracker/
permalink: /ja/skills/institutional-flow-tracker/
---

# Institutional Flow Tracker
{: .no_toc }

13Fファイリングデータを使用して、機関投資家のオーナーシップ変動とポートフォリオフローを追跡するスキルです。ヘッジファンド、投資信託、その他の機関投資家を分析し、スマートマネーの大規模な蓄積・分配が見られる銘柄を特定します。洗練された投資家が資金を投入している先を追うことで、大きな値動きの前に銘柄を発見できます。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/institutional-flow-tracker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/institutional-flow-tracker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

このスキルは、13F SECファイリングを通じて機関投資家の動向を追跡し、銘柄への「スマートマネー」フローを特定します。機関投資家の四半期ごとのオーナーシップ変動を分析することで、洗練された投資家が大きな値動きの前に蓄積している銘柄を発見したり、機関がポジションを縮小している場合の潜在的リスクを特定できます。

**重要な洞察:** 機関投資家（ヘッジファンド、年金基金、投資信託）は数兆ドルを運用し、広範なリサーチを行っています。彼らの集団的な売買パターンは、多くの場合、大きな値動きに1〜3四半期先行します。

---

## 2. 使用タイミング

以下の場合にこのスキルを使用します:
- 投資アイデアの検証（スマートマネーがあなたのテーゼに同意しているか確認）
- 新しい機会の発見（機関が蓄積している銘柄を見つける）
- リスク評価（機関が退出している銘柄を特定）
- ポートフォリオモニタリング（保有銘柄の機関投資家サポートを追跡）
- 特定の投資家の追跡（ウォーレン・バフェット、キャシー・ウッドなど）
- セクターローテーション分析（機関が資金をローテートしている先を特定）

**使用すべきでない場合:**
- リアルタイムのイントラデイシグナルを求める場合（13Fデータには45日の報告ラグあり）
- マイクロキャップ銘柄の分析（時価総額1億ドル未満は機関の関心が限定的）
- 短期トレーディングシグナルを求める場合（3ヶ月未満の期間）

---

## 3. 前提条件

- **FMP APIキー:** 環境変数 `FMP_API_KEY` を設定するか、スクリプトに `--api-key` を渡す
- **Python 3.8+:** 分析スクリプトの実行に必要
- **依存関係:** `pip install requests`（スクリプトは依存関係不足を適切に処理）

---

## 4. クイックスタート

```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

---

## 5. ワークフロー

### ステップ1: 機関投資家の大きな変動がある銘柄を特定

メインスクリーニングスクリプトを実行して、注目すべき機関投資家の動きがある銘柄を見つけます:

**クイックスキャン（機関変動上位50銘柄）:**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --top 50 \
  --min-change-percent 10
```

**セクターフォーカスのスキャン:**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --sector Technology \
  --min-institutions 20
```

**カスタムスクリーニング:**
```bash
python3 skills/institutional-flow-tracker/scripts/track_institutional_flow.py \
  --min-market-cap 2000000000 \
  --min-change-percent 15 \
  --top 100 \
  --output institutional_flow_results.json
```

**出力内容:**
- ティッカーシンボルと企業名
- 現在の機関投資家保有率（発行済み株式数に対する%）
- 前四半期比の保有株数変動
- 保有機関数
- 機関数の変動（新規買い手 vs 売り手）
- 上位の機関投資家保有者

### ステップ2: 特定銘柄の詳細分析

特定銘柄の機関投資家保有状況の詳細分析:

```bash
python3 skills/institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
```

**生成される内容:**
- 機関投資家保有率の推移（8四半期分）
- ポジション変動を含む全機関投資家保有者リスト
- 集中度分析（上位10保有者の機関保有全体に対する割合）
- 新規ポジション vs 増加 vs 減少ポジション
- 信頼性グレード付きデータ品質評価

**評価すべき主要指標:**
- **保有率:** 高い機関投資家保有率（>70%）= 安定性が高いがアップサイドは限定的
- **保有率トレンド:** 上昇 = 強気、下降 = 弱気
- **集中度:** 高い集中度（上位10が>50%）= 売却時のリスク
- **保有者の質:** 長期質の高い投資家（バークシャー、フィデリティ）の存在 vs モメンタムファンド

### ステップ3: 特定の機関投資家を追跡

> **注:** `track_institution_portfolio.py` は**未実装**です。FMP APIは機関投資家データを
> 銘柄単位で整理しており（機関単位ではない）、このAPIだけではフルポートフォリオの再構成は
> 現実的ではありません。

**代替アプローチ — `analyze_single_stock.py` で特定の機関が銘柄を保有しているか確認:**
```bash
# 銘柄を分析し、出力から特定の機関を検索
python3 skills/institutional-flow-tracker/scripts/analyze_single_stock.py AAPL
# レポートの上位20保有者テーブルで "Berkshire" や "ARK" を検索
```

**機関レベルの完全なポートフォリオ追跡には、以下の外部リソースを使用:**
1. **WhaleWisdom:** https://whalewisdom.com（無料枠あり、13Fポートフォリオビューア）
2. **SEC EDGAR:** https://www.sec.gov/cgi-bin/browse-edgar（公式13Fファイリング）
3. **DataRoma:** https://www.dataroma.com（スーパーインベスター ポートフォリオトラッカー）

### ステップ4: 解釈とアクション

解釈ガイダンスについてはリファレンスを参照:
- `references/13f_filings_guide.md` - 13Fデータの理解と制限事項
- `references/institutional_investor_types.md` - 投資家タイプとその戦略
- `references/interpretation_framework.md` - 機関フローシグナルの解釈方法

**シグナル強度フレームワーク:**

**強い強気（買い検討）:**
- 機関投資家保有率が前四半期比>15%増加
- 機関数が>10%増加
- 質の高い長期投資家がポジションを追加
- 低い現在の保有率（<40%）で成長余地あり
- 複数四半期にわたる蓄積

**中程度の強気:**
- 機関投資家保有率が前四半期比5-15%増加
- 新規買い手と売り手が混在、ネットでプラス
- 現在の保有率40-70%

**中立:**
- 保有率の変動が最小（<5%）
- 買い手と売り手の数が同程度
- 安定した機関ベース

**中程度の弱気:**
- 機関投資家保有率が前四半期比5-15%減少
- 売り手が買い手より多い
- 高い保有率（>80%）で新規買い手が限定的

**強い弱気（売却/回避検討）:**
- 機関投資家保有率が前四半期比>15%減少
- 機関数が>10%減少
- 質の高い投資家がポジションを退出
- 複数四半期にわたる分配
- 集中リスク（トップ保有者が大きなポジションを売却）

### ステップ5: ポートフォリオへの適用

**新規ポジションの場合:**
1. 投資アイデアの銘柄で機関分析を実行
2. 確認材料を探す（機関も蓄積しているか）
3. 強い弱気シグナルがあれば、再検討またはポジションサイズを縮小
4. 強い強気シグナルがあれば、テーゼへの確信を強める

**既存保有の場合:**
1. 13Fファイリング締め切り後の四半期レビュー
2. 分配の監視（早期警告システム）
3. 機関が退出中なら、テーゼを再評価
4. 広範な機関売りがあれば、ポジション縮小を検討

**スクリーニングワークフローとの統合:**
1. Value Dividend Screenerなどで候補を見つける
2. 上位候補でInstitutional Flow Trackerを実行
3. 機関の蓄積がある銘柄を優先
4. 機関の分配がある銘柄を回避

---

## 6. リソース

**リファレンス:**

- `skills/institutional-flow-tracker/references/13f_filings_guide.md`
- `skills/institutional-flow-tracker/references/institutional_investor_types.md`
- `skills/institutional-flow-tracker/references/interpretation_framework.md`

**スクリプト:**

- `skills/institutional-flow-tracker/scripts/analyze_single_stock.py`
- `skills/institutional-flow-tracker/scripts/data_quality.py`
- `skills/institutional-flow-tracker/scripts/fmp_client.py`
- `skills/institutional-flow-tracker/scripts/track_institution_portfolio.py`
- `skills/institutional-flow-tracker/scripts/track_institutional_flow.py`
