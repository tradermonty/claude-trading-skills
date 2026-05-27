---
layout: default
title: "Scenario Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 48
lang_peer: /ja/skills/scenario-analyzer/
permalink: /en/skills/scenario-analyzer/
---

# Scenario Analyzer
{: .no_toc }

ニュースヘッドラインを入力として18ヶ月シナリオを分析するスキル。
scenario-analystエージェントで主分析を実行し、
strategy-reviewerエージェントでセカンドオピニオンを取得。
1次・2次・3次影響、推奨銘柄、レビューを含む包括的レポートを日本語で生成。
使用例: /scenario-analyzer "Fed raises rates by 50bp"
トリガー: ニュース分析、シナリオ分析、18ヶ月展望、中長期投資戦略

{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/scenario-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/scenario-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

このスキルは、ニュースヘッドラインを起点として中長期（18ヶ月）の投資シナリオを分析します。
2つの専門エージェント（`scenario-analyst`と`strategy-reviewer`）を順次呼び出し、
多角的な分析と批判的レビューを統合した包括的なレポートを生成します。

---

## 2. When to Use

以下の場合にこのスキルを使用してください：

- ニュースヘッドラインから中長期の投資影響を分析したい
- 18ヶ月後のシナリオを複数構築したい
- セクター・銘柄への影響を1次/2次/3次で整理したい
- セカンドオピニオンを含む包括的な分析が必要
- 日本語でのレポート出力が必要

**使用例:**
```
/scenario-analyzer "Fed raises interest rates by 50bp, signals more hikes ahead"
/scenario-analyzer "China announces new tariffs on US semiconductors"
/scenario-analyzer "OPEC+ agrees to cut oil production by 2 million barrels per day"
```

---

## 3. Prerequisites

- **API Keys**: なし（WebSearch/WebFetchのみ使用）
- **MCP Servers**: なし
- **Dependencies**: scenario-analyst および strategy-reviewer エージェントが Task tool で利用可能であること

---

## 4. Quick Start

```bash
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

---

## 5. Workflow

### Phase 1: 準備

#### Step 1.1: ヘッドライン解析

ユーザーから入力されたヘッドラインを解析します。

1. **ヘッドライン確認**
   - 引数としてヘッドラインが渡されているか確認
   - 渡されていない場合はユーザーに入力を求める

2. **キーワード抽出**
   - 主要なエンティティ（企業名、国名、機関名）
   - 数値データ（金利、価格、数量）
   - アクション（引き上げ、引き下げ、発表、合意等）

#### Step 1.2: イベントタイプ分類

ヘッドラインを以下のカテゴリに分類：

| カテゴリ | 例 |
|---------|-----|
| 金融政策 | FOMC、ECB、日銀、利上げ、利下げ、QE/QT |
| 地政学 | 戦争、制裁、関税、貿易摩擦 |
| 規制・政策 | 環境規制、金融規制、独禁法 |
| テクノロジー | AI、EV、再エネ、半導体 |
| コモディティ | 原油、金、銅、農産物 |
| 企業・M&A | 買収、破綻、決算、業界再編 |

#### Step 1.3: リファレンス読み込み

イベントタイプに基づき、関連するリファレンスを読み込みます：

```
Read references/headline_event_patterns.md
Read references/sector_sensitivity_matrix.md
Read references/scenario_playbooks.md
```

**リファレンス内容:**
- `headline_event_patterns.md`: 過去のイベントパターンと市場反応
- `sector_sensitivity_matrix.md`: イベント×セクターの影響度マトリクス
- `scenario_playbooks.md`: シナリオ構築のテンプレートとベストプラクティス

---

### Phase 2: エージェント呼び出し

#### Step 2.1: scenario-analyst 呼び出し

Agent toolを使用してメイン分析エージェントを呼び出します。

```
Agent tool:
- subagent_type: "scenario-analyst"
- prompt: |
    以下のヘッドラインについて18ヶ月シナリオ分析を実行してください。

    ## 対象ヘッドライン
    [入力されたヘッドライン]

    ## イベントタイプ
    [分類結果]

    ## リファレンス情報
    [読み込んだリファレンスの要約]

    ## 分析要件
    1. WebSearchで過去2週間の関連ニュースを収集
    2. Base/Bull/Bearの3シナリオを構築（確率合計100%）
    3. 1次/2次/3次影響をセクター別に分析
    4. ポジティブ/ネガティブ影響銘柄を各3-5銘柄選定（米国市場のみ）
    5. 全て日本語で出力
```

**期待する出力:**
- 関連ニュース記事リスト
- 3シナリオ（Base/Bull/Bear）の詳細
- セクター影響分析（1次/2次/3次）
- 銘柄推奨リスト

#### Step 2.2: strategy-reviewer 呼び出し

scenario-analystの分析結果を受けて、レビューエージェントを呼び出します。

```
Agent tool:
- subagent_type: "strategy-reviewer"
- prompt: |
    以下のシナリオ分析をレビューしてください。

    ## 対象ヘッドライン
    [入力されたヘッドライン]

    ## 分析結果
    [scenario-analystの出力全文]

    ## レビュー要件
    以下の観点でレビューを実施：
    1. 見落とされているセクター/銘柄
    2. シナリオ確率配分の妥当性
    3. 影響分析の論理的整合性
    4. 楽観/悲観バイアスの検出
    5. 代替シナリオの提案
    6. タイムラインの現実性

    建設的かつ具体的なフィードバックを日本語で出力してください。
```

**期待する出力:**
- 見落としの指摘
- シナリオ確率への意見
- バイアスの指摘
- 代替シナリオの提案
- 最終推奨事項

---

### Phase 3: 統合・レポート生成

#### Step 3.1: 結果統合

両エージェントの出力を統合し、最終投資判断を作成します。

**統合ポイント:**
1. レビューで指摘された見落としを補完
2. 確率配分の調整（必要な場合）
3. バイアスを考慮した最終判断
4. 具体的なアクションプランの策定

#### Step 3.2: レポート生成

以下の形式で最終レポートを生成し、ファイルに保存します。

**保存先:** `reports/scenario_analysis_<topic>_YYYYMMDD.md`

```markdown
# ヘッドライン・シナリオ分析レポート

**分析日時**: YYYY-MM-DD HH:MM
**対象ヘッドライン**: [入力されたヘッドライン]
**イベントタイプ**: [分類カテゴリ]

---

---

## 6. Resources

**References:**

- `skills/scenario-analyzer/references/headline_event_patterns.md`
- `skills/scenario-analyzer/references/scenario_playbooks.md`
- `skills/scenario-analyzer/references/sector_sensitivity_matrix.md`
