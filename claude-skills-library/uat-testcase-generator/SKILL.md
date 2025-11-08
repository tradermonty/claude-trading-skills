---
name: uat-testcase-generator
description: This skill should be used when creating UAT (User Acceptance Testing) test cases in Excel format for Salesforce CRM projects. It generates standardized test case documents with summary sheets and detailed test case lists, following a specific format structure with test case ID, priority, category, scenario, preconditions, test steps, expected results, and acceptance criteria.
---

# UAT Test Case Generator

## Overview

This skill generates UAT (User Acceptance Testing) test case documents in Excel format for Salesforce CRM projects. The generated documents include a summary sheet with category breakdowns and a detailed test case list with all required fields for UAT execution.

## When to Use This Skill

Use this skill when:
- Creating UAT test case documents for Salesforce implementations
- Generating test cases based on system requirements or user stories
- Converting system flow diagrams or requirement documents into test cases
- Needing a standardized Excel format for UAT documentation with Japanese field names

## Workflow

### Step 1: Gather Information

Collect the following from the user:

1. **Project Name**: The name of the project (e.g., "Redac Salesforce CRM")
2. **Requirements Source**: User stories, system flow diagrams, or requirement documents
3. **Test Categories**: Main categories (e.g., "Data Migration", "Business Scenarios", "Security")
4. **Priority Criteria**: Guidelines for assigning High/Medium/Low priorities (if not provided, use business criticality)

### Step 2: Analyze Requirements

Review the source material and:
- Identify main test categories and sub-categories
- Determine test scenarios for each category
- Group related test cases together
- Assign priorities based on business impact

### Step 3: Generate Test Cases

Create test cases with the following structure:

| Field | Description | Example |
|-------|-------------|---------|
| **テストケースID** | Unique ID (CATEGORY-###) | `DATA-001` |
| **優先度** | High/Medium/Low | `High` |
| **カテゴリ** | Main category | `データ移行検証` |
| **サブカテゴリ** | Sub-category | `移行データ件数照合` |
| **テストシナリオ** | Brief scenario | `Account件数照合` |
| **事前条件** | Preconditions | `既存CRMからデータ移行済み` |
| **テスト手順** | Step-by-step procedure | `1. 既存CRMのAccount総件数を確認\n2. Salesforce UAT環境のAccount総件数を確認\n3. 件数を比較` |
| **期待結果** | Expected outcome | `移行元と移行先のAccount件数が一致すること` |
| **実際の結果** | Actual result (empty) | _(empty)_ |
| **合格基準** | Pass criteria | `件数差異0件` |
| **合否判定** | Pass/Fail (empty) | _(empty)_ |
| **実施日** | Test date (empty) | _(empty)_ |
| **実施者** | Tester (empty) | _(empty)_ |
| **備考** | Notes (empty) | _(empty)_ |
| **不具合ID** | Bug ID (empty) | _(empty)_ |

**Test Case ID Format**: `CATEGORY_CODE-###`
- DATA: データ移行検証
- BIZ: 業務シナリオテスト
- SEC: 認証・セキュリティテスト
- EXT: 外部連携テスト
- RPT: レポート・ダッシュボードテスト
- PERF: 性能テスト
- MOB: モバイルテスト

### Step 4: Create Excel File

Use the Python script to generate the Excel file:

```python
python scripts/generate_uat_testcases.py \
  --project "Redac Salesforce CRM" \
  --output "UAT受入試験テストケース一覧.xlsx" \
  --testcases testcases.json
```

The script will:
1. Create a "サマリー" (Summary) sheet with category counts and progress tracking
2. Create a "全テストケース" (All Test Cases) sheet with detailed test cases
3. Apply conditional formatting for visual clarity

### Step 5: Review and Deliver

- Verify all test cases are complete and actionable
- Check that priorities are correctly assigned
- Ensure test steps are clear and numbered
- Deliver the Excel file to the user

## Common Test Categories

Use these standard categories for Salesforce CRM projects:

### 1. データ移行検証 (Data Migration Verification)
**Sub-categories**:
- 移行データ件数照合 (Record count validation)
- データ品質検証 (Data quality validation)
- 関連データ整合性 (Relational integrity)
- 特殊文字・日本語テスト (Special characters and Japanese text)

### 2. 業務シナリオテスト (Business Scenario Testing)
**Sub-categories**:
- リード管理 (Lead management)
- 商談管理 (Opportunity management)
- 取引先/取引先責任者管理 (Account/Contact management)
- タスク/活動管理 (Task/Activity management)
- 契約管理 (Contract management)
- 承認プロセス (Approval processes)

### 3. 認証・セキュリティテスト (Authentication & Security)
**Sub-categories**:
- ユーザー認証 (User authentication)
- 権限管理 (Permission management)
- データ可視性 (Data visibility/sharing rules)
- プロファイル設定 (Profile settings)

### 4. 外部連携テスト (External Integration)
**Sub-categories**:
- API連携 (API integration)
- バッチ処理 (Batch processing)
- ファイル入出力 (File I/O)
- 外部システム連携 (External system integration)

### 5. レポート・ダッシュボードテスト (Reports & Dashboards)
**Sub-categories**:
- レポート表示 (Report display)
- ダッシュボード表示 (Dashboard display)
- データフィルタ (Data filtering)
- エクスポート機能 (Export functionality)

## Example Usage

**User Request**:
> "Create UAT test cases for our Salesforce data migration. We need to verify Account, Contact, and Opportunity record counts, and also test data quality like required fields and special characters."

**Claude's Response Process**:

1. **Identify Categories**:
   - Category: データ移行検証
   - Sub-categories: 移行データ件数照合, データ品質検証

2. **Generate Test Cases**:
   ```json
   [
     {
       "id": "DATA-001",
       "priority": "High",
       "category": "データ移行検証",
       "sub_category": "移行データ件数照合",
       "scenario": "Account件数照合",
       "precondition": "既存CRMからデータ移行済み",
       "steps": "1. 既存CRMのAccount総件数を確認\n2. Salesforce UAT環境のAccount総件数を確認\n3. 件数を比較",
       "expected": "移行元と移行先のAccount件数が一致すること",
       "criteria": "件数差異0件"
     },
     {
       "id": "DATA-002",
       "priority": "High",
       "category": "データ移行検証",
       "sub_category": "移行データ件数照合",
       "scenario": "Contact件数照合",
       "precondition": "既存CRMからデータ移行済み",
       "steps": "1. 既存CRMのContact総件数を確認\n2. Salesforce UAT環境のContact総件数を確認\n3. 件数を比較",
       "expected": "移行元と移行先のContact件数が一致すること",
       "criteria": "件数差異0件"
     },
     ...
   ]
   ```

3. **Execute Script**: Run `scripts/generate_uat_testcases.py`

4. **Deliver File**: Provide the generated Excel file to the user

## Scripts

### `scripts/generate_uat_testcases.py`

Python script to generate UAT test case Excel files with proper formatting.

**Usage**: See script header for detailed usage instructions and examples.

## References

### `references/uat_best_practices.md`

UAT testing best practices and guidelines for writing effective test cases.

## Tips

- Use clear, action-oriented language in test steps
- Number test steps for clarity (1. 2. 3...)
- Make expected results specific and measurable
- Define objective pass/fail criteria
- Group related test cases under the same sub-category
- Assign priorities based on business impact, not technical complexity
- Keep test scenarios focused on one specific aspect
