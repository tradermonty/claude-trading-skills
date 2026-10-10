---
layout: default
title: "Portfolio Manager"
grand_parent: 日本語
parent: スキルガイド
nav_order: 35
lang_peer: /en/skills/portfolio-manager/
permalink: /ja/skills/portfolio-manager/
---

# Portfolio Manager
{: .no_toc }

Alpaca MCPサーバーと連携し、保有銘柄やポジションを取得して、資産配分・リスク指標・個別銘柄評価・分散度・リバランス提案を含む包括的なポートフォリオ分析を行うスキルです。ポートフォリオレビュー、ポジション分析、リスク評価、パフォーマンス評価、リバランス提案が必要な場合に使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-api">Alpaca必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/portfolio-manager.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/portfolio-manager){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Alpaca MCPサーバーと連携してリアルタイムの保有データを取得し、資産配分・分散度・リスク指標・個別ポジション評価・リバランス提案を含む投資ポートフォリオの総合分析・管理を行います。詳細なポートフォリオレポートとアクション可能なインサイトを生成します。

AlpacaのブローカーAPIにMCP（Model Context Protocol）経由でアクセスし、手入力ではなく実際の現在ポジションに基づいた分析を実現します。

---

## 2. 使用タイミング

以下のリクエストがあった場合にこのスキルを使用してください：
- 「ポートフォリオを分析して」
- 「現在のポジションをレビューして」
- 「資産配分はどうなっている？」
- 「ポートフォリオのリスクをチェックして」
- 「リバランスすべき？」
- 「保有銘柄を評価して」
- 「ポートフォリオのパフォーマンスレビュー」
- 「どの銘柄を買うべき？売るべき？」
- ポートフォリオレベルの分析や管理に関するリクエスト全般

---

## 3. 前提条件

### Alpaca MCPサーバーのセットアップ

このスキルはAlpaca MCPサーバーの設定と接続が必要です。MCPサーバーは以下へのアクセスを提供します：
- 現在のポートフォリオポジション
- 口座資産額と購買力
- 過去のポジションと取引履歴
- 保有銘柄のマーケットデータ

**使用するMCPサーバーツール：**
- `get_account_info` - 口座資産額、購買力、現金残高の取得
- `get_positions` - 全ポジションの数量、取得原価、時価評価額の取得
- `get_portfolio_history` - ポートフォリオの過去パフォーマンスデータ
- マーケットデータツール（価格クォートおよびファンダメンタルズ）

Alpaca MCPサーバーが未接続の場合は、ユーザーに通知し `references/alpaca_mcp_setup.md` のセットアップ手順を案内してください。

---

## 4. クイックスタート

```bash
# Alpaca接続テスト
python3 skills/portfolio-manager/scripts/check_alpaca_connection.py

# ポートフォリオ分析はClaude + Alpaca MCPツールで実行
# セットアップの詳細: portfolio-manager/references/alpaca-mcp-setup.md
```

---

## 5. ワークフロー

### ステップ1: Alpaca MCP経由でポートフォリオデータを取得

Alpaca MCPサーバーツールを使用して現在のポートフォリオ情報を収集します。

**1.1 口座情報の取得：**
```
mcp__alpaca__get_account_info を使用して取得：
- 口座資産額（ポートフォリオ総額）
- 現金残高
- 購買力
- 口座ステータス
```

**1.2 現在のポジション取得：**
```
mcp__alpaca__get_positions を使用して全保有銘柄を取得：
- ティッカーシンボル
- 保有数量
- 平均取得価格（取得原価）
- 現在の市場価格
- 現在の時価評価額
- 未実現損益（ドルおよび%）
- ポートフォリオに占めるポジション比率（%）
```

**1.3 ポートフォリオ履歴の取得（オプション）：**
```
mcp__alpaca__get_portfolio_history でパフォーマンス分析：
- 過去の資産額推移
- 時間加重リターンの計算
- ドローダウン分析
```

**データバリデーション：**
- すべてのポジションに有効なティッカーシンボルがあることを確認
- 時価評価額の合計が口座資産額とおおよそ一致することを確認
- 古いポジションや非アクティブなポジションがないかチェック
- エッジケースの処理（端株、オプション、対応している場合は暗号資産）

### ステップ2: ポジションデータの補強

ポートフォリオの各ポジションについて、追加のマーケットデータとファンダメンタルズを収集します。

**2.1 現在のマーケットデータ：**
- リアルタイムまたは遅延価格クォート
- 日次出来高と流動性指標
- 52週レンジ
- 時価総額

**2.2 ファンダメンタルデータ：**
WebSearchまたは利用可能なマーケットデータAPIで取得：
- セクター・業種分類
- 主要バリュエーション指標（P/E、P/B、配当利回り）
- 直近の決算と財務健全性指標
- アナリストレーティングと目標株価
- 最近のニュースと重要な動き

**2.3 テクニカル分析：**
- 価格トレンド（20日、50日、200日移動平均）
- 相対的な強さ
- サポートとレジスタンスレベル
- モメンタム指標（RSI、MACD、利用可能な場合）

### ステップ3: ポートフォリオレベルの分析

リファレンスファイルのフレームワークを使用して包括的なポートフォリオ分析を実施します。

#### 3.1 資産配分分析

**`references/asset-allocation.md`** で配分フレームワークを確認。

複数の切り口で現在の配分を分析します：

**資産クラス別：**
- 株式 vs 債券 vs 現金 vs オルタナティブ
- ユーザーのリスクプロファイルに対する目標配分との比較
- 配分が投資目標に合致しているか評価

**セクター別：**
- テクノロジー、ヘルスケア、金融、消費財など
- セクター集中リスクの特定
- ベンチマークのセクターウェイト（例: S&P 500）との比較

**時価総額別：**
- 大型株 vs 中型株 vs 小型株の分布
- メガキャップへの集中度
- 時価総額分散スコア

**地域別：**
- 米国 vs 海外先進国 vs 新興国
- 国内集中リスクの評価

---

## 週次レビュー前の読み取り専用照合

`core-portfolio-weekly`では、同一口座の完全なブローカー保有情報と
ACTIVE・PARTIALLY_CLOSEDのメモリ残数量を、
[照合ガイド](https://github.com/tradermonty/claude-trading-skills/blob/main/skills/portfolio-manager/references/position-reconciliation.md)
に従って準備します。`skills/portfolio-manager/scripts/reconcile_positions.py`を
ローカル実行し、JSON・Markdownのレポートを確認します。`can_continue`がfalse、
または網羅性・口座帰属・鮮度が未確認なら資産配分・リバランスの確認を停止します。
この手動ゲートは注文を許可せず、メモリを変更しません。自動exportとreplayへの
組込みは#493の残作業です。

## 6. リソース

**リファレンス：**

- `skills/portfolio-manager/references/alpaca-mcp-setup.md`
- `skills/portfolio-manager/references/asset-allocation.md`
- `skills/portfolio-manager/references/diversification-principles.md`
- `skills/portfolio-manager/references/portfolio-risk-metrics.md`
- `skills/portfolio-manager/references/position-evaluation.md`
- `skills/portfolio-manager/references/rebalancing-strategies.md`
- `skills/portfolio-manager/references/risk-profile-questionnaire.md`
- `skills/portfolio-manager/references/target-allocations.md`
