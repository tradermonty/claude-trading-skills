---
name: scenario-analyzer
description: |
  ニュースヘッドラインを入力として18ヶ月シナリオを分析するスキル。
  scenario-analystエージェントで主分析を実行し、
  strategy-reviewerエージェントでセカンドオピニオンを取得。
  1次・2次・3次影響、推奨銘柄、レビューを含む包括的レポートを日本語で生成。
  使用例: /scenario-analyzer "Fed raises rates by 50bp"
  トリガー: ニュース分析、シナリオ分析、18ヶ月展望、中長期投資戦略
---

# Scenario Analyzer

## Overview

このスキルは、ニュースヘッドラインを起点として中長期（18ヶ月）の投資シナリオを分析します。
2つの専門エージェント（`scenario-analyst`と`strategy-reviewer`）を順次呼び出し、
多角的な分析と批判的レビューを統合した包括的なレポートを生成します。

## When to Use This Skill

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

## Prerequisites

- **API Keys**: なし（WebSearch/WebFetchのみ使用）
- **MCP Servers**: なし
- **Dependencies**: scenario-analyst および strategy-reviewer エージェントが Task tool で利用可能であること

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Skill（オーケストレーター）                        │
│                                                                      │
│  Phase 1: 準備                                                       │
│  ├─ ヘッドライン解析                                                  │
│  ├─ イベントタイプ分類                                                │
│  └─ リファレンス読み込み                                              │
│                                                                      │
│  Phase 2: エージェント呼び出し                                        │
│  ├─ scenario-analyst（主分析）                                       │
│  └─ strategy-reviewer（セカンドオピニオン）                           │
│                                                                      │
│  Phase 3: 統合・レポート生成                                          │
│  └─ reports/scenario_analysis_<topic>_YYYYMMDD.md                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow

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

## 1. 関連ニュース記事
[scenario-analystが収集したニュースリスト]

## 2. 想定シナリオ概要（18ヶ月後まで）

### Base Case（XX%確率）
[シナリオ詳細]

### Bull Case（XX%確率）
[シナリオ詳細]

### Bear Case（XX%確率）
[シナリオ詳細]

## 3. セクター・業種への影響

### 1次的影響（直接的）
[影響テーブル]

### 2次的影響（バリューチェーン・関連産業）
[影響テーブル]

### 3次的影響（マクロ・規制・技術）
[影響テーブル]

## 4. ポジティブ影響が見込まれる銘柄（3-5銘柄）
[銘柄テーブル]

## 5. ネガティブ影響が見込まれる銘柄（3-5銘柄）
[銘柄テーブル]

## 6. セカンドオピニオン・レビュー
[strategy-reviewerの出力]

## 7. 最終投資判断・示唆

### 推奨アクション
[レビューを踏まえた具体的アクション]

### リスク要因
[主要リスクの列挙]

### モニタリングポイント
[フォローすべき指標・イベント]

---
**生成**: scenario-analyzer skill
**エージェント**: scenario-analyst, strategy-reviewer
```

#### Step 3.3: レポート保存

1. `reports/` ディレクトリが存在しない場合は作成
2. `scenario_analysis_<topic>_YYYYMMDD.md` として保存（例: `scenario_analysis_venezuela_20260104.md`）
3. 保存完了をユーザーに通知
4. **プロジェクトルートに直接保存しないこと**

---

## Output

このスキルは以下のファイルを生成します：

| ファイル | 形式 | 説明 |
|---------|------|------|
| `reports/scenario_analysis_<topic>_YYYYMMDD.md` | Markdown | 包括的なシナリオ分析レポート |

**出力内容:**
- 関連ニュース記事リスト
- Base/Bull/Bear 3シナリオ（確率配分付き）
- セクター影響分析（1次/2次/3次）
- ポジティブ/ネガティブ銘柄推奨
- セカンドオピニオン・レビュー
- 最終投資判断・示唆

## Output Artifact

All output from this skill must be structured as one of the following canonical artifact types.
Each artifact carries `manual_review_required: true`, a `disclaimer`, and a `data_gaps[]` array.

| artifact_type | Pydantic model | Description |
|---------------|---------------|-------------|
| `scenario_analysis` | `ScenarioAnalysis` | Probability-weighted scenario set with trigger levels |

Schema: `schemas/json/scenario_analysis.json`

## Resources

### References
- `references/headline_event_patterns.md` - イベントパターンと市場反応
- `references/sector_sensitivity_matrix.md` - セクター感応度マトリクス
- `references/scenario_playbooks.md` - シナリオ構築テンプレート

### Agents
- `scenario-analyst` - メインシナリオ分析
- `strategy-reviewer` - セカンドオピニオン・レビュー

---

## Important Notes

### 言語
- 全ての分析・出力は**日本語**で行う
- 銘柄ティッカーは英語表記を維持

### 対象市場
- 銘柄選定は**米国市場上場銘柄のみ**
- ADR含む

### 時間軸
- シナリオは**18ヶ月**を対象
- 0-6ヶ月/6-12ヶ月/12-18ヶ月の3フェーズで記述

### 確率配分
- Base + Bull + Bear = **100%**
- 各シナリオの確率は根拠とともに記述

### セカンドオピニオン
- **必須**で実行（strategy-reviewerを常に呼び出す）
- レビュー結果は最終判断に反映

### 出力先（重要）
- **必ず** `reports/` ディレクトリ配下に保存すること
- パス: `reports/scenario_analysis_<topic>_YYYYMMDD.md`
- 例: `reports/scenario_analysis_fed_rate_hike_20260104.md`
- `reports/` ディレクトリが存在しない場合は作成すること
- **プロジェクトルートに直接保存してはならない**

---

## Quality Checklist

レポート完成前に以下を確認：

- [ ] ヘッドラインが正しく解析されているか
- [ ] イベントタイプの分類が適切か
- [ ] 3シナリオの確率合計が100%か
- [ ] 1次/2次/3次影響の論理的繋がりがあるか
- [ ] 銘柄選定に具体的な根拠があるか
- [ ] strategy-reviewerのレビューが含まれているか
- [ ] レビューを踏まえた最終判断が記載されているか
- [ ] レポートが正しいパスに保存されたか

## Data Gaps

Explicit behavior when web data is unavailable — do not fabricate events or market context.

| Scenario | Severity | Behavior |
|----------|----------|----------|
| Web search returns no results | HIGH | Halt step; note data gap in output; do not invent events |
| Fewer than 3 credible sources found | MEDIUM | Flag low-source confidence in output; mark analysis PRELIMINARY |
| Source credibility unverifiable | MEDIUM | Label source UNVERIFIED in output; apply minimum weight |
| Event data older than 10 days | MEDIUM | Warn; note staleness; mark time-sensitivity LOW |

Do not assume neutral market impact when source data is absent.
