---
name: vendor-estimate-creator
description: This skill should be used when creating cost estimates and quotations for software development projects. Use this skill when you have an RFQ (Request for Quotation), project requirements, or a project description and need to create a comprehensive estimate with WBS, effort calculations, cost breakdowns, and ROI analysis. Supports Japanese (default) and English, with systematic work breakdown, effort estimation, and markdown-formatted estimate documents.
---

# Vendor Estimate Creator（ベンダー見積書作成）

## Overview

This skill transforms RFQs or project requirements into comprehensive cost estimates and quotations for software development projects. It guides you through RFQ analysis, work breakdown, effort estimation, cost calculation, ROI analysis, and professional estimate document creation in Markdown format.

**Primary language**: Japanese (default)
**Output format**: Markdown

Use this skill when:
- You've received an RFQ or project requirements and need to create a cost estimate
- You need to calculate project effort and cost with high accuracy
- You want to provide ROI analysis to justify the investment
- You need to standardize estimate creation across your organization
- You're responding to client RFQs with professional quotations

## Core Workflows

1. **RFQ Analysis and Understanding**: Analyze RFQ documents and extract key requirements
2. **Work Breakdown and Task Identification**: Create WBS and identify all necessary tasks
3. **Effort Estimation**: Estimate effort for each task using industry standards
4. **Cost Calculation and Aggregation**: Calculate costs and aggregate to project total
5. **ROI Analysis and Business Case**: Analyze ROI and create business justification
6. **Estimate Document Generation**: Generate professional estimate documents

---

## Workflow 1: RFQ Analysis and Understanding

### Step 1: RFQ Document Review

Read and analyze the RFQ document:
- プロジェクト概要（背景、目的、期待される成果）
- 機能要件（主要機能、画面数、API数、データ要件）
- 非機能要件（性能、セキュリティ、可用性）
- 技術要件（技術スタック、開発環境、制約）
- スケジュール・予算（納期、予算制約）
- 評価基準（価格、技術力、実績等の配点）

### Step 2: Requirements Extraction

Extract key information:

#### プロジェクト規模指標
- 画面数: [XX]画面
- API数: [XX]本
- DBテーブル数: [XX]テーブル
- バッチ処理: [XX]本
- 外部連携: [XX]システム

#### プロジェクトタイプ
- Webアプリケーション
- モバイルアプリ（iOS/Android）
- 基幹システム（ERP、CRM）
- API/マイクロサービス
- データ基盤

#### 複雑度評価
- **低**: 単純なCRUD、既知技術
- **中**: 標準的なビジネスロジック
- **高**: 複雑なアルゴリズム、新技術
- **最高**: 高度な最適化、研究開発要素

### Step 3: Gap and Assumption Identification

Identify missing information and make assumptions:

**不明点リスト**:
- [ ] [不明点1]
- [ ] [不明点2]

**前提条件**:
1. **[項目]**: [前提内容]
   - 根拠: [なぜこの前提を置いたか]

### Step 4: Risk Assessment

Identify risks that affect estimation. Use `references/estimation_methodology.md` risk checklist:

#### 技術リスク
- [ ] 新しい技術スタック採用
- [ ] 厳しい性能要件
- [ ] 大量データ処理

#### 要件リスク
- [ ] 要件が曖昧
- [ ] ステークホルダー多数
- [ ] スコープ変更の可能性

**リスクレベル**:
- 低リスク: コンティンジェンシー 5-10%
- 中リスク: コンティンジェンシー 10-15%
- 高リスク: コンティンジェンシー 15-25%

---

## Workflow 2: Work Breakdown and Task Identification

### Step 1: Define Project Phases

Use `references/effort_estimation_standards.md` standard phases:

1. **要件定義（Requirements Definition）**
2. **設計（Design）**
3. **実装（Implementation）**
4. **テスト（Testing）**
5. **デプロイ・運用準備（Deployment & Operations）**
6. **プロジェクト管理（Project Management）** - 全体の10-15%
7. **品質保証（Quality Assurance）** - 全体の7-11%

### Step 2: Create WBS (Work Breakdown Structure)

For each phase, break down into tasks using `references/effort_estimation_standards.md`:

**WBS例**:
```
プロジェクト全体 (1,208人日)
├── 要件定義 (120人日)
│   ├── REQ-001: キックオフ・プロジェクト計画 (10人日)
│   ├── REQ-002: 現状業務分析 (15人日)
│   ├── REQ-003: 機能要件定義 (30人日)
│   ...
├── 設計 (200人日)
├── 実装 (450人日)
├── テスト (250人日)
├── デプロイ・運用準備 (80人日)
├── プロジェクト管理 (15% = 158人日)
├── 品質保証 (8% = 84人日)
└── コンティンジェンシー (15% = 158人日)
```

### Step 3: Validate Completeness

Check against `references/effort_estimation_standards.md`:
- [ ] すべての必須フェーズが含まれている
- [ ] プロジェクト管理工数（10-15%）が計上されている
- [ ] 品質保証工数（7-11%）が計上されている
- [ ] コンティンジェンシー（10-25%）が含まれている

---

## Workflow 3: Effort Estimation

### Step 1: Select Estimation Method

Use `references/estimation_methodology.md` to select appropriate method:

| フェーズ | 推奨手法 | 精度 |
|---------|---------|------|
| 構想段階 | 類推法 | ±50% |
| 企画段階 | パラメトリック法 | ±30% |
| 要件定義後 | ボトムアップ法 | ±10% |

### Step 2: Apply Standard Effort

Use `references/effort_estimation_standards.md` for each task.

**例: API実装の工数見積もり**

```
タスク: バックエンドAPI実装（50本）
複雑度: 中

標準工数（ミドルエンジニア）:
- 単純CRUD API: 1.5人日/API × 30本 = 45人日
- 複雑ロジックAPI: 5人日/API × 20本 = 100人日
合計: 145人日
```

### Step 3: Apply Adjustment Factors

Use adjustment factors from `references/estimation_methodology.md`:

```
ベース工数: 145人日
複雑度調整: 1.0（中）
習熟度調整: 1.0（熟練）
技術リスク調整: 1.2（中）

調整後工数 = 145人日 × 1.0 × 1.0 × 1.2 = 174人日
```

### Step 4: Validate Estimation

Cross-check using multiple methods:
- パラメトリック法で検証
- 類似プロジェクトとの比較
- フェーズ比率チェック

---

## Workflow 4: Cost Calculation and Aggregation

### Step 1: Define Labor Rates

Use `references/effort_estimation_standards.md` standard rates:

| 役割 | 単価（円/人日） |
|------|---------------|
| プロジェクトマネージャー | 100,000〜150,000 |
| アーキテクト | 90,000〜140,000 |
| シニアエンジニア | 80,000〜120,000 |
| ミドルエンジニア | 60,000〜90,000 |

### Step 2: Assign Roles and Calculate Cost

```
例:
REQ-001: 10人日 × 120,000円（PM） = 1,200,000円
IMP-004: 174人日 × 75,000円（ミドルSE） = 13,050,000円
```

### Step 3: Aggregate to Total

```
要件定義: 10,800,000円
設計: 19,000,000円
実装: 33,750,000円
テスト: 17,500,000円
デプロイ: 6,400,000円
PM・QA・予備: 40,865,000円

合計: 128,315,000円（税抜）
```

---

## Workflow 5: ROI Analysis and Business Case

### Step 1: Current State Analysis (As-Is)

Use `references/roi_analysis_guide.md` to analyze current state:

```
現在のコスト:
- 人件費: 18,000,000円/年
- システム運用コスト: 5,000,000円/年
- エラー対応コスト: 1,800,000円/年
合計: 24,800,000円/年

課題:
- 処理時間が長い（30分/件）
- エラー率が高い（5%）
```

### Step 2: Expected Benefits (To-Be)

```
新システムによる改善:
- 処理時間: 30分 → 5分（83%削減）
- エラー率: 5% → 0.5%（90%削減）

コスト削減: 18,620,000円/年
売上増加: 20,000,000円/年
年間総便益: 38,620,000円/年
```

### Step 3: Financial Metrics Calculation

Use `references/roi_analysis_guide.md` formulas:

```
ROI（5年間） = 305%
NPV（割引率10%） = 82,890,000円
投資回収期間 = 1.23年
```

### Step 4: Sensitivity Analysis

```
| シナリオ | NPV | ROI | 回収期間 |
|---------|-----|-----|---------|
| 最良ケース | 125,000,000円 | 420% | 0.9年 |
| 標準ケース | 82,890,000円 | 305% | 1.23年 |
| 悲観ケース | 38,000,000円 | 185% | 1.7年 |
```

---

## Workflow 6: Estimate Document Generation

### Step 1: Load Template

Use `assets/estimate_template_ja.md` as base template.

### Step 2: Populate Template

Fill in all 12 sections:
1. エグゼクティブサマリー
2. 前提条件
3. 見積詳細（WBS）
4. プロジェクトスケジュール
5. ROI分析
6. チーム体制
7. リスクと対策
8. 運用保守費用
9. 支払条件
10. 契約条件
11. その他
12. 承認

### Step 3: Quality Check

- [ ] すべての金額が正しく計算されている
- [ ] WBSが網羅的である
- [ ] ROI分析が説得力がある
- [ ] リスクが適切に識別されている

### Step 4: Generate Final Document

Output the complete estimate document in Markdown format.

---

## Resources

### references/

**`estimation_methodology.md`**: 見積手法ガイド
- 4つの見積手法（類推法、パラメトリック法、ボトムアップ法、三点見積もり）
- 調整係数（複雑度、習熟度、技術リスク）
- コンティンジェンシー設定
- ベストプラクティス

**`effort_estimation_standards.md`**: 工数見積基準ガイド
- 役割別生産性指標
- タスク別標準工数
- プロジェクトタイプ別標準工数

**`roi_analysis_guide.md`**: ROI分析ガイド
- 主要財務指標（ROI、NPV、IRR、回収期間）
- ベネフィット分類
- ビジネスケース作成手順

### assets/

**`estimate_template_ja.md`**: 日本語見積書テンプレート（12セクション、400+行）

---

## Best Practices

1. **Use Multiple Estimation Methods**: ボトムアップ、パラメトリック、類似PJ比較
2. **Be Conservative**: 便益は控えめ、コストは余裕を持って
3. **Document Assumptions**: 前提条件を明記
4. **Identify Risks Early**: 技術、要件、統合、チームリスク
5. **Provide ROI Justification**: ROI、NPV、IRR、回収期間、感度分析
6. **Include PM and QA Effort**: PM 10-15%、QA 7-11%

---

## Common Pitfalls

1. ❌ コンティンジェンシーを含めない
2. ❌ プロジェクト管理工数を忘れる
3. ❌ データ移行を見落とす
4. ❌ 非機能要件を軽視
5. ❌ 統合テスト工数を過小評価
6. ❌ リスクを識別しない

---

## Quick Reference

### 見積作成の10ステップ

1. [ ] RFQを読み込み、要件を抽出
2. [ ] プロジェクト規模を測定（画面数、API数等）
3. [ ] WBSを作成（フェーズ→タスク）
4. [ ] 各タスクの工数を見積もり
5. [ ] コンティンジェンシー（10-25%）を追加
6. [ ] 役割別に単価を適用してコスト計算
7. [ ] 運用保守費用を算出
8. [ ] ROI分析を実施
9. [ ] 見積書テンプレートを埋める
10. [ ] 品質チェック

---

このスキルの目的は、正確で説得力のある見積書を作成し、プロジェクトの投資価値を明確に示すことです。
