# Weekly Trade Strategy Blog - プロジェクトガイド

このプロジェクトは、米国株の週間トレード戦略ブログを自動生成するためのシステムです。

## プロジェクト構造

```
weekly-trade-strategy/
├── charts/              # チャート画像格納フォルダ
│   └── YYYY-MM-DD/     # 日付ごとのフォルダ
│       ├── chart1.jpeg
│       └── chart2.jpeg
│
├── reports/            # 分析レポート格納フォルダ
│   └── YYYY-MM-DD/    # 日付ごとのフォルダ
│       ├── technical-market-analysis.md
│       ├── us-market-analysis.md
│       └── market-news-analysis.md
│
├── blogs/              # 最終ブログ記事格納フォルダ
│   └── YYYY-MM-DD-weekly-strategy.md
│
└── .claude/
    ├── agents/         # エージェント定義
    └── skills/         # スキル定義
```

## 週間ブログ作成の標準手順

### ステップ0: 準備

1. **チャート画像の配置**
   ```bash
   # 今週の日付でフォルダ作成
   mkdir -p charts/2025-11-03

   # チャート画像を配置（18枚推奨）
   # - VIX (週足)
   # - 米10年債利回り (週足)
   # - S&P 500 Breadth Index (200日MA + 8日MA)
   # - Nasdaq 100 (週足)
   # - S&P 500 (週足)
   # - Russell 2000 (週足)
   # - Dow Jones (週足)
   # - 金先物 (週足)
   # - 銅先物 (週足)
   # - 原油 (週足)
   # - 天然ガス (週足)
   # - ウランETF (URA, 週足)
   # - Uptrend Stock Ratio (全市場)
   # - セクターパフォーマンス (1週間)
   # - セクターパフォーマンス (1ヶ月)
   # - インダストリーパフォーマンス (上位/下位)
   # - 決算カレンダー
   # - 主要銘柄ヒートマップ
   ```

2. **レポート出力フォルダ作成**
   ```bash
   mkdir -p reports/2025-11-03
   ```

### ステップ1: Technical Market Analysis

**目的**: チャート画像を分析し、テクニカル指標から市場環境を評価

**エージェント**: `technical-market-analyst`

**入力**:
- `charts/YYYY-MM-DD/*.jpeg` (全チャート画像)

**出力**:
- `reports/YYYY-MM-DD/technical-market-analysis.md`

**実行コマンド例**:
```
今週（2025-11-03）のチャート分析をtechnical-market-analystエージェントで実行してください。
charts/2025-11-03/にある全てのチャートを分析し、レポートをreports/2025-11-03/technical-market-analysis.mdに保存してください。
```

**分析内容**:
- VIX、10年債利回り、Breadth指標の現在値と評価
- 主要指数（Nasdaq, S&P500, Russell2000, Dow）のテクニカル分析
- コモディティ（金、銅、原油、ウラン）のトレンド分析
- セクターローテーション分析
- シナリオ別の確率評価

---

### ステップ2: US Market Analysis

**目的**: 市場環境の総合評価とバブルリスク検出

**エージェント**: `us-market-analyst`

**入力**:
- `reports/YYYY-MM-DD/technical-market-analysis.md` (ステップ1の結果)
- 市場データ（VIX, Breadth, 金利等）

**出力**:
- `reports/YYYY-MM-DD/us-market-analysis.md`

**実行コマンド例**:
```
us-market-analystエージェントで米国市場の総合分析を実行してください。
reports/2025-11-03/technical-market-analysis.mdを参照し、
市場環境とバブルリスクを評価してreports/2025-11-03/us-market-analysis.mdに保存してください。
```

**分析内容**:
- 現在の市場フェーズ（Risk-On / Base / Caution / Stress）
- バブル検出スコア（0-16スケール）
- セクターローテーションパターン
- ボラティリティレジーム
- リスク要因とカタリスト

---

### ステップ3: Market News Analysis

**目的**: 過去10日間のニュース影響分析と今後7日間のイベント予測

**エージェント**: `market-news-analyzer`

**入力**:
- `reports/YYYY-MM-DD/technical-market-analysis.md` (ステップ1の結果)
- `reports/YYYY-MM-DD/us-market-analysis.md` (ステップ2の結果)
- 経済カレンダー、決算カレンダー

**出力**:
- `reports/YYYY-MM-DD/market-news-analysis.md`

**実行コマンド例**:
```
market-news-analyzerエージェントでニュースとイベント分析を実行してください。
過去10日間のニュース影響と今後7日間の重要イベントを分析し、
reports/2025-11-03/market-news-analysis.mdに保存してください。
```

**分析内容**:
- 過去10日間の主要ニュースと市場への影響
- 今後7日間の経済指標スケジュール
- 主要決算発表（時価総額$2B以上）
- イベント別のシナリオ分析（確率付き）
- リスクイベントの優先順位付け

---

### ステップ4: Weekly Blog Generation

**目的**: 3つのレポートを統合し、兼業トレーダー向けの週間戦略ブログを生成

**エージェント**: `weekly-trade-blog-writer`

**入力**:
- `reports/YYYY-MM-DD/technical-market-analysis.md`
- `reports/YYYY-MM-DD/us-market-analysis.md`
- `reports/YYYY-MM-DD/market-news-analysis.md`
- `blogs/` (前週のブログ記事、連続性チェック用)

**出力**:
- `blogs/YYYY-MM-DD-weekly-strategy.md`

**実行コマンド例**:
```
weekly-trade-blog-writerエージェントで2025年11月3日週のブログ記事を作成してください。
reports/2025-11-03/配下の3つのレポートを統合し、
前週のセクター配分との連続性を保ちながら、
blogs/2025-11-03-weekly-strategy.mdに保存してください。
```

**記事構成** (200-300行):
1. **3行まとめ** - 市場環境・焦点・戦略
2. **今週のアクション** - ロット管理、売買レベル、セクター配分、重要イベント
3. **シナリオ別プラン** - Base/Risk-On/Cautionの3シナリオ
4. **マーケット状況** - 統一トリガー（10Y/VIX/Breadth）
5. **コモディティ・セクター戦術** - 金/銅/ウラン/原油
6. **兼業運用ガイド** - 朝/夜チェックリスト
7. **リスク管理** - 今週特有のリスク
8. **まとめ** - 3-5文

**重要な制約**:
- 前週からのセクター配分変更は**±10-15%以内**（段階的調整）
- 史上最高値更新中+Baseトリガーの場合、急激なポジション削減は避ける
- 現金配分は段階的に増加（例: 10% → 20-25% → 30-35%）

---

### ステップ5（オプション）: Druckenmiller Strategy Planning

**目的**: 3つの分析レポートを統合し、18ヶ月の中長期投資戦略を策定

**エージェント**: `druckenmiller-strategy-planner`

**入力**:
- `reports/YYYY-MM-DD/technical-market-analysis.md` (ステップ1の結果)
- `reports/YYYY-MM-DD/us-market-analysis.md` (ステップ2の結果)
- `reports/YYYY-MM-DD/market-news-analysis.md` (ステップ3の結果)
- 前回のDruckenmiller戦略レポート（存在する場合）

**出力**:
- `reports/YYYY-MM-DD/druckenmiller-strategy.md`

**実行コマンド例**:
```
druckenmiller-strategy-plannerエージェントで2025年11月3日時点の18ヶ月戦略を策定してください。
reports/2025-11-03/配下の3つのレポートを総合的に分析し、
Druckenmiller流の戦略フレームワークを適用して、
reports/2025-11-03/druckenmiller-strategy.mdに保存してください。
```

**分析フレームワーク**:

1. **Druckenmillerの投資哲学**
   - マクロ重視の18ヶ月先行分析
   - 確信度に基づくポジションサイジング
   - 複数要因が揃った時の集中投資
   - 素早い損切りと柔軟性

2. **4つのシナリオ分析**（確率付き）
   - **Base Case** (最高確率シナリオ)
   - **Bull Case** (楽観シナリオ)
   - **Bear Case** (リスクシナリオ)
   - **Tail Risk** (低確率の極端シナリオ)

3. **各シナリオの構成要素**
   - 主要カタリスト（政策、景気、地政学）
   - タイムライン（Q1-Q2、Q3-Q4の展開）
   - 資産クラス別の影響
   - 最適ポジショニング戦略
   - 無効化シグナル（戦略転換のトリガー）

**レポート構成** (約150-200行):
```markdown
# Strategic Investment Outlook - [Date]

## Executive Summary
[2-3段落：支配的テーマと戦略的ポジショニングの要約]

## Market Context & Current Environment
### Macroeconomic Backdrop
[金融政策、景気サイクル、マクロ指標の現状]

### Technical Market Structure
[主要テクニカルレベル、トレンド、パターン]

### Sentiment & Positioning
[市場センチメント、機関投資家ポジション、逆張り機会]

## 18-Month Scenario Analysis

### Base Case Scenario (XX% probability)
**Narrative:** [最も可能性の高い市場の道筋]
**Key Catalysts:**
- [カタリスト1]
- [カタリスト2]
**Timeline Markers:**
- [Q1-Q2の予想展開]
- [Q3-Q4の予想展開]
**Strategic Positioning:**
- [資産配分推奨]
- [具体的なトレードアイデアと確信度]
**Risk Management:**
- [無効化シグナル]
- [ストップロス/撤退基準]

### Bull Case Scenario (XX% probability)
[Base Caseと同様の構成]

### Bear Case Scenario (XX% probability)
[Base Caseと同様の構成]

### Tail Risk Scenario (XX% probability)
[Base Caseと同様の構成]

## Recommended Strategic Actions

### High Conviction Trades
[テクニカル、ファンダメンタル、センチメントが揃ったトレード]

### Medium Conviction Positions
[良好なリスク/リワードだが要因の整合性が低いポジション]

### Hedges & Protective Strategies
[リスク管理ポジションとポートフォリオ保険]

### Watchlist & Contingent Trades
[確認待ちまたは特定トリガー待ちのセットアップ]

## Key Monitoring Indicators
[シナリオ検証/無効化のための追跡指標]

## Conclusion & Next Review Date
[最終的な戦略推奨と次回見直し時期]
```

**重要な特徴**:
- 週間ブログ（短期戦術）とは異なり、**18ヶ月の中長期戦略**
- マクロ経済の構造変化や政策転換点を重視
- 確信度に応じたポジションサイジング（High/Medium/Low）
- 各シナリオに明確な無効化条件を設定
- stanley-druckenmiller-investmentスキルを活用

**実行タイミング**:
- 週間ブログと同時（四半期ごと推奨）
- FOMCなど重大イベント後
- 市場構造の大きな転換点

**不足レポートの自動生成**:
上流レポート（ステップ1-3）が存在しない場合、druckenmiller-strategy-plannerは自動的に不足エージェントを呼び出します。

---

## 一括実行スクリプト（推奨）

```bash
# 日付設定
DATE="2025-11-03"

# ステップ0: フォルダ準備
mkdir -p charts/$DATE reports/$DATE

# ステップ1-4を一括実行するプロンプト例：
「$DATE週のトレード戦略ブログを作成してください。

1. technical-market-analystでcharts/$DATE/の全チャートを分析
   → reports/$DATE/technical-market-analysis.md

2. us-market-analystで市場環境を総合評価
   → reports/$DATE/us-market-analysis.md

3. market-news-analyzerでニュース/イベント分析
   → reports/$DATE/market-news-analysis.md

4. weekly-trade-blog-writerで最終ブログ記事を生成
   → blogs/$DATE-weekly-strategy.md

各ステップを順次実行し、レポートを確認してから次に進んでください。」
```

---

## エージェント間のデータフロー

### 週間ブログ生成フロー

```
charts/YYYY-MM-DD/
  ├─> [technical-market-analyst]
  │      └─> reports/YYYY-MM-DD/technical-market-analysis.md
  │            │
  │            ├─> [us-market-analyst]
  │            │      └─> reports/YYYY-MM-DD/us-market-analysis.md
  │            │            │
  │            │            ├─> [market-news-analyzer]
  │            │            │      └─> reports/YYYY-MM-DD/market-news-analysis.md
  │            │            │            │
  │            └────────────┴────────────┴─> [weekly-trade-blog-writer]
  │                                                └─> blogs/YYYY-MM-DD-weekly-strategy.md
  │
  └─> (前週のブログ記事も参照)
       blogs/YYYY-MM-DD-weekly-strategy.md (先週)
```

### 中長期戦略レポート生成フロー（オプション）

```
reports/YYYY-MM-DD/
  ├─> technical-market-analysis.md ────┐
  ├─> us-market-analysis.md ───────────┼─> [druckenmiller-strategy-planner]
  └─> market-news-analysis.md ─────────┘      └─> reports/YYYY-MM-DD/druckenmiller-strategy.md
                                                       (18ヶ月投資戦略)
```

---

## トラブルシューティング

### エージェントがチャートを見つけられない
- `charts/YYYY-MM-DD/` フォルダが存在するか確認
- チャート画像のファイル形式が`.jpeg`または`.png`か確認

### レポートが生成されない
- `reports/YYYY-MM-DD/` フォルダが存在するか確認
- 前のステップのレポートが正常に生成されているか確認

### ブログ記事のセクター配分が急変している
- 前週のブログ記事が`blogs/`に存在するか確認
- weekly-trade-blog-writerエージェントの連続性チェック機能が有効か確認

### ブログ記事が長すぎる（300行超過）
- weekly-trade-blog-writerエージェント定義の長さ制限を確認
- 記事生成後、行数を確認: `wc -l blogs/YYYY-MM-DD-weekly-strategy.md`

---

## 推奨ワークフロー

### 日曜夜（日本時間）または金曜夜（米国時間）
1. 週末にチャートを準備
2. technical-market-analystを実行
3. 結果を確認してから次のステップへ

### 月曜朝
4. us-market-analyst、market-news-analyzerを実行
5. 3つのレポートをレビュー
6. weekly-trade-blog-writerでブログ生成
7. 最終レビューと公開

---

## 各エージェントの詳細仕様

### technical-market-analyst
- **スキル**: technical-analyst, breadth-chart-analyst, sector-analyst
- **分析対象**: 週足チャート、Breadth指標、セクターパフォーマンス
- **出力形式**: Markdown、シナリオ別確率付き

### us-market-analyst
- **スキル**: market-environment-analysis, us-market-bubble-detector
- **分析対象**: 市場フェーズ、バブルスコア、センチメント
- **出力形式**: Markdown、リスク評価

### market-news-analyzer
- **スキル**: market-news-analyst, economic-calendar-fetcher, earnings-calendar
- **分析対象**: 過去10日ニュース、今後7日イベント
- **出力形式**: Markdown、イベント別シナリオ

### weekly-trade-blog-writer
- **入力**: 上記3レポート + 前週ブログ
- **制約**: 200-300行、段階的調整（±10-15%）
- **出力形式**: 兼業トレーダー向けMarkdown（5-10分読了）

### druckenmiller-strategy-planner（オプション）
- **スキル**: stanley-druckenmiller-investment
- **分析対象**: 18ヶ月中長期マクロ戦略、シナリオ分析
- **入力**: 上記3レポート（technical, us-market, market-news）
- **出力形式**: Markdown、4シナリオ（Base/Bull/Bear/Tail Risk）、確率・確信度付き
- **特徴**: Druckenmiller流の集中投資と素早い損切り、マクロ転換点の識別
- **実行頻度**: 四半期ごと、またはFOMC等の重大イベント後

---

## バージョン管理

- **プロジェクトバージョン**: 1.0
- **最終更新日**: 2025-11-02
- **メンテナンス**: このドキュメントは定期的に更新してください

---

## 連絡先・フィードバック

このワークフローに関する改善提案や問題報告は、プロジェクトのIssueトラッカーに報告してください。
