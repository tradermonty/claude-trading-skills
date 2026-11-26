---
layout: default
title: "Uptrend Analyzer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 43
lang_peer: /en/skills/uptrend-analyzer/
permalink: /ja/skills/uptrend-analyzer/
---

# Uptrend Analyzer
{: .no_toc }

Montyのアップトレンド比率ダッシュボードのデータを使用してマーケットブレッドスを分析し、現在の市場環境を診断するスキルです。5つのコンポーネント（ブレッドス、セクター参加率、ローテーション、モメンタム、ヒストリカルコンテキスト）から0-100の複合スコアを生成します。マーケットブレッドス、アップトレンド比率、市場環境が株式エクスポージャーを支持するかどうかの質問時に使用します。APIキー不要。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/uptrend-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/uptrend-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

MontyのアップトレンドダッシュボードのCSVデータを取得し、マーケットブレッドスと市場環境を診断するスキルです。5つのコンポーネントスコアと複合スコア（0-100）を計算し、エクスポージャーガイダンス（Full/Normal/Reduced/Defensive/Preservation）を提供します。

### 活用事例: Uptrend Ratio Dashboard

[Uptrend Ratio Dashboard](https://uptrend-dashboard.streamlit.app) は、このスキルが分析するデータの元になっているダッシュボードです。市場全体と11セクターそれぞれのアップトレンド比率を公開しています。最新の数値を確かめて、スキルのレポートと見比べるのに使えます。

---

## 2. 使用タイミング

**英語：**
- 「Is the market breadth healthy?」「How broad is the rally?」
- セクター別アップトレンド比率の確認
- 市場参加率やブレッドス状況の診断
- ブレッドス分析に基づくエクスポージャーガイダンス
- MontyのアップトレンドダッシュボードやUptrend Ratioについての質問

**日本語：**
- 「市場のブレッドスは健全？」「上昇の裾野は広い？」
- セクター別のアップトレンド比率を確認したい
- 相場参加率・ブレッドス状況を診断したい
- ブレッドス分析に基づくエクスポージャーガイダンスが欲しい
- Montyのアップトレンドダッシュボードについて質問

---

## 3. 前提条件

- **APIキー：** 不要
- **Python 3.9+** 推奨

---

## 4. クイックスタート

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

---

## 5. ワークフロー

### Phase 1: Pythonスクリプトの実行

分析スクリプトを実行（APIキー不要）：

```bash
python3 skills/uptrend-analyzer/scripts/uptrend_analyzer.py
```

スクリプトの動作：
1. MontyのGitHubリポジトリからCSVデータをダウンロード
2. 5つのコンポーネントスコアを計算
3. 複合スコアとレポートを生成

### Phase 2: 結果の提示

生成されたMarkdownレポートをユーザーに提示。以下をハイライト：
- 複合スコアとゾーン分類
- エクスポージャーガイダンス（Full/Normal/Reduced/Defensive/Preservation）
- 最も強い/弱いセクターを示すセクターヒートマップ
- 主要なモメンタムとローテーションのシグナル

---

## 6. リソース

**リファレンス：**

- `skills/uptrend-analyzer/references/uptrend_methodology.md`

**スクリプト：**

- `skills/uptrend-analyzer/scripts/data_fetcher.py`
- `skills/uptrend-analyzer/scripts/report_generator.py`
- `skills/uptrend-analyzer/scripts/scorer.py`
- `skills/uptrend-analyzer/scripts/uptrend_analyzer.py`

## market-regime-daily の出所検証

必須2生成処理に同じ一意の `--run-id daily-20261017-unique` を渡します。
省略時は各処理が個別IDを生成します。JSONの `data_provenance` は主時系列の
実データ日付、UTC取得日時、出所、実行IDを記録します。不明な品質フラグはfalseです。
補助サマリーの日付は未検証であり、合成スコア全体の鮮度保証にはなりません。
主時系列の日付が欠落・不正な場合はレポート生成を停止します。

今回表示された正確なJSONパスをExposure Coachに渡し、
`--require-provenance --run-id daily-20261017-unique --as-of 2026-10-17T13:00:00Z
--max-age-days 3` を指定します。`--as-of` はタイムゾーン付き評価日時です。
schema 1.0・実行ID・UTC取得日時・未来日付・鮮度を採点前に検証し、失敗時は出力しません。
既定3暦日は取引所休日を考慮しない保守的な方針です。成功時は受理した出所と保証範囲を記録します。
任意のtop-risk等は検証対象外です。実行IDは真正性やpoint-in-timeの証明ではありません。
厳格モードを使わない従来の入出力形式も引き続き利用できます。
