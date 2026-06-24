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

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

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
