---
name: vendor-rfq-creator
description: This skill should be used when creating RFQ (Request for Quotation) documents for software development projects to send to vendors. Use this skill when you have received vague requirements from clients and need to structure them into clear, comprehensive RFQs that enable vendors to provide accurate estimates. Supports Japanese (default) and English, with systematic requirements elicitation, clarification, and markdown-formatted output.
---

# Vendor RFQ Creator（ベンダー見積依頼書作成）

## Overview

This skill transforms vague client requirements into comprehensive RFQ (Request for Quotation) documents for software development projects. It guides you through requirements elicitation, clarification, structuring, and professional RFQ creation in Markdown format.

**Primary language**: Japanese (default)
**Output format**: Markdown

Use this skill when:
- Clients provide vague or incomplete project requirements  
- You need to create formal RFQs to send to development vendors
- You want to ensure all necessary information is included for accurate estimates
- You need to standardize RFQ creation across your organization

## Core Workflows

1. **Requirements Elicitation**: Extract and understand client needs through structured questioning
2. **Requirements Structuring**: Transform vague requirements into clear specifications  
3. **RFQ Document Creation**: Generate professional, comprehensive RFQ documents
4. **Quality Review**: Verify completeness before sending to vendors

---

## Workflow 1: Requirements Elicitation

### Step 1: Initial Information Gathering

Collect whatever information the client has provided:
- プロジェクト概要 (project overview)
- 背景・課題 (background/problems)
- 期待される成果 (expected outcomes)
- 予算感・スケジュール希望 (budget/timeline preferences)

### Step 2: Identify Information Gaps

Compare received information against `references/rfq_checklist_ja.md`:

**Critical gaps** (must clarify):
- プロジェクトの目的が不明確
- 主要機能が特定されていない
- 対象ユーザーが不明
- スケジュール・予算が全く不明

**Important gaps** (should clarify):
- 非機能要件（性能、セキュリティ等）が不足
- 既存システムとの関係が不明
- データ移行の有無が不明

### Step 3: Prepare Clarification Questions

Generate structured questions using **5W1H framework**:

**Who**: 誰がこのシステムを使用しますか？ユーザー数は？  
**What**: どのような機能が必要ですか？優先順位は？  
**Where**: どこで使用されますか？  
**When**: いつまでに必要ですか？  
**Why**: なぜこのシステムが必要ですか？  
**How**: どのように実現しますか？

### Step 4: Conduct Client Interview

Present questions systematically:
1. 全体像・背景から始める
2. 具体的な機能要件へ
3. 非機能要件・制約条件
4. プロジェクト管理事項

### Step 5: Document Requirements

Create structured requirements document:

```markdown
# 顧客要望整理シート

## 1. プロジェクト概要
[背景・目的、解決したい課題、期待される効果]

## 2. 機能要件
| No. | 機能名 | 優先度 | 概要 |
|-----|--------|--------|------|
| 1 | [機能] | 必須 | [説明] |

## 3. 非機能要件
[パフォーマンス、セキュリティ、可用性等]

## 4. 制約・前提
[スケジュール、予算、技術制約]

## 5. 不明点
- [ ] [確認が必要な項目]
```

---

## Workflow 2: Requirements Structuring

### Step 1: Categorize Requirements

Organize information using RFQ structure:

1. **プロジェクト概要**: 名称、背景、目的、スコープ、成果物
2. **機能要件**: 主要機能、ユースケース、データ要件、外部連携
3. **非機能要件**: 性能、可用性、セキュリティ、拡張性、運用、UX
4. **技術要件**: 技術スタック、開発環境、標準、ライセンス
5. **PM要件**: スケジュール、予算、体制、品質管理、リスク、変更管理
6. **契約要件**: 契約形態、IP、守秘義務、保証

### Step 2: Fill Gaps with Assumptions

For unclear items, make reasonable assumptions based on:
- 業界標準 (industry standards)
- プロジェクトタイプ別の典型要件 (typical requirements by project type)

Document assumptions clearly:

```markdown
## 前提条件

以下は合理的な前提として設定しています。相違がある場合はご指摘ください。

1. **[項目名]**: [前提内容]
   - 根拠: [なぜこの前提を置いたか]
```

### Step 3: Define Scope Boundaries

Clearly define IN SCOPE and OUT OF SCOPE:

**スコープ内**: 明確に要求された機能、実現に必須の機能
**スコープ外**: 除外事項、将来フェーズ検討、クライアント側実施事項

### Step 4: Define Acceptance Criteria

For each major requirement:

```markdown
### 受入基準

**機能名**: [機能]

**受入基準**:
1. [動作確認項目1]
2. [性能基準]
3. [品質基準]
```

### Step 5: Validate Quality

Check requirements against:
- **明確性**: 曖昧な表現を避ける、数値化
- **完全性**: 必須項目が含まれている
- **実現可能性**: 技術的に実現可能、予算・スケジュールが現実的
- **検証可能性**: 受入基準が定義されている

---

## Workflow 3: RFQ Document Creation

### Step 1: Select Template

Use `assets/rfq_template_ja.md` as base template.

### Step 2: Populate Template

Fill in template with structured requirements:

#### プロジェクト概要
- プロジェクト名、背景・目的、スコープ、成果物

#### 機能要件
Create prioritized feature list:

| 優先度 | 機能名 | 概要 | 詳細 |
|--------|--------|------|------|
| 必須 | [Feature 1] | [Summary] | [Detail] |
| 推奨 | [Feature 2] | [Summary] | [Detail] |

#### 非機能要件
Be specific with numbers:
- ❌ 「高速に動作」 → ✅ 「平均応答時間3秒以内」
- ❌ 「セキュア」 → ✅ 「TLS 1.2以上、AES-256暗号化、多要素認証」

#### スケジュール・予算
- Provide target dates AND flexibility
- Disclose budget range (or not - choose strategically)

#### 見積書フォーマット
Provide standardized format including:
- WBS structure
- Required columns: タスク名、詳細、役割、工数、単価、小計
- Required phases: 要件定義、設計、実装、テスト、PM等
- Contingency (10-20%)

### Step 3: Add Vendor Instructions

Include:

**質問受付**:
- 質問受付期間、方法、フォーマット
- 回答方法（全社一斉回答）、回答予定日

**提案要件**:
- 技術提案、PM提案、チーム体制、代替案

**評価基準**:

| 評価項目 | 配点 | 評価ポイント |
|----------|------|--------------|
| 価格 | 30点 | 見積金額の妥当性 |
| 技術力 | 25点 | 技術提案の優位性 |
| 実績 | 20点 | 類似案件の実績 |
| PM | 15点 | PM手法、品質管理 |
| スケジュール | 10点 | 納期遵守の実現性 |

### Step 4: Include Supporting Materials

Attach:
- 既存システム構成図
- 画面イメージ・ワイヤーフレーム
- 業務フロー図
- データモデル

### Step 5: Generate Final Document

Create complete RFQ in Markdown format using template.

---

## Workflow 4: Quality Review

### Step 1: Completeness Check

Verify using `references/rfq_checklist_ja.md`:

**必須項目**:
- [ ] プロジェクト概要が明確
- [ ] 主要機能がリストアップ
- [ ] スケジュール・納期記載
- [ ] 見積フォーマット提供
- [ ] 提出期限・方法明記

### Step 2: Clarity Check

Avoid ambiguous language:
- ❌ 「適切に処理」 → ✅ 「エラー発生時はログ記録しエラーメッセージ表示」
- ❌ 「高速」 → ✅ 「平均応答時間3秒以内」
- ❌ 「使いやすい」 → ✅ 「3クリック以内で主要機能にアクセス可能」

### Step 3: Consistency Check

Verify:
- 数値の整合性
- 用語の統一
- 参照の正確性

### Step 4: Stakeholder Review

Get feedback from:
- プロジェクトオーナー: 要件が正しく反映されているか
- 技術リード: 技術要件が実現可能で適切か
- PM: スケジュール・体制要件が現実的か
- 調達・法務: 契約条件が適切か

### Step 5: Final Approval

- 改訂履歴を記録
- 承認者サイン取得
- 配布前最終チェック

---

## Resources

### references/

**`rfq_checklist_ja.md`**: Comprehensive checklist (150+ items)

**Structure**: 9 main sections
1. プロジェクト概要
2. 機能要件
3. 非機能要件  
4. 技術要件
5. プロジェクト管理要件
6. 契約・法務要件
7. 見積依頼特有の要件
8. 付加的な情報
9. 品質チェック

**Use during**: Workflow 2 (Structuring) and Workflow 4 (Quality Review)

### assets/

**`rfq_template_ja.md`**: Japanese RFQ template (9 sections, 400+ lines)

**Structure**:
- プロジェクト概要
- 要件詳細（機能・非機能・技術）
- プロジェクト管理要件
- 契約・法務要件
- 見積依頼内容（フォーマット付き）
- 評価・選定基準
- 提出要項
- 注意事項
- 問い合わせ先

**Use during**: Workflow 3 (RFQ Creation)

---

## Best Practices

### 1. Start with Business Value
Always begin with WHY: なぜ必要か、どんな価値を生むか、成功の定義

### 2. Be Specific with Numbers
- ❌ 「多くのユーザー」 → ✅ 「初期1,000名、3年後10,000名」

### 3. Prioritize with MoSCoW
- **Must have (必須)**: 絶対必要
- **Should have (推奨)**: 重要だが、なくてもOK
- **Could have (可能なら)**: あると良い
- **Won't have (今回は対象外)**: 将来検討

### 4. Provide Context
Include: 現状、課題、目指す姿、業務プロセス、ユーザーワークフロー

### 5. Standardize Estimate Format
Always provide WBS template with required details

### 6. Allow for Vendor Input
「提案された技術があれば記載してください」「より効率的な方式があれば提案してください」

### 7. Set Realistic Expectations
Be honest about: 予算制約、スケジュール制約、技術制約、組織制約

### 8. Plan Q&A Process
Always include Q&A period (1-2 weeks), format, fair disclosure

---

## Common Pitfalls

1. ❌ Copying from old RFQ without customization
2. ❌ Too much technical prescription
3. ❌ Ambiguous scope boundaries
4. ❌ Missing non-functional requirements
5. ❌ Unrealistic budget/timeline
6. ❌ No evaluation criteria
7. ❌ One-size-fits-all template

---

## Examples

### Example 1: E-Commerce Website

**Initial request**: 「ウェブサイトを作りたい。商品を買えるようにしたい。予算500万円、早く作ってほしい。」

**After elicitation**: ECサイト、商品約100、会員機能、クレカ決済、同時100ユーザー、99%稼働率、PCI-DSS対応

**RFQ output**: 9-section comprehensive document with clear requirements, evaluation criteria, standardized estimate format

### Example 2: Mobile SFA App

**Initial request**: 「営業マン用アプリ。顧客情報見たり商談記録入力。iPhone/Android」

**After clarification**: SFAモバイルアプリ、Salesforce連携、50名、オフライン動作、GPS記録

**RFQ specifies**: 詳細機能、オフライン同期、既存システム連携仕様、モバイル特有要件

### Example 3: Data Migration

**Initial request**: 「古いシステムから新しいシステムにデータ移行したい。データ量は多い。」

**After clarification**: Access→PostgreSQL、10年分、顧客10万件・取引200万件、一括移行、整合性100%、24時間以内

**RFQ includes**: データマッピング表、クレンジング要件、リハーサル、ロールバック計画

---

## Quick Reference

### 15-Minute Checklist
1. [ ] プロジェクト名・目的
2. [ ] 主要機能リスト（優先度）
3. [ ] スケジュール・納期
4. [ ] 予算レンジ
5. [ ] 見積フォーマット
6. [ ] 提出期限・方法

### Common Requirements by Type

**Webアプリ**: レスポンシブ、SSL/TLS、ログイン、3秒応答、100同時接続
**モバイル**: iOS15+/Android11+、オフライン、プッシュ通知、2秒応答
**基幹システム**: 99.9%可用性、バックアップ、監査ログ、権限管理、帳票
**データ基盤**: ETL、TB級処理、BI連携、バッチ・リアルタイム処理

---

## Version History

- **v1.0** (2025-01-07): Initial release
  - 4 core workflows
  - Japanese RFQ template (400+ lines)
  - Comprehensive checklist (150+ items)
  - Requirements elicitation guidance
  - Quality review framework

---

このスキルの目的は、ベンダーが正確な見積もりを出せるようにすることです。不明確な点を残さず、しかし過度に制約しすぎないバランスが重要です。
