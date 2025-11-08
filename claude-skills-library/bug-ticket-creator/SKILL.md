---
name: bug-ticket-creator
description: This skill should be used when creating bug/defect reports during system testing. Use this skill when you discover a bug, need to document test failures, or want to create comprehensive bug tickets with proper reproduction steps, severity assessment, and environment details. Guides users through interactive questioning to gather all necessary information and generates professional bug ticket documents in Markdown format. Supports Japanese (default) and English.
---

# Bug Ticket Creator（不具合チケット作成）

## Overview

This skill transforms bug discoveries into comprehensive, professional bug tickets through interactive dialogue. It guides testers through systematic questioning to gather reproduction steps, environment details, severity assessment, and all necessary information, then generates a complete bug report in Markdown format.

**Primary language**: Japanese (default) with English support
**Output format**: Markdown (.md file)
**Use case**: Software testing, QA, bug reporting

Use this skill when:
- You discovered a bug during testing and need to create a bug ticket
- You want to ensure all necessary information is captured in the bug report
- You need help organizing reproduction steps systematically
- You want to determine appropriate severity and priority
- You need a professional, standardized bug report format

## Core Workflows

1. **Initial Bug Discovery**: Capture what happened and where
2. **Reproduction Steps Collection**: Systematically gather step-by-step reproduction procedure
3. **Expected vs Actual Behavior**: Clarify the gap between specification and reality
4. **Environment Information Collection**: Gather OS, browser, device, and configuration details
5. **Severity and Priority Assessment**: Determine bug classification and urgency
6. **Bug Ticket Generation**: Create complete Markdown bug report document

---

## Workflow 1: Initial Bug Discovery

### Purpose
Capture the initial discovery of the bug and gather high-level context through interactive questioning.

### Step 1: Greet and Understand Context

Start with a friendly greeting and ask about the bug discovery:

```
こんにちは！不具合チケット作成をお手伝いします。

まず、発見された不具合について教えてください：
1. 何が起きましたか？（簡単に教えてください）
2. どこで起きましたか？（どの画面・機能ですか？）
3. いつ起きましたか？（テスト中、実際の使用中など）
```

**Key questions to ask**:
- 何が問題か？（What is the problem?）
- どこで発生したか？（Where did it occur?）
- どのような状況で発生したか？（Under what circumstances?）

### Step 2: Categorize the Bug Type

Based on the user's description, identify the bug type using `references/defect_classification_guide.md`:

Ask clarifying questions to determine:
- **機能不具合（Functional Defect）**: 機能が動作しない、誤動作する
- **UI/UX不具合（UI/UX Defect）**: 表示崩れ、デザイン不一致、操作性問題
- **パフォーマンス不具合（Performance Defect）**: 遅い、タイムアウト、リソース消費
- **データ不具合（Data Defect）**: データ損失、不整合、破損
- **セキュリティ不具合（Security Defect）**: 認証問題、情報漏洩、脆弱性
- **統合・連携不具合（Integration Defect）**: 外部APIエラー、データ連携失敗
- **環境依存不具合（Environment-Specific Defect）**: 特定ブラウザ、OS、デバイスでのみ発生

**Example dialogue**:
```
この問題は以下のどれに近いですか？
1. 機能が全く動かない、または誤動作する
2. 見た目がおかしい、レイアウトが崩れる
3. 動作が遅い、タイムアウトする
4. データが保存されない、壊れる
5. セキュリティ上の懸念がある
6. 外部システムとの連携で問題がある
7. 特定の環境でのみ発生する

番号で教えてください。
```

### Step 3: Assess Initial Severity

Get a rough idea of severity by asking:

```
この不具合の影響について教えてください：
- システム全体が使えなくなっていますか？
- 主要な機能が使えなくなっていますか？
- 一部の機能に問題がありますか？
- 見た目だけの問題ですか？
```

Make a preliminary severity assessment (to be refined later):
- Critical: システム全体が使用不可、データ損失、セキュリティリスク
- High: 主要機能が使用不可、回避策なし
- Medium: 機能に問題があるが回避策あり
- Low: 視覚的な問題のみ、影響軽微

---

## Workflow 2: Reproduction Steps Collection

### Purpose
Systematically gather detailed reproduction steps following the CLEAR principles from `references/reproduction_steps_guide.md`.

### Step 1: Establish Preconditions

Ask about the starting state:

```
再現手順を整理します。まず、事前条件を教えてください：

1. ログイン状態:
   - ログインしていますか？していませんか？
   - どのユーザー権限ですか？（管理者、一般ユーザー等）

2. データの準備:
   - 特定のテストデータが必要ですか？
   - どのような状態のデータですか？

3. 開始画面:
   - どの画面から始めますか？（URLを教えてください）
```

**Capture**:
- ログイン状態（Login status）
- ユーザー権限（User role/permissions）
- 必要なテストデータ（Required test data）
- 初期画面/URL（Starting page/URL）
- その他の準備（Other preparations）

### Step 2: Gather Step-by-Step Actions

Guide the user through detailed step collection:

```
では、不具合が発生するまでの操作を一つずつ教えてください。
最初の操作から順番に、できるだけ詳しく説明してください。

例:
- 「トップページの右上にあるログインボタンをクリック」
- 「メールアドレス欄に user@example.com を入力」

一つ操作を教えていただいたら、次の操作を聞きます。
```

**For each step, ask**:
- 「次は何をしましたか？」
- 「どのボタン/リンク/フィールドを操作しましたか？」
- 「何を入力しましたか？」（入力値を具体的に）
- 「どれを選択しましたか？」（選択肢の場合）

**Apply the principles**:
- **One action per step**: 一つの手順に一つの操作
- **Be specific**: 「ログインボタン」ではなく「画面右上の青い『ログイン』ボタン」
- **Include values**: 入力した値を具体的に記載
- **Use verbs**: クリック、入力、選択、チェックなど明確な動詞を使用

### Step 3: Identify the Failure Point

Ask when the problem occurs:

```
どの時点で問題が発生しましたか？
- 上記の手順のどこで不具合が起きましたか？
- その時、何が起きましたか？
```

### Step 4: Check Reproducibility

Confirm reproduction rate:

```
この問題は毎回発生しますか？
- 何回試しましたか？
- そのうち何回発生しましたか？
- 発生したりしなかったりする場合、何か傾向はありますか？
```

**Determine reproduction rate**:
- 100%（常に）: 毎回必ず再現
- 50-99%（頻繁）: 高頻度で再現
- 10-49%（時々）: たまに再現
- 1-9%（稀）: 稀にしか再現しない
- 1回のみ: 一度だけ発生、再現できない

---

## Workflow 3: Expected vs Actual Behavior Clarification

### Purpose
Clearly define the gap between expected behavior (specification) and actual behavior (bug).

### Step 1: Clarify Expected Behavior

Ask what should happen:

```
では、期待される動作について教えてください：
- 本来、何が起きるべきでしたか？
- 仕様書やデザインでは、どのように動作する予定でしたか？
- 成功した場合、どのような画面や結果が表示されるはずですか？
```

**Capture in specific terms**:
- 画面遷移（Expected page transitions）
- 表示されるメッセージ（Expected messages）
- データの状態（Expected data state）
- その他の観測可能な結果（Other observable outcomes）

**Example**:
```
期待される結果:
- 「保存が完了しました」という緑色の成功メッセージが表示される
- 商品一覧ページ（/products）にリダイレクトされる
- 商品一覧で在庫数が更新されている
```

### Step 2: Document Actual Behavior

Ask what actually happened:

```
では、実際に何が起きたか教えてください：
- どのような画面が表示されましたか？
- エラーメッセージは表示されましたか？（全文を教えてください）
- 画面はどのような状態ですか？
- データはどうなっていますか？
```

**Be thorough**:
- エラーメッセージ全文（Full error message text）
- 画面の状態（Screen state）
- ブラウザコンソールのエラー（Browser console errors）
- ネットワークエラー（Network errors if applicable）

**Prompt for screenshots/logs**:
```
もしスクリーンショットやエラーログがあれば、後で添付していただけますか？
- スクリーンショット: [ファイル名を記載予定]
- ブラウザコンソールログ: [ログをコピー予定]
- サーバーログ: [該当箇所を抜粋予定]
```

---

## Workflow 4: Environment Information Collection

### Purpose
Gather comprehensive environment details that may affect the bug.

### Step 1: Collect Basic Environment Info

Ask systematically:

```
環境情報を教えてください：

1. OS:
   - Windows, Mac, Linux, iOS, Androidのどれですか？
   - バージョンは？（例: Windows 11, macOS Sonoma 14.1, iOS 17.2）

2. ブラウザまたはアプリ:
   - 何を使っていますか？（Chrome, Safari, Firefox等）
   - バージョンは？（ブラウザのメニューの「バージョン情報」で確認できます）

3. デバイス:
   - PC、スマートフォン、タブレットのどれですか？
   - 機種名は？（例: iPhone 15 Pro, Dell XPS 13）
```

### Step 2: Collect Additional Environment Details

For more complex bugs, ask:

```
追加の環境情報:
1. 画面解像度: [わかれば教えてください]
2. ネットワーク環境: Wi-Fi? 有線LAN? モバイル回線?
3. ブラウザ拡張機能: 何か入れていますか？（広告ブロッカー等）
4. 言語設定: 日本語? 英語?
5. タイムゾーン: 日本（JST）? その他?
```

### Step 3: Check Environment Dependency

Verify if the bug is environment-specific:

```
この問題は他の環境でも発生しますか？
- 別のブラウザで試しましたか？
- 別のデバイスで試しましたか？
- 別のユーザーでも再現しますか？
```

---

## Workflow 5: Severity and Priority Assessment

### Purpose
Determine appropriate severity and priority using `references/severity_priority_guide.md`.

### Step 1: Assess Severity (Technical Impact)

Ask guiding questions based on severity criteria:

```
重要度（Severity）を判定します。以下の質問に答えてください：

1. システム全体が使用できなくなっていますか？
   → Yes: Critical候補

2. データが失われたり、壊れたりしますか？
   → Yes: Critical候補

3. セキュリティ上の問題（情報漏洩、不正アクセス可能）がありますか？
   → Yes: Critical候補

4. 主要な機能が全く使えませんか？回避策はありませんか？
   → Yes: High候補

5. 機能に問題がありますが、回避策がありますか？
   → Yes: Medium候補

6. 見た目だけの問題で、機能には影響ありませんか？
   → Yes: Low候補
```

**Determine Severity**:
- **Critical**: システム使用不可、データ損失、セキュリティリスク
- **High**: 主要機能使用不可、回避策なし
- **Medium**: 機能に問題あるが回避策あり
- **Low**: 視覚的問題のみ、影響軽微

### Step 2: Assess Priority (Business Urgency)

Ask business impact questions:

```
優先度（Priority）を判定します：

1. この問題は本番環境で発生していますか？
   → Yes: P0またはP1候補

2. これは主要な機能ですか？多くのユーザーが使いますか？
   → Yes: P1候補

3. リリース予定日が近いですか？
   → Yes: 優先度を1段階上げる

4. VIP顧客や重要な顧客に影響がありますか？
   → Yes: 優先度を1段階上げる

5. 影響は限定的で、時間がある時に対応で問題ありませんか？
   → Yes: P2またはP3候補
```

**Determine Priority**:
- **P0（最優先）**: 本番環境で発生中、サービス停止、即座対応が必要
- **P1（高優先）**: 1-3営業日以内の対応が必要
- **P2（中優先）**: 次回リリースで対応
- **P3（低優先）**: バックログに追加、時間がある時に対応

### Step 3: Explain Severity/Priority Combination

Explain the determined severity and priority:

```
判定結果:
- 重要度（Severity）: [Critical/High/Medium/Low]
- 優先度（Priority）: [P0/P1/P2/P3]

[判定理由を説明]

この組み合わせの意味:
[対応目安を説明]
```

---

## Workflow 6: Bug Ticket Generation

### Purpose
Generate a complete, professional bug ticket in Markdown format.

### Step 1: Gather Remaining Information

Ask for any missing information:

```
チケット作成に必要な最後の情報を確認します：

1. チケットタイトル:
   - 不具合を端的に表すタイトルを考えてください
   - 例: 「ログイン時に特定のメールアドレスで500エラーが発生」

2. 回避策:
   - もし一時的な回避方法があれば教えてください
   - なければ「なし」で構いません

3. 添付ファイル:
   - スクリーンショット、動画、ログファイルなど、添付する予定のファイル名を教えてください

4. その他補足:
   - 開発チームに伝えたい追加情報はありますか？
```

### Step 2: Select Template

Determine language preference:

```
チケットは日本語と英語、どちらで作成しますか？
1. 日本語（Japanese）
2. 英語（English）
```

Based on selection:
- 日本語: Use `assets/bug_ticket_template_ja.md`
- English: Use `assets/bug_ticket_template_en.md`

### Step 3: Populate Template

Fill in all collected information into the template:

**Header Section**:
- チケットID（仮）: BUG-XXXX（チーム内で採番）
- タイトル: User-provided title
- 作成日: Current date
- 報告者: User's name
- ステータス: 新規
- Severity: Determined severity
- Priority: Determined priority

**Classification Section**:
- 不具合タイプ: From Workflow 1
- サブカテゴリ: Specific categorization
- 影響範囲: Assessed impact scope
- 発生フェーズ: Testing phase
- 影響ユーザー数: Estimated affected users

**Preconditions Section**:
- From Workflow 2, Step 1

**Reproduction Steps Section**:
- From Workflow 2, Step 2 and 3
- Numbered list with detailed actions

**Expected Result Section**:
- From Workflow 3, Step 1
- Specific, observable outcomes

**Actual Result Section**:
- From Workflow 3, Step 2
- Exact error messages, screen states

**Reproduction Rate Section**:
- From Workflow 2, Step 4
- Percentage and notes

**Environment Section**:
- From Workflow 4
- OS, browser, device, resolution, network, etc.

**Attachments Section**:
- List of files to be attached

**Additional Information Section**:
- Error messages (full text)
- Browser console logs
- Network logs
- Server logs

**Workaround Section**:
- From Workflow 6, Step 1

**Impact Analysis Section**:
- Business impact
- Security impact
- User impact

**Recommended Action Section**:
- Recommended priority (already determined)
- Recommended approach (if any)

### Step 4: Review and Refine

Present the draft to the user:

```
チケットの内容を確認してください。
修正や追加したい箇所はありますか？

[チケット内容を表示]

問題なければ、マークダウンファイルとして保存します。
ファイル名は何にしますか？
例: BUG-001_login_error.md
```

### Step 5: Generate Markdown File

Create the bug ticket as a Markdown file using the Write tool:

```markdown
File name format:
- BUG-[NUMBER]_[short-description]_[YYYY-MM-DD].md
- Example: BUG-001_login_500_error_2025-01-07.md

Use the Write tool to create the Markdown file with the populated template.
```

### Step 6: Provide Next Steps

Guide the user on next steps:

```
✅ 不具合チケットを作成しました！

ファイル: [ファイル名].md

次のステップ:
1. スクリーンショットやログファイルを準備
2. チケット管理システム（JIRA, Redmine, GitHub Issues等）に登録
3. 開発チームに通知
4. チケットIDを更新（システムで採番されたIDに置き換え）

何か他にお手伝いできることはありますか？
```

---

## Leveraging Reference Materials

This skill integrates comprehensive reference guides for accurate bug classification and reporting.

### When to Reference

**`defect_classification_guide.md`**:
- During bug type identification (Workflow 1)
- To understand sub-categories
- For examples of each defect type

**`severity_priority_guide.md`**:
- During severity assessment (Workflow 5, Step 1)
- During priority assessment (Workflow 5, Step 2)
- To explain severity/priority combinations
- For edge case decisions

**`reproduction_steps_guide.md`**:
- During reproduction steps collection (Workflow 2)
- To ensure CLEAR principles are followed
- For examples of good vs bad steps
- For guidance on preconditions and environment info

### Key Principles from References

**CLEAR Principles** (from reproduction_steps_guide.md):
- **C**omplete: すべての必要な情報が含まれている
- **L**ogical: 手順が論理的な順序
- **E**xplicit: 曖昧な表現がなく具体的
- **A**ctionable: 誰でも同じ手順を実行できる
- **R**eproducible: 何度でも同じ結果になる

**Severity vs Priority** (from severity_priority_guide.md):
- Severity = Technical impact (QA判定)
- Priority = Business urgency (PO/PM判定)
- High severity ≠ High priority (always)

**Defect Classification** (from defect_classification_guide.md):
- 7 major defect types with sub-categories
- Clear examples for each type
- Impact scope assessment

---

## Best Practices

### 1. Interactive and Patient
- Ask one question at a time
- Don't overwhelm the user with too many questions at once
- Be patient and allow time for detailed responses

### 2. Clarify and Confirm
- Paraphrase user responses to confirm understanding
- Ask follow-up questions for vague responses
- Example: 「エラーが出ました」→「どのようなエラーメッセージが表示されましたか？全文を教えてください」

### 3. Guide Without Assuming
- Don't assume technical knowledge
- Explain terms when necessary (e.g., "ブラウザのコンソールログは、F12キーを押して開発者ツールを開くと見られます")
- Provide examples to guide responses

### 4. Systematic Collection
- Follow the workflows in order
- Don't skip steps even if they seem obvious
- Missing information leads to back-and-forth later

### 5. Professional Output
- Generate clean, well-formatted Markdown
- Follow template structure strictly
- Include all sections even if some are "N/A" or "なし"

### 6. Encourage Evidence
- Always ask for screenshots, videos, and logs
- Evidence makes bugs easier to reproduce and fix
- Help users know where to find logs (browser console, server logs)

---

## Common Pitfalls to Avoid

### ❌ Don't Do This

1. **Accepting vague descriptions**
   - ❌ 「エラーが出る」で終わらせる
   - ✅ エラーメッセージの全文を聞く

2. **Skipping reproduction rate**
   - ❌ 再現頻度を聞かない
   - ✅ 「毎回発生しますか？何回中何回ですか？」と聞く

3. **Incomplete environment info**
   - ❌ 「Chrome」だけを記録
   - ✅ 「Chrome 120.0.6099.109 (64-bit)」まで記録

4. **Combining multiple actions**
   - ❌ 「ログインして商品を編集する」
   - ✅ 「1. ログインボタンをクリック」「2. メール入力」...と分解

5. **Not asking for evidence**
   - ❌ 口頭説明だけで終わる
   - ✅ スクリーンショットやログを依頼

---

## Resources

### references/

**`defect_classification_guide.md`**: 不具合分類ガイド
- 7つの不具合タイプ分類（機能、UI/UX、パフォーマンス、データ、セキュリティ、統合、環境依存）
- サブカテゴリと具体例
- 発生フェーズ分類、原因分類、影響範囲分類
- 分類選択ガイドとベストプラクティス

**`severity_priority_guide.md`**: 重要度・優先度判定ガイド
- 重要度（Severity）4段階: Critical, High, Medium, Low
- 優先度（Priority）4段階: P0, P1, P2, P3
- 判定基準、判定フローチャート、マトリックス
- 実際の判定例、特殊ケース、よくある判定ミス

**`reproduction_steps_guide.md`**: 再現手順の書き方ガイド
- CLEAR原則（Complete, Logical, Explicit, Actionable, Reproducible）
- 事前条件、再現手順、期待結果、実際結果、環境情報の書き方
- 良い例と悪い例の比較
- スクリーンショット・動画・ログの添付ガイド

### assets/

**`bug_ticket_template_ja.md`**: 日本語不具合チケットテンプレート
- 完全な12セクション構成
- ヘッダー、分類、再現手順、期待結果、実際結果、環境情報、添付ファイル、影響分析、推奨対応、更新履歴、チェックリスト
- プロフェッショナルなフォーマット

**`bug_ticket_template_en.md`**: English bug ticket template
- Complete 12-section structure
- Header, classification, reproduction steps, expected/actual results, environment, attachments, impact analysis, recommended action, update history, quality checklist
- Professional format

---

## Quick Reference

### 対話フロー概要（6 Workflows）

1. **初期発見** → 何が、どこで、いつ起きたか
2. **再現手順** → 事前条件、ステップバイステップ、再現率
3. **期待vs実際** → 本来の動作、実際の動作、ギャップ
4. **環境情報** → OS、ブラウザ、デバイス、解像度等
5. **重要度・優先度** → Severity（技術影響）、Priority（ビジネス緊急性）
6. **チケット生成** → テンプレート選択、情報記入、Markdown出力

### 必須質問リスト

- [ ] 何が起きましたか？
- [ ] どこで起きましたか？
- [ ] 再現手順は？（ステップバイステップ）
- [ ] 期待される結果は？
- [ ] 実際の結果は？
- [ ] 再現率は？（X回中Y回）
- [ ] OS、ブラウザ、デバイスは？
- [ ] スクリーンショットはありますか？
- [ ] エラーメッセージは？（全文）
- [ ] 重要度・優先度の判断材料は？

---

このスキルの目的は、テスターが不具合を発見した際に、開発チームが迅速に理解・修正できる高品質な不具合チケットを作成することです。
