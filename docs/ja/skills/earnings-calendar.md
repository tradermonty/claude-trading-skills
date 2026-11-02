---
layout: default
title: "Earnings Calendar"
grand_parent: 日本語
parent: スキルガイド
nav_order: 15
lang_peer: /en/skills/earnings-calendar/
permalink: /ja/skills/earnings-calendar/
---

# Earnings Calendar
{: .no_toc }

Financial Modeling Prep (FMP) APIを使用して、米国株式の今後の決算発表を取得するスキルです。ユーザーが決算カレンダーデータを要求した場合、翌週にどの企業が決算を発表するか知りたい場合、または週次の決算レビューが必要な場合に使用します。市場への影響が大きい中型株以上（時価総額20億ドル超）に焦点を当て、日付とタイミング別にクリーンなマークダウンテーブル形式でデータを整理します。複数環境（CLI、Desktop、Web）に対応し、柔軟なAPIキー管理をサポートします。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/earnings-calendar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/earnings-calendar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Financial Modeling Prep (FMP) APIを使用して、米国株式の今後の決算発表を取得するスキルです。市場動向に影響を与える可能性のある、中型株以上の時価総額（20億ドル超）を持つ企業に焦点を当てます。翌週に決算を発表する企業を日付とタイミング（寄り前、引け後、未発表）別にグループ化したマークダウンレポートを生成します。

**主な機能:**
- 信頼性の高い構造化された決算データにFMP APIを使用
- 時価総額（20億ドル超）でフィルタリングし、市場に影響のある企業に集中
- EPSおよび売上予想を含む
- マルチ環境対応（CLI、Desktop、Web）
- 柔軟なAPIキー管理
- 日付、タイミング、時価総額で整理

---

## 2. 前提条件

### FMP APIキー

このスキルにはFinancial Modeling Prep APIキーが必要です。

**無料APIキーの取得方法:**
1. アクセス: https://site.financialmodelingprep.com/developer/docs
2. 無料アカウントに登録
3. APIキーを即座に受領
4. 無料枠: 250 APIコール/日（週次の決算カレンダーには十分）

**環境別APIキー設定:**

**Claude Code (CLI):**
```bash
export FMP_API_KEY="your-api-key-here"
```

**Claude Desktop:**
システムで環境変数を設定するか、MCPサーバーを設定します。

**Claude Web:**
スキル実行時にAPIキーが要求されます（現在のセッションのみ保存）。

---

## 3. クイックスタート

```bash
# 日付範囲を位置引数 START_DATE END_DATE で指定。APIキーは FMP_API_KEY から取得
python3 skills/earnings-calendar/scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09

# APIキーは任意の第3位置引数としても渡せる
python3 skills/earnings-calendar/scripts/fetch_earnings_fmp.py \
  2025-11-03 2025-11-09 YOUR_KEY
```

---

## 4. ワークフロー

### ステップ1: 現在日付の取得と対象週の計算

**重要**: 必ず正確な現在日付を取得することから始めます。

現在の日付と時刻を取得します：
- システムの日付/時刻で今日の日付を取得
- 注意: 「今日の日付」は環境（<env>タグ）で提供されます
- 対象週を計算: 現在日付から次の7日間

**日付範囲の計算:**
```
現在日付: [例: 2025年11月2日]
対象週の開始: [現在日付 + 1日、例: 2025年11月3日]
対象週の終了: [現在日付 + 7日、例: 2025年11月9日]
```

**日付は YYYY-MM-DD 形式** でAPI互換性を確保します。

### ステップ2: FMP APIガイドの読み込み

データ取得前に、包括的なFMP APIガイドを読み込みます：

```
Read: references/fmp_api_guide.md
```

このガイドには以下が含まれます：
- FMP APIエンドポイント構造とパラメータ
- 認証要件
- 時価総額フィルタリング戦略（Company Profile APIを使用）
- 決算タイミングの規約（BMO、AMC、TAS）
- レスポンス形式とフィールド説明
- エラーハンドリング戦略

### ステップ3: APIキーの検出と設定

環境に基づいてAPIキーの利用可能性を検出します。

#### 3.1 環境変数のチェック（CLI/Desktop）

```bash
if [ ! -z "$FMP_API_KEY" ]; then
  echo "API key found in environment"
  API_KEY=$FMP_API_KEY
fi
```

環境変数が設定されていればステップ4に進みます。

#### 3.2 ユーザーへのAPIキー入力要求（Desktop/Web）

環境変数が見つからない場合、AskUserQuestionツールを使用します。

### ステップ4: FMP APIによる決算データの取得

Pythonスクリプトを使用してFMP APIから決算データを取得します。

```bash
python skills/earnings-calendar/scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09
```

**スクリプトのワークフロー**（自動）：
1. APIキーと日付パラメータの検証
2. FMP Earnings Calendar APIを日付範囲で呼び出し
3. 企業プロファイル（時価総額、セクター、業種）の取得
4. 時価総額20億ドル超の企業でフィルタリング
5. タイミングの正規化（BMO/AMC/TAS）
6. 日付→タイミング→時価総額（降順）でソート
7. JSONをstdoutに出力

### ステップ5: データの処理と整理

決算データ（JSON形式）を取得後、処理・整理します：
- JSONデータのパース
- データ構造の検証
- 日付別グループ化
- タイミング別サブグループ化（BMO/AMC/TAS）
- 各タイミンググループ内で時価総額降順ソート
- サマリー統計の計算

### ステップ6: マークダウンレポートの生成

レポート生成スクリプトを使用して、JSONデータからフォーマット済みマークダウンレポートを作成します。

```bash
python skills/earnings-calendar/scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
```

---

## 5. リソース

**リファレンス:**

- `skills/earnings-calendar/references/fmp_api_guide.md`

**スクリプト:**

- `skills/earnings-calendar/scripts/fetch_earnings_fmp.py`

- `skills/earnings-calendar/scripts/fmp_client.py`
- `skills/earnings-calendar/scripts/_fmp_compat.py`
- `skills/earnings-calendar/scripts/generate_report.py`
