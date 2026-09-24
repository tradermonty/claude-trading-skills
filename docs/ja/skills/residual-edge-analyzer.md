---
layout: default
title: "Residual Edge Analyzer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 52
lang_peer: /en/skills/residual-edge-analyzer/
permalink: /ja/skills/residual-edge-analyzer/
generated: false
---

# Residual Edge Analyzer
{: .no_toc }

戦略のリターン系列を、宣言済みベースラインへのエクスポージャーと残差エッジに分離します。リターンベースのOLSアトリビューション、HAC推論、ローリング安定性、代替ベースライン感度分析、レジーム別内訳を使用します。バックテスト、アウトオブサンプル、ライブのリターンに、マーケット、等ウェイト、モメンタム、セクター、またはユーザー指定ファクターのリターンを超える独立したアルファが含まれるか評価するとき、ドローダウンがベースライン要因か戦略固有の振る舞いかを説明するとき、バックテスト後にアトリビューション品質ゲートが必要なときに使用します。保有銘柄ベースのBrinsonアトリビューション、特徴量レベルのShapley説明、日付付きリターン系列なしの要約指標からの分析には使用しません。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/residual-edge-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/residual-edge-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

戦略の見かけのパフォーマンスが、事前宣言したベースラインのリターン系列との明示的な比較に耐えるか検証します。データを外部取得したり取引エクスポージャーを変更したりせず、監査可能なJSON成果物と簡潔なMarkdownレポートを生成します。

`backtest-expert` の後の反証ゲートとして扱い、取引承認としては扱いません。

---

## 2. 前提条件

- Python 3.9以降を使用します。
- 同じ行にISO日付、戦略リターン、すべてのベースラインリターンを含むCSVを1件用意します。
- [入力contract](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/residual-edge-analyzer/references/input-contract.md) に従ったJSON仕様を用意します。
- 実際の期間リターンを指定します。CAGR、シャープレシオ、累積損益などの要約指標で代用しません。

---

## 3. クイックスタート

```bash
python3 skills/residual-edge-analyzer/scripts/analyze_residual_edge.py \
  --input reports/strategy_returns.csv \
  --config reports/residual_edge_config.json \
  --output-json reports/residual_edge_report.json \
  --output-markdown reports/residual_edge_report.md
```

---

## 4. 仕組み

### 1. 結果を見る前に問いを定義する

主張する独立エッジを1文で記述します。戦略の単純な模倣として妥当なプライマリベースラインを1つ選び、さらに少なくとも1つの代替ベースラインモデルを選びます。

以下をコンフィグに記録します。

- `baseline_selection: predeclared`
- `strategy_return_basis` と `baseline_return_basis`: ともに `gross` またはともに `net`
- `analysis_scope`: `out_of_sample`、`live`、`in_sample` のいずれか
- `universe_data`: `point_in_time`、`current_constituents`、`not_applicable` のいずれか

判定級の評価にはすべての宣言が必須です。1つでも欠けると未宣言として扱われ、問題なし扱いにはならず、レポートは `REVIEW_REQUIRED` に格下げされます。`not_applicable` は、ユニバース所属を持たないベースラインを空欄のままにせず明示的に宣言するために存在します。

好ましい残差結果が出るという理由でベースラインを選んではいけません。

### 2. リターン系列コントラクトを検証する

以下を必須とします。

- 一意なISO日付
- -100%を上回る有限の数値リターン
- 戦略とベースラインで同一の頻度・コスト基準
- 同一ユニバースの等ウェイト／モメンタムベースラインにはpoint-in-timeの所属情報
- 説明対象の損失期間と独立に定義されたレジームラベル

日付付き戦略リターン系列がない入力では停止します。要約のみの入力は観測値を捏造せず、不足として報告します。

### 3. アナライザーを実行する

```bash
python3 skills/residual-edge-analyzer/scripts/analyze_residual_edge.py \
  --input reports/strategy_returns.csv \
  --config reports/residual_edge_config.json \
  --output-json reports/residual_edge_report.json \
  --output-markdown reports/residual_edge_report.md
```

スクリプトは事前宣言したプライマリモデルとすべての感度モデルを1回の実行で走らせます。切片付きOLSモデルとHAC／Newey-West標準誤差を使用します。残差エッジレシオを年率アルファ÷年率残差ボラティリティとして報告します。切片によりOLS残差の平均はゼロになるため、生のOLS残差平均からシャープレシオを計算してはいけません。

### 4. エビデンスを解釈する

4つのステータスを診断ラベルとして使用します。

- `RESIDUAL_EDGE`: アルファ、残差エッジレシオ、ローリング安定性が設定閾値をクリア。
- `BASELINE_EXPLAINED`: ベースラインのR-squaredが高く、残差エビデンスが弱い。
- `RESIDUAL_FRAGILE`: 1つ以上の頑健性ゲートに不合格、または宣言済みベースラインモデル間で結果が変わる。ローリング分析が無効・利用不可・不完全の場合、感度モデルが未指定の場合もこのステータスを使用します。
- `INSUFFICIENT_EVIDENCE`: サンプルが設定済み下限を下回る。

`decision_eligibility` は別途読み取ります。重要な来歴・コスト基準・サンプル・多重共線性の警告がある場合、ローリングエビデンスが利用できない場合、代替ベースラインを検証していない場合、統計的に興味深い結果であっても `REVIEW_REQUIRED` のままです。

確認項目:

1. プライマリおよび感度モデルのステータス
2. 年率アルファとHAC t値
3. 残差エッジレシオと残差の自己相関
4. ローリングアルファの安定性
5. マルチファクターモデルのVIF
6. 事前宣言レジーム別のアクティブリターン内訳

### 5. 所見を引き継ぐ

- ベースライン選択、OOS、安定性の所見を `backtest-expert` に戻します。
- 繰り返し発生する残差失敗レジームを `signal-postmortem` に送ります。
- `trade-performance-coach` にはエビデンスと運用制約のみ渡します。
- ポジションサイズ、エクスポージャー、注文を自動変更しません。

---

## 5. リファレンス

**リファレンス:**

- `skills/residual-edge-analyzer/references/input-contract.md`
- `skills/residual-edge-analyzer/references/methodology.md`

**スクリプト:**

- `skills/residual-edge-analyzer/scripts/analyze_residual_edge.py`
