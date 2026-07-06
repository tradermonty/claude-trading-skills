---
layout: default
title: "Economic Calendar Fetcher"
grand_parent: 日本語
parent: スキルガイド
nav_order: 17
lang_peer: /en/skills/economic-calendar-fetcher/
permalink: /ja/skills/economic-calendar-fetcher/
---

# Economic Calendar Fetcher
{: .no_toc }

FMP APIを使用して、今後の経済イベントやデータ発表を取得します。スクリプトは生のJSON/textを出力し、アシスタントがフィルタリング・影響度評価・時系列マークダウンレポートの生成を担います。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/economic-calendar-fetcher.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/economic-calendar-fetcher){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Financial Modeling Prep (FMP) Economic Calendar APIから、今後の経済イベントやデータ発表を取得するスキルです。中央銀行の金融政策決定、雇用統計、インフレデータ（CPI/PPI）、GDP発表、小売売上高、製造業データなど、金融市場に影響を与える予定された経済指標を取得します。

Pythonスクリプトを使用してFMP APIにクエリを実行し、生のJSON/textを返します。アシスタントがそのデータを受け取り、フィルタリング・影響度評価・時系列マークダウンレポートの生成を行います。ファイルの自動保存はありません。

**主な機能:**
- 指定した日付範囲の経済イベントを取得（最大90日間）
- 柔軟なAPIキー提供をサポート（環境変数またはCLI引数）
- 影響度レベル、国、イベントタイプでフィルタリング（フィルタリングはアシスタントが実施）
- フィルタリング結果を影響分析付きの構造化マークダウンレポートで提示（スクリプトではなくアシスタントが生成）
- デフォルトで次の7日間のクイック市場見通し

**データソース:**
- FMP Economic Calendar API: `https://financialmodelingprep.com/stable/economic-calendar`（singular "economic"）
- 主要経済圏をカバー: 米国、EU、英国、日本、中国、カナダ、オーストラリア
- イベントタイプ: 中央銀行決定、雇用、インフレ、GDP、貿易、住宅、サーベイ
- レガシー注意: `https://financialmodelingprep.com/api/v3/economic_calendar` はFMP側で廃止済みのため、フォールバックとして使用しないでください。

---

## 2. 使用タイミング

以下の場合に使用します：

1. **経済カレンダーの照会:**
   - 「今週の経済イベントは？」
   - 「今後2週間の経済カレンダーを見せて」
   - 「次のFOMC会合はいつ？」
   - 「来月発表される主要な経済データは？」

2. **市場イベントの計画:**
   - 「今週の市場で注目すべきことは？」
   - 「高インパクトの経済指標発表はある？」
   - 「次の雇用統計/CPI発表/GDP発表はいつ？」

3. **特定の日付範囲のリクエスト:**
   - 「1月1日から1月31日までの経済イベントを取得」
   - 「2025年第1四半期の経済カレンダーは？」

4. **国別クエリ:**
   - 「来週の米国経済データ発表を見せて」
   - 「ECBの予定イベントは？」
   - 「日本のインフレデータ発表はいつ？」

**以下の場合には使用しないでください:**
- 過去の経済イベント（過去の分析には market-news-analyst を使用）
- 企業の決算カレンダー（このスキルは決算を除外）
- リアルタイムの市場データやライブクオート
- テクニカル分析やチャート解釈

---

## 3. 前提条件

- **FMP APIキー**（必須）: https://financialmodelingprep.com で無料キーに登録（250リクエスト/日）。`FMP_API_KEY` 環境変数で設定するか、スクリプトに `--api-key` を渡す。
- **Python 3.10+**: `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py` の実行に必要。
- **サードパーティパッケージ不要**: スクリプトはPython標準ライブラリのみ使用。

---

## 4. クイックスタート

```bash
# デフォルト: 次の7日間
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# 特定の日付範囲（最大90日間）
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-11-01 --to 2025-11-30 \
  --api-key YOUR_KEY \
  --format json
```

---

## 5. ワークフロー

経済カレンダーの取得と分析には以下のステップに従います：

### ステップ1: FMP APIキーの取得

**APIキーの利用可能性を確認:**

1. まず FMP_API_KEY 環境変数が設定されているか確認
2. 利用不可の場合、チャットでAPIキーの提供をユーザーに依頼
3. ユーザーがAPIキーを持っていない場合、手順を案内：
   - https://financialmodelingprep.com にアクセス
   - 無料アカウントに登録（250リクエスト/日のリミット）
   - APIダッシュボードでキーを取得

### ステップ2: 日付範囲の決定

**ユーザーリクエストに基づいて適切な日付範囲を設定:**

**デフォルト（特定の日付指定なし）:** 本日 + 7日間
**ユーザーが期間を指定:** 正確な日付を使用（形式を検証: YYYY-MM-DD）
**最大範囲:** 90日間（FMP APIの制限）

### ステップ3: APIフェッチスクリプトの実行

**適切なパラメータで get_economic_calendar.py スクリプトを実行:**

```bash
# 基本的な使用法（デフォルト7日間）
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# 特定の日付範囲
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-31 \
  --api-key YOUR_KEY \
  --format json

# 環境変数使用（--api-key 不要）
export FMP_API_KEY=your_key_here
python3 skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-01-01 \
  --to 2025-01-07
```

**スクリプトパラメータ:**
- `--from`: 開始日（YYYY-MM-DD） - デフォルト: 今日
- `--to`: 終了日（YYYY-MM-DD） - デフォルト: 今日 + 7日間
- `--api-key`: FMP APIキー（FMP_API_KEY環境変数設定時は任意）
- `--format`: 出力形式（json または text） - デフォルト: json
- `--output`: 出力ファイルパス（任意、デフォルト: stdout）

### ステップ4: イベントのパースとフィルタリング

スクリプトからのJSONレスポンスを処理します：

1. **イベントデータのパース:** APIレスポンスからすべてのイベントを抽出
2. **ユーザー指定のフィルターを適用:**
   - 影響度レベル: 「High」「Medium」「Low」
   - 国: 「US」「EU」「JP」「CN」など
   - イベントタイプ: FOMC、CPI、雇用、GDPなど

### ステップ5: 市場影響度の評価

各イベントの市場への重要性を評価します：

**影響度レベルの分類（FMPより）:**
- **High Impact:** 主要な市場変動イベント（FOMC金利決定、NFP、CPI、GDP）
- **Medium Impact:** 重要だがボラティリティは低い（小売売上、PMI、消費者信頼感）
- **Low Impact:** マイナー指標（週次失業保険申請件数、地域製造業サーベイ）

### ステップ6: 出力レポートの生成

> **責務分担:** スクリプトはJSON/textの生データを出力します。このステップはアシスタントがスクリプトの出力を使って実施します。マークダウンファイルは自動生成されません。結果はチャットで表示され、必要に応じて `reports/` に保存できます。

以下のセクションを含む構造化マークダウンレポートを作成します：

**レポートヘッダー:**

```markdown
# Economic Calendar
**Period:** [開始日] to [終了日]
**Report Generated:** [タイムスタンプ]
**Total Events:** [件数]
**High Impact Events:** [件数]
```

**イベント一覧（時系列順）:**

各イベントについて提供する内容：

```markdown
## [日付] - [曜日]

### [イベント名] ([影響度レベル])
- **Country:** [国コード] ([通貨])
- **Time:** [HH:MM UTC]
- **Previous:** [値]
- **Estimate:** [コンセンサス予測]
- **Impact Assessment:** [分析]

**Market Implications:**
[このイベントが重要な理由、市場が注目するポイント、典型的な反応パターンを2〜3文で]

---
```

**イベント記載例:**

```markdown
## 2025-01-15 - Wednesday

### Consumer Price Index (CPI) YoY (High Impact)
- **Country:** US (USD)
- **Time:** 14:30 UTC（8:30 AM ET — 米国夏時間カレンダーに基づきアシスタントが変換）
- **Previous:** 2.6%
- **Estimate:** 2.7%
- **Impact Assessment:** 非常に高 - Fed金融政策のコアインフレ指標

**Market Implications:**
予測超過（>2.7%）はタカ派的なFed期待を強め、株式への圧力とUSD支持につながる可能性があります。2.7%以下ならディスインフレの継続を示唆し、リスク資産を支持します。オプション市場は発表日の S&P 500 の 1.2% 変動を織り込んでいます。

---
```

**サマリーセクション:**

```markdown
## Key Takeaways

**最も影響度の高い日:**
- [日付]: [イベント] - [複合影響度の根拠]

**中央銀行の動向:**
- [Fed/ECB/BOJの予定会合やスピーチの要約]

**主要データ発表:**
- 雇用: [NFP、失業率の日付]
- インフレ: [CPI、PPIの日付]
- 成長: [GDP、小売売上高の日付]

**市場ポジショニングの考慮点:**
[トレーダーがこれらのイベントに向けてどのようにポジショニングするかの2〜3の箇条書き]

**リスクイベント:**
[不確実性や予測との乖離可能性が特に高いイベントを強調]
```

**フィルター適用時の注記:**

ユーザーがフィルターを指定した場合、先頭に明記：

```markdown
**Filters Applied:**
- Impact Level: High only
- Country: US
- Events shown: [X] of [Y] total events in date range
```

**出力:**
- 結果はチャットで表示されます。ファイルは自動生成されません。
- **生のJSON/textデータ**をディスクに保存する場合: スクリプト実行時に `--output reports/economic_calendar_[START]_to_[END].json` を指定してください。
- **マークダウンレポート**を保存する場合: チャット上でアシスタントが生成した後、`reports/` への書き出しを依頼してください。

---

## 6. リソース

**リファレンス:**

- `skills/economic-calendar-fetcher/references/fmp_api_documentation.md`

**スクリプト:**

- `skills/economic-calendar-fetcher/scripts/get_economic_calendar.py`
